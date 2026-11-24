from __future__ import annotations

from collections.abc import Callable
from typing import Any

import streamlit as st

from src.services.dto import ExecutivePageDTO
from src.ui.components.kpi_card import KpiAccent, render_kpi_card
from src.ui.formatting import (
    fmt_brl_cell,
    fmt_int_cell,
    fmt_pct_cell,
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
        margin_accent: KpiAccent = (
            "alert_warn" if dto.kpis.contribution_margin_pct < dto.kpis.margin_target_pct else "gold"
        )
        render_kpi_card(
            title="Margem Líquida %",
            value=format_pct(dto.kpis.contribution_margin_pct),
            subfooter_left=f"Meta: {dto.kpis.margin_target_pct:.1f}%",
            delta_html=margin_delta,
            accent=margin_accent,
            help_text=(
                "Índice de rentabilidade real (Margem de Contribuição ÷ Faturamento Bruto). "
                f"Meta estipulada de governança: {dto.kpis.margin_target_pct:.1f}%."
            ),
        )

    with col5:
        cust_delta = get_delta_html(dto.kpis.active_customers_delta_pct, kind="pct", invert_color=False)
        cust_accent: KpiAccent = "alert_warn" if (dto.kpis.active_customers_delta_pct or 0.0) < 0 else "teal"
        render_kpi_card(
            title=f"{customer_plural} Ativos",
            value=format_int(dto.kpis.active_customers),
            subfooter_left=f"Ticket: {format_brl(dto.kpis.avg_ticket, compact=True)}",
            delta_html=cust_delta,
            accent=cust_accent,
            help_text=(
                f"Quantidade de {customer_plural.lower()} distintos com pedido faturado.<br><br>"
                f"<strong>Ritmo Trimestral (90d):</strong> "
                f"{format_brl(dto.kpis.projected_quarter_revenue_brl, compact=True)}."
            ),
        )


def render_prudence_anomalies_section(dto: ExecutivePageDTO) -> None:
    """Renderiza os principais alertas do Radar de Anomalias lado a lado em formato compacto."""
    if dto.anomalies_df is None or dto.anomalies_df.empty:
        st.info(
            "Nenhuma anomalia crítica detectada no período. Parâmetros operacionais dentro da normalidade."
        )
        return

    records = dto.anomalies_df.head(3).to_dict(orient="records")
    cols = st.columns(len(records))
    for col, row in zip(cols, records, strict=False):
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
            'gap: 0.35rem; margin-bottom: 0.2rem;">'
            f'<span style="font-size: 0.72rem; font-weight: 700; text-transform: uppercase; '
            f'color: {color_border};">[{sev}] {cat}</span>'
            f'<span style="font-size: 0.76rem; font-weight: 600; color: var(--kyb-text);">'
            f"{format_brl(impact, compact=True)}</span>"
            "</div>"
        )
        card_html = (
            f'<div style="background: var(--kyb-card-bg); border-left: 4px solid {color_border}; '
            "border-top: 1px solid var(--kyb-border); border-right: 1px solid var(--kyb-border); "
            "border-bottom: 1px solid var(--kyb-border); border-radius: 6px; padding: 0.45rem 0.65rem; "
            'height: 100%;">'
            f"{card_top}"
            f'<div style="font-size: 0.83rem; font-weight: 600; color: var(--kyb-text); '
            f'margin-bottom: 0.15rem; line-height: 1.25;">{title}</div>'
            f'<div style="font-size: 0.76rem; color: var(--kyb-text-muted); line-height: 1.3;">'
            f"<strong>Ação:</strong> {rec}</div>"
            "</div>"
        )
        with col:
            st.markdown(card_html, unsafe_allow_html=True)


def render_monthly_sales_table_section(dto: ExecutivePageDTO) -> None:
    """Renderiza a tabela detalhada de vendas mês a mês em padrão pt-BR sem corte horizontal."""
    if dto.monthly_sales_table_df is None or dto.monthly_sales_table_df.empty:
        return

    df_view = dto.monthly_sales_table_df.copy()
    rename_map = {
        "month_label": "Mês",
        "orders_count": "Pedidos",
        "total_units": "Unidades",
        "gross_revenue": "Fat. Bruto",
        "mom_gross_pct": "Δ MoM",
        "avg_discount_pct": "Desc. %",
        "net_revenue": "Receita Líq.",
        "contribution_margin": "Margem Contr.",
    }
    cols_order = [c for c in rename_map if c in df_view.columns]
    df_display = df_view[cols_order].rename(columns=rename_map)

    fmt_map: dict[Any, str | Callable[[object], str] | None] = {
        k: fn
        for k, fn in (
            ("Pedidos", fmt_int_cell),
            ("Unidades", fmt_int_cell),
            ("Fat. Bruto", fmt_brl_cell),
            ("Δ MoM", lambda v: fmt_pct_cell(v, decimals=1, signed=True)),
            ("Desc. %", fmt_pct_cell),
            ("Receita Líq.", fmt_brl_cell),
            ("Margem Contr.", fmt_brl_cell),
        )
        if k in df_display.columns
    }
    st.dataframe(
        df_display.style.format(fmt_map),
        use_container_width=True,
        height=185,
        hide_index=True,
    )
