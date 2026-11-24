from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from src.ui.formatting import format_brl, format_int
from src.ui.theme import get_theme_tokens


def _empty_supply_fig(message: str, *, theme_mode: str = "light") -> go.Figure:
    """Retorna figura Plotly vazia padronizada para os gráficos de Supply/PCP."""
    tokens = get_theme_tokens(theme_mode)
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
        font={"size": 13, "color": tokens["text_muted"]},
    )
    fig.update_layout(
        template="kyberna_dark" if theme_mode == "dark" else "kyberna_light",
        title=None,
        height=245,
        margin={"l": 12, "r": 12, "t": 12, "b": 12},
        xaxis={"visible": False},
        yaxis={"visible": False},
    )
    return fig


def stockout_by_family_chart(
    family_supply_df: pd.DataFrame,
    *,
    theme_mode: str = "light",
) -> go.Figure:
    """Barras horizontais empilhadas de receita em risco de ruptura por Família (Curva A vs B/C)."""
    if family_supply_df.empty or float(family_supply_df["protected_revenue_brl"].sum()) <= 0.0:
        return _empty_supply_fig(
            "Sem SKUs abaixo do Ponto de Pedido nos filtros atuais.",
            theme_mode=theme_mode,
        )

    tokens = get_theme_tokens(theme_mode)
    template_name = "kyberna_dark" if theme_mode == "dark" else "kyberna_light"

    df = (
        family_supply_df[family_supply_df["protected_revenue_brl"] > 0.0]
        .sort_values("protected_revenue_brl", ascending=True)
        .copy()
    )
    fams = df["family"].astype(str).tolist()
    curve_a = [float(v) for v in df["curve_a_revenue_brl"]]
    other_bc = [float(v) for v in df["other_curves_revenue_brl"]]
    totals = [float(v) for v in df["protected_revenue_brl"]]
    skus_cnt = [int(v) for v in df["stockout_skus"]]
    boxes_cnt = [int(v) for v in df["suggested_order_boxes"]]

    total_labels = [
        f"{format_brl(tot, compact=True, decimals=1)} · {sk} SKUs"
        for tot, sk in zip(totals, skus_cnt, strict=False)
    ]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            y=fams,
            x=curve_a,
            name="Curva A",
            orientation="h",
            marker={"color": tokens["negative"]},
            customdata=list(zip(skus_cnt, boxes_cnt, strict=False)),
            hovertemplate=(
                "<b>%{y} · Curva A</b><br>Receita em Risco (30d): R$ %{x:,.2f}<br>"
                "SKUs Abaixo ROP: %{customdata[0]} | Ordem: %{customdata[1]} cx<extra></extra>"
            ),
        )
    )
    fig.add_trace(
        go.Bar(
            y=fams,
            x=other_bc,
            name="Curvas B/C",
            orientation="h",
            marker={"color": tokens["warning"]},
            text=total_labels,
            textposition="outside",
            cliponaxis=False,
            hovertemplate=("<b>%{y} · Curvas B/C</b><br>Receita em Risco (30d): R$ %{x:,.2f}<extra></extra>"),
        )
    )

    max_x = max(max(totals, default=0.0) * 1.34, 1.0)
    fig.update_layout(
        template=template_name,
        title=None,
        barmode="stack",
        height=245,
        margin={"l": 14, "r": 58, "t": 16, "b": 16},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1.0},
        xaxis={
            "title": {"text": "Receita Protegida 30d (R$)", "standoff": 8},
            "range": [0, max_x],
            "automargin": True,
        },
        yaxis={"title": None, "automargin": True},
    )
    return fig


def sop_demand_vs_stock_chart(
    family_supply_df: pd.DataFrame,
    *,
    theme_mode: str = "light",
) -> go.Figure:
    """Comparativo S&OP por família: Estoque Atual (un) vs. Demanda Prevista 30d (un)."""
    if family_supply_df.empty:
        return _empty_supply_fig(
            "Sem dados S&OP disponíveis para os filtros selecionados.",
            theme_mode=theme_mode,
        )

    tokens = get_theme_tokens(theme_mode)
    template_name = "kyberna_dark" if theme_mode == "dark" else "kyberna_light"

    df = family_supply_df.sort_values("forecast_30d_units", ascending=True).copy()
    fams = df["family"].astype(str).tolist()
    stock_u = [float(v) for v in df["stock_units"]]
    fc_u = [float(v) for v in df["forecast_30d_units"]]
    wapes = [float(v) for v in df["family_wape_pct"]]
    orders = [int(v) for v in df["suggested_order_boxes"]]

    max_val = max(max(stock_u, default=0.0), max(fc_u, default=0.0)) * 1.24

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            y=fams,
            x=stock_u,
            name="Estoque Atual (un)",
            orientation="h",
            marker={"color": tokens["teal_500"]},
            text=[f"{format_int(round(v))} un" for v in stock_u],
            textposition="outside",
            cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>Estoque Atual: %{x:,.0f} un<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            y=fams,
            x=fc_u,
            name="Demanda Prevista 30d (un)",
            orientation="h",
            marker={"color": tokens["brass_500"]},
            customdata=list(zip(wapes, orders, strict=False)),
            text=[f"{format_int(round(v))} un" for v in fc_u],
            textposition="outside",
            cliponaxis=False,
            hovertemplate=(
                "<b>%{y}</b><br>Demanda Prevista 30d: %{x:,.0f} un<br>"
                "WAPE Família: %{customdata[0]:.1f}% | Ordem ROP: %{customdata[1]} cx<extra></extra>"
            ),
        )
    )

    fig.update_layout(
        template=template_name,
        title=None,
        barmode="group",
        height=245,
        margin={"l": 14, "r": 52, "t": 16, "b": 16},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1.0},
        xaxis={
            "title": {"text": "Unidades (Estoque vs. Previsão 30d)", "standoff": 8},
            "range": [0, max(max_val, 10.0)],
            "automargin": True,
        },
        yaxis={"title": None, "automargin": True},
    )
    return fig
