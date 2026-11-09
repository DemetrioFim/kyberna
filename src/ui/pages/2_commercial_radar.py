from __future__ import annotations

import streamlit as st

from src.core.scenarios import load_scenario_config
from src.ui.cache import cached_commercial_dashboard
from src.ui.components.justice_sections import (
    render_champions_vampires_section,
    render_justice_banner,
    render_justice_headline,
    render_justice_kpi_cards,
    render_portfolio_health_section,
    render_sales_rep_justice_section,
    render_white_space_opportunities_section,
)
from src.ui.components.prescription import (
    render_prescription_box,
    section_header,
)
from src.ui.state import get_app_state


def render_page() -> None:
    """Entrypoint da Página 3 — Justiça (Rentabilidade Comercial, Margem & Carteira / Radar Comercial)."""
    state = get_app_state()
    scenario_cfg = load_scenario_config(state.scenario_id)
    labels = scenario_cfg.labels
    theme_mode = state.theme_mode

    # Título Virtus e Radar Comercial
    st.title("3. Justiça — Rentabilidade Comercial, Margem & Carteira")
    st.caption(
        f"A troca de valor entre a empresa, seus clientes e sua força de vendas está justa e saudável? "
        f"Diagnóstico de margem líquida, Radar Comercial de churn e sortimento ausente: "
        f"**{scenario_cfg.display_name}** ({scenario_cfg.company_profile})."
    )

    # Consulta com cache do Streamlit
    dto = cached_commercial_dashboard(
        state.scenario_id,
        regiao=state.regiao,
        uf=state.uf,
        families=tuple(state.families),
        sales_reps=tuple(state.sales_reps),
        risk_status="Todos",
        rfm_segment="Todos",
        quadrant="Todos",
    )

    # 1. Banner Filosófico e Manchete Executiva da Justiça
    render_justice_banner(dto)
    render_justice_headline(dto)

    # 2. Faixa de KPI Cards Virtus (5 Indicadores-Chave)
    render_justice_kpi_cards(dto, labels.customer_plural)

    # 3. Bloco 1 — Matriz de Rentabilidade: Campeões vs. Vampiros (4 Abas)
    render_champions_vampires_section(dto, labels)

    # 4. Bloco 2 — Justiça da Força de Vendas (Quadrante + Tabela de Desempenho dos RCAs)
    render_sales_rep_justice_section(
        dto,
        rep_label=labels.sales_rep,
        show_rep_efficiency=scenario_cfg.capabilities.rep_efficiency,
        theme_mode=theme_mode,
    )

    # 5. Bloco 3 — Saúde da Carteira, Funil do Ciclo e Dispersão de Atraso
    render_portfolio_health_section(
        dto,
        customer_label=labels.customer,
        theme_mode=theme_mode,
    )

    # 6. Bloco 4 — Oportunidades White Space (Cross-Sell com SKU Âncora & Pitch Comercial)
    render_white_space_opportunities_section(
        dto,
        customer_label=labels.customer,
        theme_mode=theme_mode,
    )

    # 7. Prescrição Tática de Justiça e Governança Comercial
    section_header(
        "Prescrição Tática de Governança Comercial e Reativação",
        "Recomendações quantificadas em R$ para direcionamento imediato da equipe de vendas",
        help_text=(
            "Diretrizes geradas pelo motor analítico priorizando ações de resgate com maior "
            "retorno em margem de contribuição líquida e menor risco de atrito comercial."
        ),
    )
    render_prescription_box(
        title=dto.prescription_title,
        recommendation_html=dto.prescription_html,
        impact_brl=dto.prescription_impact_brl,
        action_hint="Priorize o contato com os lojistas do topo da lista antes do fechamento semanal.",
        help_text="Diretrizes táticas consolidadas com base no valor em risco e oportunidades de cross-sell.",
    )


render_page()
