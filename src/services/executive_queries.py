from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

import pandas as pd

from src.core.logging import get_logger
from src.core.types import ScenarioId
from src.db.repository import DataRepository

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

    where_sql = f"WHERE {' AND '.join(clauses)}"
    return where_sql, params, joins


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
        COALESCE(SUM(f.units), 0) AS total_units
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
    clauses: list[str] = ["scenario_id = ?"]
    params: list[Any] = [scenario_id]

    if regiao != "Todas":
        clauses.append("region = ?")
        params.append(regiao)
    if uf != "Todas":
        clauses.append("state = ?")
        params.append(uf)
    if families:
        fam_list = list(families)
        placeholders = ", ".join(["?"] * len(fam_list))
        clauses.append(f"family IN ({placeholders})")
        params.extend(fam_list)
    if sales_reps:
        rep_list = list(sales_reps)
        placeholders = ", ".join(["?"] * len(rep_list))
        clauses.append(f"sales_rep_id IN ({placeholders})")
        params.extend(rep_list)

    if start_date_key is not None:
        start_ym = f"{start_date_key // 10000:04d}-{((start_date_key % 10000) // 100):02d}"
        clauses.append("year_month >= ?")
        params.append(start_ym)

    if end_date_key is not None:
        end_ym = f"{end_date_key // 10000:04d}-{((end_date_key % 10000) // 100):02d}"
        clauses.append("year_month <= ?")
        params.append(end_ym)

    where_sql = f"WHERE {' AND '.join(clauses)}"
    sql = f"""
    SELECT
        year_month,
        CASE month
            WHEN 1 THEN 'Jan/' || RIGHT(CAST(year AS VARCHAR), 2)
            WHEN 2 THEN 'Fev/' || RIGHT(CAST(year AS VARCHAR), 2)
            WHEN 3 THEN 'Mar/' || RIGHT(CAST(year AS VARCHAR), 2)
            WHEN 4 THEN 'Abr/' || RIGHT(CAST(year AS VARCHAR), 2)
            WHEN 5 THEN 'Mai/' || RIGHT(CAST(year AS VARCHAR), 2)
            WHEN 6 THEN 'Jun/' || RIGHT(CAST(year AS VARCHAR), 2)
            WHEN 7 THEN 'Jul/' || RIGHT(CAST(year AS VARCHAR), 2)
            WHEN 8 THEN 'Ago/' || RIGHT(CAST(year AS VARCHAR), 2)
            WHEN 9 THEN 'Set/' || RIGHT(CAST(year AS VARCHAR), 2)
            WHEN 10 THEN 'Out/' || RIGHT(CAST(year AS VARCHAR), 2)
            WHEN 11 THEN 'Nov/' || RIGHT(CAST(year AS VARCHAR), 2)
            WHEN 12 THEN 'Dez/' || RIGHT(CAST(year AS VARCHAR), 2)
        END AS month_label,
        ROUND(SUM(gross_revenue), 2) AS gross_revenue,
        ROUND(SUM(net_revenue), 2) AS net_revenue,
        ROUND(SUM(contribution_margin), 2) AS contribution_margin,
        ROUND(SUM(contribution_margin) / NULLIF(SUM(gross_revenue), 0) * 100.0, 2) AS margin_pct
    FROM gold.mart_margin_monthly
    {where_sql}
    GROUP BY year_month, year, month
    ORDER BY year_month ASC
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
            WHEN 1 THEN 'Jan/' || RIGHT(CAST(YEAR(d.full_date) AS VARCHAR), 2)
            WHEN 2 THEN 'Fev/' || RIGHT(CAST(YEAR(d.full_date) AS VARCHAR), 2)
            WHEN 3 THEN 'Mar/' || RIGHT(CAST(YEAR(d.full_date) AS VARCHAR), 2)
            WHEN 4 THEN 'Abr/' || RIGHT(CAST(YEAR(d.full_date) AS VARCHAR), 2)
            WHEN 5 THEN 'Mai/' || RIGHT(CAST(YEAR(d.full_date) AS VARCHAR), 2)
            WHEN 6 THEN 'Jun/' || RIGHT(CAST(YEAR(d.full_date) AS VARCHAR), 2)
            WHEN 7 THEN 'Jul/' || RIGHT(CAST(YEAR(d.full_date) AS VARCHAR), 2)
            WHEN 8 THEN 'Ago/' || RIGHT(CAST(YEAR(d.full_date) AS VARCHAR), 2)
            WHEN 9 THEN 'Set/' || RIGHT(CAST(YEAR(d.full_date) AS VARCHAR), 2)
            WHEN 10 THEN 'Out/' || RIGHT(CAST(YEAR(d.full_date) AS VARCHAR), 2)
            WHEN 11 THEN 'Nov/' || RIGHT(CAST(YEAR(d.full_date) AS VARCHAR), 2)
            WHEN 12 THEN 'Dez/' || RIGHT(CAST(YEAR(d.full_date) AS VARCHAR), 2)
        END AS month_label,
        COUNT(DISTINCT f.order_id) AS orders_count,
        COUNT(DISTINCT f.customer_id) AS active_customers,
        COALESCE(SUM(f.units), 0) AS total_units,
        ROUND(COALESCE(SUM(f.boxes), 0), 1) AS total_boxes,
        ROUND(COALESCE(SUM(f.gross_revenue), 0), 2) AS gross_revenue,
        ROUND(COALESCE(SUM(f.discount_amount), 0), 2) AS discount_amount,
        ROUND(
            COALESCE(SUM(f.discount_amount) / NULLIF(SUM(f.gross_revenue), 0) * 100.0, 0), 2
        ) AS avg_discount_pct,
        ROUND(COALESCE(SUM(f.net_revenue), 0), 2) AS net_revenue,
        ROUND(COALESCE(SUM(f.cogs), 0), 2) AS cogs,
        ROUND(COALESCE(SUM(f.commission_amount), 0), 2) AS commission_amount,
        ROUND(COALESCE(SUM(f.freight_amount), 0), 2) AS freight_amount,
        ROUND(COALESCE(SUM(f.contribution_margin), 0), 2) AS contribution_margin,
        ROUND(
            COALESCE(SUM(f.contribution_margin) / NULLIF(SUM(f.gross_revenue), 0) * 100.0, 0), 2
        ) AS margin_pct,
        ROUND(COALESCE(SUM(f.gross_revenue) / NULLIF(COUNT(DISTINCT f.order_id), 0), 0), 2) AS avg_ticket
    FROM gold.fact_sales f
    {joins_sql}
    {where_sql}
    GROUP BY 1, 2
    ORDER BY 1 ASC
    """
    df = repo.query(sql, params)
    if df.empty:
        return df

    # Variação MoM (Mês sobre Mês)
    df["mom_gross_pct"] = (df["gross_revenue"].pct_change() * 100.0).round(1)
    df["mom_margin_pct"] = (df["contribution_margin"].pct_change() * 100.0).round(1)
    return df


def query_top_drivers(
    repo: DataRepository,
    by: Literal["product", "customer"],
    *,
    where_sql: str,
    params: list[Any],
    joins: list[str],
    limit: int = 10,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Consulta Top Geradores e Top Detratores/Menor Margem por Produto ou Cliente."""
    joins_copy = list(joins)
    if by == "product":
        if "JOIN gold.dim_product p ON f.product_id = p.product_id" not in joins_copy:
            joins_copy.append("JOIN gold.dim_product p ON f.product_id = p.product_id")
        joins_sql = " ".join(joins_copy)
        base_sql = f"""
        SELECT
            p.product_name AS name,
            p.family AS secondary_label,
            ROUND(SUM(f.gross_revenue), 2) AS gross_revenue,
            ROUND(SUM(f.discount_amount) / NULLIF(SUM(f.gross_revenue), 0) * 100.0, 1) AS discount_pct,
            ROUND(SUM(f.contribution_margin), 2) AS contribution_margin,
            ROUND(SUM(f.contribution_margin) / NULLIF(SUM(f.gross_revenue), 0) * 100.0, 1) AS margin_pct
        FROM gold.fact_sales f
        {joins_sql}
        {where_sql}
        GROUP BY p.product_name, p.family
        """
    else:
        if "JOIN gold.dim_customer c ON f.customer_id = c.customer_id" not in joins_copy:
            joins_copy.append("JOIN gold.dim_customer c ON f.customer_id = c.customer_id")
        joins_sql = " ".join(joins_copy)
        base_sql = f"""
        SELECT
            c.trade_name AS name,
            c.state || ' - ' || c.segment AS secondary_label,
            ROUND(SUM(f.gross_revenue), 2) AS gross_revenue,
            ROUND(SUM(f.discount_amount) / NULLIF(SUM(f.gross_revenue), 0) * 100.0, 1) AS discount_pct,
            ROUND(SUM(f.contribution_margin), 2) AS contribution_margin,
            ROUND(SUM(f.contribution_margin) / NULLIF(SUM(f.gross_revenue), 0) * 100.0, 1) AS margin_pct
        FROM gold.fact_sales f
        {joins_sql}
        {where_sql}
        GROUP BY c.trade_name, c.state, c.segment
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
    joins_sql = " ".join(joins_copy)

    sql = f"""
    WITH cust AS (
        SELECT
            c.customer_id,
            SUM(f.gross_revenue) AS rev,
            SUM(f.contribution_margin) / NULLIF(SUM(f.gross_revenue), 0) AS rate
        FROM gold.fact_sales f
        {joins_sql}
        {where_sql}
        GROUP BY c.customer_id
        HAVING SUM(f.contribution_margin) / NULLIF(SUM(f.gross_revenue), 0) < {target_rate}
    )
    SELECT
        COUNT(*) AS low_margin_count,
        ROUND(COALESCE(SUM(rev * ({target_rate} - rate)), 0), 2) AS potential_recovery_brl
    FROM cust
    """
    df = repo.query(sql, params)
    if df.empty:
        return 0, 0.0
    return int(df["low_margin_count"].iloc[0]), float(df["potential_recovery_brl"].iloc[0])
