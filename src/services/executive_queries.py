from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

import pandas as pd

from src.core.logging import get_logger
from src.core.types import ScenarioId
from src.db.repository import DataRepository
from src.services.prudence_anomalies import query_prudence_anomalies

__all__ = [
    "build_filter_clauses",
    "query_margin_recovery_potential",
    "query_monthly_sales_table",
    "query_monthly_trend",
    "query_prudence_anomalies",
    "query_raw_kpis",
    "query_top_drivers",
]

logger = get_logger(__name__)


def build_filter_clauses(
    scenario_id: ScenarioId,
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    families: Sequence[str] = (),
    sales_reps: Sequence[str] = (),
    start_date_key: int | None = None,
    end_date_key: int | None = None,
) -> tuple[str, list[Any], list[str]]:
    """Gera cláusula WHERE, parâmetros e lista de tabelas dimensionais para JOIN."""
    clauses: list[str] = ["f.scenario_id = ?"]
    params: list[Any] = [scenario_id]
    joins: list[str] = []

    need_customer = False
    need_product = False
    need_rep = False

    if regiao != "Todas":
        clauses.append("c.region = ?")
        params.append(regiao)
        need_customer = True

    if uf != "Todas":
        clauses.append("c.state = ?")
        params.append(uf)
        need_customer = True

    if families:
        fam_list = list(families)
        placeholders = ", ".join(["?"] * len(fam_list))
        clauses.append(f"p.family IN ({placeholders})")
        params.extend(fam_list)
        need_product = True

    if sales_reps:
        rep_list = list(sales_reps)
        placeholders = ", ".join(["?"] * len(rep_list))
        clauses.append(f"(f.sales_rep_id IN ({placeholders}) OR r.name IN ({placeholders}))")
        params.extend(rep_list)
        params.extend(rep_list)
        need_rep = True

    if start_date_key is not None:
        clauses.append("f.date_key >= ?")
        params.append(start_date_key)

    if end_date_key is not None:
        clauses.append("f.date_key <= ?")
        params.append(end_date_key)

    if need_customer:
        joins.append("JOIN gold.dim_customer c ON f.customer_id = c.customer_id")
    if need_product:
        joins.append("JOIN gold.dim_product p ON f.product_id = p.product_id")
    if need_rep:
        joins.append("JOIN gold.dim_sales_rep r ON f.sales_rep_id = r.sales_rep_id")

    return f"WHERE {' AND '.join(clauses)}", params, joins


def query_raw_kpis(
    repo: DataRepository,
    where_sql: str,
    params: list[Any],
    joins: list[str],
) -> pd.DataFrame:
    """Executa a agregação analítica dos KPIs do Waterfall sobre gold.fact_sales."""
    joins_sql = " ".join(joins)
    sql = f"""
    SELECT
        COUNT(DISTINCT f.order_id) AS total_orders,
        COUNT(DISTINCT f.customer_id) AS active_customers,
        ROUND(COALESCE(SUM(f.gross_revenue), 0), 2) AS gross_revenue,
        ROUND(COALESCE(SUM(f.discount_amount), 0), 2) AS discount_amount,
        ROUND(COALESCE(SUM(f.gross_revenue - f.discount_amount), 0), 2) AS net_price_revenue,
        ROUND(COALESCE(SUM(f.tax_amount), 0), 2) AS tax_amount,
        ROUND(COALESCE(SUM(f.net_revenue), 0), 2) AS net_revenue,
        ROUND(COALESCE(SUM(f.cogs), 0), 2) AS cogs,
        ROUND(COALESCE(SUM(f.commission_amount), 0), 2) AS commission_amount,
        ROUND(COALESCE(SUM(f.freight_amount), 0), 2) AS freight_amount,
        ROUND(COALESCE(SUM(f.contribution_margin), 0), 2) AS contribution_margin,
        ROUND(COALESCE(SUM(f.boxes), 0), 2) AS total_boxes,
        COALESCE(SUM(f.units), 0) AS total_units,
        MIN(f.date_key) AS min_date_key,
        MAX(f.date_key) AS max_date_key
    FROM gold.fact_sales f
    {joins_sql}
    {where_sql}
    """
    return repo.query(sql, params)


def query_monthly_trend(
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
    """Consulta a série temporal de faturamento e margem no mart_margin_monthly."""
    clauses: list[str] = ["m.scenario_id = ?"]
    params: list[Any] = [scenario_id]
    joins_sql = ""

    if regiao != "Todas":
        clauses.append("m.region = ?")
        params.append(regiao)
    if uf != "Todas":
        clauses.append("m.state = ?")
        params.append(uf)
    if families:
        fam_list = list(families)
        clauses.append(f"m.family IN ({', '.join(['?'] * len(fam_list))})")
        params.extend(fam_list)
    if sales_reps:
        rep_list = list(sales_reps)
        placeholders = ", ".join(["?"] * len(rep_list))
        clauses.append(f"(m.sales_rep_id IN ({placeholders}) OR r.name IN ({placeholders}))")
        params.extend(rep_list)
        params.extend(rep_list)
        joins_sql = "LEFT JOIN gold.dim_sales_rep r ON m.sales_rep_id = r.sales_rep_id"

    if start_date_key is not None:
        clauses.append("m.year_month >= ?")
        params.append(f"{start_date_key // 10000:04d}-{((start_date_key % 10000) // 100):02d}")
    if end_date_key is not None:
        clauses.append("m.year_month <= ?")
        params.append(f"{end_date_key // 10000:04d}-{((end_date_key % 10000) // 100):02d}")

    where_sql = f"WHERE {' AND '.join(clauses)}"
    sql = f"""
    SELECT
        m.year_month,
        CASE m.month
            WHEN 1 THEN 'Jan/' WHEN 2 THEN 'Fev/' WHEN 3 THEN 'Mar/' WHEN 4 THEN 'Abr/'
            WHEN 5 THEN 'Mai/' WHEN 6 THEN 'Jun/' WHEN 7 THEN 'Jul/' WHEN 8 THEN 'Ago/'
            WHEN 9 THEN 'Set/' WHEN 10 THEN 'Out/' WHEN 11 THEN 'Nov/' WHEN 12 THEN 'Dez/'
        END || RIGHT(CAST(m.year AS VARCHAR), 2) AS month_label,
        ROUND(SUM(m.gross_revenue), 2) AS gross_revenue,
        ROUND(SUM(m.discount_amount), 2) AS discount_amount,
        ROUND(SUM(m.discount_amount) / NULLIF(SUM(m.gross_revenue), 0) * 100.0, 1) AS avg_discount_pct,
        ROUND(SUM(m.net_revenue), 2) AS net_revenue,
        ROUND(SUM(m.contribution_margin), 2) AS contribution_margin,
        ROUND(SUM(m.contribution_margin) / NULLIF(SUM(m.gross_revenue), 0) * 100.0, 2) AS margin_pct
    FROM gold.mart_margin_monthly m
    {joins_sql}
    {where_sql}
    GROUP BY m.year_month, m.year, m.month
    ORDER BY m.year_month ASC
    """
    return repo.query(sql, params)


def query_monthly_sales_table(
    repo: DataRepository,
    *,
    where_sql: str,
    params: list[Any],
    joins: list[str],
) -> pd.DataFrame:
    """Consulta o demonstrativo detalhado de vendas mês a mês para exibição em tabela analítica."""
    joins_copy = list(joins)
    if "JOIN gold.dim_date d ON f.date_key = d.date_key" not in joins_copy:
        joins_copy.append("JOIN gold.dim_date d ON f.date_key = d.date_key")
    joins_sql = " ".join(joins_copy)

    sql = f"""
    SELECT
        strftime(d.full_date, '%Y-%m') AS year_month,
        CASE MONTH(d.full_date)
            WHEN 1 THEN 'Jan/' WHEN 2 THEN 'Fev/' WHEN 3 THEN 'Mar/' WHEN 4 THEN 'Abr/'
            WHEN 5 THEN 'Mai/' WHEN 6 THEN 'Jun/' WHEN 7 THEN 'Jul/' WHEN 8 THEN 'Ago/'
            WHEN 9 THEN 'Set/' WHEN 10 THEN 'Out/' WHEN 11 THEN 'Nov/' WHEN 12 THEN 'Dez/'
        END || RIGHT(CAST(YEAR(d.full_date) AS VARCHAR), 2) AS month_label,
        COUNT(DISTINCT f.order_id) AS orders_count,
        COUNT(DISTINCT f.customer_id) AS active_customers,
        COALESCE(SUM(f.units), 0) AS total_units,
        ROUND(COALESCE(SUM(f.boxes), 0), 1) AS total_boxes,
        ROUND(COALESCE(SUM(f.gross_revenue), 0), 2) AS gross_revenue,
        ROUND(COALESCE(SUM(f.discount_amount), 0), 2) AS discount_amount,
        ROUND(
            COALESCE(SUM(f.discount_amount) / NULLIF(SUM(f.gross_revenue), 0) * 100.0, 0),
            2
        ) AS avg_discount_pct,
        ROUND(COALESCE(SUM(f.net_revenue), 0), 2) AS net_revenue,
        ROUND(COALESCE(SUM(f.cogs), 0), 2) AS cogs,
        ROUND(COALESCE(SUM(f.commission_amount), 0), 2) AS commission_amount,
        ROUND(COALESCE(SUM(f.freight_amount), 0), 2) AS freight_amount,
        ROUND(COALESCE(SUM(f.contribution_margin), 0), 2) AS contribution_margin,
        ROUND(
            COALESCE(SUM(f.contribution_margin) / NULLIF(SUM(f.gross_revenue), 0) * 100.0, 0),
            2
        ) AS margin_pct,
        ROUND(COALESCE(SUM(f.gross_revenue) / NULLIF(COUNT(DISTINCT f.order_id), 0), 0), 2) AS avg_ticket
    FROM gold.fact_sales f
    {joins_sql}
    {where_sql}
    GROUP BY 1, 2
    ORDER BY 1 ASC
    """
    df = repo.query(sql, params)
    if not df.empty:
        df["mom_gross_pct"] = (df["gross_revenue"].pct_change() * 100.0).round(1)
        df["mom_margin_pct"] = (df["contribution_margin"].pct_change() * 100.0).round(1)
    return df


def query_top_drivers(
    repo: DataRepository,
    by: Literal["product", "customer", "family", "sales_rep"] = "product",
    *,
    where_sql: str,
    params: list[Any],
    joins: list[str],
    limit: int = 10,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Consulta Top Geradores e Top Detratores/Menor Margem por Produto, Cliente, Família ou RCA."""
    joins_copy = list(joins)
    if by == "product":
        if "JOIN gold.dim_product p ON f.product_id = p.product_id" not in joins_copy:
            joins_copy.append("JOIN gold.dim_product p ON f.product_id = p.product_id")
        group_cols = "p.product_name, p.family"
        select_cols = "p.product_name AS name, p.family AS secondary_label"
    elif by == "customer":
        if "JOIN gold.dim_customer c ON f.customer_id = c.customer_id" not in joins_copy:
            joins_copy.append("JOIN gold.dim_customer c ON f.customer_id = c.customer_id")
        group_cols = "c.trade_name, c.state, c.segment"
        select_cols = "c.trade_name AS name, c.state || ' - ' || c.segment AS secondary_label"
    elif by == "family":
        if "JOIN gold.dim_product p ON f.product_id = p.product_id" not in joins_copy:
            joins_copy.append("JOIN gold.dim_product p ON f.product_id = p.product_id")
        group_cols = "p.family"
        select_cols = (
            "p.family AS name, "
            "CAST(COUNT(DISTINCT p.product_id) AS VARCHAR) || ' SKUs ativos' AS secondary_label"
        )
    else:  # sales_rep
        if "JOIN gold.dim_sales_rep r ON f.sales_rep_id = r.sales_rep_id" not in joins_copy:
            joins_copy.append("JOIN gold.dim_sales_rep r ON f.sales_rep_id = r.sales_rep_id")
        group_cols = "r.name, r.region"
        select_cols = "r.name AS name, r.region AS secondary_label"

    joins_sql = " ".join(joins_copy)
    base_sql = f"""
    SELECT
        {select_cols},
        ROUND(SUM(f.gross_revenue), 2) AS gross_revenue,
        ROUND(SUM(f.discount_amount) / NULLIF(SUM(f.gross_revenue), 0) * 100.0, 1) AS discount_pct,
        ROUND(SUM(f.contribution_margin), 2) AS contribution_margin,
        ROUND(SUM(f.contribution_margin) / NULLIF(SUM(f.gross_revenue), 0) * 100.0, 1) AS margin_pct
    FROM gold.fact_sales f
    {joins_sql}
    {where_sql}
    GROUP BY {group_cols}
    """
    gen_sql = f"{base_sql} ORDER BY contribution_margin DESC LIMIT {limit}"
    dest_sql = (
        f"{base_sql} HAVING SUM(f.gross_revenue) > 0 "
        f"ORDER BY margin_pct ASC, gross_revenue DESC LIMIT {limit}"
    )
    return repo.query(gen_sql, params), repo.query(dest_sql, params)


def query_margin_recovery_potential(
    repo: DataRepository,
    *,
    where_sql: str,
    params: list[Any],
    joins: list[str],
    target_rate: float = 0.22,
) -> tuple[int, float]:
    """Calcula quantidade de clientes com margem abaixo do teto e potencial de recuperação."""
    joins_copy = list(joins)
    if "JOIN gold.dim_customer c ON f.customer_id = c.customer_id" not in joins_copy:
        joins_copy.append("JOIN gold.dim_customer c ON f.customer_id = c.customer_id")
    sql = f"""
    WITH cust AS (
        SELECT c.customer_id, SUM(f.gross_revenue) AS rev,
               SUM(f.contribution_margin) / NULLIF(SUM(f.gross_revenue), 0) AS rate
        FROM gold.fact_sales f
        {" ".join(joins_copy)}
        {where_sql}
        GROUP BY c.customer_id
        HAVING SUM(f.contribution_margin) / NULLIF(SUM(f.gross_revenue), 0) < {target_rate}
    )
    SELECT COUNT(*) AS low_margin_count,
           ROUND(COALESCE(SUM(rev * ({target_rate} - rate)), 0), 2) AS potential_recovery_brl
    FROM cust
    """
    df = repo.query(sql, params)
    if df.empty:
        return 0, 0.0
    return int(df["low_margin_count"].iloc[0]), float(df["potential_recovery_brl"].iloc[0])
