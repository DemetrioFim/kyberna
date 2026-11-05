from __future__ import annotations

import streamlit as st

from src.core.scenarios import ScenarioLabels, load_scenario_config
from src.services.dto import ExecutivePageDTO
from src.ui.cache import cached_executive_dashboard
from src.ui.components.charts import (
    abc_xyz_heatmap,
    dual_trend,
    waterfall_margin,
)
from src.ui.components.kpi_card import render_kpi_card
from src.ui.components.prescription import (
    render_prescription_box,
    section_header,
)
from src.ui.components.tables import render_margin_drivers_table
from src.ui.formatting import (
    format_brl,
    format_int,
    format_pct,
    get_delta_html,
)
from src.ui.state import get_app_state


def _render_kpi_cards(dto: ExecutivePageDTO, customer_plural: str) -> None:
    """Renderiza a linha superior com os 5 KPI Cards executivos."""
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        gross_delta = get_delta_html(dto.kpis.gross_revenue_delta_pct, kind="pct")
        render_kpi_card(
            title="Faturamento Bruto",
            value=format_brl(dto.kpis.gross_revenue, compact=True),
            subfooter_left=f"{format_int(dto.kpis.total_units)} un",
            delta_html=gross_delta,
            accent="teal",
            help_text="Receita bruta total faturada a preço de tabela",
        )

    with col2:
        tax_pct = dto.kpis.tax_amount / dto.kpis.gross_revenue * 100.0 if dto.kpis.gross_revenue > 0 else 0.0
        net_delta = get_delta_html(dto.kpis.net_revenue_delta_pct, kind="pct")
        render_kpi_card(
            title="Receita Líquida",
            value=format_brl(dto.kpis.net_revenue, compact=True),
            subfooter_left=f"Impostos: {tax_pct:.1f}%",
            delta_html=net_delta,
            accent="brass",
            help_text="Receita faturada deduzida de descontos comerciais e impostos (ICMS/PIS/COFINS)",
        )

    with col3:
        cm_delta = get_delta_html(dto.kpis.contribution_margin_delta_pct, kind="pct")
        render_kpi_card(
            title="Margem Contribuição",
            value=format_brl(dto.kpis.contribution_margin, compact=True),
            subfooter_left=f"CPV: {format_brl(dto.kpis.cogs, compact=True)}",
            delta_html=cm_delta,
            accent="green",
            help_text="Margem real líquida que sobra no bolso após custos variáveis e frete",
        )

    with col4:
        margin_delta = get_delta_html(dto.kpis.margin_pct_delta_pp, kind="pp")
        render_kpi_card(
            title="Margem Líquida %",
            value=format_pct(dto.kpis.contribution_margin_pct),
            subfooter_left="Margem / Fat. Bruto",
            delta_html=margin_delta,
            accent="gold",
            help_text="Percentual da margem de contribuição sobre o faturamento bruto",
        )

    with col5:
        cust_delta = get_delta_html(
            dto.kpis.active_customers_delta_pct,
            kind="pct",
            invert_color=False,
        )
        render_kpi_card(
            title=f"{customer_plural} Ativos",
            value=format_int(dto.kpis.active_customers),
            subfooter_left=f"Ticket: {format_brl(dto.kpis.avg_ticket, compact=True)}",
            delta_html=cust_delta,
            accent="red",
            help_text=f"Total de {customer_plural.lower()} que compraram no período",
        )


def _render_visual_section(dto: ExecutivePageDTO, theme_mode: str) -> None:
    """Renderiza a seção comparativa em duas colunas: Waterfall e Tendência Dupla."""
    col_wat, col_trend = st.columns([1, 1])

    with col_wat:
        section_header(
            "Decomposição da Margem Real",
            "Do faturamento bruto até o lucro líquido no bolso",
        )
        fig_wat = waterfall_margin(dto.waterfall_df, theme_mode=theme_mode)
        st.plotly_chart(fig_wat, use_container_width=True)

    with col_trend:
        section_header(
            "Evolução: Volume vs. Margem %",
            "Identifique visualmente o efeito boca de jacaré",
        )
        fig_trend = dual_trend(dto.monthly_trend_df, theme_mode=theme_mode)
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

        with st.expander(f"📋 Ver Lista de SKUs ({len(display_skus)} itens)", expanded=False):
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


def _render_drivers_section(dto: ExecutivePageDTO, labels: ScenarioLabels) -> None:
    """Renderiza o ranking dos maiores geradores e destruidores de margem."""
    section_header(
        "Destaques de Margem: Geradores vs. Destratores",
        "Identifique onde o lucro é gerado e onde ocorrem vazamentos por descontos e frete",
    )

    tab_products, tab_customers = st.tabs(
        [
            f"📦 Por {labels.product_family}",
            f"👥 Por {labels.customer}",
        ]
    )

    with tab_products:
        p_col1, p_col2 = st.columns(2)
        with p_col1:
            st.markdown("##### 🟢 Top 10 Produtos Mais Lucrativos")
            render_margin_drivers_table(dto.top_generators_df, is_generator=True)
        with p_col2:
            st.markdown("##### 🔴 Top 10 Produtos com Menor Margem %")
            render_margin_drivers_table(dto.top_destroyers_df, is_generator=False)

    with tab_customers:
        c_col1, c_col2 = st.columns(2)
        with c_col1:
            st.markdown(f"##### 🟢 Top 10 {labels.customer_plural} Mais Lucrativos")
            render_margin_drivers_table(dto.top_customer_generators_df, is_generator=True)
        with c_col2:
            st.markdown(f"##### 🔴 Top 10 {labels.customer_plural} com Menor Margem %")
            render_margin_drivers_table(dto.top_customer_destroyers_df, is_generator=False)


def render_page() -> None:
    """Renderiza a página 'Visão Executiva & Margem Real' conectada ao repositório analítico."""
    state = get_app_state()
    scenario = load_scenario_config(state.scenario_id)

    st.title("📊 Visão Executiva & Margem Real")
    st.caption(
        f"Diagnóstico contábil e prescritivo da operação: **{scenario.display_name}** "
        f"({scenario.company_profile})."
    )

    dto: ExecutivePageDTO = cached_executive_dashboard(
        state.scenario_id,
        regiao=state.regiao,
        uf=state.uf,
        families=state.families,
        sales_reps=state.sales_reps,
        selected_cell=state.selected_abc_xyz_cell,
    )

    # 1. Manchete Executiva Dinâmica
    st.markdown(
        f"""
        <div style="background: rgba(13, 148, 136, 0.08); border-left: 4px solid #0d9488;
                    padding: 0.85rem 1.25rem; border-radius: 6px; margin: 1rem 0 1.5rem 0;">
            <div style="font-size: 0.82rem; font-weight: 700; text-transform: uppercase;
                        letter-spacing: 0.05em; color: #0d9488; margin-bottom: 0.25rem;">
                {dto.headline_title}
            </div>
            <div style="font-size: 1rem; line-height: 1.45;">
                {dto.headline_text}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 2. Linha de 5 KPI Cards
    _render_kpi_cards(dto, scenario.labels.customer_plural)
    st.markdown("---")

    # 3. Seção Visual: Waterfall e Tendência Dupla
    _render_visual_section(dto, theme_mode=state.theme_mode)
    st.markdown("---")

    # 4. Matriz ABC/XYZ em Fragmento Reativo
    section_header(
        "Matriz 3x3 ABC/XYZ & Gestão Prescritiva de Portfólio",
        "Cruza a contribuição na margem (ABC) com a volatilidade da demanda semanal (XYZ)",
    )
    _render_abc_xyz_fragment(dto, theme_mode=state.theme_mode)
    st.markdown("---")

    # 5. Ranking de Geradores vs. Destruidores de Margem
    _render_drivers_section(dto, scenario.labels)
    st.markdown("---")

    # 6. Bloco Prescritivo Executivo
    action_msg = "Definir tabela regressiva de descontos e revisar parâmetros de frete no simulador."
    render_prescription_box(
        title=dto.prescription_title,
        recommendation_html=dto.prescription_html,
        impact_brl=dto.prescription_impact_brl,
        action_hint=action_msg,
    )


render_page()
