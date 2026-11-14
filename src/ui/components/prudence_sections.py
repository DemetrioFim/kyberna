from __future__ import annotations

import streamlit as st

from src.services.dto import ExecutivePageDTO
from src.ui.components.kpi_card import render_kpi_card
from src.ui.components.prescription import section_header
from src.ui.formatting import (
    format_brl,
    format_int,
    format_pct,
    get_delta_html,
)


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


def render_prudence_anomalies_section(dto: ExecutivePageDTO) -> None:
    """Renderiza a seção do Radar de Anomalias e alertas de governança."""
    section_header(
        "Radar de Anomalias & Desvios da Semana",
        "Detecção estatística automática de descontos fora da política, margem comprimida e risco",
        help_text=(
            "Monitoramento contínuo de exceções nas vendas que ameaçam a entrega da meta de margem "
            "ou indicam quebra de disciplina comercial antes do fechamento do mês."
        ),
    )

    if dto.anomalies_df is None or dto.anomalies_df.empty:
        st.info(
            "Nenhuma anomalia crítica detectada no período. Parâmetros operacionais dentro da normalidade."
        )
        return

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
            'margin-bottom: 0.2rem;">'
            f'<span style="font-size: 0.76rem; font-weight: 700; text-transform: uppercase; '
            f'color: {color_border};">[{sev}] {cat}</span>'
            f'<span style="font-size: 0.82rem; font-weight: 600; color: var(--kyb-text);">'
            f"Impacto Est.: {format_brl(impact, compact=True)}</span>"
            "</div>"
        )
        card_html = (
            f'<div style="background: var(--kyb-card-bg); border-left: 4px solid {color_border}; '
            "border-top: 1px solid var(--kyb-border); border-right: 1px solid var(--kyb-border); "
            "border-bottom: 1px solid var(--kyb-border); border-radius: 6px; padding: 0.6rem 0.85rem; "
            'margin-bottom: 0.5rem;">'
            f"{card_top}"
            f'<div style="font-size: 0.9rem; font-weight: 600; color: var(--kyb-text); '
            f'margin-bottom: 0.15rem;">{title}</div>'
            f'<div style="font-size: 0.82rem; color: var(--kyb-text-muted);">'
            f"<strong>Recomendação:</strong> {rec}</div>"
            "</div>"
        )
        st.markdown(card_html, unsafe_allow_html=True)


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
        height=210,
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
