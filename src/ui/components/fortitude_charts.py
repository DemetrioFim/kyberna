from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from src.services.dto import FortitudeKpisDTO
from src.ui.formatting import format_brl
from src.ui.theme import get_theme_tokens

__all__ = [
    "build_aging_buckets_chart",
    "build_breakeven_curve_chart",
    "build_concentration_chart",
    "build_cycle_comparison_chart",
]


def build_cycle_comparison_chart(
    cycle_df: pd.DataFrame,
    theme_mode: str = "light",
) -> go.Figure:
    """Gera Waterfall do Ciclo Financeiro (PME + PMR - PMP = Ciclo em dias)."""
    tokens = get_theme_tokens(theme_mode)
    template_name = "kyberna_dark" if theme_mode == "dark" else "kyberna_light"
    if cycle_df.empty:
        fig = go.Figure()
        fig.update_layout(template=template_name, height=245, title=None)
        return fig

    text_vals = [
        f"{float(v):+.0f}d" if m == "relative" else f"{float(v):.0f}d"
        for v, m in zip(cycle_df["days"], cycle_df["measure"], strict=False)
    ]
    fig = go.Figure(
        go.Waterfall(
            orientation="v",
            measure=cycle_df["measure"].tolist(),
            x=cycle_df["component"].tolist(),
            y=cycle_df["days"].tolist(),
            text=text_vals,
            textposition="outside",
            cliponaxis=False,
            connector={"line": {"color": tokens["border_subtle"], "width": 1.4, "dash": "dot"}},
            increasing={"marker": {"color": tokens["teal_500"]}},
            decreasing={"marker": {"color": tokens["positive"]}},
            totals={"marker": {"color": tokens["brass_500"]}},
        )
    )
    rel_pos = float(cycle_df.loc[cycle_df["measure"] != "total", "days"].clip(lower=0).sum())
    max_y = max(rel_pos * 1.18, 130.0)
    fig.update_layout(
        template=template_name,
        title=None,
        showlegend=False,
        height=245,
        margin={"l": 16, "r": 16, "t": 20, "b": 20},
        yaxis={"showgrid": False, "showticklabels": False, "title": "", "range": [-10, max_y]},
        waterfallgap=0.28,
    )
    return fig


def build_breakeven_curve_chart(
    curve_df: pd.DataFrame,
    kpis: FortitudeKpisDTO,
    theme_mode: str = "light",
) -> go.Figure:
    """Gera curva acumulada diária (dias 1..30) da Margem vs. Custo Fixo Mensal."""
    tokens = get_theme_tokens(theme_mode)
    template_name = "kyberna_dark" if theme_mode == "dark" else "kyberna_light"
    if curve_df.empty:
        fig = go.Figure()
        fig.update_layout(template=template_name, height=245, title=None)
        return fig

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=curve_df["day_of_month"],
            y=curve_df["cum_contribution_margin_brl"],
            mode="lines",
            name="Margem Acumulada",
            line={"color": tokens["teal_500"], "width": 2.6},
            fill="tozeroy",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=curve_df["day_of_month"],
            y=curve_df["fixed_cost_line_brl"],
            mode="lines",
            name="Custo Fixo Mensal",
            line={"color": tokens["negative"], "width": 2.0, "dash": "dash"},
        )
    )
    fig.add_vline(
        x=kpis.breakeven_day_of_month,
        line_dash="dot",
        line_color=tokens["brass_500"],
        annotation_text=f"Equilíbrio: Dia {kpis.breakeven_day_of_month}",
        annotation_position="top left",
    )
    fig.update_layout(
        template=template_name,
        title=None,
        height=245,
        margin={"l": 16, "r": 16, "t": 24, "b": 24},
        xaxis={"title": "Dia do Mês", "dtick": 5},
        yaxis={"title": "R$ Acumulado", "showgrid": True, "gridcolor": tokens["border_subtle"]},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
    )
    return fig


def build_aging_buckets_chart(
    aging_buckets_df: pd.DataFrame,
    theme_mode: str = "light",
) -> go.Figure:
    """Gera barras horizontais com os 4 estágios de atraso (aging) da carteira."""
    tokens = get_theme_tokens(theme_mode)
    template_name = "kyberna_dark" if theme_mode == "dark" else "kyberna_light"
    if aging_buckets_df.empty:
        fig = go.Figure()
        fig.update_layout(template=template_name, height=245, title=None)
        return fig

    df = aging_buckets_df.sort_values("bucket_order", ascending=False).copy()
    color_map = {
        1: tokens["positive"],
        2: tokens["warning"],
        3: tokens["brass_500"],
        4: tokens["negative"],
    }
    colors = [color_map.get(int(b), tokens["teal_500"]) for b in df["bucket_order"]]
    labels = [
        f"{format_brl(float(r), compact=True, decimals=1)} ({float(p):.1f}% · {int(c)} cli.)"
        for r, p, c in zip(
            df["revenue_12m_brl"], df["revenue_share_pct"], df["customers_count"], strict=False
        )
    ]

    fig = go.Figure(
        go.Bar(
            orientation="h",
            y=df["bucket"].tolist(),
            x=df["revenue_12m_brl"].tolist(),
            marker_color=colors,
            text=labels,
            textposition="outside",
            cliponaxis=False,
        )
    )
    max_x = max(float(df["revenue_12m_brl"].max()) * 1.42, 1.0)
    fig.update_layout(
        template=template_name,
        title=None,
        showlegend=False,
        height=245,
        margin={"l": 12, "r": 24, "t": 16, "b": 18},
        xaxis={"showgrid": False, "showticklabels": False, "title": "", "range": [0, max_x]},
        yaxis={"title": "", "automargin": True},
    )
    return fig


def build_concentration_chart(
    customer_df: pd.DataFrame,
    theme_mode: str = "light",
) -> go.Figure:
    """Gera ranking Pareto horizontal dos Top 10 clientes por receita líquida (12m)."""
    tokens = get_theme_tokens(theme_mode)
    template_name = "kyberna_dark" if theme_mode == "dark" else "kyberna_light"
    if customer_df.empty:
        fig = go.Figure()
        fig.update_layout(template=template_name, height=245, title=None)
        return fig

    top10 = customer_df.head(10).iloc[::-1].copy()
    short_names = [n[:26] + "..." if len(str(n)) > 26 else str(n) for n in top10["customer_name"]]
    labels = [
        f"{format_brl(float(r), compact=True, decimals=1)} ({float(s):.1f}%)"
        for r, s in zip(top10["revenue_12m_brl"], top10["share_pct"], strict=False)
    ]
    fig = go.Figure(
        go.Bar(
            orientation="h",
            y=short_names,
            x=top10["revenue_12m_brl"].tolist(),
            marker_color=tokens["teal_500"],
            text=labels,
            textposition="outside",
            cliponaxis=False,
        )
    )
    max_x = max(float(top10["revenue_12m_brl"].max()) * 1.38, 1.0)
    fig.update_layout(
        template=template_name,
        title=None,
        showlegend=False,
        height=245,
        margin={"l": 12, "r": 20, "t": 16, "b": 16},
        xaxis={"showgrid": False, "showticklabels": False, "title": "", "range": [0, max_x]},
        yaxis={"title": "", "automargin": True},
    )
    return fig
