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
    render_prescription_box,
    section_header,
)
from src.ui.components.prudence_sections import (
    render_monthly_sales_table_section,
    render_prudence_anomalies_section,
    render_prudence_banner,
    render_prudence_drivers_section,
    render_prudence_headline,
    render_prudence_kpis,
    render_what_if_quick_fragment,
)
from src.ui.state import get_app_state


def _render_visual_section(dto: ExecutivePageDTO, theme_mode: str) -> None:
    """Renderiza a seção comparativa em duas colunas: Waterfall e Tendência Dupla com Meta."""
    col_wat, col_trend = st.columns([1, 1])

    with col_wat:
        section_header(
            "Decomposição da Margem Real",
            "Do faturamento bruto até o lucro líquido no bolso",
            help_text=(
                "Demonstração visual contábil (Waterfall) das deduções da receita bruta: "
                "Descontos comerciais, Impostos sobre vendas, CPV, Comissões de RCAs e Frete CIF "
                "até a Margem de Contribuição líquida final."
            ),
        )
        fig_wat = waterfall_margin(dto.waterfall_df, theme_mode=theme_mode)
        st.plotly_chart(fig_wat, use_container_width=True)

    with col_trend:
        section_header(
            "Evolução: Volume vs. Margem %",
            "Identifique visualmente o efeito boca de jacaré",
            help_text=(
                "Evolução histórica mensal do Faturamento Bruto (barras) versus Margem Líquida % (linha). "
                "Linha tracejada indica a Meta de Margem de governança (26.0%)."
            ),
        )
        fig_trend = dual_trend(
            dto.monthly_trend_df,
            theme_mode=theme_mode,
            target_margin_pct=dto.kpis.margin_target_pct,
        )
        st.plotly_chart(fig_trend, use_container_width=True)


@st.fragment
def _render_abc_xyz_fragment(dto: ExecutivePageDTO, theme_mode: str) -> None:
    """Fragmento isolado para exploração interativa da Matriz ABC/XYZ sem rerun global."""
    col_mat, col_ctrl = st.columns([2, 1])

    with col_ctrl:
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

        selected_cell = st.selectbox(
            "Filtrar Célula da Matriz",
            options=cell_options,
            index=cell_idx,
            key="_abc_xyz_cell_select",
            help="Selecione uma célula específica (ex: AX para alta margem e estabilidade).",
        )
        st.session_state.selected_abc_xyz_cell = selected_cell if selected_cell != "Todas" else None

        if selected_cell != "Todas" and not dto.abc_xyz_matrix_df.empty:
            cell_col = "abc_xyz_cell" if "abc_xyz_cell" in dto.abc_xyz_matrix_df.columns else "cell"
            cell_info = dto.abc_xyz_matrix_df[dto.abc_xyz_matrix_df[cell_col] == selected_cell]
            if not cell_info.empty:
                policy_text = str(cell_info["recommended_policy"].iloc[0])
                sku_cnt = int(cell_info["sku_count"].iloc[0])
                m_share = float(cell_info["margin_share_pct"].iloc[0])
                st.info(
                    f"**Célula {selected_cell}** ({sku_cnt} SKUs | {m_share:.1f}% da Margem Total)\n\n"
                    f"**Política Prescritiva:** {policy_text}"
                )

    with col_mat:
        fig_heatmap = abc_xyz_heatmap(
            dto.abc_xyz_matrix_df,
            theme_mode=theme_mode,
            selected_cell=st.session_state.get("selected_abc_xyz_cell"),
        )
        st.plotly_chart(fig_heatmap, use_container_width=True)

    if not dto.abc_xyz_skus_df.empty:
        display_skus = dto.abc_xyz_skus_df.copy()
        if st.session_state.get("selected_abc_xyz_cell"):
            display_skus = display_skus[
                display_skus["abc_xyz_class"] == st.session_state.selected_abc_xyz_cell
            ]

        with st.expander(f"Ver Lista de SKUs ({len(display_skus)} itens)", expanded=False):
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
                column_config={
                    "Fat. Bruto (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
                    "Margem Líq. (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
                    "Margem Líq. (%)": st.column_config.NumberColumn(format="%.1f%%"),
                    "Volatilidade (CV)": st.column_config.NumberColumn(format="%.2f"),
                },
                hide_index=True,
            )


def render_page() -> None:
    """Renderiza a página '1. Prudência — Visão Executiva & Margem Real'."""
    state = get_app_state()
    scenario = load_scenario_config(state.scenario_id)

    st.title("1. Prudência — Visão Executiva & Margem Real")
    st.caption(
        f"Previsibilidade de metas e proteção de margem: **{scenario.display_name}** "
        f"({scenario.company_profile})."
    )

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

    # 1. Banner Temporal & Manchete Dinâmica de Prudência
    render_prudence_banner(dto)
    render_prudence_headline(dto)

    # 2. 5 KPI Cards com Pacing Executivo
    render_prudence_kpis(dto, scenario.labels.customer_plural)
    st.markdown("---")

    # 3. Seção Visual: Waterfall da Margem Real e Tendência Dupla com Meta
    _render_visual_section(dto, theme_mode=state.theme_mode)
    st.markdown("---")

    # 4. Simulador Executivo What-If de 3 Alavancas (Breakeven Rápido)
    render_what_if_quick_fragment(dto)
    st.markdown("---")

    # 5. Radar de Anomalias & Alertas Críticos de Prudência
    render_prudence_anomalies_section(dto)
    st.markdown("---")

    # 6. Demonstrativo de Vendas Mensal (Mês a Mês)
    render_monthly_sales_table_section(dto)
    st.markdown("---")

    # 7. Matriz 3x3 ABC/XYZ com Fragmento Interativo
    section_header(
        "Matriz 3x3 ABC/XYZ & Gestão Prescritiva de Portfólio",
        "Cruza a contribuição na margem (ABC) com a volatilidade da demanda semanal (XYZ)",
        help_text=(
            "Classificação bidimensional de SKUs: ABC por contribuição acumulada na margem "
            "(A=80%, B=15%, C=5%) e XYZ por estabilidade semanal da demanda "
            "(X estável CV≤0.5, Y moderado 0.5<CV≤1.0, Z errático CV>1.0)."
        ),
    )
    _render_abc_xyz_fragment(dto, theme_mode=state.theme_mode)
    st.markdown("---")

    # 8. Matriz de Lucratividade: Geradores vs. Destratores de Margem (4 Abas)
    render_prudence_drivers_section(dto, scenario.labels)
    st.markdown("---")

    # 9. Veredito Prescritivo de Prudência
    action_msg = "Definir tabela regressiva de descontos e revisar parâmetros de frete no simulador."
    render_prescription_box(
        title=dto.prescription_title,
        recommendation_html=dto.prescription_html,
        impact_brl=dto.prescription_impact_brl,
        action_hint=action_msg,
        help_text=(
            "Diagnóstico prescritivo gerado a partir do desvio de margem dos clientes que operam "
            "abaixo do piso saudável (22%). Estima o impacto de proteção de margem ao aplicar "
            "ajustes comerciais."
        ),
    )


render_page()
