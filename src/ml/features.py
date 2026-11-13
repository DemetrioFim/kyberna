from __future__ import annotations

from datetime import date, datetime

import duckdb
import pandas as pd

from src.core.logging import get_logger
from src.core.paths import get_duckdb_path
from src.core.types import ScenarioId
from src.ml.sku_features import (
    DEFAULT_SCENARIO,
    compute_customer_family_features,
    compute_sku_features,
    resolve_as_of_date,
)

logger = get_logger(__name__)

__all__ = [
    "DEFAULT_SCENARIO",
    "compute_customer_family_features",
    "compute_customer_features",
    "compute_feature_store",
    "compute_sku_features",
    "resolve_as_of_date",
]


def compute_customer_features(
    con: duckdb.DuckDBPyConnection,
    as_of_date: date | datetime | str | None = None,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
) -> pd.DataFrame:
    """Gera o catálogo de features comportamentais e financeiras por cliente até a data de corte.

    Garante zero vazamento temporal (nenhuma transação posterior a `as_of_date` é lida).
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
            ) AS revenue_6m,
            ROUND(
                SUM(
                    CASE WHEN full_date > DATE '{cutoff_str}' - INTERVAL 365 DAY
                         THEN gross_revenue ELSE 0 END
                ),
                2
            ) AS revenue_12m,
            ROUND(
                SUM(
                    CASE WHEN full_date > DATE '{cutoff_str}' - INTERVAL 365 DAY
                         THEN contribution_margin ELSE 0 END
                ),
                2
            ) AS margin_12m
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
        t.revenue_12m,
        t.margin_12m,
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


def compute_feature_store(
    con: duckdb.DuckDBPyConnection | None = None,
    as_of_date: date | datetime | str | None = None,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
) -> dict[str, pd.DataFrame]:
    """Orquestra a geração das 3 bases de features analíticas sem vazamento temporal."""
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
