from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from src.core.scenarios import load_scenario_config
from src.services.dto import ExecutivePageDTO
from src.ui.cache import cached_executive_dashboard, cached_family_elasticity
from src.ui.components.charts import (
    dual_trend,
    family_margin_chart,
    waterfall_margin,
)
from src.ui.components.prescription import (
    render_cockpit_header,
    render_prescription_box,
    section_header,
)
from src.ui.components.prudence_sections import (
    render_monthly_sales_table_section,
    render_prudence_anomalies_section,
    render_prudence_kpis,
)
from src.ui.components.simulator_charts import elasticity_family_chart
from src.ui.components.simulator_section import render_what_if_quick_fragment
from src.ui.state import get_app_state


def _render_sku_list_table(dto: ExecutivePageDTO) -> None:
    """Renderiza a lista de SKUs com scroll interno de 210px."""
    if dto.abc_xyz_skus_df.empty:
        st.info("Nenhum SKU disponível para a seleção atual.")
        return

    display_skus = dto.abc_xyz_skus_df.copy()
    if st.session_state.get("selected_abc_xyz_cell"):
        display_skus = display_skus[display_skus["abc_xyz_class"] == st.session_state.selected_abc_xyz_cell]

    sku_view = display_skus.rename(
        columns={
            "product_name": "Produto",
            "family": "Família",
            "abc_xyz_class": "Célula",
            "gross_revenue": "Fat. Bruto (R$)",
            "contribution_margin": "Margem Líq. (R$)",
            "margin_pct": "Margem Líq. (%)",
            "weekly_cv": "Volatilidade (CV)",
            "policy": "Política Operacional",
        }
    )
    st.dataframe(
        sku_view,
        use_container_width=True,
        height=185,
        column_config={
            "Fat. Bruto (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
            "Margem Líq. (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
            "Margem Líq. (%)": st.column_config.NumberColumn(format="%.1f%%"),
            "Volatilidade (CV)": st.column_config.NumberColumn(format="%.2f"),
        },
        hide_index=True,
    )


def _get_static_diagnostic_figures(
    dto: ExecutivePageDTO,
    cache_key: tuple[object, ...],
    scenario_id: str,
    theme_mode: str,
) -> tuple[go.Figure, go.Figure, go.Figure, go.Figure]:
    """Memoiza os 4 gráficos estáticos da Tela 1 em sessão para manter interações < 300 ms."""
    cached = st.session_state.get("_exec_static_figs")
    if isinstance(cached, tuple) and len(cached) == 2 and cached[0] == cache_key:
        figs: tuple[go.Figure, go.Figure, go.Figure, go.Figure] = cached[1]
        return figs

    fig_trend = dual_trend(
        dto.monthly_trend_df,
        theme_mode=theme_mode,
        target_margin_pct=dto.kpis.margin_target_pct,
    )
    fig_wat = waterfall_margin(dto.waterfall_df, theme_mode=theme_mode)
    fig_fam = family_margin_chart(dto.abc_xyz_skus_df, theme_mode=theme_mode)
    elasticity_df = cached_family_elasticity(scenario_id)  # type: ignore[arg-type]
    fig_el = elasticity_family_chart(elasticity_df, theme_mode=theme_mode)
    figs = (fig_trend, fig_wat, fig_fam, fig_el)
    st.session_state["_exec_static_figs"] = (cache_key, figs)
    return figs


def _render_elasticity_overview_section(fig_fam: go.Figure, fig_el: go.Figure) -> None:
    """Renderiza a visão executiva de Margem por Família e Elasticidade-Preço na Tela 1."""
    section_header(
        "Rentabilidade & Elasticidade-Preço por Família",
        "Margem de contribuição por linha de produto e sensibilidade de demanda (β)",
        help_text=(
            "Na 1ª aba: faturamento e margem líquida por família de produto. Na 2ª aba: coeficiente β "
            "estimado via regressão log-log robusta (Huber + Bootstrap) que alimenta o Simulador What-If."
        ),
    )
    t_fam, t_el = st.tabs(["Margem por Família", "Elasticidade-Preço (β)"])
    with t_fam:
        st.plotly_chart(fig_fam, use_container_width=True)
    with t_el:
        st.plotly_chart(fig_el, use_container_width=True)


def render_page() -> None:
    """Renderiza a página 'Visão Executiva & Margem Real' em formato Cockpit Z-Pattern."""
    state = get_app_state()
    scenario = load_scenario_config(state.scenario_id)

    dto: ExecutivePageDTO = cached_executive_dashboard(
        state.scenario_id,
        regiao=state.regiao,
        uf=state.uf,
        families=state.families,
        sales_reps=state.sales_reps,
        selected_cell=state.selected_abc_xyz_cell,
        period_preset=state.period_preset,
        selected_month=state.selected_month,
    )
    fig_cache_key: tuple[object, ...] = (
        state.scenario_id,
        state.regiao,
        state.uf,
        tuple(state.families) if state.families else None,
        tuple(state.sales_reps) if state.sales_reps else None,
        state.selected_abc_xyz_cell,
        state.period_preset,
        state.selected_month,
        state.theme_mode,
    )
    fig_trend, fig_wat, fig_fam, fig_el = _get_static_diagnostic_figures(
        dto,
        fig_cache_key,
        state.scenario_id,
        state.theme_mode,
    )

    # 1. Faixa 1 — Topo (Status em 5s): Cabeçalho Cockpit unificado + 5 KPI Cards
    render_cockpit_header(
        title="Visão Executiva & Margem Real",
        virtue_badge="1. Prudência",
        headline_title=dto.headline_title,
        headline_text=dto.headline_text,
        as_of_date_label=dto.as_of_date_label,
        help_text=(
            "Síntese executiva calculando ritmo comercial contra metas e dispersão de margem real "
            "na janela temporal filtrada."
        ),
    )
    render_prudence_kpis(dto, scenario.labels.customer_plural)

    # 2. Faixa 2 — Meio (Diagnóstico Visual em 2 Colunas lado a lado)
    col_diag_left, col_diag_right = st.columns([1.1, 1.0])

    with col_diag_left:
        section_header(
            "Evolução & Decomposição da Margem",
            "Ritmo mensal de faturamento vs. meta e DRE completo da operação",
            help_text=(
                "Acompanha o equilíbrio entre volume faturado e margem percentual frente à meta, "
                "além do detalhamento DRE até a margem líquida."
            ),
        )
        t_evol, t_wat = st.tabs(
            [
                "Ritmo Mensal: Volume vs. Margem %",
                "Decomposição DRE (Waterfall)",
            ]
        )
        with t_evol:
            st.plotly_chart(fig_trend, use_container_width=True)
        with t_wat:
            st.plotly_chart(fig_wat, use_container_width=True)

    with col_diag_right:
        _render_elasticity_overview_section(fig_fam, fig_el)

    # 3. Faixa 3 — Base (Detalhamento & Plano de Ação em 2 Colunas lado a lado)
    col_act_left, col_act_right = st.columns([1.2, 1.0])

    with col_act_left:
        section_header(
            "Auditoria de Exceções & Demonstrativo",
            "Radar de anomalias da semana, demonstrativo mês a mês e portfólio de SKUs",
            help_text=(
                "Monitoramento de exceções críticas nas vendas, demonstrativo financeiro mensal "
                "e desempenho por SKU."
            ),
        )
        t_anom, t_table, t_skus = st.tabs(
            [
                "Radar de Anomalias",
                "Demonstrativo Mês a Mês",
                "Portfólio de SKUs",
            ]
        )
        with t_anom:
            render_prudence_anomalies_section(dto)
        with t_table:
            render_monthly_sales_table_section(dto)
        with t_skus:
            _render_sku_list_table(dto)

    with col_act_right:
        section_header(
            "Decisão & Simulador Prescritivo What-If",
            "Veredito prescritivo de proteção de margem e simulação interativa de alavancas",
            help_text=(
                "Consolida o impacto financeiro estimado e permite testar variações de preço, "
                "desconto, CMV e comissão com elasticidade real."
            ),
        )
        t_presc, t_whatif = st.tabs(
            [
                "Veredito Prescritivo",
                "Simulador Rápido What-If",
            ]
        )
        with t_presc:
            render_prescription_box(
                title=dto.prescription_title,
                recommendation_html=dto.prescription_html,
                impact_brl=dto.prescription_impact_brl,
                action_hint=(
                    "Definir tabela regressiva de descontos e revisar parâmetros de frete no simulador."
                ),
                help_text=(
                    "Diagnóstico prescritivo gerado a partir do desvio de margem dos clientes que operam "
                    "abaixo do piso saudável (22%). Estima o impacto de proteção de margem ao aplicar "
                    "ajustes comerciais."
                ),
            )
        with t_whatif:
            render_what_if_quick_fragment(dto, theme_mode=state.theme_mode)


render_page()
