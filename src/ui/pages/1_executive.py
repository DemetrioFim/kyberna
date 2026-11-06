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
from src.ui.components.kpi_card import info_tooltip_html, render_kpi_card
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
            help_text=(
                "Receita bruta total faturada a preço de tabela (Unidades x Preço de Lista), "
                "antes de deduções comerciais e impostos.<br><br>"
                "<strong>No rodapé:</strong> volume físico total expedido e variação contra "
                "o período anterior."
            ),
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
            help_text=(
                "Faturamento efetivo após dedução de descontos comerciais e tributos sobre vendas "
                "(ICMS + PIS + COFINS). Nota: IPI é calculado por fora.<br><br>"
                "<strong>No rodapé:</strong> alíquota média de impostos sobre a receita bruta."
            ),
        )

    with col3:
        cm_delta = get_delta_html(dto.kpis.contribution_margin_delta_pct, kind="pct")
        render_kpi_card(
            title="Margem Contribuição",
            value=format_brl(dto.kpis.contribution_margin, compact=True),
            subfooter_left=f"CPV: {format_brl(dto.kpis.cogs, compact=True)}",
            delta_html=cm_delta,
            accent="green",
            help_text=(
                "Lucro operacional líquido que sobra no bolso após pagar Custo da Mercadoria (CPV), "
                "Comissões de RCAs e Frete CIF (Receita Líquida - CPV - Comissões - Frete)."
            ),
        )

    with col4:
        margin_delta = get_delta_html(dto.kpis.margin_pct_delta_pp, kind="pp")
        render_kpi_card(
            title="Margem Líquida %",
            value=format_pct(dto.kpis.contribution_margin_pct),
            subfooter_left="Margem / Fat. Bruto",
            delta_html=margin_delta,
            accent="gold",
            help_text=(
                "Índice de rentabilidade real (Margem de Contribuição ÷ Faturamento Bruto). "
                "Indica quantos centavos de cada R$ 1,00 faturado efetivamente viram lucro líquido."
            ),
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
            subfooter_left=f"Ticket: {format_brl(dto.kpis.avg_ticket, compact=False, decimals=0)}",
            delta_html=cust_delta,
            accent="red",
            help_text=(
                f"Quantidade de {customer_plural.lower()} distintos (CNPJs) com pelo menos um "
                "pedido faturado no período.<br><br>"
                "<strong>No rodapé:</strong> Ticket Médio faturado por pedido e variação de clientes ativos."
            ),
        )


def _render_visual_section(dto: ExecutivePageDTO, theme_mode: str) -> None:
    """Renderiza a seção comparativa em duas colunas: Waterfall e Tendência Dupla."""
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
                "O 'efeito boca de jacaré' surge quando o volume cresce mas a margem despenca por "
                "descontos excessivos."
            ),
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
        help_text=(
            "Ranqueamento dos 10 maiores geradores absolutos de margem de contribuição (R$) "
            "em contraste com os 10 itens com menor margem percentual (ou negativa) para revisão imediata."
        ),
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


def _render_temporal_context_banner(dto: ExecutivePageDTO) -> None:
    """Exibe barra informativa com o período de vendas filtrado, comparativo de deltas e data-âncora."""
    info_icon = info_tooltip_html(
        "Indica a janela exata de faturamento considerada em todos os cards, gráficos e tabelas, "
        "além da régua histórica adotada para o cálculo de variações percentuais (Δ).",
        align="left",
    )
    banner_html = (
        '<div style="display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; '
        "gap: 0.75rem; background: rgba(31, 122, 140, 0.07); border: 1px solid rgba(31, 122, 140, 0.25); "
        'border-radius: 6px; padding: 0.6rem 1rem; margin: 0.5rem 0 1rem 0; font-size: 0.88rem;">'
        '<div style="display: flex; align-items: center; gap: 0.5rem;">'
        "<span>📅 <strong>Período Ativo:</strong> "
        f'<span style="color: #0d9488; font-weight: 600;">{dto.period_label}</span></span>'
        f"{info_icon}"
        "</div>"
        "<div>"
        "<span>🔄 <strong>Comparativo (Δ):</strong> "
        f'<span style="color: #475569;">{dto.comparison_label}</span></span>'
        "</div>"
        "<div>"
        "<span>⚓ <strong>Data-Âncora:</strong> "
        f'<span style="color: #475569;">{dto.as_of_date_label}</span></span>'
        "</div>"
        "</div>"
    )
    st.markdown(banner_html, unsafe_allow_html=True)


def _render_monthly_sales_table_section(dto: ExecutivePageDTO) -> None:
    """Renderiza a tabela detalhada de vendas mês a mês para conferência analítica."""
    if dto.monthly_sales_table_df is None or dto.monthly_sales_table_df.empty:
        return

    section_header(
        "Demonstrativo de Vendas Mensal (Mês a Mês)",
        "Acompanhamento detalhado da evolução do faturamento bruto, receita líquida e margem de contribuição",
        help_text=(
            "Detalhamento histórico mês a mês das vendas com volume físico (unidades e caixas), "
            "faturamento bruto, descontos médios concedidos, receita líquida faturada, "
            "margem de contribuição (R$ e %) e variação mensal MoM%."
        ),
    )

    df_view = dto.monthly_sales_table_df.copy()
    rename_map = {
        "month_label": "Mês",
        "orders_count": "Pedidos",
        "active_customers": "Clientes Ativos",
        "total_units": "Unidades",
        "total_boxes": "Caixas Master",
        "gross_revenue": "Fat. Bruto (R$)",
        "mom_gross_pct": "Δ Fat. MoM %",
        "discount_amount": "Desconto (R$)",
        "avg_discount_pct": "Desc. Médio %",
        "net_revenue": "Receita Líq. (R$)",
        "contribution_margin": "Margem Contr. (R$)",
        "margin_pct": "Margem %",
        "mom_margin_pct": "Δ Margem MoM %",
        "avg_ticket": "Ticket Médio (R$)",
    }
    cols_order = [c for c in rename_map if c in df_view.columns]
    df_display = df_view[cols_order].rename(columns=rename_map)

    st.dataframe(
        df_display,
        use_container_width=True,
        column_config={
            "Mês": st.column_config.TextColumn("Mês"),
            "Pedidos": st.column_config.NumberColumn("Pedidos", format="%d"),
            "Clientes Ativos": st.column_config.NumberColumn("Clientes", format="%d"),
            "Unidades": st.column_config.NumberColumn("Unidades", format="%d"),
            "Caixas Master": st.column_config.NumberColumn("Caixas", format="%.1f"),
            "Fat. Bruto (R$)": st.column_config.NumberColumn("Fat. Bruto", format="R$ %.2f"),
            "Δ Fat. MoM %": st.column_config.NumberColumn("Δ Fat. MoM", format="%.1f%%"),
            "Desconto (R$)": st.column_config.NumberColumn("Descontos", format="R$ %.2f"),
            "Desc. Médio %": st.column_config.NumberColumn("Desc. %", format="%.1f%%"),
            "Receita Líq. (R$)": st.column_config.NumberColumn("Receita Líq.", format="R$ %.2f"),
            "Margem Contr. (R$)": st.column_config.NumberColumn("Margem Contr.", format="R$ %.2f"),
            "Margem %": st.column_config.NumberColumn("Margem %", format="%.1f%%"),
            "Δ Margem MoM %": st.column_config.NumberColumn("Δ Margem MoM", format="%.1f%%"),
            "Ticket Médio (R$)": st.column_config.NumberColumn("Ticket Médio", format="R$ %.2f"),
        },
        hide_index=True,
    )


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
        period_preset=state.period_preset,
        selected_month=state.selected_month,
    )

    # 1. Banner de Contexto Temporal
    _render_temporal_context_banner(dto)

    # 2. Manchete Executiva Dinâmica com Ícone Informativo
    headline_info = info_tooltip_html(
        "Síntese executiva automatizada calculada a partir da dispersão de margem "
        "dos clientes e do faturamento total.",
        align="left",
    )
    title_div_style = (
        "font-size: 0.82rem; font-weight: 700; text-transform: uppercase; "
        "letter-spacing: 0.05em; color: #0d9488; margin-bottom: 0.25rem; "
        "display: flex; align-items: center; gap: 0.5rem;"
    )
    manchete_html = (
        '<div style="background: rgba(13, 148, 136, 0.08); border-left: 4px solid #0d9488; '
        'padding: 0.85rem 1.25rem; border-radius: 6px; margin: 1rem 0 1.5rem 0;">'
        f'<div style="{title_div_style}">'
        f"<span>{dto.headline_title}</span>{headline_info}"
        "</div>"
        f'<div style="font-size: 1rem; line-height: 1.45;">{dto.headline_text}</div>'
        "</div>"
    )
    st.markdown(manchete_html, unsafe_allow_html=True)

    # 2. Linha de 5 KPI Cards
    _render_kpi_cards(dto, scenario.labels.customer_plural)
    st.markdown("---")

    # 3. Seção Visual: Waterfall e Tendência Dupla
    _render_visual_section(dto, theme_mode=state.theme_mode)
    st.markdown("---")

    # 4. Demonstrativo de Vendas Mensal
    _render_monthly_sales_table_section(dto)
    st.markdown("---")

    # 5. Matriz ABC/XYZ em Fragmento Reativo
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
        help_text=(
            "Diagnóstico prescritivo gerado a partir do desvio de margem dos clientes que operam "
            "abaixo do piso saudável (22%). Estima o impacto de proteção de margem ao aplicar "
            "ajustes comerciais."
        ),
    )


render_page()
