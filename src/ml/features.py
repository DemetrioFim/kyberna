from __future__ import annotations

from datetime import date, datetime
from typing import Final

import duckdb
import pandas as pd

from src.core.logging import get_logger
from src.core.paths import get_duckdb_path
from src.core.types import ScenarioId

logger = get_logger(__name__)

DEFAULT_SCENARIO: Final[ScenarioId] = "c1_toys"


def resolve_as_of_date(
    con: duckdb.DuckDBPyConnection,
    as_of_date: date | datetime | str | None = None,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
) -> date:
    """Resolve a data de corte (as_of_date) para cálculo das features temporais.

    Se as_of_date for None, consulta a data máxima faturada para o cenário.

    Args:
        con: Conexão ativa com o DuckDB.
        as_of_date: Data fornecida (ou None para usar a mais recente da base).
        scenario_id: Identificador do cenário (ex: 'c1_toys').

    Returns:
        datetime.date resolvida.
    """
    if as_of_date is not None:
        if isinstance(as_of_date, str):
            return datetime.strptime(as_of_date[:10], "%Y-%m-%d").date()
        if isinstance(as_of_date, datetime):
            return as_of_date.date()
        return as_of_date

    # Consulta data máxima da base Gold para o cenário
    max_date_row = con.execute(
        f"""
        SELECT MAX(d.full_date)
        FROM gold.fact_sales f
        JOIN gold.dim_date d ON f.date_key = d.date_key
        WHERE f.scenario_id = '{scenario_id}'
        """
    ).fetchone()

    if max_date_row and max_date_row[0] is not None:
        val = max_date_row[0]
        return val if isinstance(val, date) else val.date()

    return date(2024, 12, 31)


# ==============================================================================
# 1. Features por Cliente (Customer Feature Store)
# ==============================================================================


def compute_customer_features(
    con: duckdb.DuckDBPyConnection,
    as_of_date: date | datetime | str | None = None,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
) -> pd.DataFrame:
    """Gera o catálogo de features comportamentais e financeiras por cliente até a data de corte.

    Garante zero vazamento temporal (nenhuma transação posterior a `as_of_date` é lida).

    Features calculadas (grão: customer_id):
        - as_of_date: data de corte (ISO YYYY-MM-DD)
        - customer_id: identificador canônico do cliente
        - first_order_date: data do primeiro pedido registrado
        - last_order_date: data da compra mais recente
        - recency_days: dias sem comprar na data de corte (as_of_date - last_order_date)
        - tenure_days: dias de relacionamento (as_of_date - first_order_date)
        - frequency: contagem de pedidos distintos
        - gross_revenue: faturamento bruto acumulado (R$)
        - net_revenue: receita líquida acumulada (R$)
        - contribution_margin: margem de contribuição líquida acumulada (R$)
        - margin_pct: margem de contribuição relativa (%)
        - avg_ticket: ticket médio por pedido (R$)
        - n_families: número de famílias de brinquedos distintas compradas
        - n_skus: número de SKUs distintos comprados
        - revenue_3m: faturamento bruto nos últimos 90 dias
        - revenue_6m: faturamento bruto nos últimos 180 dias
        - trend_3m_vs_6m: índice de aceleração/desaceleração da receita (2 * 3m / 6m)
        - Estatísticas do ciclo de recompra:
            - n_intervals: número de intervalos entre compras distintas
            - avg_interval_days: média de dias entre recompras consecutivas (ciclo médio)
            - median_interval_days: mediana de dias entre recompras consecutivas
            - std_interval_days: desvio padrão do ciclo de recompra
            - min_interval_days, max_interval_days: extremos do intervalo
            - delay_ratio: razão de atraso (recency_days / avg_interval_days)

    Args:
        con: Conexão ativa com o DuckDB.
        as_of_date: Data de corte (None para usar a última disponível).
        scenario_id: Identificador do cenário (ex: 'c1_toys').

    Returns:
        pd.DataFrame com 1 linha por cliente com transações até `as_of_date`.
    """
    cutoff = resolve_as_of_date(con, as_of_date, scenario_id=scenario_id)
    cutoff_str = cutoff.isoformat()
    logger.info("Computando customer_features para '%s' com as_of_date=%s...", scenario_id, cutoff_str)

    query = f"""
    WITH filtered_sales AS (
        SELECT
            f.customer_id,
            f.order_id,
            f.product_id,
            p.family,
            d.full_date::DATE AS full_date,
            f.gross_revenue,
            f.net_revenue,
            f.contribution_margin
        FROM gold.fact_sales f
        JOIN gold.dim_date d ON f.date_key = d.date_key
        JOIN gold.dim_product p ON f.product_id = p.product_id
        WHERE f.scenario_id = '{scenario_id}'
          AND d.full_date <= DATE '{cutoff_str}'
    ),
    distinct_dates AS (
        SELECT DISTINCT
            customer_id,
            full_date
        FROM filtered_sales
    ),
    dates_with_lag AS (
        SELECT
            customer_id,
            full_date,
            LAG(full_date) OVER (PARTITION BY customer_id ORDER BY full_date) AS prev_date
        FROM distinct_dates
    ),
    intervals AS (
        SELECT
            customer_id,
            (full_date - prev_date)::INTEGER AS interval_days
        FROM dates_with_lag
        WHERE prev_date IS NOT NULL
    ),
    interval_stats AS (
        SELECT
            customer_id,
            COUNT(*)::INTEGER AS n_intervals,
            ROUND(AVG(interval_days), 2) AS avg_interval_days,
            ROUND(MEDIAN(interval_days), 2) AS median_interval_days,
            ROUND(COALESCE(STDDEV_SAMP(interval_days), 0.0), 2) AS std_interval_days,
            MIN(interval_days)::INTEGER AS min_interval_days,
            MAX(interval_days)::INTEGER AS max_interval_days
        FROM intervals
        GROUP BY customer_id
    ),
    agg_totals AS (
        SELECT
            customer_id,
            MIN(full_date)::DATE AS first_order_date,
            MAX(full_date)::DATE AS last_order_date,
            COUNT(DISTINCT order_id)::INTEGER AS frequency,
            COUNT(DISTINCT family)::INTEGER AS n_families,
            COUNT(DISTINCT product_id)::INTEGER AS n_skus,
            ROUND(SUM(gross_revenue), 2) AS gross_revenue,
            ROUND(SUM(net_revenue), 2) AS net_revenue,
            ROUND(SUM(contribution_margin), 2) AS contribution_margin,
            ROUND(
                SUM(contribution_margin) / NULLIF(SUM(gross_revenue), 0) * 100.0,
                2
            ) AS margin_pct,
            ROUND(
                SUM(gross_revenue) / NULLIF(COUNT(DISTINCT order_id), 0),
                2
            ) AS avg_ticket,
            ROUND(
                SUM(
                    CASE WHEN full_date > DATE '{cutoff_str}' - INTERVAL 90 DAY
                         THEN gross_revenue ELSE 0 END
                ),
                2
            ) AS revenue_3m,
            ROUND(
                SUM(
                    CASE WHEN full_date > DATE '{cutoff_str}' - INTERVAL 180 DAY
                         THEN gross_revenue ELSE 0 END
                ),
                2
            ) AS revenue_6m
        FROM filtered_sales
        GROUP BY customer_id
    )
    SELECT
        DATE '{cutoff_str}' AS as_of_date,
        t.customer_id,
        t.first_order_date,
        t.last_order_date,
        (DATE '{cutoff_str}' - t.last_order_date::DATE)::INTEGER AS recency_days,
        (DATE '{cutoff_str}' - t.first_order_date::DATE)::INTEGER AS tenure_days,
        t.frequency,
        t.n_families,
        t.n_skus,
        t.gross_revenue,
        t.net_revenue,
        t.contribution_margin,
        t.margin_pct,
        t.avg_ticket,
        t.revenue_3m,
        t.revenue_6m,
        ROUND(
            (t.revenue_3m * 2.0) / NULLIF(t.revenue_6m, 0),
            2
        ) AS trend_3m_vs_6m,
        COALESCE(i.n_intervals, 0) AS n_intervals,
        i.avg_interval_days,
        i.median_interval_days,
        COALESCE(i.std_interval_days, 0.0) AS std_interval_days,
        i.min_interval_days,
        i.max_interval_days,
        ROUND(
            (DATE '{cutoff_str}' - t.last_order_date::DATE) / NULLIF(i.avg_interval_days, 0),
            2
        ) AS delay_ratio
    FROM agg_totals t
    LEFT JOIN interval_stats i ON t.customer_id = i.customer_id
    ORDER BY t.gross_revenue DESC NULLS LAST, t.customer_id ASC
    """
    df = con.execute(query).df()
    logger.info("Customer features computadas com sucesso: %d clientes.", len(df))
    return df


# ==============================================================================
# 2. Features por SKU (Product Feature Store)
# ==============================================================================


def compute_sku_features(
    con: duckdb.DuckDBPyConnection,
    as_of_date: date | datetime | str | None = None,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
    lookback_weeks: int = 26,
) -> pd.DataFrame:
    """Gera o catálogo de features de demanda e variabilidade por SKU até a data de corte.

    Features calculadas (grão: product_id):
        - as_of_date: data de corte
        - product_id: código EAN-13
        - item_number: código natural
        - product_name, family: dados cadastrais
        - units_sold, boxes_sold: volume acumulado
        - gross_revenue, contribution_margin: valor acumulado
        - margin_pct: margem acumulada (%)
        - first_sale_date, last_sale_date: ciclo de vida de venda
        - recency_days: dias desde a última venda do produto
        - weekly_demand_mean: média semanal de unidades vendidas nas últimas N semanas
        - weekly_demand_std: desvio padrão semanal
        - weekly_cv: coeficiente de variação (std / mean) para classificação XYZ
        - daily_demand_mean: demanda diária estimada (weekly_demand_mean / 7.0)

    Args:
        con: Conexão ativa com o DuckDB.
        as_of_date: Data de corte.
        scenario_id: Identificador do cenário.
        lookback_weeks: Janela retrospectiva em semanas para volatilidade XYZ (padrão: 26).

    Returns:
        pd.DataFrame com 1 linha por produto ativo na dimensão Gold.
    """
    cutoff = resolve_as_of_date(con, as_of_date, scenario_id=scenario_id)
    cutoff_str = cutoff.isoformat()
    lookback_days = lookback_weeks * 7

    logger.info(
        "Computando sku_features para '%s' (as_of_date=%s, lookback=%d semanas)...",
        scenario_id,
        cutoff_str,
        lookback_weeks,
    )

    query = f"""
    WITH filtered_sales AS (
        SELECT
            f.product_id,
            d.full_date::DATE AS full_date,
            f.units,
            f.boxes,
            f.gross_revenue,
            f.contribution_margin
        FROM gold.fact_sales f
        JOIN gold.dim_date d ON f.date_key = d.date_key
        WHERE f.scenario_id = '{scenario_id}'
          AND d.full_date <= DATE '{cutoff_str}'
    ),
    cum_product AS (
        SELECT
            product_id,
            MIN(full_date)::DATE AS first_sale_date,
            MAX(full_date)::DATE AS last_sale_date,
            SUM(units)::BIGINT AS units_sold,
            ROUND(SUM(boxes), 2) AS boxes_sold,
            ROUND(SUM(gross_revenue), 2) AS gross_revenue,
            ROUND(SUM(contribution_margin), 2) AS contribution_margin,
            ROUND(
                SUM(contribution_margin) / NULLIF(SUM(gross_revenue), 0) * 100.0,
                2
            ) AS margin_pct
        FROM filtered_sales
        GROUP BY product_id
    ),
    weeks_series AS (
        SELECT generate_series::INTEGER AS week_idx
        FROM generate_series(0, {lookback_weeks - 1})
    ),
    dim_p AS (
        SELECT DISTINCT
            product_id,
            item_number,
            product_name,
            family,
            pack,
            base_unit_cost,
            base_unit_price
        FROM gold.dim_product
    ),
    product_weeks_grid AS (
        SELECT
            p.product_id,
            w.week_idx
        FROM dim_p p
        CROSS JOIN weeks_series w
    ),
    weekly_sales AS (
        SELECT
            product_id,
            CAST((DATE '{cutoff_str}' - full_date) / 7 AS INTEGER) AS week_idx,
            SUM(units) AS units
        FROM filtered_sales
        WHERE full_date > DATE '{cutoff_str}' - INTERVAL {lookback_days} DAY
        GROUP BY product_id, week_idx
    ),
    grid_units AS (
        SELECT
            pw.product_id,
            pw.week_idx,
            COALESCE(ws.units, 0)::BIGINT AS units
        FROM product_weeks_grid pw
        LEFT JOIN weekly_sales ws
          ON pw.product_id = ws.product_id AND pw.week_idx = ws.week_idx
    ),
    volatility_stats AS (
        SELECT
            product_id,
            ROUND(AVG(units), 2) AS weekly_demand_mean,
            ROUND(COALESCE(STDDEV_SAMP(units), 0.0), 2) AS weekly_demand_std,
            ROUND(
                COALESCE(STDDEV_SAMP(units), 0.0) / NULLIF(AVG(units), 0),
                4
            ) AS weekly_cv,
            ROUND(AVG(units) / 7.0, 2) AS daily_demand_mean
        FROM grid_units
        GROUP BY product_id
    )
    SELECT
        DATE '{cutoff_str}' AS as_of_date,
        p.product_id,
        p.item_number,
        p.product_name,
        p.family,
        p.pack,
        p.base_unit_cost,
        p.base_unit_price,
        COALESCE(c.units_sold, 0) AS units_sold,
        COALESCE(c.boxes_sold, 0.0) AS boxes_sold,
        COALESCE(c.gross_revenue, 0.0) AS gross_revenue,
        COALESCE(c.contribution_margin, 0.0) AS contribution_margin,
        COALESCE(c.margin_pct, 0.0) AS margin_pct,
        c.first_sale_date,
        c.last_sale_date,
        CASE
            WHEN c.last_sale_date IS NOT NULL
            THEN (DATE '{cutoff_str}' - c.last_sale_date)::INTEGER
            ELSE NULL
        END AS recency_days,
        COALESCE(v.weekly_demand_mean, 0.0) AS weekly_demand_mean,
        COALESCE(v.weekly_demand_std, 0.0) AS weekly_demand_std,
        COALESCE(v.weekly_cv, 0.0) AS weekly_cv,
        COALESCE(v.daily_demand_mean, 0.0) AS daily_demand_mean
    FROM dim_p p
    LEFT JOIN cum_product c ON p.product_id = c.product_id
    LEFT JOIN volatility_stats v ON p.product_id = v.product_id
    ORDER BY c.gross_revenue DESC NULLS LAST, p.product_id ASC
    """
    df = con.execute(query).df()
    logger.info("SKU features computadas com sucesso: %d produtos.", len(df))
    return df


# ==============================================================================
# 3. Features por Cliente x Família (Customer-Family Feature Store)
# ==============================================================================


def compute_customer_family_features(
    con: duckdb.DuckDBPyConnection,
    as_of_date: date | datetime | str | None = None,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
) -> pd.DataFrame:
    """Gera o catálogo de penetração de categorias e mix de compra cliente x família.

    Base fundamental para o algoritmo de White Space (cross-sell B2B no Marco M3).

    Features calculadas (grão: customer_id x family):
        - as_of_date: data de corte
        - customer_id: identificador do cliente
        - family: família de produtos
        - first_purchase_date: primeira compra da família
        - last_purchase_date: compra mais recente da família
        - family_recency_days: dias sem comprar essa família específica
        - family_orders_count: número de pedidos distintos contendo essa família
        - family_units: unidades compradas da família
        - family_boxes: caixas master compradas
        - family_gross_revenue: faturamento bruto da família para o cliente
        - family_contribution_margin: margem de contribuição da família
        - family_margin_pct: margem percentual (%) da família para o cliente
        - family_revenue_share: participação relativa da família no faturamento total do cliente

    Args:
        con: Conexão ativa com o DuckDB.
        as_of_date: Data de corte.
        scenario_id: Identificador do cenário.

    Returns:
        pd.DataFrame com 1 linha por par (customer_id, family) com compras até as_of_date.
    """
    cutoff = resolve_as_of_date(con, as_of_date, scenario_id=scenario_id)
    cutoff_str = cutoff.isoformat()
    logger.info(
        "Computando customer_family_features para '%s' com as_of_date=%s...",
        scenario_id,
        cutoff_str,
    )

    query = f"""
    WITH filtered_sales AS (
        SELECT
            f.customer_id,
            p.family,
            f.order_id,
            d.full_date::DATE AS full_date,
            f.units,
            f.boxes,
            f.gross_revenue,
            f.contribution_margin
        FROM gold.fact_sales f
        JOIN gold.dim_date d ON f.date_key = d.date_key
        JOIN gold.dim_product p ON f.product_id = p.product_id
        WHERE f.scenario_id = '{scenario_id}'
          AND d.full_date <= DATE '{cutoff_str}'
    ),
    cust_family_agg AS (
        SELECT
            customer_id,
            family,
            MIN(full_date)::DATE AS first_purchase_date,
            MAX(full_date)::DATE AS last_purchase_date,
            (DATE '{cutoff_str}' - MAX(full_date)::DATE)::INTEGER AS family_recency_days,
            COUNT(DISTINCT order_id)::INTEGER AS family_orders_count,
            SUM(units)::BIGINT AS family_units,
            ROUND(SUM(boxes), 2) AS family_boxes,
            ROUND(SUM(gross_revenue), 2) AS family_gross_revenue,
            ROUND(SUM(contribution_margin), 2) AS family_contribution_margin,
            ROUND(
                SUM(contribution_margin) / NULLIF(SUM(gross_revenue), 0) * 100.0,
                2
            ) AS family_margin_pct
        FROM filtered_sales
        GROUP BY customer_id, family
    ),
    cust_totals AS (
        SELECT
            customer_id,
            SUM(family_gross_revenue) AS total_customer_revenue
        FROM cust_family_agg
        GROUP BY customer_id
    )
    SELECT
        DATE '{cutoff_str}' AS as_of_date,
        cf.customer_id,
        cf.family,
        cf.first_purchase_date,
        cf.last_purchase_date,
        cf.family_recency_days,
        cf.family_orders_count,
        cf.family_units,
        cf.family_boxes,
        cf.family_gross_revenue,
        cf.family_contribution_margin,
        cf.family_margin_pct,
        ROUND(
            cf.family_gross_revenue / NULLIF(ct.total_customer_revenue, 0),
            4
        ) AS family_revenue_share
    FROM cust_family_agg cf
    JOIN cust_totals ct ON cf.customer_id = ct.customer_id
    ORDER BY cf.customer_id ASC, cf.family_gross_revenue DESC NULLS LAST, cf.family ASC
    """
    df = con.execute(query).df()
    logger.info("Customer-family features computadas com sucesso: %d registros.", len(df))
    return df


# ==============================================================================
# 4. Feature Store Integrada
# ==============================================================================


def compute_feature_store(
    con: duckdb.DuckDBPyConnection | None = None,
    as_of_date: date | datetime | str | None = None,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
) -> dict[str, pd.DataFrame]:
    """Orquestra a geração das 3 bases de features analíticas sem vazamento temporal.

    Args:
        con: Conexão ativa com o DuckDB (ou abre o catálogo local se None).
        as_of_date: Data de corte (None para usar a última disponível).
        scenario_id: Identificador do cenário.

    Returns:
        Dicionário com as 3 tabelas de features:
            - "customer_features": DataFrame por cliente
            - "sku_features": DataFrame por produto
            - "customer_family_features": DataFrame por cliente x família
    """
    close_con = False
    if con is None:
        con = duckdb.connect(str(get_duckdb_path()))
        close_con = True

    try:
        resolved_date = resolve_as_of_date(con, as_of_date, scenario_id=scenario_id)
        logger.info(
            "Iniciando Feature Store da Kyberna para '%s' com data-base %s...",
            scenario_id,
            resolved_date.isoformat(),
        )

        customer_df = compute_customer_features(con, as_of_date=resolved_date, scenario_id=scenario_id)
        sku_df = compute_sku_features(con, as_of_date=resolved_date, scenario_id=scenario_id)
        cust_fam_df = compute_customer_family_features(con, as_of_date=resolved_date, scenario_id=scenario_id)

        return {
            "customer_features": customer_df,
            "sku_features": sku_df,
            "customer_family_features": cust_fam_df,
        }
    finally:
        if close_con:
            con.close()
