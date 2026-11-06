from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from src.core.logging import get_logger
from src.core.types import ScenarioId
from src.db.repository import DataRepository
from src.services.commercial_queries import (
    query_commercial_kpis_data,
    query_priority_risk_customers,
    query_rep_performance_data,
    query_rfm_summary_data,
    query_white_space_matrix_data,
)
from src.services.dto import (
    CommercialKpisDTO,
    CommercialPageDTO,
)
from src.ui.formatting import format_brl

logger = get_logger(__name__)


def build_commercial_headline(kpis: CommercialKpisDTO) -> tuple[str, str]:
    """Gera a manchete executiva dinâmica e contextualizada para o Radar Comercial."""
    rev_risk_str = format_brl(kpis.annual_revenue_at_risk_brl, compact=True, decimals=1)
    ws_rev_str = format_brl(kpis.white_space_potential_revenue_brl, compact=True, decimals=1)

    if kpis.at_risk_customers > 0:
        title = (
            f"Radar de Churn: {kpis.at_risk_customers} clientes fora do ciclo "
            f"com {rev_risk_str} em risco imediato"
        )
        text = (
            f"Atualmente, <b>{kpis.at_risk_customers_pct:.1f}%</b> da base ativa de clientes ultrapassou "
            f"seu ciclo histórico de compra (delay ratio > 1.5). Paralelamente, a inteligência de "
            f"recomendações mapeou <b>{ws_rev_str}</b> em potencial de cross-sell (White Space) pronto "
            f"para abordagem imediata pelos representantes responsáveis."
        )
    else:
        title = "Carteira de Clientes no Ciclo Saudável"
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

    title = "Plano Tático de Reativação e Oferta de Sortimento"
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
        "<li><b>Gestão de Alçada:</b> Para representantes no quadrante <i>'Volume sem margem'</i>, "
        "travar concessão de descontos acima da política e vincular a comissão à rentabilidade "
        "líquida da venda.</li>"
        "</ul>"
    )
    return title, html, top_margin_at_risk


def build_commercial_dashboard(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    sales_reps: Sequence[str] = (),
    risk_status: str = "Todos",
    rfm_segment: str = "Todos",
    as_of_date_label: str = "31/12/2024",
) -> CommercialPageDTO:
    """Orquestra as consultas analíticas e consolida o payload puro consumido pela Tela 2.

    Args:
        repo: Repositório de dados ativo (DuckDB ou Azure SQL).
        scenario_id: Identificador do cenário ('c1_toys', etc.).
        regiao: Filtro de macrorregião geográfica.
        uf: Filtro de estado/UF.
        sales_reps: Lista de representantes filtrados.
        risk_status: Filtro de status de churn ('Todos', 'Em Risco Imediato', etc.).
        rfm_segment: Filtro de segmento RFM ('Todos', 'Campeões', etc.).
        as_of_date_label: Rótulo da data de corte para exibição.

    Returns:
        CommercialPageDTO completo e validado.
    """
    logger.info(
        "Construindo dashboard comercial para '%s' (regiao=%s, uf=%s, risk=%s, rfm=%s)...",
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
    kpis = CommercialKpisDTO(**kpis_raw)

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
    )

    rep_df = query_rep_performance_data(
        repo,
        scenario_id,
        regiao=regiao,
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
        prescription_title=prescription_title,
        prescription_html=prescription_html,
        prescription_impact_brl=impact_brl,
        as_of_date_label=as_of_date_label,
    )
