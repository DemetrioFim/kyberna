from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.services.dto import ExecutivePageDTO, TemperancePageDTO
from src.services.inventory_dto import InventoryPageDTO
from src.ui.components.kpi_card import render_kpi_card
from src.ui.formatting import fmt_brl_cell, fmt_pct_cell, format_brl, format_int
from src.ui.theme import get_theme_tokens


def _cell_stats(matrix_df: pd.DataFrame, abc: str, xyz: str) -> tuple[int, float]:
    """Extrai quantidade de SKUs e % de MC de uma célula da Matriz ABC/XYZ."""
    if matrix_df.empty or "abc_class" not in matrix_df.columns or "xyz_class" not in matrix_df.columns:
        return 0, 0.0
    sub = matrix_df[(matrix_df["abc_class"] == abc) & (matrix_df["xyz_class"] == xyz)]
    if sub.empty:
        return 0, 0.0
    share_col = "margin_share_pct" if "margin_share_pct" in sub.columns else "margin_pct"
    return int(sub["sku_count"].iloc[0]), float(sub[share_col].iloc[0])


def render_admin_portfolio_kpis(exec_dto: ExecutivePageDTO, inv_dto: InventoryPageDTO) -> None:
    """Renderiza os 5 KPIs da Aba 1 (Portfólio & Curva ABC/XYZ) de Prudência Administrativa."""
    skus_df = exec_dto.abc_xyz_skus_df
    matrix_df = exec_dto.abc_xyz_matrix_df
    sku_total = len(skus_df) if not skus_df.empty else len(inv_dto.sku_options_df)
    fam_count = int(skus_df["family"].nunique()) if not skus_df.empty and "family" in skus_df.columns else 0

    share_col = "margin_share_pct" if "margin_share_pct" in matrix_df.columns else "margin_pct"
    curva_a_pct = (
        float(matrix_df[matrix_df["abc_class"] == "A"][share_col].sum())
        if not matrix_df.empty and "abc_class" in matrix_df.columns and share_col in matrix_df.columns
        else 0.0
    )
    ax_skus, ax_share = _cell_stats(matrix_df, "A", "X")
    cz_skus, cz_share = _cell_stats(matrix_df, "C", "Z")
    orders_str = format_int(exec_dto.kpis.total_orders)
    boxes_str = format_int(exec_dto.kpis.total_boxes)

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        render_kpi_card(
            title="SKUs Ativos no Portfólio",
            value=f"{format_int(sku_total)} SKUs",
            subfooter_left=f"{fam_count} famílias ativas",
            accent="teal",
            help_text="Total de SKUs ativos no catálogo que registraram movimentação no filtro atual.",
        )
    with c2:
        render_kpi_card(
            title="Margem na Curva A",
            value=f"{curva_a_pct:.1f}%",
            subfooter_left="Meta ABC: Top 80% MC",
            accent="green",
            help_text="Fatia da Margem de Contribuição concentrada nos SKUs prioritários de Classe A.",
        )
    with c3:
        render_kpi_card(
            title="SKUs Classe AX (Core)",
            value=f"{format_int(ax_skus)} SKUs",
            subfooter_left=f"{ax_share:.1f}% da Margem Total",
            accent="teal",
            help_text=("Produtos de alta margem (A) e demanda regular (X): política JIT / ruptura zero."),
        )
    with c4:
        render_kpi_card(
            title="SKUs Classe CZ (Cauda)",
            value=f"{format_int(cz_skus)} SKUs",
            subfooter_left=f"{cz_share:.1f}% da Margem Total",
            accent="alert_warn" if cz_skus > 40 else "brass",
            help_text=(
                "Itens de baixa margem (C) e giro intermitente (Z): candidatos a venda sob encomenda."
            ),
        )
    with c5:
        render_kpi_card(
            title="Ticket Médio por Pedido",
            value=format_brl(exec_dto.kpis.avg_ticket, compact=True),
            subfooter_left=f"{orders_str} pedidos · {boxes_str} cx",
            accent="brass",
            help_text="Valor bruto médio faturado por pedido e volume expedido em caixas master.",
        )


def render_admin_inventory_kpis(
    temp_dto: TemperancePageDTO,
    inv_dto: InventoryPageDTO,
    *,
    is_scoped: bool = False,
) -> None:
    """Renderiza os 5 KPIs da Aba 2 (Estoque, Ruptura & Capital Travado) de Prudência."""
    t_k = temp_dto.kpis
    i_k = inv_dto.kpis
    locked_cap = i_k.locked_capital_brl if i_k.locked_capital_brl > 0 else t_k.locked_capital_brl
    locked_cnt = i_k.locked_skus_count if i_k.locked_skus_count > 0 else t_k.locked_skus_count
    rup_a_skus = (
        i_k.stockout_curve_a_skus_count
        if i_k.stockout_curve_a_skus_count > 0
        else t_k.stockout_risk_skus_count
    )
    prot_rev = i_k.protected_revenue_brl if i_k.protected_revenue_brl > 0 else t_k.stockout_risk_revenue_brl
    stock_total_str = format_brl(i_k.total_stock_value_brl, compact=True, decimals=1)
    scope_suffix = " · Armazém global" if is_scoped else ""

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        render_kpi_card(
            title="Capital Travado (>120d)",
            value=format_brl(locked_cap, compact=True, decimals=1),
            subfooter_left=f"Estoque total: {stock_total_str}{scope_suffix}",
            accent="gold",
            help_text=(
                "Capital imobilizado a custo contábil no estoque excedente acima de 120 dias de cobertura "
                "(posição corporativa do armazém)."
            ),
        )
    with c2:
        render_kpi_card(
            title="SKUs Imobilizados (>120d)",
            value=f"{format_int(locked_cnt)} SKUs",
            subfooter_left=f"Saudáveis: {format_int(i_k.healthy_skus_count)} SKUs",
            accent="alert_warn" if locked_cnt > 0 else "green",
            help_text="Quantidade de SKUs com excesso crônico de cobertura, exigindo campanhas de saldo.",
        )
    with c3:
        render_kpi_card(
            title="Ruptura Iminente (Curva A)",
            value=f"{format_int(rup_a_skus)} SKUs",
            subfooter_left=f"Total abaixo ROP: {format_int(i_k.stockout_risk_skus_count)} SKUs",
            accent="alert_neg",
            help_text=(
                "SKUs de Curva A com estoque abaixo do Ponto de Pedido (Lead Time + Estoque de Segurança). "
                "O rodapé indica o total de todas as curvas (A/B/C) abaixo do ROP."
            ),
        )
    with c4:
        curva_a_rev = format_brl(i_k.stockout_curve_a_revenue_brl, compact=True, decimals=1)
        render_kpi_card(
            title="Receita Protegida (Ruptura)",
            value=format_brl(prot_rev, compact=True, decimals=1),
            subfooter_left=f"Curva A: {curva_a_rev}",
            accent="alert_neg",
            help_text=(
                "Faturamento potencial preservado nos próximos 30 dias ao executar o ressuprimento imediato "
                "de todos os itens abaixo do ROP."
            ),
        )
    with c5:
        render_kpi_card(
            title="Ordem Sugerida (Reposição)",
            value=f"{format_int(i_k.suggested_order_boxes_total)} cx",
            subfooter_left="Caixas master abaixo do ROP",
            accent="teal",
            help_text=(
                "Soma de caixas master recomendadas para normalizar todos os itens abaixo do Ponto de Pedido."
            ),
        )


def render_admin_demand_policy_kpis(
    exec_dto: ExecutivePageDTO,
    temp_dto: TemperancePageDTO,
    inv_dto: InventoryPageDTO,
) -> None:
    """Renderiza os 5 KPIs da Aba 3 (Demanda 30d & Conformidade de Alçadas) de Prudência."""
    t_k = temp_dto.kpis
    sku_fc_cnt = len(inv_dto.sku_options_df)
    anom_cnt = len(exec_dto.anomalies_df) if exec_dto.anomalies_df is not None else 0

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        render_kpi_card(
            title="Projeção de Demanda (30d)",
            value=format_brl(inv_dto.kpis.forecast_30d_revenue_brl, compact=True, decimals=2),
            subfooter_left=f"{format_int(inv_dto.kpis.forecast_30d_units_total)} un previstas (30d)",
            accent="teal",
            help_text=(
                "Soma da demanda prevista pelo StatsForecast nos próximos 30 dias valorizada a preço de "
                "lista para os SKUs filtrados."
            ),
        )
    with c2:
        render_kpi_card(
            title="SKUs no Motor Forecast",
            value=f"{format_int(sku_fc_cnt)} SKUs",
            subfooter_left="Modelos AutoETS / Croston",
            accent="green",
            help_text=(
                "Quantidade de SKUs com previsão estatística diária de 30 dias e bandas de confiança 80%/95%."
            ),
        )
    with c3:
        render_kpi_card(
            title="Descontos Fora de Tabela",
            value=format_brl(t_k.excess_discount_brl, compact=True, decimals=1),
            subfooter_left="Alçadas P=3% · M=6,5% · G=10,5%",
            accent="alert_neg",
            help_text="Concessões acima do teto comercial autorizado para o porte de cada cliente.",
        )
    with c4:
        render_kpi_card(
            title="Peso Fora da Política",
            value=f"{t_k.excess_discount_pct_of_discount:.1f}%",
            subfooter_left=f"Erosão total: {format_brl(t_k.total_commercial_erosion_brl, compact=True)}",
            accent="alert_warn",
            help_text="Percentual dos descontos totais concedidos sem respaldo na política de alçadas.",
        )
    with c5:
        render_kpi_card(
            title="Exceções Operacionais",
            value=f"{anom_cnt} alertas",
            subfooter_left="Radar semanal automático",
            accent="alert_warn" if anom_cnt > 0 else "green",
            help_text="Quantidade de desvios críticos detectados nas regras de auditoria operacional.",
        )


def render_sku_portfolio_table(exec_dto: ExecutivePageDTO) -> None:
    """Renderiza a tabela operacional de Portfólio de SKUs com scroll interno."""
    if exec_dto.abc_xyz_skus_df.empty:
        st.info("Nenhum SKU disponível para a seleção atual.")
        return

    cols_src = [
        c
        for c in (
            "product_name",
            "family",
            "abc_xyz_class",
            "gross_revenue",
            "contribution_margin",
            "margin_pct",
            "policy",
        )
        if c in exec_dto.abc_xyz_skus_df.columns
    ]
    sku_view = exec_dto.abc_xyz_skus_df[cols_src].rename(
        columns={
            "product_name": "Produto",
            "family": "Família",
            "abc_xyz_class": "Célula",
            "gross_revenue": "Fat. Bruto",
            "contribution_margin": "Margem Líq.",
            "margin_pct": "Margem %",
            "policy": "Política Operacional",
        }
    )
    fmt_map: dict[Any, str | Callable[[object], str] | None] = {
        k: fn
        for k, fn in (
            ("Fat. Bruto", fmt_brl_cell),
            ("Margem Líq.", fmt_brl_cell),
            ("Margem %", fmt_pct_cell),
        )
        if k in sku_view.columns
    }
    st.dataframe(
        sku_view.style.format(fmt_map),
        use_container_width=True,
        height=185,
        hide_index=True,
    )


def family_policy_violations_chart(df: pd.DataFrame, *, theme_mode: str = "light") -> go.Figure:
    """Gráfico horizontal de descontos fora do teto por família (1. Prudência — Aba 3)."""
    tokens = get_theme_tokens(theme_mode)
    template_name = "kyberna_dark" if theme_mode == "dark" else "kyberna_light"

    if df.empty or "family" not in df.columns or "excess_discount_brl" not in df.columns:
        fig = go.Figure()
        fig.update_layout(template=template_name, title=None, height=245)
        return fig

    top_df = df.head(8).iloc[::-1].copy()
    excess_vals = [float(v) for v in top_df["excess_discount_brl"]]
    avg_disc_vals = (
        [float(v) for v in top_df["avg_discount_pct"]]
        if "avg_discount_pct" in top_df.columns
        else [0.0] * len(top_df)
    )
    bar_colors = [tokens["negative"] if v > 0 else tokens["teal_500"] for v in excess_vals]
    texts = [
        f"{format_brl(ex, compact=True, decimals=1)} ({disc:.1f}%)"
        for ex, disc in zip(excess_vals, avg_disc_vals, strict=False)
    ]

    fig = go.Figure(
        go.Bar(
            x=excess_vals,
            y=top_df["family"].astype(str).tolist(),
            orientation="h",
            marker={"color": bar_colors},
            customdata=avg_disc_vals,
            text=texts,
            textposition="outside",
            cliponaxis=False,
            hovertemplate=(
                "<b>%{y}</b><br>Excesso Fora do Teto: R$ %{x:,.2f}<br>"
                "Desconto Médio: %{customdata:.1f}%<extra></extra>"
            ),
        )
    )
    max_x = max(max(excess_vals, default=0.0) * 1.28, 1.0)
    fig.update_layout(
        template=template_name,
        title=None,
        height=245,
        margin={"l": 16, "r": 64, "t": 12, "b": 16},
        xaxis={
            "title": {"text": "Excesso Fora do Teto (R$)", "standoff": 8},
            "range": [0, max_x],
            "automargin": True,
        },
        yaxis={"title": None, "automargin": True},
    )
    return fig
