from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

from src.core.logging import get_logger
from src.core.types import ScenarioId
from src.db.repository import DataRepository

logger = get_logger(__name__)


def build_commercial_filter_clauses(
    scenario_id: ScenarioId,
    *,
    prefix: str = "cr",
    regiao: str = "Todas",
    uf: str = "Todas",
    sales_reps: Sequence[str] = (),
    risk_status: str = "Todos",
    rfm_segment: str = "Todos",
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
        params.extend(rep_list)
        params.extend(rep_list)

    if risk_status != "Todos":
        clauses.append("cr.risk_status = ?")
        params.append(risk_status)

    if rfm_segment != "Todos":
        clauses.append("rfm.rfm_segment = ?")
        params.append(rfm_segment)

    return f"WHERE {' AND '.join(clauses)}", params


def query_commercial_kpis_data(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    sales_reps: Sequence[str] = (),
    risk_status: str = "Todos",
    rfm_segment: str = "Todos",
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
    )

    sql = f"""
    WITH base_customers AS (
        SELECT
            c.customer_id,
            cr.risk_status,
            COALESCE(cr.annual_revenue_at_risk, 0.0) AS annual_revenue_at_risk,
            COALESCE(cr.annual_margin_at_risk, 0.0) AS annual_margin_at_risk,
            cr.recency_days,
            cr.delay_ratio
        FROM gold.dim_customer c
        LEFT JOIN gold.dim_sales_rep r ON c.sales_rep_id = r.sales_rep_id
        JOIN gold.mart_customer_risk cr ON c.customer_id = cr.customer_id
        LEFT JOIN gold.mart_rfm rfm
            ON c.customer_id = rfm.customer_id AND rfm.scenario_id = cr.scenario_id
        {where_sql}
    ),
    ws_scoped AS (
        SELECT
            ws.customer_id,
            SUM(ws.potential_revenue_brl) AS ws_rev,
            SUM(ws.potential_margin_brl) AS ws_margin
        FROM gold.mart_white_space ws
        JOIN base_customers b ON ws.customer_id = b.customer_id
        WHERE ws.scenario_id = '{scenario_id}'
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
        ROUND(COALESCE(SUM(w.ws_margin), 0.0), 2) AS white_space_potential_margin_brl
    FROM base_customers b
    LEFT JOIN ws_scoped w ON b.customer_id = w.customer_id
    """
    df = repo.query(sql, params)
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
        }

    row = df.iloc[0]
    total = int(row["total_customers"])
    active = int(row["active_customers"])
    at_risk = int(row["at_risk_customers"])
    at_risk_pct = round((at_risk / max(total, 1)) * 100.0, 1)
    positivation = round((active / max(total, 1)) * 100.0, 1)

    return {
        "total_customers": total,
        "active_customers": active,
        "at_risk_customers": at_risk,
        "at_risk_customers_pct": at_risk_pct,
        "annual_revenue_at_risk_brl": float(row["annual_revenue_at_risk_brl"]),
        "annual_margin_at_risk_brl": float(row["annual_margin_at_risk_brl"]),
        "white_space_potential_revenue_brl": float(row["white_space_potential_revenue_brl"]),
        "white_space_potential_margin_brl": float(row["white_space_potential_margin_brl"]),
        "avg_positivation_pct": positivation,
    }


def query_priority_risk_customers(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    sales_reps: Sequence[str] = (),
    risk_status: str = "Todos",
    rfm_segment: str = "Todos",
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
    )

    sql = f"""
    WITH top_ws AS (
        SELECT
            customer_id,
            recommended_family AS top_opportunity_family,
            potential_revenue_brl AS top_opportunity_brl,
            action_pitch AS top_opportunity_pitch
        FROM gold.mart_white_space
        WHERE scenario_id = '{scenario_id}' AND rank_order = 1
    )
    SELECT
        c.customer_id,
        COALESCE(c.trade_name, c.company_name) AS customer_name,
        c.city,
        c.state,
        c.region,
        r.name AS sales_rep_name,
        rfm.rfm_segment,
        cr.risk_status,
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
    return repo.query(sql, params)


def query_rfm_summary_data(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    sales_reps: Sequence[str] = (),
) -> pd.DataFrame:
    """Consulta o resumo dos 9 segmentos RFM sob os filtros ativos."""
    where_sql, params = build_commercial_filter_clauses(
        scenario_id,
        prefix="rfm",
        regiao=regiao,
        uf=uf,
        sales_reps=sales_reps,
    )

    sql = f"""
    SELECT
        rfm.rfm_segment,
        COUNT(c.customer_id)::INTEGER AS customer_count,
        ROUND(SUM(rfm.gross_revenue), 2) AS gross_revenue,
        ROUND(SUM(rfm.contribution_margin), 2) AS contribution_margin,
        ROUND(
            SUM(rfm.contribution_margin) / NULLIF(SUM(rfm.gross_revenue), 0) * 100.0,
            2
        ) AS margin_pct,
        ROUND(AVG(rfm.gross_revenue / NULLIF(rfm.frequency, 0)), 2) AS avg_ticket,
        COUNT(
            CASE WHEN cr.risk_status IN ('Em Risco Imediato', 'Adormecido / Perdido') THEN 1 END
        )::INTEGER AS at_risk_count
    FROM gold.dim_customer c
    LEFT JOIN gold.dim_sales_rep r ON c.sales_rep_id = r.sales_rep_id
    JOIN gold.mart_rfm rfm ON c.customer_id = rfm.customer_id
    LEFT JOIN gold.mart_customer_risk cr
        ON c.customer_id = cr.customer_id AND cr.scenario_id = rfm.scenario_id
    {where_sql}
    GROUP BY rfm.rfm_segment
    ORDER BY gross_revenue DESC
    """
    df = repo.query(sql, params)
    if df.empty:
        return pd.DataFrame()

    total_customers = df["customer_count"].sum()
    df["customer_share_pct"] = np.round((df["customer_count"] / max(total_customers, 1)) * 100.0, 1)
    return df


def query_white_space_matrix_data(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    sales_reps: Sequence[str] = (),
) -> pd.DataFrame:
    """Consulta a distribuição de oportunidades White Space por Família Recomendada e Segmento RFM."""
    where_sql, params = build_commercial_filter_clauses(
        scenario_id,
        prefix="ws",
        regiao=regiao,
        uf=uf,
        sales_reps=sales_reps,
    )

    sql = f"""
    SELECT
        ws.recommended_family,
        COALESCE(rfm.rfm_segment, 'Outros') AS rfm_segment,
        COUNT(ws.customer_id)::INTEGER AS opportunities_count,
        ROUND(SUM(ws.potential_revenue_brl), 2) AS potential_revenue_brl,
        ROUND(SUM(ws.potential_margin_brl), 2) AS potential_margin_brl
    FROM gold.mart_white_space ws
    JOIN gold.dim_customer c ON ws.customer_id = c.customer_id
    LEFT JOIN gold.dim_sales_rep r ON c.sales_rep_id = r.sales_rep_id
    LEFT JOIN gold.mart_rfm rfm
        ON c.customer_id = rfm.customer_id AND rfm.scenario_id = ws.scenario_id
    LEFT JOIN gold.mart_customer_risk cr
        ON c.customer_id = cr.customer_id AND cr.scenario_id = ws.scenario_id
    {where_sql}
    GROUP BY ws.recommended_family, rfm.rfm_segment
    ORDER BY potential_revenue_brl DESC
    """
    return repo.query(sql, params)


def query_rep_performance_data(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    regiao: str = "Todas",
    sales_reps: Sequence[str] = (),
) -> pd.DataFrame:
    """Consulta a performance dos representantes e quadrantes para exibição cartesiana."""
    clauses = ["rp.scenario_id = ?"]
    params: list[Any] = [scenario_id]

    if regiao != "Todas":
        clauses.append("rp.region = ?")
        params.append(regiao)

    if sales_reps:
        rep_list = list(sales_reps)
        placeholders = ", ".join(["?"] * len(rep_list))
        clauses.append(f"(rp.sales_rep_id IN ({placeholders}) OR rp.sales_rep_name IN ({placeholders}))")
        params.extend(rep_list)
        params.extend(rep_list)

    where_sql = f"WHERE {' AND '.join(clauses)}"

    sql = f"""
    SELECT
        rp.sales_rep_id,
        rp.sales_rep_name,
        rp.region,
        rp.quadrant,
        rp.portfolio_customers,
        rp.active_customers,
        rp.positivation_pct,
        rp.avg_families_per_customer,
        rp.gross_revenue,
        rp.avg_discount_pct,
        rp.contribution_margin,
        rp.margin_pct,
        rp.revenue_at_risk_brl,
        rp.white_space_potential_brl,
        rp.action_prescription
    FROM gold.mart_rep_performance rp
    {where_sql}
    ORDER BY rp.gross_revenue DESC
    """
    return repo.query(sql, params)
