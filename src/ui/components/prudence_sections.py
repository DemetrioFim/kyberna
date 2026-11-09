from __future__ import annotations

import streamlit as st

from src.core.scenarios import ScenarioLabels
from src.services.dto import ExecutivePageDTO
from src.services.simulator import simulate_quick_what_if
from src.ui.components.kpi_card import info_tooltip_html, render_kpi_card
from src.ui.components.prescription import section_header
from src.ui.components.tables import render_margin_drivers_table
from src.ui.formatting import (
    format_brl,
    format_int,
    format_pct,
    get_delta_html,
)


def render_prudence_banner(dto: ExecutivePageDTO) -> None:
    """Exibe barra informativa com o período de vendas filtrado, comparativo e data-âncora."""
    info_icon = info_tooltip_html(
        "Indica a janela exata de faturamento considerada em todos os cards, gráficos e tabelas, "
        "além da régua histórica adotada para o cálculo de variações percentuais (Δ).",
        align="left",
    )
    b_style = (
        'style="display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; '
        "gap: 0.75rem; background: var(--kyb-card-bg); border: 1px solid var(--kyb-border); "
        'border-radius: 6px; padding: 0.6rem 1rem; margin: 0.5rem 0 1rem 0; font-size: 0.88rem;"'
    )
    banner_html = (
        f"<div {b_style}>"
        f"<div><span><strong>Período:</strong> "
        f'<span style="color: var(--kyb-teal); font-weight: 600;">{dto.period_label}</span></span>'
        f"{info_icon}</div>"
        f"<div><span><strong>Comparativo (Δ):</strong> "
        f'<span style="color: var(--kyb-text-muted);">{dto.comparison_label}</span></span></div>'
        f"<div><span><strong>Data-Âncora:</strong> "
        f'<span style="color: var(--kyb-text-muted);">{dto.as_of_date_label}</span></span></div>'
        "</div>"
    )
    st.markdown(banner_html, unsafe_allow_html=True)


def render_prudence_headline(dto: ExecutivePageDTO) -> None:
    """Renderiza a manchete executiva dinâmica de Prudência com chamada de direção."""
    headline_info = info_tooltip_html(
        "Síntese executiva calculando ritmo comercial contra metas e dispersão de margem real.",
        align="left",
    )
    h_style = (
        'style="background: var(--kyb-card-bg); border-left: 4px solid var(--kyb-teal); '
        "border-top: 1px solid var(--kyb-border); border-right: 1px solid var(--kyb-border); "
        "border-bottom: 1px solid var(--kyb-border); padding: 0.85rem 1.25rem; border-radius: 6px; "
        'margin: 0.5rem 0 1.25rem 0;"'
    )
    t_style = (
        'style="font-size: 0.82rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; '
        'color: var(--kyb-teal); margin-bottom: 0.25rem; display: flex; align-items: center; gap: 0.5rem;"'
    )
    manchete_html = (
        f"<div {h_style}>"
        f"<div {t_style}><span>{dto.headline_title}</span>{headline_info}</div>"
        f'<div style="font-size: 1rem; line-height: 1.45; color: var(--kyb-text);">{dto.headline_text}</div>'
        "</div>"
    )
    st.markdown(manchete_html, unsafe_allow_html=True)


def render_prudence_kpis(dto: ExecutivePageDTO, customer_plural: str) -> None:
    """Renderiza a linha superior com 5 KPI Cards e métricas de Pacing executivo."""
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        gross_delta = get_delta_html(dto.kpis.gross_revenue_delta_pct, kind="pct")
        pacing_sub = f"Meta: {dto.kpis.revenue_pacing_pct:.1f}% | {format_int(dto.kpis.total_boxes)} cx"
        render_kpi_card(
            title="Faturamento Bruto",
            value=format_brl(dto.kpis.gross_revenue, compact=True),
            subfooter_left=pacing_sub,
            delta_html=gross_delta,
            accent="teal",
            help_text=(
                "Receita bruta total faturada a preço de tabela.<br><br>"
                f"<strong>Pacing da Meta:</strong> {dto.kpis.revenue_pacing_pct:.1f}% da meta projetada.<br>"
                f"<strong>Volume físico:</strong> {format_int(dto.kpis.total_boxes)} caixas master expedidas."
            ),
        )

    with col2:
        tax_pct = dto.kpis.tax_amount / dto.kpis.gross_revenue * 100.0 if dto.kpis.gross_revenue > 0 else 0.0
        net_delta = get_delta_html(dto.kpis.net_revenue_delta_pct, kind="pct")
        render_kpi_card(
            title="Receita Líquida",
            value=format_brl(dto.kpis.net_revenue, compact=True),
            subfooter_left=f"Tributos: {tax_pct:.1f}% Fat.",
            delta_html=net_delta,
            accent="brass",
            help_text=(
                "Receita efetiva após dedução de descontos e tributos (ICMS/PIS/COFINS).<br><br>"
                "<strong>No rodapé:</strong> carga tributária efetiva média."
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
                "Lucro líquido no bolso que sobra após abater Custo das Mercadorias (CPV), "
                "Comissões de RCAs e Frete CIF."
            ),
        )

    with col4:
        margin_delta = get_delta_html(dto.kpis.margin_pct_delta_pp, kind="pp")
        render_kpi_card(
            title="Margem Líquida %",
            value=format_pct(dto.kpis.contribution_margin_pct),
            subfooter_left=f"Meta: {dto.kpis.margin_target_pct:.1f}%",
            delta_html=margin_delta,
            accent="gold",
            help_text=(
                "Índice de rentabilidade real (Margem de Contribuição ÷ Faturamento Bruto). "
                f"Meta estipulada de governança: {dto.kpis.margin_target_pct:.1f}%."
            ),
        )

    with col5:
        cust_delta = get_delta_html(dto.kpis.active_customers_delta_pct, kind="pct", invert_color=False)
        render_kpi_card(
            title=f"{customer_plural} Ativos",
            value=format_int(dto.kpis.active_customers),
            subfooter_left=f"Ticket: {format_brl(dto.kpis.avg_ticket, compact=True)}",
            delta_html=cust_delta,
            accent="red",
            help_text=(
                f"Quantidade de {customer_plural.lower()} distintos com pedido faturado.<br><br>"
                f"<strong>Projeção 30d:</strong> "
                f"{format_brl(dto.kpis.projected_quarter_revenue_brl, compact=True)}."
            ),
        )


@st.fragment
def render_what_if_quick_fragment(dto: ExecutivePageDTO) -> None:
    """Fragmento interativo de simulação rápida de cenários com 3 alavancas e cálculo de breakeven."""
    section_header(
        "Simulador Executivo de Cenários (What-If)",
        "Analise instantaneamente o impacto de preço, desconto e custos no lucro líquido e breakeven",
        help_text=(
            "Simulação dinâmica considerando elasticidade de demanda (-1.2). "
            "Calcula o volume extra necessário para compensar descontos adicionais."
        ),
    )

    col_ctrl, col_res = st.columns([1, 2])

    with col_ctrl:
        st.markdown("###### Alavancas de Decisão")
        price_delta = st.slider(
            "Tabela de Preços (% delta)",
            min_value=-15.0,
            max_value=15.0,
            value=0.0,
            step=0.5,
            help="Reajuste percentual aplicado a todos os preços de tabela.",
            key="_what_if_price",
        )
        discount_delta = st.slider(
            "Desconto Adicional (p.p.)",
            min_value=-5.0,
            max_value=10.0,
            value=0.0,
            step=0.5,
            help="Aumento ou redução de desconto médio concedido pela força de vendas.",
            key="_what_if_disc",
        )
        cogs_delta = st.slider(
            "Custo Mercadoria / CPV (%)",
            min_value=-10.0,
            max_value=15.0,
            value=0.0,
            step=0.5,
            help="Inflação ou redução no custo unitário das matérias-primas e produtos.",
            key="_what_if_cogs",
        )

    res = simulate_quick_what_if(
        dto.kpis,
        price_change_pct=price_delta,
        discount_change_pp=discount_delta,
        commission_or_cost_change_pct=cogs_delta,
    )

    with col_res:
        st.markdown("###### Resultado Projetado da Simulação")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric(
                label="Faturamento Simulado",
                value=format_brl(res["simulated_revenue_brl"], compact=True),
                delta=f"{res['estimated_volume_pct']:+.1f}% vol est.",
                help="Receita bruta projetada ajustada pelo novo preço e elasticidade de volume.",
            )
        with c2:
            st.metric(
                label="Margem Contribuição",
                value=format_brl(res["simulated_margin_brl"], compact=True),
                delta=f"{format_brl(res['margin_delta_brl'], compact=True)} no bolso",
                delta_color="normal" if res["margin_delta_brl"] >= 0 else "inverse",
                help="Resultado líquido final de margem operacional após deduções.",
            )
        with c3:
            be_val = res["breakeven_volume_pct"]
            be_str = f"{be_val:+.1f}% volume" if be_val < 500 else "Inviável"
            st.metric(
                label="Volume de Breakeven",
                value=be_str,
                delta=f"Margem: {res['simulated_margin_pct']:.1f}%",
                help="Variação percentual de volume necessária para manter o mesmo lucro líquido original.",
            )

        if res["margin_delta_brl"] < 0:
            st.caption(
                f"*Atenção de Prudência:* Para compensar essa concessão e manter o lucro atual, "
                f"a equipe comercial precisa vender **{res['breakeven_volume_pct']:+.1f}% mais unidades**."
            )
        elif res["margin_delta_brl"] > 0:
            st.caption(
                f"*Ganho de Prudência:* Esta calibragem gera "
                f"**{format_brl(res['margin_delta_brl'], compact=True)} adicionais** de margem líquida."
            )


def render_prudence_anomalies_section(dto: ExecutivePageDTO) -> None:
    """Renderiza a seção do Radar de Anomalias e alertas de governança."""
    if dto.anomalies_df is None or dto.anomalies_df.empty:
        return

    section_header(
        "Radar de Anomalias & Alertas de Prudência",
        "Detecção estatística automática de desvios de desconto, margem comprimida e risco de churn",
        help_text=(
            "Monitoramento contínuo de exceções nas vendas que ameaçam a entrega da meta de margem "
            "ou indicam quebra de disciplina comercial antes do fechamento do mês."
        ),
    )

    df_anom = dto.anomalies_df.copy()
    for row in df_anom.to_dict(orient="records"):
        sev = str(row.get("severity", "Média"))
        cat = str(row.get("category", "Geral"))
        title = str(row.get("title", ""))
        rec = str(row.get("recommendation", ""))
        impact = float(row.get("impact_brl", 0.0))

        color_border = (
            "var(--kyb-neg)"
            if sev in ("Crítica", "Alta")
            else "var(--kyb-warn)"
            if sev == "Média"
            else "var(--kyb-teal)"
        )

        card_top = (
            '<div style="display: flex; justify-content: space-between; align-items: center; '
            'margin-bottom: 0.25rem;">'
            f'<span style="font-size: 0.78rem; font-weight: 700; text-transform: uppercase; '
            f'color: {color_border};">[{sev}] {cat}</span>'
            f'<span style="font-size: 0.85rem; font-weight: 600; color: var(--kyb-text);">'
            f"Impacto Est.: {format_brl(impact, compact=True)}</span>"
            "</div>"
        )
        card_html = (
            f'<div style="background: var(--kyb-card-bg); border-left: 4px solid {color_border}; '
            "border-top: 1px solid var(--kyb-border); border-right: 1px solid var(--kyb-border); "
            "border-bottom: 1px solid var(--kyb-border); border-radius: 6px; padding: 0.75rem 1rem; "
            'margin-bottom: 0.6rem;">'
            f"{card_top}"
            f'<div style="font-size: 0.95rem; font-weight: 600; color: var(--kyb-text); '
            f'margin-bottom: 0.2rem;">{title}</div>'
            f'<div style="font-size: 0.85rem; color: var(--kyb-text-muted);">'
            f"<strong>Recomendação:</strong> {rec}</div>"
            "</div>"
        )
        st.markdown(card_html, unsafe_allow_html=True)


def render_prudence_drivers_section(dto: ExecutivePageDTO, labels: ScenarioLabels) -> None:
    """Renderiza o ranking dos maiores geradores e destruidores de margem em 4 dimensões."""
    section_header(
        "Matriz de Lucratividade: Geradores vs. Destratores de Margem",
        "Descubra quem alavanca o lucro líquido e onde ocorrem sangrias comerciais",
        help_text=(
            "Identificação dos 10 maiores geradores de margem líquida (R$) versus os 10 maiores detratores "
            "(menor margem % ou margem negativa) para orientar renegociação imediata."
        ),
    )

    t_fam, t_prod, t_cust, t_rep = st.tabs(
        [
            f"Por {labels.product_family}",
            "Por Produto (SKU)",
            f"Por {labels.customer_plural}",
            f"Por {labels.sales_rep}",
        ]
    )
    tabs_data = [
        (
            t_fam,
            f"Top Linhas / {labels.product_family}",
            dto.top_family_generators_df,
            dto.top_family_destroyers_df,
        ),
        (t_prod, "Top 10 Produtos (SKUs)", dto.top_generators_df, dto.top_destroyers_df),
        (
            t_cust,
            f"Top 10 {labels.customer_plural}",
            dto.top_customer_generators_df,
            dto.top_customer_destroyers_df,
        ),
        (t_rep, f"Top 10 {labels.sales_rep}", dto.top_rep_generators_df, dto.top_rep_destroyers_df),
    ]
    for tab, title, gen_df, dest_df in tabs_data:
        with tab:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"##### {title} Mais Lucrativos")
                render_margin_drivers_table(gen_df, is_generator=True)
            with c2:
                st.markdown(f"##### {title} com Menor Margem %")
                render_margin_drivers_table(dest_df, is_generator=False)


def render_monthly_sales_table_section(dto: ExecutivePageDTO) -> None:
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
