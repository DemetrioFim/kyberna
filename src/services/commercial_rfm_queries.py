from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

from src.core.types import ScenarioId
from src.db.repository import DataRepository

__all__ = [
    "build_commercial_filter_clauses",
    "build_scoped_sales_cte",
    "query_cycle_health_funnel",
    "query_rfm_summary_data",
    "query_silent_churn_customers",
]


def build_commercial_filter_clauses(
    scenario_id: ScenarioId,
    *,
    prefix: str = "cr",
    regiao: str = "Todas",
    uf: str = "Todas",
    sales_reps: Sequence[str] = (),
    risk_status: str = "Todos",
    rfm_segment: str = "Todos",
    families: Sequence[str] = (),
    start_date_key: int | None = None,
    end_date_key: int | None = None,
) -> tuple[str, list[Any]]:
    """Constrói a cláusula WHERE e parâmetros para consultas de clientes e inteligência comercial."""
    clauses: list[str] = [f"{prefix}.scenario_id = ?"]
    params: list[Any] = [scenario_id]

    if regiao != "Todas":
        clauses.append("c.region = ?")
        params.append(regiao)
    if uf != "Todas":
        clauses.append("c.state = ?")
        params.append(uf)
    if sales_reps:
        rep_list = list(sales_reps)
        placeholders = ", ".join(["?"] * len(rep_list))
        clauses.append(f"(c.sales_rep_id IN ({placeholders}) OR r.name IN ({placeholders}))")
        params.extend([*rep_list, *rep_list])
    if risk_status != "Todos":
        clauses.append("cr.risk_status = ?")
        params.append(risk_status)
    if rfm_segment != "Todos":
        clauses.append("rfm.rfm_segment = ?")
        params.append(rfm_segment)
    if families or start_date_key is not None or end_date_key is not None:
        fs_clauses = [f"fs_c.scenario_id = {prefix}.scenario_id", "fs_c.customer_id = c.customer_id"]
        fs_join = ""
        if families:
            fam_list = list(families)
            ph = ", ".join(["?"] * len(fam_list))
            fs_join = "JOIN gold.dim_product p_c ON fs_c.product_id = p_c.product_id"
            fs_clauses.append(f"p_c.family IN ({ph})")
            params.extend(fam_list)
        if start_date_key is not None:
            fs_clauses.append("fs_c.date_key >= ?")
            params.append(start_date_key)
        if end_date_key is not None:
            fs_clauses.append("fs_c.date_key <= ?")
            params.append(end_date_key)
        clauses.append(
            f"EXISTS (SELECT 1 FROM gold.fact_sales fs_c {fs_join} WHERE {' AND '.join(fs_clauses)})"
        )

    return f"WHERE {' AND '.join(clauses)}", params


def build_scoped_sales_cte(
    scenario_id: ScenarioId,
    *,
    families: Sequence[str] = (),
    start_date_key: int | None = None,
    end_date_key: int | None = None,
) -> tuple[str, list[Any]]:
    """Constrói CTE agregado de receita/margem filtrada por família e período."""
    clauses = ["f_sc.scenario_id = ?"]
    params: list[Any] = [scenario_id]
    join_sql = ""
    if families:
        fam_list = list(families)
        ph = ", ".join(["?"] * len(fam_list))
        join_sql = "JOIN gold.dim_product p_sc ON f_sc.product_id = p_sc.product_id"
        clauses.append(f"p_sc.family IN ({ph})")
        params.extend(fam_list)
    if start_date_key is not None:
        clauses.append("f_sc.date_key >= ?")
        params.append(start_date_key)
    if end_date_key is not None:
        clauses.append("f_sc.date_key <= ?")
        params.append(end_date_key)
    cte_sql = f"""
    scoped_sales AS (
        SELECT
            f_sc.customer_id,
            ROUND(COALESCE(SUM(f_sc.gross_revenue), 0.0), 2) AS gross_revenue,
            ROUND(COALESCE(SUM(f_sc.contribution_margin), 0.0), 2) AS contribution_margin,
            COUNT(DISTINCT f_sc.order_id)::INTEGER AS orders_count
        FROM gold.fact_sales f_sc
        {join_sql}
        WHERE {" AND ".join(clauses)}
        GROUP BY f_sc.customer_id
    )"""
    return cte_sql, params


def query_cycle_health_funnel(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    families: Sequence[str] = (),
    sales_reps: Sequence[str] = (),
    rfm_segment: str = "Todos",
    start_date_key: int | None = None,
    end_date_key: int | None = None,
) -> pd.DataFrame:
    """Consulta o funil de saúde do ciclo de recompra dividido em 4 estágios."""
    where_sql, params = build_commercial_filter_clauses(
        scenario_id,
        prefix="cr",
        regiao=regiao,
        uf=uf,
        sales_reps=sales_reps,
        rfm_segment=rfm_segment,
        families=families,
        start_date_key=start_date_key,
        end_date_key=end_date_key,
    )
    sql = f"""
    SELECT
        CASE
            WHEN cr.delay_ratio <= 1.1 THEN '1. No Ciclo'
            WHEN cr.delay_ratio <= 1.5 THEN '2. Atenção'
            WHEN cr.delay_ratio <= 2.5 THEN '3. Em Risco Imediato'
            ELSE '4. Adormecido / Perdido'
        END AS cycle_stage,
        COUNT(c.customer_id)::INTEGER AS customer_count,
        ROUND(COALESCE(SUM(cr.annual_revenue_at_risk), 0.0), 2) AS annual_revenue_brl,
        ROUND(COALESCE(SUM(cr.annual_margin_at_risk), 0.0), 2) AS annual_margin_brl,
        ROUND(COALESCE(AVG(cr.delay_ratio), 1.0), 2) AS avg_delay_ratio
    FROM gold.dim_customer c
    LEFT JOIN gold.dim_sales_rep r ON c.sales_rep_id = r.sales_rep_id
    JOIN gold.mart_customer_risk cr ON c.customer_id = cr.customer_id
    LEFT JOIN gold.mart_rfm rfm
        ON c.customer_id = rfm.customer_id AND rfm.scenario_id = cr.scenario_id
    {where_sql}
    GROUP BY 1
    ORDER BY 1 ASC
    """
    df = repo.query(sql, params)
    if df.empty:
        return pd.DataFrame(
            columns=[
                "cycle_stage",
                "customer_count",
                "customer_share_pct",
                "annual_revenue_brl",
                "annual_margin_brl",
                "avg_delay_ratio",
            ]
        )
    total_c = df["customer_count"].sum()
    df["customer_share_pct"] = np.round((df["customer_count"] / max(total_c, 1)) * 100.0, 1)
    return df


def query_rfm_summary_data(
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
    """Consulta o resumo dos 9 segmentos RFM sob os filtros ativos com LTV médio."""
    where_sql, params = build_commercial_filter_clauses(
        scenario_id,
        prefix="rfm",
        regiao=regiao,
        uf=uf,
        sales_reps=sales_reps,
        families=families,
        start_date_key=start_date_key,
        end_date_key=end_date_key,
    )
    is_sales_scoped = bool(families) or start_date_key is not None or end_date_key is not None
    if is_sales_scoped:
        scoped_cte, scoped_params = build_scoped_sales_cte(
            scenario_id,
            families=families,
            start_date_key=start_date_key,
            end_date_key=end_date_key,
        )
        cte_sql = f"WITH {scoped_cte}"
        sales_join = "LEFT JOIN scoped_sales ss ON c.customer_id = ss.customer_id"
        rev_col = "COALESCE(ss.gross_revenue, 0.0)"
        margin_col = "COALESCE(ss.contribution_margin, 0.0)"
        freq_col = "NULLIF(ss.orders_count, 0)"
    else:
        scoped_params = []
        cte_sql = ""
        sales_join = ""
        rev_col = "rfm.gross_revenue"
        margin_col = "rfm.contribution_margin"
        freq_col = "NULLIF(rfm.frequency, 0)"

    sql = f"""
    {cte_sql}
    SELECT
        rfm.rfm_segment,
        COUNT(c.customer_id)::INTEGER AS customer_count,
        ROUND(SUM({rev_col}), 2) AS gross_revenue,
        ROUND(SUM({margin_col}), 2) AS contribution_margin,
        ROUND(SUM({margin_col}) / NULLIF(SUM({rev_col}), 0) * 100.0, 2) AS margin_pct,
        ROUND(AVG({rev_col} / {freq_col}), 2) AS avg_ticket,
        COUNT(
            CASE WHEN cr.risk_status IN ('Em Risco Imediato', 'Adormecido / Perdido') THEN 1 END
        )::INTEGER AS at_risk_count,
        ROUND(
            COALESCE(AVG({margin_col} / GREATEST(cr.churn_probability, 0.10)), 0.0), 2
        ) AS estimated_ltv_brl
    FROM gold.dim_customer c
    LEFT JOIN gold.dim_sales_rep r ON c.sales_rep_id = r.sales_rep_id
    JOIN gold.mart_rfm rfm ON c.customer_id = rfm.customer_id
    LEFT JOIN gold.mart_customer_risk cr
        ON c.customer_id = cr.customer_id AND cr.scenario_id = rfm.scenario_id
    {sales_join}
    {where_sql}
    GROUP BY rfm.rfm_segment
    ORDER BY gross_revenue DESC
    """
    df = repo.query(sql, [*scoped_params, *params])
    if df.empty:
        return pd.DataFrame()
    total_customers = df["customer_count"].sum()
    df["customer_share_pct"] = np.round((df["customer_count"] / max(total_customers, 1)) * 100.0, 1)
    return df


def query_silent_churn_customers(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    families: Sequence[str] = (),
    sales_reps: Sequence[str] = (),
    limit: int = 50,
) -> pd.DataFrame:
    """Identifica clientes no ciclo (delay <= 1.2) com queda >35% de faturamento ou perda de mix."""
    clauses = ["f.scenario_id = ?"]
    params: list[Any] = [scenario_id]
    if regiao != "Todas":
        clauses.append("c.region = ?")
        params.append(regiao)
    if uf != "Todas":
        clauses.append("c.state = ?")
        params.append(uf)
    if families:
        fam_list = list(families)
        ph = ", ".join(["?"] * len(fam_list))
        clauses.append(f"p.family IN ({ph})")
        params.extend(fam_list)
    if sales_reps:
        rep_list = list(sales_reps)
        ph = ", ".join(["?"] * len(rep_list))
        clauses.append(f"(c.sales_rep_id IN ({ph}) OR r.name IN ({ph}))")
        params.extend([*rep_list, *rep_list])

    sql = f"""
    WITH max_dt AS (
        SELECT COALESCE(MAX(d2.full_date), DATE '2024-12-31') AS mx
        FROM gold.fact_sales f2
        JOIN gold.dim_date d2 ON f2.date_key = d2.date_key
        WHERE f2.scenario_id = ?
    ),
    cust_windows AS (
        SELECT
            f.customer_id,
            ROUND(COALESCE(SUM(CASE
                WHEN d.full_date > (m.mx - INTERVAL 180 DAY) AND d.full_date <= (m.mx - INTERVAL 90 DAY)
                THEN f.gross_revenue ELSE 0.0 END), 0.0), 2) AS rev_prev_90d,
            ROUND(COALESCE(SUM(CASE
                WHEN d.full_date > (m.mx - INTERVAL 90 DAY) AND d.full_date <= m.mx
                THEN f.gross_revenue ELSE 0.0 END), 0.0), 2) AS rev_curr_90d,
            COUNT(DISTINCT CASE
                WHEN d.full_date > (m.mx - INTERVAL 180 DAY) AND d.full_date <= (m.mx - INTERVAL 90 DAY)
                THEN p.family END)::INTEGER AS fams_prev,
            COUNT(DISTINCT CASE
                WHEN d.full_date > (m.mx - INTERVAL 90 DAY) AND d.full_date <= m.mx
                THEN p.family END)::INTEGER AS fams_curr
        FROM gold.fact_sales f
        JOIN gold.dim_date d ON f.date_key = d.date_key
        JOIN gold.dim_product p ON f.product_id = p.product_id
        JOIN gold.dim_customer c ON f.customer_id = c.customer_id
        LEFT JOIN gold.dim_sales_rep r ON c.sales_rep_id = r.sales_rep_id
        CROSS JOIN max_dt m
        WHERE {" AND ".join(clauses)}
        GROUP BY f.customer_id
    )
    SELECT
        c.customer_id,
        COALESCE(c.trade_name, c.company_name) AS customer_name,
        c.state,
        COALESCE(r.name, 'Sem RCA') AS sales_rep_name,
        ROUND(cr.delay_ratio, 2) AS delay_ratio,
        w.rev_prev_90d,
        w.rev_curr_90d,
        ROUND(((w.rev_curr_90d - w.rev_prev_90d) / NULLIF(w.rev_prev_90d, 0.0)) * 100.0, 1) AS drop_pct,
        w.fams_prev,
        w.fams_curr,
        COALESCE(c.whatsapp, '') AS whatsapp
    FROM cust_windows w
    JOIN gold.mart_customer_risk cr ON cr.customer_id = w.customer_id AND cr.scenario_id = ?
    JOIN gold.dim_customer c ON c.customer_id = w.customer_id
    LEFT JOIN gold.dim_sales_rep r ON c.sales_rep_id = r.sales_rep_id
    WHERE cr.delay_ratio <= 1.2
      AND w.rev_prev_90d > 0.0
      AND (
          (w.rev_curr_90d / w.rev_prev_90d) < 0.65
          OR (w.fams_curr < w.fams_prev AND (w.rev_curr_90d / w.rev_prev_90d) <= 0.80)
      )
    ORDER BY (w.rev_prev_90d - w.rev_curr_90d) DESC, w.rev_prev_90d DESC
    LIMIT {limit}
    """
    try:
        return repo.query(sql, [scenario_id, *params, scenario_id])
    except Exception:
        return pd.DataFrame(
            columns=[
                "customer_id",
                "customer_name",
                "state",
                "sales_rep_name",
                "delay_ratio",
                "rev_prev_90d",
                "rev_curr_90d",
                "drop_pct",
                "fams_prev",
                "fams_curr",
                "whatsapp",
            ]
        )
