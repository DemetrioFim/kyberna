from __future__ import annotations

import streamlit as st

from src.core.scenarios import load_scenario_config
from src.services.dto import ExecutivePageDTO, FortitudePageDTO, TemperancePageDTO
from src.services.pricing_dto import PricingPageDTO
from src.ui.cache import (
    cached_executive_dashboard,
    cached_fortitude_dashboard,
    cached_pricing_dashboard,
    cached_temperance_dashboard,
)
from src.ui.components.charts import dual_trend, waterfall_margin
from src.ui.components.fortitude_charts import (
    build_breakeven_curve_chart,
    build_cycle_comparison_chart,
)
from src.ui.components.fortitude_sections import (
    render_fortitude_kpi_cards,
    render_fortitude_verdict_section,
)
from src.ui.components.justice_sections import render_term_leak_table
from src.ui.components.prescription import (
    render_cockpit_header,
    render_prescription_box,
    section_header,
)
from src.ui.components.pricing_sections import (
    render_pricing_analytics_fragment,
    render_pricing_deviations_table,
    render_pricing_kpis,
    render_pricing_verdict_section,
)
from src.ui.components.prudence_sections import (
    render_monthly_sales_table_section,
    render_prudence_kpis,
)
from src.ui.state import AppState, get_app_state


def _render_tab_dre(
    state: AppState,
    exec_dto: ExecutivePageDTO,
    customer_plural: str,
) -> None:
    """Aba 1: DRE Gerencial & Margem Real."""
    st.markdown(
        "<div style='font-size:0.78rem; color:var(--kyb-text-muted); margin-bottom:0.25rem;'>"
        f"<strong style='color:var(--kyb-text);'>Janela:</strong> {exec_dto.period_label} · "
        f"<span style='color:var(--kyb-teal); font-weight:600;'>{exec_dto.comparison_label}</span>"
        "</div>",
        unsafe_allow_html=True,
    )
    render_prudence_kpis(exec_dto, customer_plural)

    col_l, col_r = st.columns([1.0, 1.05])
    with col_l:
        section_header(
            "Decomposição DRE Completa (Waterfall)",
            "Do faturamento bruto de tabela até a margem de contribuição",
            help_text="Deduz descontos comerciais, impostos (ICMS/PIS/COFINS), CPV, comissões e frete.",
        )
        st.plotly_chart(
            waterfall_margin(exec_dto.waterfall_df, theme_mode=state.theme_mode),
            use_container_width=True,
            theme=None,
        )
    with col_r:
        section_header(
            "Ritmo Mensal: Faturamento vs. Margem de Contribuição %",
            "Evolução temporal de volume frente à meta de rentabilidade",
            help_text="Identifica se ganhos de volume estão ocorrendo com sacrifício de margem.",
        )
        st.plotly_chart(
            dual_trend(
                exec_dto.monthly_trend_df,
                theme_mode=state.theme_mode,
                target_margin_pct=exec_dto.kpis.margin_target_pct,
            ),
            use_container_width=True,
            theme=None,
        )

    col_bl, col_br = st.columns([1.3, 1.0])
    with col_bl:
        section_header("Demonstrativo Financeiro Mês a Mês", "Série contábil consolidada com deltas MoM")
        render_monthly_sales_table_section(exec_dto)
    with col_br:
        section_header("Veredito Financeiro de Margem", "Alavancas prioritárias de proteção do lucro")
        render_prescription_box(
            title=exec_dto.prescription_title,
            recommendation_html=exec_dto.prescription_html,
            impact_brl=exec_dto.prescription_impact_brl,
            action_hint="Aprofunde testes de precificação no Simulador What-If em 4. Temperança.",
            help_text=(
                "Estimativa financeira de ganho ao recuperar clientes abaixo do piso saudável de margem."
            ),
        )


def _render_tab_cash_cycle(
    fort_dto: FortitudePageDTO,
    temp_dto: TemperancePageDTO,
    theme_mode: str,
) -> None:
    """Aba 2: Fluxo de Caixa, Runway & Ciclo (NCG)."""
    render_fortitude_kpi_cards(fort_dto, temp_dto=temp_dto)
    col_l, col_r = st.columns([1.0, 1.0])
    with col_l:
        section_header(
            "Ciclo Financeiro em Dias (PME + PMR - PMP)",
            "Quantos dias a tesouraria financia a operação antes de receber",
            help_text="Cada dia reduzido no ciclo libera Capital de Giro (NCG) direto para o caixa.",
        )
        st.plotly_chart(
            build_cycle_comparison_chart(fort_dto.cycle_components_df, theme_mode=theme_mode),
            use_container_width=True,
            theme=None,
        )
    with col_r:
        section_header(
            "Curva Diária do Break-Even Acumulado",
            "Dia exato do mês em que a margem paga 100% dos custos fixos",
            help_text="Acompanhamento intra-mês da geração operacional até o ponto de equilíbrio.",
        )
        st.plotly_chart(
            build_breakeven_curve_chart(fort_dto.breakeven_curve_df, fort_dto.kpis, theme_mode=theme_mode),
            use_container_width=True,
            theme=None,
        )

    col_bl, col_br = st.columns([1.15, 1.0])
    with col_bl:
        section_header(
            "Custo Financeiro de Prazo Concedido",
            "Carregamento financeiro de prazos médios esticados acima de 30 dias",
        )
        render_term_leak_table(temp_dto)
    with col_br:
        section_header("Veredito de Solvência & NCG", "Liberação imediata de caixa sem endividamento")
        render_fortitude_verdict_section(fort_dto)


def _render_tab_pricing(
    state: AppState,
    pricing_dto: PricingPageDTO,
) -> None:
    """Aba 3: Precificação, Banda Ideal & Drivers (SHAP)."""
    render_pricing_kpis(pricing_dto)
    render_pricing_analytics_fragment(state, pricing_dto)

    col_bl, col_br = st.columns([1.2, 1.0])
    with col_bl:
        section_header(
            "Auditoria de Desvios de Preço (Fora da Banda)",
            "SKUs com maior vazamento financeiro abaixo do piso contextual P25",
        )
        render_pricing_deviations_table(pricing_dto)
    with col_br:
        section_header(
            "Veredito de Política de Preços",
            "Contenção de subprecificação e captura em famílias inelásticas",
        )
        render_pricing_verdict_section(pricing_dto)


def render_page() -> None:
    """Renderiza a Página 3 — 3. Justiça (Governança Financeira, Caixa & Precificação)."""
    state = get_app_state()
    labels = load_scenario_config(state.scenario_id).labels

    exec_dto = cached_executive_dashboard(
        state.scenario_id,
        regiao=state.regiao,
        uf=state.uf,
        families=state.families,
        sales_reps=state.sales_reps,
        selected_cell=state.selected_abc_xyz_cell,
        period_preset=state.period_preset,
        comparison_mode=state.comparison_mode,
        selected_month=state.selected_month,
        selected_quarter=state.selected_quarter,
        selected_semester=state.selected_semester,
        custom_start_date=state.custom_start_date,
        custom_end_date=state.custom_end_date,
    )
    fort_dto = cached_fortitude_dashboard(
        state.scenario_id,
        regiao=state.regiao,
        uf=state.uf,
        families=tuple(state.families),
        sales_reps=tuple(state.sales_reps),
        period_preset=state.period_preset,
        comparison_mode=state.comparison_mode,
        selected_month=state.selected_month,
        selected_quarter=state.selected_quarter,
        selected_semester=state.selected_semester,
        custom_start_date=state.custom_start_date,
        custom_end_date=state.custom_end_date,
    )
    temp_dto = cached_temperance_dashboard(
        state.scenario_id,
        regiao=state.regiao,
        uf=state.uf,
        families=state.families,
        sales_reps=state.sales_reps,
        period_preset=state.period_preset,
        comparison_mode=state.comparison_mode,
        selected_month=state.selected_month,
        selected_quarter=state.selected_quarter,
        selected_semester=state.selected_semester,
        custom_start_date=state.custom_start_date,
        custom_end_date=state.custom_end_date,
    )
    pricing_dto = cached_pricing_dashboard(
        state.scenario_id,
        regiao=state.regiao,
        uf=state.uf,
        families=tuple(state.families),
        sales_reps=tuple(state.sales_reps),
        period_preset=state.period_preset,
        comparison_mode=state.comparison_mode,
        selected_month=state.selected_month,
        selected_quarter=state.selected_quarter,
        selected_semester=state.selected_semester,
        custom_start_date=state.custom_start_date,
        custom_end_date=state.custom_end_date,
    )

    render_cockpit_header(
        title="Justiça · Governança Financeira, Caixa & Precificação",
        virtue_badge="3. Justiça",
        headline_title=exec_dto.headline_title,
        headline_text=exec_dto.headline_text,
        as_of_date_label=exec_dto.as_of_date_label,
        comparison_label=exec_dto.comparison_label,
        help_text=(
            "Visão financeira completa em 3 abas estilo PowerBI: DRE Gerencial & Margem de Contribuição, "
            "Fluxo de Caixa/NCG e Precificação Contextual (Banda Ideal + SHAP)."
        ),
    )

    tab_dre, tab_cash, tab_pricing = st.tabs(
        [
            "DRE Gerencial & Margem Real",
            "Fluxo de Caixa, Runway & Ciclo (NCG)",
            "Precificação, Banda Ideal & Drivers (SHAP)",
        ]
    )
    with tab_dre:
        _render_tab_dre(state, exec_dto, labels.customer_plural)
    with tab_cash:
        _render_tab_cash_cycle(fort_dto, temp_dto, state.theme_mode)
    with tab_pricing:
        _render_tab_pricing(state, pricing_dto)


render_page()
