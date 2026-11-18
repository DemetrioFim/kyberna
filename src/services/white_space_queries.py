from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pandas as pd

from src.core.types import ScenarioId
from src.db.repository import DataRepository


def _build_ws_filter_clauses(
    scenario_id: ScenarioId,
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    sales_reps: Sequence[str] = (),
    rfm_segment: str = "Todos",
    families: Sequence[str] = (),
    include_rfm: bool = True,
    include_families: bool = True,
) -> tuple[str, list[Any]]:
    """Constrói cláusulas WHERE e parâmetros compartilhados para consultas White Space."""
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
    if include_rfm and rfm_segment != "Todos":
        clauses.append("rfm.rfm_segment = ?")
        params.append(rfm_segment)
    if include_families and families:
        fam_list = list(families)
        placeholders = ", ".join(["?"] * len(fam_list))
        clauses.append(f"ws.recommended_family IN ({placeholders})")
        params.extend(fam_list)

    return f"WHERE {' AND '.join(clauses)}", params


def query_apriori_rules_data(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    families: Sequence[str] = (),
) -> pd.DataFrame:
    """Consulta regras de associação Apriori persistidas (`family` e `sku`) com Suporte, Confiança e Lift."""
    clauses: list[str] = ["scenario_id = ?"]
    params: list[Any] = [scenario_id]
    if families:
        fam_list = list(families)
        placeholders = ", ".join(["?"] * len(fam_list))
        clauses.append(f"(antecedent_family IN ({placeholders}) OR consequent_family IN ({placeholders}))")
        params.extend(fam_list)
        params.extend(fam_list)

    sql = f"""
    SELECT
        rule_level,
        antecedent_id,
        antecedent_name,
        antecedent_family,
        consequent_id,
        consequent_name,
        consequent_family,
        pair_baskets,
        total_baskets,
        ROUND(support * 100.0, 2) AS support_pct,
        ROUND(confidence * 100.0, 2) AS confidence_pct,
        ROUND(lift, 2) AS lift,
        ROUND(leverage, 4) AS leverage,
        antecedent_name || ' → ' || consequent_name AS rule_label
    FROM gold.mart_apriori_rules
    WHERE {" AND ".join(clauses)}
    ORDER BY lift DESC, confidence_pct DESC, support_pct DESC
    """
    try:
        return repo.query(sql, params)
    except Exception:
        return pd.DataFrame(
            columns=[
                "rule_level",
                "antecedent_id",
                "antecedent_name",
                "antecedent_family",
                "consequent_id",
                "consequent_name",
                "consequent_family",
                "pair_baskets",
                "total_baskets",
                "support_pct",
                "confidence_pct",
                "lift",
                "leverage",
                "rule_label",
            ]
        )


def query_white_space_coverage_kpis(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    sales_reps: Sequence[str] = (),
    families: Sequence[str] = (),
) -> dict[str, float | int]:
    """Calcula alcance real de lojas elegíveis, total de ofertas e mix médio sem teto LIMIT 50."""
    where_sql, params = _build_ws_filter_clauses(
        scenario_id,
        regiao=regiao,
        uf=uf,
        sales_reps=sales_reps,
        families=families,
        include_rfm=False,
    )
    ws_sql = f"""
    SELECT
        COUNT(DISTINCT ws.customer_id)::INTEGER AS eligible_customers,
        COUNT(*)::INTEGER AS total_offers
    FROM gold.mart_white_space ws
    JOIN gold.dim_customer c ON ws.customer_id = c.customer_id
    LEFT JOIN gold.dim_sales_rep r ON c.sales_rep_id = r.sales_rep_id
    {where_sql}
    """
    ws_df = repo.query(ws_sql, params)
    eligible = int(ws_df["eligible_customers"].iloc[0]) if not ws_df.empty else 0
    offers = int(ws_df["total_offers"].iloc[0]) if not ws_df.empty else 0

    mix_clauses: list[str] = ["f.scenario_id = ?"]
    mix_params: list[Any] = [scenario_id]
    if regiao != "Todas":
        mix_clauses.append("c.region = ?")
        mix_params.append(regiao)
    if uf != "Todas":
        mix_clauses.append("c.state = ?")
        mix_params.append(uf)
    if sales_reps:
        rep_list = list(sales_reps)
        placeholders = ", ".join(["?"] * len(rep_list))
        mix_clauses.append(f"(c.sales_rep_id IN ({placeholders}) OR r.name IN ({placeholders}))")
        mix_params.extend(rep_list)
        mix_params.extend(rep_list)

    mix_sql = f"""
    WITH cust_fams AS (
        SELECT
            f.customer_id,
            COUNT(DISTINCT p.family) AS fam_cnt
        FROM gold.fact_sales f
        JOIN gold.dim_product p ON f.product_id = p.product_id
        JOIN gold.dim_customer c ON f.customer_id = c.customer_id
        LEFT JOIN gold.dim_sales_rep r ON c.sales_rep_id = r.sales_rep_id
        WHERE {" AND ".join(mix_clauses)}
        GROUP BY f.customer_id
    )
    SELECT
        ROUND(COALESCE(AVG(fam_cnt), 0.0), 1) AS avg_families_per_customer,
        (
            SELECT COUNT(DISTINCT p.family)::INTEGER
            FROM gold.fact_sales f2
            JOIN gold.dim_product p ON f2.product_id = p.product_id
            WHERE f2.scenario_id = ?
        ) AS total_fams
    FROM cust_fams
    """
    mix_df = repo.query(mix_sql, [*mix_params, scenario_id])
    avg_fams = float(mix_df["avg_families_per_customer"].iloc[0]) if not mix_df.empty else 0.0
    total_fams = int(mix_df["total_fams"].iloc[0]) if not mix_df.empty else 7

    return {
        "white_space_eligible_customers": eligible,
        "white_space_total_offers": offers,
        "avg_families_per_customer": avg_fams,
        "total_catalog_families": max(total_fams, 1),
    }


def query_white_space_matrix_data(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    sales_reps: Sequence[str] = (),
    families: Sequence[str] = (),
) -> pd.DataFrame:
    """Consulta oportunidades White Space por Família x Segmento RFM com métricas Apriori médias."""
    where_sql, params = _build_ws_filter_clauses(
        scenario_id,
        regiao=regiao,
        uf=uf,
        sales_reps=sales_reps,
        families=families,
        include_rfm=False,
    )
    sql = f"""
    SELECT
        ws.recommended_family,
        COALESCE(rfm.rfm_segment, 'Outros') AS rfm_segment,
        COUNT(DISTINCT ws.customer_id)::INTEGER AS opportunities_count,
        ROUND(SUM(ws.potential_revenue_brl), 2) AS potential_revenue_brl,
        ROUND(SUM(ws.potential_margin_brl), 2) AS potential_margin_brl,
        ROUND(COALESCE(AVG(ws.apriori_confidence), 0.0) * 100.0, 1) AS avg_confidence_pct,
        ROUND(COALESCE(AVG(ws.apriori_lift), 1.0), 2) AS avg_lift
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
    limit: int = 200,
) -> pd.DataFrame:
    """Consulta oportunidades de Cross-Sell CNPJ a CNPJ com Segmento RFM, SKU Âncora e Apriori reais."""
    where_sql, params = _build_ws_filter_clauses(
        scenario_id,
        regiao=regiao,
        uf=uf,
        sales_reps=sales_reps,
        rfm_segment=rfm_segment,
        families=families,
    )
    sql = f"""
    SELECT
        c.customer_id,
        COALESCE(c.trade_name, c.company_name) AS customer_name,
        c.state,
        c.city,
        r.name AS sales_rep_name,
        COALESCE(rfm.rfm_segment, 'Regular') AS rfm_segment,
        ws.recommended_family,
        COALESCE(ws.best_rule_antecedent, ws.recommended_family) AS best_rule_antecedent,
        ws.recommended_anchor_sku AS recommended_top_sku,
        COALESCE(c.segment, 'Lojista') || ' (Perfil ' || c.size || ')' AS anchor_sku_name,
        ROUND(COALESCE(ws.apriori_support, 0.0) * 100.0, 2) AS apriori_support_pct,
        ROUND(COALESCE(ws.apriori_confidence, 0.0) * 100.0, 2) AS apriori_confidence_pct,
        ROUND(COALESCE(ws.apriori_lift, 1.0), 2) AS apriori_lift,
        ROUND(COALESCE(ws.apriori_lift, 1.0), 2) AS affinity_lift,
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
