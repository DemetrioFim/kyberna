from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pandas as pd

from src.core.logging import get_logger
from src.core.types import ScenarioId
from src.db.repository import DataRepository
from src.services.commercial_rep_queries import query_rep_performance_data
from src.services.commercial_rfm_queries import (
    build_commercial_filter_clauses,
    build_scoped_sales_cte,
    query_cycle_health_funnel,
    query_rfm_summary_data,
    query_silent_churn_customers,
)
from src.services.white_space_queries import (
    query_top_white_space_deals,
    query_white_space_matrix_data,
)

__all__ = [
    "build_commercial_filter_clauses",
    "query_commercial_kpis_data",
    "query_cycle_health_funnel",
    "query_priority_risk_customers",
    "query_rep_performance_data",
    "query_rfm_summary_data",
    "query_silent_churn_customers",
    "query_top_white_space_deals",
    "query_white_space_matrix_data",
]

logger = get_logger(__name__)


def query_commercial_kpis_data(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    families: Sequence[str] = (),
    sales_reps: Sequence[str] = (),
    risk_status: str = "Todos",
    rfm_segment: str = "Todos",
    start_date_key: int | None = None,
    end_date_key: int | None = None,
) -> dict[str, Any]:
    """Consulta os KPIs agregados de clientes, risco de churn e potencial White Space."""
    where_sql, params = build_commercial_filter_clauses(
        scenario_id,
        prefix="cr",
        regiao=regiao,
        uf=uf,
        sales_reps=sales_reps,
        risk_status=risk_status,
        rfm_segment=rfm_segment,
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
        cte_prefix = f"WITH {scoped_cte},"
        sales_join = "LEFT JOIN scoped_sales ss ON c.customer_id = ss.customer_id"
        rev_expr = "COALESCE(ss.gross_revenue, 0.0) AS gross_revenue"
        margin_expr = "COALESCE(ss.contribution_margin, 0.0) AS contribution_margin"
    else:
        scoped_params = []
        cte_prefix = "WITH"
        sales_join = ""
        rev_expr = "COALESCE(rfm.gross_revenue, 0.0) AS gross_revenue"
        margin_expr = "COALESCE(rfm.contribution_margin, 0.0) AS contribution_margin"

    ws_clauses = ["ws.scenario_id = ?"]
    ws_params: list[Any] = [scenario_id]
    if families:
        fam_list = list(families)
        ph = ", ".join(["?"] * len(fam_list))
        ws_clauses.append(f"ws.recommended_family IN ({ph})")
        ws_params.extend(fam_list)

    sql = f"""
    {cte_prefix} base_customers AS (
        SELECT
            c.customer_id,
            cr.risk_status,
            COALESCE(cr.annual_revenue_at_risk, 0.0) AS annual_revenue_at_risk,
            COALESCE(cr.annual_margin_at_risk, 0.0) AS annual_margin_at_risk,
            cr.recency_days,
            cr.delay_ratio,
            COALESCE(cr.churn_probability, 0.10) AS churn_probability,
            {rev_expr},
            {margin_expr}
        FROM gold.dim_customer c
        LEFT JOIN gold.dim_sales_rep r ON c.sales_rep_id = r.sales_rep_id
        JOIN gold.mart_customer_risk cr ON c.customer_id = cr.customer_id
        LEFT JOIN gold.mart_rfm rfm
            ON c.customer_id = rfm.customer_id AND rfm.scenario_id = cr.scenario_id
        {sales_join}
        {where_sql}
    ),
    ws_scoped AS (
        SELECT
            ws.customer_id,
            SUM(ws.potential_revenue_brl) AS ws_rev,
            SUM(ws.potential_margin_brl) AS ws_margin
        FROM gold.mart_white_space ws
        JOIN base_customers b ON ws.customer_id = b.customer_id
        WHERE {" AND ".join(ws_clauses)}
        GROUP BY ws.customer_id
    )
    SELECT
        COUNT(b.customer_id)::INTEGER AS total_customers,
        COUNT(CASE WHEN b.delay_ratio <= 1.5 THEN 1 END)::INTEGER AS active_customers,
        COUNT(
            CASE WHEN b.risk_status IN ('Em Risco Imediato', 'Adormecido / Perdido') THEN 1 END
        )::INTEGER AS at_risk_customers,
        ROUND(COALESCE(SUM(
            CASE WHEN b.risk_status IN ('Em Risco Imediato', 'Adormecido / Perdido')
            THEN b.annual_revenue_at_risk END
        ), 0.0), 2) AS annual_revenue_at_risk_brl,
        ROUND(COALESCE(SUM(
            CASE WHEN b.risk_status IN ('Em Risco Imediato', 'Adormecido / Perdido')
            THEN b.annual_margin_at_risk END
        ), 0.0), 2) AS annual_margin_at_risk_brl,
        ROUND(COALESCE(SUM(w.ws_rev), 0.0), 2) AS white_space_potential_revenue_brl,
        ROUND(COALESCE(SUM(w.ws_margin), 0.0), 2) AS white_space_potential_margin_brl,
        COUNT(
            CASE WHEN b.delay_ratio > 1.1 AND b.delay_ratio <= 1.5 THEN 1 END
        )::INTEGER AS attention_customers,
        ROUND(COALESCE(SUM(
            CASE WHEN b.delay_ratio > 1.1 AND b.delay_ratio <= 1.5 THEN b.annual_revenue_at_risk END
        ), 0.0), 2) AS attention_revenue_brl,
        ROUND(
            COALESCE(AVG(b.contribution_margin / GREATEST(b.churn_probability, 0.10)), 0.0), 2
        ) AS avg_ltv_brl,
        COUNT(
            CASE WHEN b.gross_revenue > 15000 AND (b.contribution_margin / NULLIF(b.gross_revenue, 0)) < 0.15
            THEN 1 END
        )::INTEGER AS vampire_customers_count
    FROM base_customers b
    LEFT JOIN ws_scoped w ON b.customer_id = w.customer_id
    """
    df = repo.query(sql, [*scoped_params, *params, *ws_params])
    if df.empty:
        return {
            "total_customers": 0,
            "active_customers": 0,
            "at_risk_customers": 0,
            "at_risk_customers_pct": 0.0,
            "annual_revenue_at_risk_brl": 0.0,
            "annual_margin_at_risk_brl": 0.0,
            "white_space_potential_revenue_brl": 0.0,
            "white_space_potential_margin_brl": 0.0,
            "avg_positivation_pct": 0.0,
            "attention_customers": 0,
            "attention_customers_pct": 0.0,
            "attention_revenue_brl": 0.0,
            "avg_ltv_brl": 0.0,
            "vampire_customers_count": 0,
        }

    row = df.iloc[0]
    total = int(row["total_customers"])
    active = int(row["active_customers"])
    at_risk = int(row["at_risk_customers"])
    att_cnt = int(row["attention_customers"])
    return {
        "total_customers": total,
        "active_customers": active,
        "at_risk_customers": at_risk,
        "at_risk_customers_pct": round((at_risk / max(total, 1)) * 100.0, 1),
        "annual_revenue_at_risk_brl": float(row["annual_revenue_at_risk_brl"]),
        "annual_margin_at_risk_brl": float(row["annual_margin_at_risk_brl"]),
        "white_space_potential_revenue_brl": float(row["white_space_potential_revenue_brl"]),
        "white_space_potential_margin_brl": float(row["white_space_potential_margin_brl"]),
        "avg_positivation_pct": round((active / max(total, 1)) * 100.0, 1),
        "attention_customers": att_cnt,
        "attention_customers_pct": round((att_cnt / max(total, 1)) * 100.0, 1),
        "attention_revenue_brl": float(row["attention_revenue_brl"]),
        "avg_ltv_brl": float(row["avg_ltv_brl"]),
        "vampire_customers_count": int(row["vampire_customers_count"]),
    }


def query_priority_risk_customers(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    families: Sequence[str] = (),
    sales_reps: Sequence[str] = (),
    risk_status: str = "Todos",
    rfm_segment: str = "Todos",
    start_date_key: int | None = None,
    end_date_key: int | None = None,
    limit: int = 150,
) -> pd.DataFrame:
    """Consulta a lista priorizada de clientes para ação comercial ordenada por valor em risco."""
    where_sql, params = build_commercial_filter_clauses(
        scenario_id,
        prefix="cr",
        regiao=regiao,
        uf=uf,
        sales_reps=sales_reps,
        risk_status=risk_status,
        rfm_segment=rfm_segment,
        families=families,
        start_date_key=start_date_key,
        end_date_key=end_date_key,
    )
    sql = f"""
    WITH top_ws AS (
        SELECT
            customer_id,
            recommended_family AS top_opportunity_family,
            potential_revenue_brl AS top_opportunity_brl,
            action_pitch AS top_opportunity_pitch
        FROM gold.mart_white_space
        WHERE scenario_id = ? AND rank_order = 1
    )
    SELECT
        c.customer_id,
        COALESCE(c.trade_name, c.company_name) AS customer_name,
        c.city, c.state, c.region,
        r.name AS sales_rep_name,
        rfm.rfm_segment, cr.risk_status,
        ROUND(cr.delay_ratio, 2) AS delay_ratio,
        cr.recency_days,
        ROUND(cr.expected_cycle_days, 1) AS expected_cycle_days,
        ROUND(COALESCE(cr.annual_revenue_at_risk, 0.0), 2) AS annual_revenue_at_risk,
        ROUND(COALESCE(cr.annual_margin_at_risk, 0.0), 2) AS annual_margin_at_risk,
        COALESCE(ws.top_opportunity_family, 'N/D') AS top_opportunity_family,
        ROUND(COALESCE(ws.top_opportunity_brl, 0.0), 2) AS top_opportunity_brl,
        COALESCE(ws.top_opportunity_pitch, '') AS top_opportunity_pitch,
        COALESCE(c.whatsapp, '') AS whatsapp
    FROM gold.dim_customer c
    LEFT JOIN gold.dim_sales_rep r ON c.sales_rep_id = r.sales_rep_id
    JOIN gold.mart_customer_risk cr ON c.customer_id = cr.customer_id
    LEFT JOIN gold.mart_rfm rfm
        ON c.customer_id = rfm.customer_id AND rfm.scenario_id = cr.scenario_id
    LEFT JOIN top_ws ws ON c.customer_id = ws.customer_id
    {where_sql}
    ORDER BY cr.annual_revenue_at_risk DESC, cr.delay_ratio DESC
    LIMIT {limit}
    """
    return repo.query(sql, [scenario_id, *params])
