from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pandas as pd

from src.core.logging import get_logger
from src.core.types import ScenarioId
from src.db.repository import DataRepository

logger = get_logger(__name__)


def build_pricing_fact_clauses(
    scenario_id: ScenarioId,
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    families: Sequence[str] = (),
    sales_reps: Sequence[str] = (),
    start_date_key: int | None = None,
    end_date_key: int | None = None,
) -> tuple[str, list[Any]]:
    """Monta cláusula WHERE parametrizada para `gold.fact_sales` com joins padrões."""
    clauses = ["f.scenario_id = ?", "f.units > 0", "p.base_unit_price > 0"]
    params: list[Any] = [scenario_id]
    if regiao != "Todas":
        clauses.append("c.region = ?")
        params.append(regiao)
    if uf != "Todas":
        clauses.append("c.state = ?")
        params.append(uf)
    if families:
        fam_list = list(families)
        placeholders = ", ".join(["?"] * len(fam_list))
        clauses.append(f"p.family IN ({placeholders})")
        params.extend(fam_list)
    if sales_reps:
        rep_list = list(sales_reps)
        placeholders = ", ".join(["?"] * len(rep_list))
        clauses.append(f"r.name IN ({placeholders})")
        params.extend(rep_list)
    if start_date_key is not None and end_date_key is not None:
        clauses.append("f.date_key BETWEEN ? AND ?")
        params.extend([start_date_key, end_date_key])
    return " AND ".join(clauses), params


def query_filtered_pricing_kpis(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    families: Sequence[str] = (),
    sales_reps: Sequence[str] = (),
    start_date_key: int | None = None,
    end_date_key: int | None = None,
) -> dict[str, float | int]:
    """Calcula os 5 KPIs de realização, vazamento e upside inelástico sobre o recorte filtrado."""
    where_sql, params = build_pricing_fact_clauses(
        scenario_id,
        regiao=regiao,
        uf=uf,
        families=families,
        sales_reps=sales_reps,
        start_date_key=start_date_key,
        end_date_key=end_date_key,
    )
    sql = f"""
    WITH line_eval AS (
        SELECT
            f.order_id,
            f.product_id,
            f.units,
            (f.unit_net_price / p.base_unit_price) * 100.0 AS idx,
            COALESCE(pr.contextual_band_low_idx, 88.0) AS band_low_idx,
            COALESCE(pr.contextual_band_high_idx, 94.5) AS band_high_idx,
            p.base_unit_price,
            f.unit_net_price,
            COALESCE(e.beta_hat, -1.2) AS beta_hat,
            GREATEST(
                0.25,
                1.0 - COALESCE(
                    (f.tax_amount + f.commission_amount) / NULLIF(f.unit_net_price * f.units, 0.0),
                    0.23,
                )
            ) AS net_keep
        FROM gold.fact_sales f
        JOIN gold.dim_product p ON f.product_id = p.product_id
        JOIN gold.dim_customer c ON f.customer_id = c.customer_id
        JOIN gold.dim_sales_rep r ON f.sales_rep_id = r.sales_rep_id
        LEFT JOIN gold.mart_price_realization pr
          ON f.scenario_id = pr.scenario_id AND f.product_id = pr.product_id
        LEFT JOIN gold.mart_price_elasticity e
          ON f.scenario_id = e.scenario_id AND p.family = e.family
        WHERE {where_sql}
    ),
    window_span AS (
        SELECT GREATEST(
            DATEDIFF('day', MIN(d.full_date), MAX(d.full_date)) + 1.0,
            30.0
        ) / 365.0 AS years_span
        FROM gold.fact_sales f
        JOIN gold.dim_product p ON f.product_id = p.product_id
        JOIN gold.dim_customer c ON f.customer_id = c.customer_id
        JOIN gold.dim_sales_rep r ON f.sales_rep_id = r.sales_rep_id
        JOIN gold.dim_date d ON f.date_key = d.date_key
        WHERE {where_sql}
    )
    SELECT
        COALESCE(AVG(le.idx), 0.0) AS realization_index_pct,
        COALESCE(STDDEV(le.idx) / NULLIF(AVG(le.idx), 0.0) * 100.0, 0.0) AS price_cv_pct,
        COALESCE(
            AVG(CASE WHEN le.idx < le.band_low_idx THEN 100.0 ELSE 0.0 END),
            0.0,
        ) AS below_band_sales_pct,
        COALESCE(
            SUM(GREATEST(0.0, (le.band_low_idx / 100.0) * le.base_unit_price - le.unit_net_price) * le.units),
            0.0
        ) AS subpricing_leakage_brl,
        COALESCE(
            SUM(
                CASE
                    WHEN le.beta_hat > -1.0 AND le.idx < le.band_high_idx THEN
                        GREATEST(
                            0.0,
                            le.units
                            * POWER(
                                LEAST(GREATEST(le.band_high_idx / NULLIF(le.idx, 0.0), 1.0), 1.25),
                                le.beta_hat,
                            )
                            * ((le.band_high_idx / 100.0) * le.base_unit_price)
                            - le.units * le.unit_net_price
                        ) * le.net_keep
                    ELSE 0.0
                END
            ) / MAX(ws.years_span),
            0.0
        ) AS inelastic_reprice_upside_brl,
        COUNT(DISTINCT le.order_id)::INTEGER AS orders_count,
        COUNT(DISTINCT le.product_id)::INTEGER AS skus_count
    FROM line_eval le
    CROSS JOIN window_span ws
    """
    try:
        df = repo.query(sql, params=[*params, *params])
    except Exception as exc:
        logger.warning("Falha ao consultar KPIs de precificação para %s: %s", scenario_id, exc)
        return {
            "realization_index_pct": 0.0,
            "price_cv_pct": 0.0,
            "below_band_sales_pct": 0.0,
            "subpricing_leakage_brl": 0.0,
            "inelastic_reprice_upside_brl": 0.0,
            "orders_count": 0,
            "skus_count": 0,
        }

    if df.empty:
        return {
            "realization_index_pct": 0.0,
            "price_cv_pct": 0.0,
            "below_band_sales_pct": 0.0,
            "subpricing_leakage_brl": 0.0,
            "inelastic_reprice_upside_brl": 0.0,
            "orders_count": 0,
            "skus_count": 0,
        }
    r0 = df.iloc[0]
    return {
        "realization_index_pct": round(float(r0["realization_index_pct"]), 2),
        "price_cv_pct": round(float(r0["price_cv_pct"]), 2),
        "below_band_sales_pct": round(float(r0["below_band_sales_pct"]), 1),
        "subpricing_leakage_brl": round(float(r0["subpricing_leakage_brl"]), 2),
        "inelastic_reprice_upside_brl": round(float(r0["inelastic_reprice_upside_brl"]), 2),
        "orders_count": int(r0["orders_count"]),
        "skus_count": int(r0["skus_count"]),
    }


def query_pricing_boxplot_data(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    families: Sequence[str] = (),
    sales_reps: Sequence[str] = (),
    start_date_key: int | None = None,
    end_date_key: int | None = None,
) -> pd.DataFrame:
    """Retorna quantis realizados (% e R$/un.) e banda contextual por Família ou Top 10 SKUs."""
    where_sql, params = build_pricing_fact_clauses(
        scenario_id,
        regiao=regiao,
        uf=uf,
        families=families,
        sales_reps=sales_reps,
        start_date_key=start_date_key,
        end_date_key=end_date_key,
    )
    if len(families) == 1:
        group_expr = "p.product_name"
        limit_sql = "LIMIT 10"
    else:
        group_expr = "p.family"
        limit_sql = ""

    sql = f"""
    WITH line_eval AS (
        SELECT
            {group_expr} AS group_label,
            p.family,
            p.base_unit_price,
            f.unit_net_price,
            f.units,
            (f.unit_net_price / p.base_unit_price) * 100.0 AS idx,
            COALESCE(pr.contextual_band_low_idx, 88.0) AS band_low_idx,
            COALESCE(pr.contextual_band_expected_idx, 91.5) AS band_expected_idx,
            COALESCE(pr.contextual_band_high_idx, 94.5) AS band_high_idx,
            COALESCE(pr.min_healthy_idx, 78.0) AS min_healthy_idx
        FROM gold.fact_sales f
        JOIN gold.dim_product p ON f.product_id = p.product_id
        JOIN gold.dim_customer c ON f.customer_id = c.customer_id
        JOIN gold.dim_sales_rep r ON f.sales_rep_id = r.sales_rep_id
        LEFT JOIN gold.mart_price_realization pr
          ON f.scenario_id = pr.scenario_id AND f.product_id = pr.product_id
        WHERE {where_sql}
    )
    SELECT
        group_label,
        MAX(family) AS family,
        ROUND(QUANTILE_CONT(idx, 0.05), 2) AS p05,
        ROUND(QUANTILE_CONT(idx, 0.25), 2) AS p25,
        ROUND(QUANTILE_CONT(idx, 0.50), 2) AS p50,
        ROUND(QUANTILE_CONT(idx, 0.75), 2) AS p75,
        ROUND(QUANTILE_CONT(idx, 0.95), 2) AS p95,
        ROUND(AVG(idx), 2) AS realized_mean,
        ROUND(AVG(band_low_idx), 2) AS band_low,
        ROUND(AVG(band_expected_idx), 2) AS band_expected,
        ROUND(AVG(band_high_idx), 2) AS band_high,
        ROUND(AVG(min_healthy_idx), 2) AS min_healthy_idx,
        ROUND(AVG(base_unit_price), 2) AS avg_base_price_brl,
        ROUND(QUANTILE_CONT(unit_net_price, 0.05), 2) AS p05_brl,
        ROUND(QUANTILE_CONT(unit_net_price, 0.25), 2) AS p25_brl,
        ROUND(QUANTILE_CONT(unit_net_price, 0.50), 2) AS p50_brl,
        ROUND(QUANTILE_CONT(unit_net_price, 0.75), 2) AS p75_brl,
        ROUND(QUANTILE_CONT(unit_net_price, 0.95), 2) AS p95_brl,
        ROUND(AVG(unit_net_price), 2) AS realized_mean_brl,
        ROUND(AVG((band_low_idx / 100.0) * base_unit_price), 2) AS band_low_brl,
        ROUND(AVG((band_high_idx / 100.0) * base_unit_price), 2) AS band_high_brl,
        ROUND(AVG((min_healthy_idx / 100.0) * base_unit_price), 2) AS min_healthy_brl,
        ROUND(SUM(GREATEST(0.0, (band_low_idx / 100.0) * base_unit_price - unit_net_price) * units), 2)
            AS price_leakage_brl
    FROM line_eval
    GROUP BY group_label
    ORDER BY price_leakage_brl DESC, SUM(units) DESC
    {limit_sql}
    """
    try:
        return repo.query(sql, params=params)
    except Exception as exc:
        logger.warning("Falha ao consultar boxplot de precificação para %s: %s", scenario_id, exc)
        return pd.DataFrame()


def query_pricing_deviations(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    families: Sequence[str] = (),
    sales_reps: Sequence[str] = (),
    start_date_key: int | None = None,
    end_date_key: int | None = None,
) -> pd.DataFrame:
    """Lista os SKUs com maior vazamento financeiro abaixo da banda contextual no recorte."""
    where_sql, params = build_pricing_fact_clauses(
        scenario_id,
        regiao=regiao,
        uf=uf,
        families=families,
        sales_reps=sales_reps,
        start_date_key=start_date_key,
        end_date_key=end_date_key,
    )
    sql = f"""
    WITH line_leak AS (
        SELECT
            f.product_id,
            p.product_name,
            p.family,
            COALESCE(pr.abc_class, 'C') AS abc_class,
            (f.unit_net_price / p.base_unit_price) * 100.0 AS idx,
            COALESCE(pr.contextual_band_low_idx, 88.0) AS band_low_idx,
            COALESCE(pr.contextual_band_high_idx, 94.5) AS band_high_idx,
            COALESCE(pr.min_healthy_idx, 78.0) AS min_healthy_idx,
            COALESCE(pr.inelastic_upside_brl, 0.0) AS inelastic_upside_brl,
            GREATEST(0.0, (COALESCE(pr.contextual_band_low_idx, 88.0) / 100.0) * p.base_unit_price
                - f.unit_net_price) * f.units AS line_leak_brl,
            r.name AS rep_name
        FROM gold.fact_sales f
        JOIN gold.dim_product p ON f.product_id = p.product_id
        JOIN gold.dim_customer c ON f.customer_id = c.customer_id
        JOIN gold.dim_sales_rep r ON f.sales_rep_id = r.sales_rep_id
        LEFT JOIN gold.mart_price_realization pr
          ON f.scenario_id = pr.scenario_id AND f.product_id = pr.product_id
        WHERE {where_sql}
    ),
    rep_rank AS (
        SELECT
            product_id,
            rep_name,
            SUM(line_leak_brl) AS rep_leak,
            ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY SUM(line_leak_brl) DESC, rep_name ASC) AS rn
        FROM line_leak
        GROUP BY product_id, rep_name
    )
    SELECT
        l.product_id,
        MAX(l.product_name) AS product_name,
        MAX(l.family) AS family,
        MAX(l.abc_class) AS abc_class,
        ROUND(AVG(l.idx), 2) AS realized_idx_mean,
        ROUND(AVG(l.band_low_idx), 2) AS contextual_band_low_idx,
        ROUND(AVG(l.band_high_idx), 2) AS contextual_band_high_idx,
        ROUND(AVG(l.min_healthy_idx), 2) AS min_healthy_idx,
        ROUND(AVG(CASE WHEN l.idx < l.band_low_idx THEN 100.0 ELSE 0.0 END), 1) AS below_band_orders_pct,
        ROUND(SUM(l.line_leak_brl), 2) AS price_leakage_brl,
        ROUND(MAX(l.inelastic_upside_brl), 2) AS inelastic_upside_brl,
        MAX(rr.rep_name) AS primary_offender_rep
    FROM line_leak l
    LEFT JOIN rep_rank rr ON l.product_id = rr.product_id AND rr.rn = 1
    GROUP BY l.product_id
    HAVING SUM(l.line_leak_brl) > 0
    ORDER BY price_leakage_brl DESC, below_band_orders_pct DESC
    LIMIT 50
    """
    try:
        return repo.query(sql, params=params)
    except Exception as exc:
        logger.warning("Falha ao consultar desvios de preço para %s: %s", scenario_id, exc)
        return pd.DataFrame()


def query_family_pricing_bands(
    repo: DataRepository,
    scenario_id: ScenarioId,
) -> pd.DataFrame:
    """Retorna faixas competitivas relativas (delta vs. preço atual) por família para o Simulador."""
    sql = """
    SELECT
        family,
        ROUND((AVG(contextual_band_low_idx) - AVG(realized_idx_mean)) / 100.0, 4) AS band_low_delta_pct,
        ROUND((AVG(contextual_band_high_idx) - AVG(realized_idx_mean)) / 100.0, 4) AS band_high_delta_pct,
        ROUND((AVG(min_healthy_idx) - AVG(realized_idx_mean)) / 100.0, 4) AS min_healthy_delta_pct
    FROM gold.mart_price_realization
    WHERE scenario_id = ?
    GROUP BY family
    ORDER BY family ASC
    """
    try:
        return repo.query(sql, params=[scenario_id])
    except Exception:
        return pd.DataFrame()
