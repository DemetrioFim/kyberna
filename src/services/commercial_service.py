from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

import pandas as pd

from src.core.logging import get_logger
from src.core.types import ScenarioId
from src.db.repository import DataRepository
from src.services.commercial_queries import (
    query_commercial_kpis_data,
    query_cycle_health_funnel,
    query_priority_risk_customers,
    query_rep_performance_data,
    query_rfm_summary_data,
    query_top_white_space_deals,
    query_white_space_matrix_data,
)
from src.services.dto import (
    CommercialKpisDTO,
    CommercialPageDTO,
)
from src.services.executive_service import get_top_margin_drivers
from src.services.white_space_queries import (
    query_apriori_rules_data,
    query_white_space_coverage_kpis,
)
from src.ui.formatting import format_brl

logger = get_logger(__name__)


def build_commercial_headline(kpis: CommercialKpisDTO) -> tuple[str, str]:
    """Gera a manchete executiva dinâmica e contextualizada para o Radar Comercial."""
    rev_risk_str = format_brl(kpis.annual_revenue_at_risk_brl, compact=True, decimals=1)
    ws_rev_str = format_brl(kpis.white_space_potential_revenue_brl, compact=True, decimals=1)

    if kpis.at_risk_customers > 0:
        title = (
            f"Radar Comercial · Radar de Churn: {kpis.at_risk_customers} clientes fora do ciclo "
            f"com {rev_risk_str} em risco imediato"
        )
        text = (
            f"Atualmente, <b>{kpis.at_risk_customers_pct:.1f}%</b> da base ativa ultrapassou "
            f"seu ciclo de recompra (delay > 1.5). Identificamos <b>{kpis.vampire_customers_count} "
            f"clientes com margem comprimida</b> (< 15%) e potencial de <b>{ws_rev_str}</b> em cross-sell "
            f"(White Space) pronto para abordagem imediata pelos representantes responsáveis."
        )
    else:
        title = "Radar Comercial: Carteira de Clientes no Ciclo Saudável"
        text = (
            f"Nenhum cliente crítico em atraso detectado no recorte selecionado. Oportunidade de "
            f"<b>{ws_rev_str}</b> em expansão de mix (White Space) disponível para alavancar faturamento."
        )

    return title, text


def build_commercial_prescription(
    kpis: CommercialKpisDTO,
    priority_df: pd.DataFrame,
) -> tuple[str, str, float | None]:
    """Elabora a recomendação prescritiva acionável quantificada em R$ para a equipe comercial."""
    if priority_df.empty:
        return (
            "Manutenção do Plano de Visitas e Abordagem de Expansão",
            "<p>A carteira analisada apresenta estabilidade de recompra. Mantenha o cronograma regular "
            "de atendimento e priorize as ofertas de White Space mapeadas para cada segmento.</p>",
            None,
        )

    top_count = min(10, len(priority_df))
    top_revenue_at_risk = float(priority_df.head(top_count)["annual_revenue_at_risk"].sum())
    top_margin_at_risk = float(priority_df.head(top_count)["annual_margin_at_risk"].sum())
    top_ws_potential = float(priority_df.head(top_count)["top_opportunity_brl"].sum())

    title = "Plano Tático de Ação: Reativação e Oferta de Sortimento"
    html = (
        f"<p>Priorize a abordagem imediata dos <b>Top {top_count} lojistas</b> com maior valor exposto. "
        f"Este grupo isolado responde por <b>{format_brl(top_revenue_at_risk)}</b> de receita anualizada "
        f"e <b>{format_brl(top_margin_at_risk)}</b> de margem de contribuição líquida.</p>"
        "<ul style='margin-left: 20px; line-height: 1.6;'>"
        "<li><b>Ação de Reativação Imediata:</b> Acione os RCAs responsáveis para contato presencial ou "
        "WhatsApp com oferta especial de frete ou condição nos clientes com atraso superior a 50% "
        "(delay ratio > 1.5).</li>"
        "<li><b>Abordagem de Mix (White Space):</b> Em cada contato de resgate, utilize "
        "o argumento prescrito e o SKU âncora recomendado, capturando até "
        f"<b>{format_brl(top_ws_potential)}</b> em pedidos imediatos de reposição.</li>"
        "<li><b>Gestão de Alçada para 'Clientes Vampiros':</b> Travar concessão de descontos nos clientes "
        "de alto volume e margem inferior a 15%, vinculando a comissão à rentabilidade líquida da venda.</li>"
        "</ul>"
    )
    return title, html, top_margin_at_risk


def _query_vampire_customers(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    sales_reps: Sequence[str] = (),
) -> pd.DataFrame:
    """Retorna exatamente as contas Vampiro (<15% MC e > R$ 15k faturamento) conciliadas com o KPI."""
    clauses = ["f.scenario_id = ?"]
    params: list[object] = [scenario_id]
    if regiao != "Todas":
        clauses.append("c.region = ?")
        params.append(regiao)
    if uf != "Todas":
        clauses.append("c.state = ?")
        params.append(uf)
    if sales_reps:
        rep_list = list(sales_reps)
        ph = ", ".join(["?"] * len(rep_list))
        clauses.append(f"(c.sales_rep_id IN ({ph}) OR r.name IN ({ph}))")
        params.extend(rep_list)
        params.extend(rep_list)

    sql = f"""
    SELECT
        COALESCE(c.trade_name, c.company_name) AS customer_name,
        c.state,
        r.name AS sales_rep_name,
        ROUND(SUM(f.gross_revenue), 2) AS gross_revenue,
        ROUND(SUM(f.discount_amount) / NULLIF(SUM(f.gross_revenue), 0) * 100.0, 2) AS avg_discount_pct,
        ROUND(SUM(f.contribution_margin), 2) AS contribution_margin,
        ROUND(SUM(f.contribution_margin) / NULLIF(SUM(f.gross_revenue), 0) * 100.0, 2) AS margin_pct
    FROM gold.fact_sales f
    JOIN gold.dim_customer c ON f.customer_id = c.customer_id
    LEFT JOIN gold.dim_sales_rep r ON c.sales_rep_id = r.sales_rep_id
    WHERE {" AND ".join(clauses)}
    GROUP BY c.customer_id, c.trade_name, c.company_name, c.state, r.name
    HAVING SUM(f.gross_revenue) > 15000
       AND (SUM(f.contribution_margin) / NULLIF(SUM(f.gross_revenue), 0) * 100.0) < 15.0
    ORDER BY margin_pct ASC, gross_revenue DESC
    """
    try:
        return repo.query(sql, params=params)
    except Exception:
        return pd.DataFrame()


def build_commercial_dashboard(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    families: Sequence[str] = (),
    sales_reps: Sequence[str] = (),
    risk_status: str = "Todos",
    rfm_segment: str = "Todos",
    quadrant: str = "Todos",
    start_date_key: int | None = None,
    end_date_key: int | None = None,
    as_of_date_label: str = "31/12/2024",
) -> CommercialPageDTO:
    """Orquestra as consultas analíticas e consolida o payload consumido pela Página 3 — Justiça."""
    logger.info(
        "Construindo dashboard de Justiça Comercial para '%s' (regiao=%s, uf=%s, risk=%s, rfm=%s)...",
        scenario_id,
        regiao,
        uf,
        risk_status,
        rfm_segment,
    )

    kpis_raw = query_commercial_kpis_data(
        repo,
        scenario_id,
        regiao=regiao,
        uf=uf,
        sales_reps=sales_reps,
        risk_status=risk_status,
        rfm_segment=rfm_segment,
    )
    ws_cov = query_white_space_coverage_kpis(
        repo,
        scenario_id,
        regiao=regiao,
        uf=uf,
        sales_reps=sales_reps,
        families=families,
    )
    apriori_rules_df = query_apriori_rules_data(repo, scenario_id, families=families)
    apriori_stats: dict[str, float | int] = {
        "apriori_rules_count": 0,
        "apriori_max_lift": 0.0,
        "apriori_avg_confidence_pct": 0.0,
        "apriori_avg_support_pct": 0.0,
    }
    if not apriori_rules_df.empty:
        sku_sub = apriori_rules_df[apriori_rules_df["rule_level"] == "sku"]
        stat_df = sku_sub if not sku_sub.empty else apriori_rules_df
        apriori_stats = {
            "apriori_rules_count": len(apriori_rules_df),
            "apriori_max_lift": round(float(apriori_rules_df["lift"].max()), 2),
            "apriori_avg_confidence_pct": round(float(stat_df["confidence_pct"].mean()), 1),
            "apriori_avg_support_pct": round(float(stat_df["support_pct"].mean()), 2),
        }
    kpis = CommercialKpisDTO(**kpis_raw, **ws_cov, **apriori_stats)

    priority_df = query_priority_risk_customers(
        repo,
        scenario_id,
        regiao=regiao,
        uf=uf,
        sales_reps=sales_reps,
        risk_status=risk_status,
        rfm_segment=rfm_segment,
    )
    rfm_df = query_rfm_summary_data(
        repo,
        scenario_id,
        regiao=regiao,
        uf=uf,
        sales_reps=sales_reps,
    )
    ws_matrix_df = query_white_space_matrix_data(
        repo,
        scenario_id,
        regiao=regiao,
        uf=uf,
        sales_reps=sales_reps,
        families=families,
    )
    top_ws_deals_df = query_top_white_space_deals(
        repo,
        scenario_id,
        regiao=regiao,
        uf=uf,
        sales_reps=sales_reps,
        rfm_segment=rfm_segment,
        families=families,
    )
    cycle_funnel_df = query_cycle_health_funnel(
        repo,
        scenario_id,
        regiao=regiao,
        uf=uf,
        sales_reps=sales_reps,
        rfm_segment=rfm_segment,
    )
    rep_df = query_rep_performance_data(
        repo,
        scenario_id,
        regiao=regiao,
        uf=uf,
        sales_reps=sales_reps,
        quadrant=quadrant,
    )

    # 4 Dimensões de Campeões vs. Vampiros
    dims: tuple[Literal["family", "product", "customer", "sales_rep"], ...] = (
        "family",
        "product",
        "customer",
        "sales_rep",
    )
    drvs = [
        get_top_margin_drivers(
            repo,
            scenario_id,
            by=d,
            regiao=regiao,
            uf=uf,
            families=families,
            sales_reps=sales_reps,
            start_date_key=start_date_key,
            end_date_key=end_date_key,
            limit=10,
        )
        for d in dims
    ]
    (top_gen_f, top_dest_f), (top_gen_p, top_dest_p) = drvs[0], drvs[1]
    (top_gen_c, top_dest_c), (top_gen_r, top_dest_r) = drvs[2], drvs[3]

    vampires_df = _query_vampire_customers(
        repo,
        scenario_id,
        regiao=regiao,
        uf=uf,
        sales_reps=sales_reps,
    )
    headline_title, headline_text = build_commercial_headline(kpis)
    prescription_title, prescription_html, impact_brl = build_commercial_prescription(kpis, priority_df)

    return CommercialPageDTO(
        scenario_id=scenario_id,
        kpis=kpis,
        headline_title=headline_title,
        headline_text=headline_text,
        priority_risk_df=priority_df,
        rfm_summary_df=rfm_df,
        white_space_matrix_df=ws_matrix_df,
        rep_performance_df=rep_df,
        apriori_rules_df=apriori_rules_df,
        cycle_funnel_df=cycle_funnel_df,
        top_white_space_deals_df=top_ws_deals_df,
        champions_df=top_gen_c,
        vampires_df=vampires_df,
        top_family_generators_df=top_gen_f,
        top_family_destroyers_df=top_dest_f,
        top_product_generators_df=top_gen_p,
        top_product_destroyers_df=top_dest_p,
        top_customer_generators_df=top_gen_c,
        top_customer_destroyers_df=top_dest_c,
        top_rep_generators_df=top_gen_r,
        top_rep_destroyers_df=top_dest_r,
        prescription_title=prescription_title,
        prescription_html=prescription_html,
        prescription_impact_brl=impact_brl,
        as_of_date_label=as_of_date_label,
    )
