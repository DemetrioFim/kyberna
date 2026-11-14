from __future__ import annotations

import streamlit as st

from src.core.scenarios import load_scenario_config
from src.services.dto import ExecutivePageDTO
from src.ui.cache import cached_executive_dashboard
from src.ui.components.charts import (
    abc_xyz_heatmap,
    dual_trend,
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
        height=210,
        column_config={
            "Fat. Bruto (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
            "Margem Líq. (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
            "Margem Líq. (%)": st.column_config.NumberColumn(format="%.1f%%"),
            "Volatilidade (CV)": st.column_config.NumberColumn(format="%.2f"),
        },
        hide_index=True,
    )


@st.fragment
def _render_abc_xyz_fragment(dto: ExecutivePageDTO, theme_mode: str) -> None:
    """Fragmento isolado para exploração interativa da Matriz ABC/XYZ em cockpit."""
    col_mat_head, col_mat_ctrl = st.columns([1.5, 1.0])

    with col_mat_head:
        section_header(
            "Matriz 3x3 ABC/XYZ & Demanda",
            "Cruza relevância financeira e variabilidade",
            help_text=(
                "Classificação bidimensional de SKUs: Curva ABC por contribuição na margem "
                "(A=80%, B=15%, C=5%) e Matriz XYZ por regularidade da demanda semanal: "
                "X estável (CV ≤ 1,5), Y sazonal (CV entre 1,5 e 2,5) e Z intermitente (CV superior a 2,5)."
            ),
        )

    cell_options = [
        "Todas",
        "AX",
        "AY",
        "AZ",
        "BX",
        "BY",
        "BZ",
        "CX",
        "CY",
        "CZ",
    ]
    current_cell = st.session_state.get("selected_abc_xyz_cell", "Todas")
    cell_idx = cell_options.index(current_cell) if current_cell in cell_options else 0

    with col_mat_ctrl:
        selected_cell = st.selectbox(
            "Filtrar Célula da Matriz",
            options=cell_options,
            index=cell_idx,
            key="_abc_xyz_cell_select",
            label_visibility="collapsed",
        )
        st.session_state.selected_abc_xyz_cell = selected_cell if selected_cell != "Todas" else None

    fig_heatmap = abc_xyz_heatmap(
        dto.abc_xyz_matrix_df,
        theme_mode=theme_mode,
        selected_cell=st.session_state.get("selected_abc_xyz_cell"),
    )
    st.plotly_chart(fig_heatmap, use_container_width=True)

    if selected_cell != "Todas" and not dto.abc_xyz_matrix_df.empty:
        cell_col = "abc_xyz_cell" if "abc_xyz_cell" in dto.abc_xyz_matrix_df.columns else "cell"
        cell_info = dto.abc_xyz_matrix_df[dto.abc_xyz_matrix_df[cell_col] == selected_cell]
        if not cell_info.empty:
            policy_text = str(cell_info["recommended_policy"].iloc[0])
            st.caption(f"**Célula {selected_cell}:** {policy_text}")


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

    # 1. Faixa 1 — Topo (Status em 5s): Cabeçalho Cockpit unificado + 5 KPI Cards
    render_cockpit_header(
        title="Visão Executiva & Margem Real",
        subtitle=f"{scenario.display_name} ({scenario.company_profile})",
        virtue_badge="1. Prudência",
        headline_title=dto.headline_title,
        headline_text=dto.headline_text,
        period_badge=f"{dto.period_label} · Δ {dto.comparison_label}",
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
        t_evol, t_wat = st.tabs(
            [
                "Ritmo Mensal: Volume vs. Margem %",
                "Decomposição DRE (Waterfall)",
            ]
        )
        with t_evol:
            fig_trend = dual_trend(
                dto.monthly_trend_df,
                theme_mode=state.theme_mode,
                target_margin_pct=dto.kpis.margin_target_pct,
            )
            st.plotly_chart(fig_trend, use_container_width=True)
        with t_wat:
            fig_wat = waterfall_margin(dto.waterfall_df, theme_mode=state.theme_mode)
            st.plotly_chart(fig_wat, use_container_width=True)

    with col_diag_right:
        _render_abc_xyz_fragment(dto, theme_mode=state.theme_mode)

    # 3. Faixa 3 — Base (Detalhamento & Plano de Ação em 2 Colunas lado a lado)
    col_act_left, col_act_right = st.columns([1.2, 1.0])

    with col_act_left:
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
