from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pandas as pd

from src.core.types import ScenarioId
from src.db.repository import DataRepository


def query_white_space_matrix_data(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    sales_reps: Sequence[str] = (),
    families: Sequence[str] = (),
) -> pd.DataFrame:
    """Consulta a distribuição de oportunidades White Space por Família Recomendada e Segmento RFM."""
    clauses: list[str] = ["ws.scenario_id = ?"]
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
    if families:
        fam_list = list(families)
        placeholders = ", ".join(["?"] * len(fam_list))
        clauses.append(f"ws.recommended_family IN ({placeholders})")
        params.extend(fam_list)

    where_sql = f"WHERE {' AND '.join(clauses)}"
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
    {where_sql}
    GROUP BY ws.recommended_family, rfm.rfm_segment
    ORDER BY potential_revenue_brl DESC
    """
    return repo.query(sql, params)


def query_top_white_space_deals(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    sales_reps: Sequence[str] = (),
    rfm_segment: str = "Todos",
    families: Sequence[str] = (),
    limit: int = 50,
) -> pd.DataFrame:
    """Consulta as maiores oportunidades de Cross-Sell CNPJ a CNPJ com SKU Âncora e Pitch acionável."""
    clauses: list[str] = ["ws.scenario_id = ?"]
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
    if rfm_segment != "Todos":
        clauses.append("rfm.rfm_segment = ?")
        params.append(rfm_segment)
    if families:
        fam_list = list(families)
        placeholders = ", ".join(["?"] * len(fam_list))
        clauses.append(f"ws.recommended_family IN ({placeholders})")
        params.extend(fam_list)

    where_sql = f"WHERE {' AND '.join(clauses)}"
    sql = f"""
    SELECT
        c.customer_id,
        COALESCE(c.trade_name, c.company_name) AS customer_name,
        c.state,
        c.city,
        r.name AS sales_rep_name,
        COALESCE(rfm.rfm_segment, 'Regular') AS rfm_segment,
        ws.recommended_family,
        ws.recommended_family || ' - Sortimento A' AS recommended_top_sku,
        COALESCE(c.segment, 'Lojista') || ' (Perfil ' || c.size || ')' AS anchor_sku_name,
        ROUND(COALESCE(ws.item_affinity_score * 1.5, 1.2), 2) AS affinity_lift,
        ROUND(ws.potential_revenue_brl, 2) AS potential_revenue_brl,
        ROUND(ws.potential_margin_brl, 2) AS potential_margin_brl,
        ws.action_pitch,
        COALESCE(c.whatsapp, '') AS whatsapp
    FROM gold.mart_white_space ws
    JOIN gold.dim_customer c ON ws.customer_id = c.customer_id
    LEFT JOIN gold.dim_sales_rep r ON c.sales_rep_id = r.sales_rep_id
    LEFT JOIN gold.mart_rfm rfm
        ON c.customer_id = rfm.customer_id AND rfm.scenario_id = ws.scenario_id
    {where_sql}
    ORDER BY ws.potential_revenue_brl DESC, ws.potential_margin_brl DESC
    LIMIT {limit}
    """
    return repo.query(sql, params)
