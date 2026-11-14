from __future__ import annotations

import streamlit as st

from src.core.scenarios import load_scenario_config
from src.ui.cache import cached_commercial_dashboard
from src.ui.components.charts import quadrant_scatter
from src.ui.components.commercial_charts import (
    cycle_delay_scatter,
    cycle_health_funnel_chart,
    rfm_treemap,
    white_space_heatmap,
)
from src.ui.components.export_bar import render_commercial_export_bar
from src.ui.components.justice_sections import (
    render_champions_vampires_section,
    render_critical_customers_table,
    render_justice_kpi_cards,
    render_sales_reps_table,
    render_white_space_deals_table,
)
from src.ui.components.prescription import render_cockpit_header, render_prescription_box
from src.ui.state import get_app_state


def _pluralize_rep_label(rep_label: str) -> str:
    """Pluraliza corretamente rótulos de força de vendas com ou sem parênteses."""
    overrides = {
        "RCA (Representante)": "RCAs (Representantes)",
        "Vendedor de Rota": "Vendedores de Rota",
        "Gerente de Loja": "Gerentes de Loja",
        "Balconista / Atendente": "Balconistas / Atendentes",
    }
    if rep_label in overrides:
        return overrides[rep_label]
    if "(" in rep_label:
        base, rest = rep_label.split("(", 1)
        return f"{base.strip()}s ({rest.rstrip(')')}s)"
    return f"{rep_label}s"


def render_page() -> None:
    """Entrypoint da Página 3 — Justiça em formato Cockpit Z-Pattern."""
    state = get_app_state()
    scenario_cfg = load_scenario_config(state.scenario_id)
    labels = scenario_cfg.labels
    rep_plural = _pluralize_rep_label(labels.sales_rep)
    theme_mode = state.theme_mode

    dto = cached_commercial_dashboard(
        state.scenario_id,
        regiao=state.regiao,
        uf=state.uf,
        families=tuple(state.families),
        sales_reps=tuple(state.sales_reps),
        risk_status="Todos",
        rfm_segment="Todos",
        quadrant="Todos",
        period_preset=state.period_preset,
        selected_month=state.selected_month,
    )

    # 1. Faixa 1 — Topo (Status em 5s): Cabeçalho Cockpit unificado + 5 KPI Cards
    render_cockpit_header(
        title="Radar Comercial, Margem & Carteira",
        subtitle="",
        virtue_badge="3. Justiça",
        headline_title=dto.headline_title,
        headline_text=dto.headline_text,
        as_of_date_label=dto.as_of_date_label,
        help_text=(
            "Equilíbrio entre rentabilidade por produto/cliente, mitigação de churn pelo ciclo de recompra, "
            "mérito da força de vendas (RCAs) e potencial de expansão White Space."
        ),
    )
    render_justice_kpi_cards(dto, labels.customer_plural)

    # 2. Faixa 2 — Meio (Diagnóstico Visual em 2 Colunas lado a lado)
    col_diag_left, col_diag_right = st.columns([1.0, 1.0])

    with col_diag_left:
        t_quad, t_champ = st.tabs(
            [
                f"Força de Vendas ({rep_plural})",
                "Rentabilidade (Campeões vs. Vampiros)",
            ]
        )
        with t_quad:
            if not dto.rep_performance_df.empty:
                fig_quad = quadrant_scatter(
                    dto.rep_performance_df,
                    x_col="gross_revenue",
                    y_col="margin_pct",
                    label_col="sales_rep_name",
                    size_col="revenue_at_risk_brl",
                    theme_mode=theme_mode,
                )
                st.plotly_chart(fig_quad, use_container_width=True)
            else:
                st.info("Nenhum dado de representantes no filtro.")
        with t_champ:
            render_champions_vampires_section(dto, labels)

    with col_diag_right:
        t_scatter, t_rfm, t_funnel, t_ws = st.tabs(
            [
                "Atraso de Recompra (Ciclo)",
                "Segmentação RFM & LTV",
                "Funil de Recompra",
                "Matriz White Space",
            ]
        )
        with t_scatter:
            fig_scatter = cycle_delay_scatter(dto.priority_risk_df, theme_mode=theme_mode)
            st.plotly_chart(fig_scatter, use_container_width=True)
        with t_rfm:
            fig_rfm = rfm_treemap(dto.rfm_summary_df, theme_mode=theme_mode)
            st.plotly_chart(fig_rfm, use_container_width=True)
        with t_funnel:
            if not dto.cycle_funnel_df.empty:
                fig_funnel = cycle_health_funnel_chart(dto.cycle_funnel_df, theme_mode=theme_mode)
                st.plotly_chart(fig_funnel, use_container_width=True)
            else:
                st.info("Sem dados de funil no filtro.")
        with t_ws:
            fig_ws = white_space_heatmap(dto.white_space_matrix_df, theme_mode=theme_mode)
            st.plotly_chart(fig_ws, use_container_width=True)

    # 3. Faixa 3 — Base (Detalhamento & Ação em 2 Colunas lado a lado)
    col_act_left, col_act_right = st.columns([1.35, 1.0])

    with col_act_left:
        t_crit, t_deals, t_reps = st.tabs(
            [
                f"{labels.customer_plural} em Risco",
                "Pitch Cross-Sell (White Space)",
                f"Desempenho dos {rep_plural}",
            ]
        )
        with t_crit:
            render_critical_customers_table(dto, labels.customer)
        with t_deals:
            render_white_space_deals_table(dto, labels.customer)
        with t_reps:
            render_sales_reps_table(dto, labels.sales_rep)

    with col_act_right:
        render_prescription_box(
            title=dto.prescription_title,
            recommendation_html=dto.prescription_html,
            impact_brl=dto.prescription_impact_brl,
            action_hint="Priorize o contato com os lojistas do topo da lista antes do fechamento semanal.",
            help_text=(
                "Diretrizes táticas consolidadas com base no valor em risco e oportunidades de cross-sell."
            ),
        )
        render_commercial_export_bar(
            dto.priority_risk_df,
            dto.top_white_space_deals_df,
            scenario_id=state.scenario_id,
            scenario_name=scenario_cfg.display_name,
        )


render_page()
