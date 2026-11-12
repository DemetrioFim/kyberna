from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd

from src.core.logging import get_logger
from src.core.types import ScenarioId
from src.db.repository import DataRepository
from src.etl.finance.margin_waterfall import load_discounts_config
from src.services.fortitude_risk_queries import (
    AGING_BUCKET_ORDER,
    query_aging_buckets_and_customers,
    query_concentration_data,
    trailing_12m_cte,
)
from src.services.temperance_queries import build_temperance_filter_clauses

logger = get_logger(__name__)

__all__ = [
    "AGING_BUCKET_ORDER",
    "query_aging_buckets_and_customers",
    "query_concentration_data",
    "query_fortitude_financial_base",
    "query_pme_weighted",
    "query_pmr_weighted",
]


def query_fortitude_financial_base(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    sales_reps: Sequence[str] = (),
    families: Sequence[str] = (),
) -> dict[str, float | int]:
    """Consulta médias mensais dos últimos 12 meses de receita, margem e clientes ativos."""
    where_sql, filter_params = build_temperance_filter_clauses(
        scenario_id,
        regiao=regiao,
        uf=uf,
        sales_reps=sales_reps,
        families=families,
    )
    sql = f"""
    {trailing_12m_cte()}
    SELECT
        GREATEST(COUNT(DISTINCT d.year_month), 1)::INTEGER AS active_months,
        COALESCE(SUM(f.gross_revenue), 0.0) AS gross_revenue_12m,
        COALESCE(SUM(f.net_revenue), 0.0) AS net_revenue_12m,
        COALESCE(SUM(f.contribution_margin), 0.0) AS contribution_margin_12m,
        COUNT(DISTINCT f.customer_id)::INTEGER AS active_customers_count
    FROM gold.fact_sales f
    JOIN gold.dim_date d ON f.date_key = d.date_key
    JOIN gold.dim_customer c ON f.customer_id = c.customer_id
    JOIN gold.dim_product p ON f.product_id = p.product_id
    JOIN gold.dim_sales_rep r ON f.sales_rep_id = r.sales_rep_id
    CROSS JOIN max_dt m
    WHERE {where_sql}
      AND d.full_date > (m.max_full_date - INTERVAL 12 MONTH)
    """
    params: list[Any] = [scenario_id, *filter_params]
    df = repo.query(sql, params=params)
    if df.empty:
        return {
            "active_months": 12,
            "monthly_gross_revenue_brl": 0.0,
            "monthly_net_revenue_brl": 0.0,
            "monthly_contribution_margin_brl": 0.0,
            "active_customers_count": 0,
        }

    row = df.iloc[0]
    months = max(int(row["active_months"]), 1)
    return {
        "active_months": months,
        "monthly_gross_revenue_brl": float(row["gross_revenue_12m"]) / months,
        "monthly_net_revenue_brl": float(row["net_revenue_12m"]) / months,
        "monthly_contribution_margin_brl": float(row["contribution_margin_12m"]) / months,
        "active_customers_count": int(row["active_customers_count"]),
    }


def query_pme_weighted(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    families: Sequence[str] = (),
) -> float:
    """Calcula o Prazo Médio de Estocagem (PME em dias) ponderado pelo valor em estoque."""
    params: list[Any] = [scenario_id]
    fam_clause = ""
    if families:
        fam_list = list(families)
        ph = ", ".join(["?"] * len(fam_list))
        fam_clause = f" AND inv.family IN ({ph})"
        params.extend(fam_list)

    sql = f"""
    SELECT
        COALESCE(
            SUM(inv.coverage_days * inv.stock_value_brl) / NULLIF(SUM(inv.stock_value_brl), 0.0),
            AVG(inv.coverage_days),
            0.0
        ) AS pme_days
    FROM gold.inventory_snapshot inv
    WHERE inv.scenario_id = ? {fam_clause}
    """
    df = repo.query(sql, params=params)
    if df.empty or pd.isna(df.iloc[0]["pme_days"]):
        return 0.0
    return float(df.iloc[0]["pme_days"])


def query_pmr_weighted(
    repo: DataRepository,
    scenario_id: ScenarioId,
    pmr_by_size: Mapping[str, float],
    extra_pmr_days: float,
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    sales_reps: Sequence[str] = (),
    families: Sequence[str] = (),
) -> float:
    """Calcula o Prazo Médio de Recebimento (PMR em dias) ponderado pela receita líquida."""
    high_reps = list(load_discounts_config().rep_bias.high_discount_reps)
    where_sql, filter_params = build_temperance_filter_clauses(
        scenario_id,
        regiao=regiao,
        uf=uf,
        sales_reps=sales_reps,
        families=families,
    )

    p_days = float(pmr_by_size.get("P", 28.0))
    m_days = float(pmr_by_size.get("M", 42.0))
    g_days = float(pmr_by_size.get("G", 56.0))
    default_days = m_days

    if high_reps:
        rep_ph = ", ".join(["?"] * len(high_reps))
        extra_expr = f"CASE WHEN f.sales_rep_id IN ({rep_ph}) THEN ? ELSE 0.0 END"
        rep_params: list[Any] = [*high_reps, float(extra_pmr_days)]
    else:
        extra_expr = "0.0"
        rep_params = []

    sql = f"""
    {trailing_12m_cte()}
    , scoped_orders AS (
        SELECT
            f.net_revenue,
            (
                CASE c.size
                    WHEN 'P' THEN ?
                    WHEN 'M' THEN ?
                    WHEN 'G' THEN ?
                    ELSE ?
                END + {extra_expr}
            ) AS effective_pmr
        FROM gold.fact_sales f
        JOIN gold.dim_date d ON f.date_key = d.date_key
        JOIN gold.dim_customer c ON f.customer_id = c.customer_id
        JOIN gold.dim_product p ON f.product_id = p.product_id
        JOIN gold.dim_sales_rep r ON f.sales_rep_id = r.sales_rep_id
        CROSS JOIN max_dt m
        WHERE {where_sql}
          AND d.full_date > (m.max_full_date - INTERVAL 12 MONTH)
    )
    SELECT
        COALESCE(
            SUM(effective_pmr * net_revenue) / NULLIF(SUM(net_revenue), 0.0),
            AVG(effective_pmr),
            ?
        ) AS pmr_days
    FROM scoped_orders
    """
    params: list[Any] = [
        scenario_id,
        p_days,
        m_days,
        g_days,
        default_days,
        *rep_params,
        *filter_params,
        default_days,
    ]
    df = repo.query(sql, params=params)
    if df.empty or pd.isna(df.iloc[0]["pmr_days"]):
        return round(default_days, 1)
    return float(df.iloc[0]["pmr_days"])
