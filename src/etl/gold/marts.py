from __future__ import annotations

from typing import Final

import duckdb

from src.core.logging import get_logger
from src.core.paths import get_data_dir
from src.core.types import ScenarioId
from src.ml.abc_xyz import build_abc_xyz_mart
from src.ml.churn import build_customer_risk_mart
from src.ml.rep_performance import build_rep_performance_mart
from src.ml.rfm import build_rfm_mart
from src.ml.white_space import build_white_space_mart

logger = get_logger(__name__)

DEFAULT_SCENARIO: Final[ScenarioId] = "c1_toys"


def build_margin_monthly_mart(
    con: duckdb.DuckDBPyConnection,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
) -> int:
    """Gera o mart analítico mensal agregado `mart_margin_monthly` no DuckDB.

    Grão da agregação:
        mês (year_month) x família de produto x estado (UF) x representante (RCA).

    Métricas calculadas:
        - orders_count: volume de pedidos distintos
        - customers_count: clientes ativos no mês
        - units e boxes: volume físico vendido
        - Waterfall completo: gross_revenue, discount_amount, net_price_revenue,
          tax_amount, net_revenue, cogs, commission_amount, freight_amount,
          contribution_margin e margin_pct (%).

    Args:
        con: Conexão ativa com o DuckDB.
        scenario_id: Identificador do cenário (ex: 'c1_toys').

    Returns:
        Número de linhas geradas no mart.
    """
    logger.info("Construindo mart analítico `mart_margin_monthly` para cenário '%s'...", scenario_id)

    con.execute("CREATE SCHEMA IF NOT EXISTS gold")
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {scenario_id}")

    mart_sql = f"""
    CREATE OR REPLACE TABLE {scenario_id}.mart_margin_monthly AS
    SELECT
        f.scenario_id,
        d.year_month,
        d.year,
        d.month,
        d.month_name,
        p.family,
        c.state,
        c.region,
        f.sales_rep_id,
        COUNT(DISTINCT f.order_id)::INTEGER AS orders_count,
        COUNT(DISTINCT f.customer_id)::INTEGER AS customers_count,
        SUM(f.units)::BIGINT AS units,
        ROUND(SUM(f.boxes), 2) AS boxes,
        ROUND(SUM(f.gross_revenue), 2) AS gross_revenue,
        ROUND(SUM(f.discount_amount), 2) AS discount_amount,
        ROUND(SUM(f.gross_revenue - f.discount_amount), 2) AS net_price_revenue,
        ROUND(SUM(f.tax_amount), 2) AS tax_amount,
        ROUND(SUM(f.net_revenue), 2) AS net_revenue,
        ROUND(SUM(f.cogs), 2) AS cogs,
        ROUND(SUM(f.commission_amount), 2) AS commission_amount,
        ROUND(SUM(f.freight_amount), 2) AS freight_amount,
        ROUND(SUM(f.contribution_margin), 2) AS contribution_margin,
        ROUND(
            SUM(f.contribution_margin) / NULLIF(SUM(f.gross_revenue), 0) * 100.0,
            2
        ) AS margin_pct
    FROM gold.fact_sales f
    JOIN gold.dim_date d ON f.date_key = d.date_key
    JOIN gold.dim_product p ON f.product_id = p.product_id
    JOIN gold.dim_customer c ON f.customer_id = c.customer_id
    WHERE f.scenario_id = '{scenario_id}'
    GROUP BY
        f.scenario_id,
        d.year_month,
        d.year,
        d.month,
        d.month_name,
        p.family,
        c.state,
        c.region,
        f.sales_rep_id
    ORDER BY
        d.year_month,
        p.family,
        c.state,
        f.sales_rep_id
    """

    con.execute(mart_sql)
    con.execute(
        f"CREATE OR REPLACE TABLE gold.mart_margin_monthly AS SELECT * FROM {scenario_id}.mart_margin_monthly"
    )

    row = con.execute(f"SELECT COUNT(*) FROM {scenario_id}.mart_margin_monthly").fetchone()
    count = int(row[0]) if row else 0

    # Exporta Parquet
    snapshot_dir = get_data_dir() / "gold" / "snapshot" / scenario_id
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    parquet_p = snapshot_dir / "mart_margin_monthly.parquet"
    con.execute(
        f"COPY gold.mart_margin_monthly TO '{parquet_p.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)"
    )

    logger.info("Mart `mart_margin_monthly` criado com %d registros e salvo em %s.", count, parquet_p)
    return count


def build_gold_marts(
    con: duckdb.DuckDBPyConnection,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
) -> dict[str, int]:
    """Orquestra a geração de todos os marts analíticos da camada Gold.

    Args:
        con: Conexão ativa com o DuckDB.
        scenario_id: Identificador do cenário (ex: 'c1_toys').

    Returns:
        Dicionário com nomes dos marts e contagens de linhas geradas.
    """
    logger.info("Iniciando geração dos marts Gold para cenário '%s'...", scenario_id)
    counts: dict[str, int] = {}
    counts["mart_margin_monthly"] = build_margin_monthly_mart(con, scenario_id=scenario_id)

    # Mart analítico da Matriz ABC/XYZ
    abc_df = build_abc_xyz_mart(con, scenario_id=scenario_id)
    counts["mart_abc_xyz"] = len(abc_df)

    # Mart analítico da Segmentação RFM
    rfm_df = build_rfm_mart(con, scenario_id=scenario_id)
    counts["mart_rfm"] = len(rfm_df)

    # Mart analítico de Risco de Churn e Ciclo de Recompra
    churn_df = build_customer_risk_mart(con, scenario_id=scenario_id)
    counts["mart_customer_risk"] = len(churn_df)

    # Mart analítico da Matriz White Space e Recomendações de Cross-Sell B2B
    white_space_df = build_white_space_mart(con, scenario_id=scenario_id)
    counts["mart_white_space"] = len(white_space_df)

    # Mart analítico de Eficiência Comercial de Representantes (RCAs)
    rep_perf_df = build_rep_performance_mart(con, scenario_id=scenario_id)
    counts["mart_rep_performance"] = len(rep_perf_df)

    return counts
