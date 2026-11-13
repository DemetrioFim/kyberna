from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pandas as pd

from src.core.logging import get_logger
from src.core.types import ScenarioId
from src.db.repository import DataRepository
from src.services.dto import TemperanceKpisDTO
from src.services.temperance_inventory_queries import (
    query_temperance_inventory_details,
    query_temperance_inventory_kpis,
)
from src.services.temperance_policy_queries import (
    build_rep_bias_cte_sql,
    build_temperance_filter_clauses,
    load_temperance_policy_params,
    query_discount_policy_violations,
    query_term_leak_by_rep,
)

logger = get_logger(__name__)

__all__ = [
    "build_temperance_filter_clauses",
    "query_commercial_erosion_waterfall",
    "query_discount_policy_violations",
    "query_temperance_inventory_details",
    "query_temperance_kpis",
    "query_term_leak_by_rep",
]


def query_temperance_kpis(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    sales_reps: Sequence[str] = (),
    families: Sequence[str] = (),
    start_date_key: int | None = None,
    end_date_key: int | None = None,
) -> TemperanceKpisDTO:
    """Calcula os KPIs consolidados de Temperança, erosão de margem e estoque."""
    policy = load_temperance_policy_params(scenario_id)
    where_sql, params = build_temperance_filter_clauses(
        scenario_id,
        regiao=regiao,
        uf=uf,
        sales_reps=sales_reps,
        families=families,
        start_date_key=start_date_key,
        end_date_key=end_date_key,
    )

    sales_sql = f"""
    SELECT
        COALESCE(SUM(f.gross_revenue), 0.0) AS gross_revenue,
        COALESCE(SUM(f.discount_amount), 0.0) AS discount_amount,
        COALESCE(SUM(f.tax_amount), 0.0) AS tax_amount,
        COALESCE(SUM(f.net_revenue), 0.0) AS net_revenue,
        COALESCE(SUM(f.cogs), 0.0) AS cogs,
        COALESCE(SUM(f.commission_amount), 0.0) AS commission_amount,
        COALESCE(SUM(f.freight_amount), 0.0) AS freight_amount,
        COALESCE(SUM(f.contribution_margin), 0.0) AS contribution_margin,
        COALESCE(ROUND(SUM(GREATEST(0.0, f.discount_amount - f.gross_revenue * CASE c.size
            WHEN 'P' THEN ?
            WHEN 'M' THEN ?
            WHEN 'G' THEN ?
            ELSE ? END)), 2), 0.0) AS excess_discount_brl
    FROM gold.fact_sales f
    JOIN gold.dim_customer c ON f.customer_id = c.customer_id
    JOIN gold.dim_product p ON f.product_id = p.product_id
    JOIN gold.dim_sales_rep r ON f.sales_rep_id = r.sales_rep_id
    WHERE {where_sql}
    """
    sales_params = [policy["cap_p"], policy["cap_m"], policy["cap_g"], policy["cap_def"], *params]
    df_sales = repo.query(sales_sql, params=sales_params)

    rep_bias_expr, rep_bias_params = build_rep_bias_cte_sql(scenario_id, policy)
    term_sql = f"""
    WITH rep_bias AS (
        SELECT
            f_rep.sales_rep_id,
            {rep_bias_expr} AS extra_pmr
        FROM (SELECT DISTINCT sales_rep_id FROM gold.fact_sales WHERE scenario_id = ?) f_rep
    ),
    order_pmr AS (
        SELECT
            (f.gross_revenue - f.discount_amount) AS net_price_revenue,
            (CASE c.size WHEN 'P' THEN ? WHEN 'M' THEN ? WHEN 'G' THEN ? ELSE ? END
                + rb.extra_pmr) AS customer_pmr
        FROM gold.fact_sales f
        JOIN gold.dim_customer c ON f.customer_id = c.customer_id
        JOIN rep_bias rb ON f.sales_rep_id = rb.sales_rep_id
        JOIN gold.dim_product p ON f.product_id = p.product_id
        JOIN gold.dim_sales_rep r ON f.sales_rep_id = r.sales_rep_id
        WHERE {where_sql}
    )
    SELECT
        COALESCE(ROUND(SUM(GREATEST(0, customer_pmr - ?) * (? / 30.0) * net_price_revenue), 2), 0.0)
            AS term_leak_brl
    FROM order_pmr
    """
    term_params = [
        *rep_bias_params,
        policy["pmr_p"],
        policy["pmr_m"],
        policy["pmr_g"],
        policy["std_term"],
        *params,
        policy["std_term"],
        policy["rate_monthly"],
    ]
    df_term = repo.query(term_sql, params=term_params)
    term_leak = float(df_term["term_leak_brl"].iloc[0]) if not df_term.empty else 0.0

    inv_kpis = query_temperance_inventory_kpis(repo, scenario_id, families=families)

    if not df_sales.empty:
        r0 = df_sales.iloc[0]
        gross = float(r0["gross_revenue"])
        disc = float(r0["discount_amount"])
        comm = float(r0["commission_amount"])
        freight = float(r0["freight_amount"])
        excess_disc = float(r0["excess_discount_brl"])
    else:
        gross = disc = comm = freight = excess_disc = 0.0

    total_erosion = disc + comm + freight
    erosion_pct = (total_erosion / gross * 100.0) if gross > 0 else 0.0
    disc_pct = (disc / gross * 100.0) if gross > 0 else 0.0
    excess_pct = (excess_disc / disc * 100.0) if disc > 0 else 0.0

    return TemperanceKpisDTO(
        gross_revenue=gross,
        total_commercial_erosion_brl=round(total_erosion, 2),
        total_commercial_erosion_pct=round(erosion_pct, 1),
        discount_amount=round(disc, 2),
        discount_pct_of_gross=round(disc_pct, 1),
        excess_discount_brl=round(excess_disc, 2),
        excess_discount_pct_of_discount=round(excess_pct, 1),
        financial_term_leak_brl=round(term_leak, 2),
        freight_erosion_brl=round(freight, 2),
        commission_erosion_brl=round(comm, 2),
        total_stock_value_brl=round(float(inv_kpis["total_stock_value_brl"]), 2),
        locked_capital_brl=round(float(inv_kpis["locked_capital_brl"]), 2),
        locked_skus_count=int(inv_kpis["locked_skus_count"]),
        stockout_risk_skus_count=int(inv_kpis["stockout_risk_skus_count"]),
        stockout_risk_revenue_brl=round(float(inv_kpis["stockout_risk_revenue_brl"]), 2),
    )


def query_commercial_erosion_waterfall(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    sales_reps: Sequence[str] = (),
    families: Sequence[str] = (),
    start_date_key: int | None = None,
    end_date_key: int | None = None,
) -> pd.DataFrame:
    """Gera a tabela estruturada das 9 etapas do Waterfall de Margem Real."""
    where_sql, params = build_temperance_filter_clauses(
        scenario_id,
        regiao=regiao,
        uf=uf,
        sales_reps=sales_reps,
        families=families,
        start_date_key=start_date_key,
        end_date_key=end_date_key,
    )

    sql = f"""
    SELECT
        COALESCE(SUM(f.gross_revenue), 0.0) AS gross_revenue,
        COALESCE(SUM(f.discount_amount), 0.0) AS discount_amount,
        COALESCE(SUM(f.gross_revenue - f.discount_amount), 0.0) AS net_price_revenue,
        COALESCE(SUM(f.tax_amount), 0.0) AS tax_amount,
        COALESCE(SUM(f.net_revenue), 0.0) AS net_revenue,
        COALESCE(SUM(f.cogs), 0.0) AS cogs,
        COALESCE(SUM(f.commission_amount), 0.0) AS commission_amount,
        COALESCE(SUM(f.freight_amount), 0.0) AS freight_amount,
        COALESCE(SUM(f.contribution_margin), 0.0) AS contribution_margin
    FROM gold.fact_sales f
    JOIN gold.dim_customer c ON f.customer_id = c.customer_id
    JOIN gold.dim_product p ON f.product_id = p.product_id
    JOIN gold.dim_sales_rep r ON f.sales_rep_id = r.sales_rep_id
    WHERE {where_sql}
    """
    df = repo.query(sql, params=params)
    if df.empty:
        return pd.DataFrame()

    r = df.iloc[0]
    gross = float(r["gross_revenue"])
    base = gross if gross > 0 else 1.0

    def _step(k: str, lbl: str, amt: float, m: str, c: str) -> dict[str, Any]:
        return {"step_key": k, "label": lbl, "amount": amt, "measure": m, "color": c}

    steps: list[dict[str, Any]] = [
        _step("gross_revenue", "1. Faturamento Bruto", gross, "absolute", "#0ea5e9"),
        _step("discount", "2. Descontos Comerciais", -float(r["discount_amount"]), "relative", "#ef4444"),
        _step("net_price_revenue", "3. Receita Faturada", float(r["net_price_revenue"]), "total", "#38bdf8"),
        _step("tax", "4. Impostos (ICMS/PIS/COFINS)", -float(r["tax_amount"]), "relative", "#f97316"),
        _step("net_revenue", "5. Receita Líquida", float(r["net_revenue"]), "total", "#0284c7"),
        _step("cogs", "6. CPV (Custo Mercadoria)", -float(r["cogs"]), "relative", "#64748b"),
        _step("commission", "7. Comissões RCA", -float(r["commission_amount"]), "relative", "#eab308"),
        _step("freight", "8. Frete CIF Expedição", -float(r["freight_amount"]), "relative", "#f59e0b"),
        _step(
            "contribution_margin",
            "9. Margem Contribuição",
            float(r["contribution_margin"]),
            "total",
            "#10b981",
        ),
    ]

    for s in steps:
        s["pct_of_gross"] = round(abs(float(s["amount"])) / base * 100.0, 1)

    return pd.DataFrame(steps)
