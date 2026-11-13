from __future__ import annotations

from datetime import date, datetime
from typing import Final

import duckdb
import pandas as pd

from src.core.logging import get_logger
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
    """
    if as_of_date is not None:
        if isinstance(as_of_date, str):
            return datetime.strptime(as_of_date[:10], "%Y-%m-%d").date()
        if isinstance(as_of_date, datetime):
            return as_of_date.date()
        return as_of_date

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


def compute_sku_features(
    con: duckdb.DuckDBPyConnection,
    as_of_date: date | datetime | str | None = None,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
    lookback_weeks: int = 26,
) -> pd.DataFrame:
    """Gera o catálogo de features de demanda e variabilidade por SKU até a data de corte."""
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


def compute_customer_family_features(
    con: duckdb.DuckDBPyConnection,
    as_of_date: date | datetime | str | None = None,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
) -> pd.DataFrame:
    """Gera o catálogo de penetração de categorias e mix de compra cliente x família."""
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
