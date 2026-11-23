from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from src.services.dto import SimulationResult
from src.ui.formatting import format_brl
from src.ui.theme import get_theme_tokens

__all__ = [
    "elasticity_family_chart",
    "profit_curve_chart",
    "tornado_sensitivity_chart",
]


def profit_curve_chart(
    sim_result: SimulationResult,
    current_price_pct: float,
    *,
    theme_mode: str = "light",
) -> go.Figure:
    """Curva Lucro x Preço com marcadores Atual (0%), Simulado e Ótimo."""
    tokens = get_theme_tokens(theme_mode)
    template_name = "kyberna_dark" if theme_mode == "dark" else "kyberna_light"

    df = sim_result.profit_curve_df.copy()
    if df.empty:
        fig = go.Figure()
        fig.update_layout(template=template_name, title=None, height=260)
        return fig

    x_pct = df["delta_price_pct"] * 100.0
    y_margin = df["contribution_margin"]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=x_pct,
            y=y_margin,
            mode="lines",
            name="Lucro Projetado",
            line={"color": tokens["teal_500"], "width": 2.6},
            hovertemplate="Δ Preço: %{x:+.1f}%<br>Margem: R$ %{y:,.0f}<extra></extra>",
        )
    )

    # Ponto Atual (0%)
    fig.add_trace(
        go.Scatter(
            x=[0.0],
            y=[sim_result.contribution_margin_0],
            mode="markers",
            name="Atual (0%)",
            marker={"color": tokens["text_muted"], "size": 9, "symbol": "circle"},
            hovertemplate=(
                f"<b>Atual (0%)</b><br>Margem: {format_brl(sim_result.contribution_margin_0)}<extra></extra>"
            ),
        )
    )

    # Ponto Simulado
    fig.add_trace(
        go.Scatter(
            x=[current_price_pct],
            y=[sim_result.contribution_margin_1],
            mode="markers",
            name="Simulado",
            marker={"color": tokens["brass_500"], "size": 11, "symbol": "diamond"},
            hovertemplate=(
                f"<b>Simulado ({current_price_pct:+.1f}%)</b><br>"
                f"Margem: {format_brl(sim_result.contribution_margin_1)}<extra></extra>"
            ),
        )
    )

    # Ponto Ótimo
    opt_pct = sim_result.optimal_price_change_pct * 100.0
    fig.add_trace(
        go.Scatter(
            x=[opt_pct],
            y=[sim_result.optimal_margin_brl],
            mode="markers",
            name="Ótimo",
            marker={"color": tokens["positive"], "size": 11, "symbol": "star"},
            hovertemplate=(
                f"<b>Ótimo ({opt_pct:+.1f}%)</b><br>"
                f"Margem: {format_brl(sim_result.optimal_margin_brl)}<extra></extra>"
            ),
        )
    )

    fig.update_layout(
        template=template_name,
        title=None,
        height=260,
        margin={"l": 16, "r": 12, "t": 16, "b": 16},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1.0},
        xaxis={"title": {"text": "Variação de Preço de Tabela (%)", "standoff": 8}, "automargin": True},
        yaxis={"title": {"text": "Margem de Contribuição (R$)", "standoff": 8}, "automargin": True},
    )
    return fig


def tornado_sensitivity_chart(
    tornado_df: pd.DataFrame,
    *,
    theme_mode: str = "light",
) -> go.Figure:
    """Gráfico Tornado de sensibilidade individual (impacto R$ na margem)."""
    tokens = get_theme_tokens(theme_mode)
    template_name = "kyberna_dark" if theme_mode == "dark" else "kyberna_light"

    if tornado_df.empty:
        fig = go.Figure()
        fig.update_layout(template=template_name, title=None, height=260)
        return fig

    # Inverter ordem para que o driver de maior swing fique no topo do gráfico horizontal
    df = tornado_df.sort_values("swing_brl", ascending=True).reset_index(drop=True)
    adv_labels = df["adverse_label"].tolist() if "adverse_label" in df.columns else ["Adverso"] * len(df)
    fav_labels = (
        df["favorable_label"].tolist() if "favorable_label" in df.columns else ["Favorável"] * len(df)
    )

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            y=df["driver"],
            x=df["low_delta_brl"],
            customdata=adv_labels,
            orientation="h",
            name="Cenário Adverso",
            marker_color=tokens["negative"],
            hovertemplate="<b>%{y}</b><br>Cenário Adverso (%{customdata}): %{x:+,.0f} R$<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            y=df["driver"],
            x=df["high_delta_brl"],
            customdata=fav_labels,
            orientation="h",
            name="Cenário Favorável",
            marker_color=tokens["positive"],
            hovertemplate="<b>%{y}</b><br>Cenário Favorável (%{customdata}): %{x:+,.0f} R$<extra></extra>",
        )
    )

    fig.update_layout(
        template=template_name,
        title=None,
        height=260,
        barmode="relative",
        margin={"l": 16, "r": 12, "t": 16, "b": 16},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1.0},
        xaxis={"title": {"text": "Impacto na Margem (R$)", "standoff": 8}, "automargin": True},
        yaxis={"title": None, "automargin": True},
    )
    fig.add_vline(x=0.0, line_width=1.2, line_dash="solid", line_color=tokens["chart_zero_line"])
    return fig


def elasticity_family_chart(elasticity_df: pd.DataFrame, *, theme_mode: str = "light") -> go.Figure:
    """Gráfico exclusivo de Elasticidade-Preço por Família (Tela 4 — Temperança)."""
    tokens = get_theme_tokens(theme_mode)
    template_name = "kyberna_dark" if theme_mode == "dark" else "kyberna_light"

    if elasticity_df.empty:
        fig = go.Figure()
        fig.update_layout(template=template_name, title=None, height=245)
        return fig

    df = elasticity_df.sort_values("beta_hat", ascending=True).reset_index(drop=True)
    colors = [tokens["negative"] if float(b) < -1.0 else tokens["positive"] for b in df["beta_hat"].tolist()]
    texts = [
        f"{float(b):.2f} ({c})" for b, c in zip(df["beta_hat"], df["elasticity_classification"], strict=False)
    ]

    fig = go.Figure(
        go.Bar(
            y=df["family"],
            x=df["beta_hat"],
            orientation="h",
            marker={"color": colors},
            text=texts,
            textposition="outside",
            cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>Elasticidade β: %{x:.2f}<extra></extra>",
        )
    )
    min_beta = float(df["beta_hat"].min()) if not df.empty else -1.5
    x_min = min(min_beta * 1.52, -1.65)
    fig.add_vline(
        x=-1.0,
        line_width=1.5,
        line_dash="dash",
        line_color=tokens["warning"],
        annotation_text="Limiar Elástico (-1.0)",
        annotation_position="top left",
        annotation_bgcolor=tokens["surface_card"],
        annotation_borderpad=2,
        annotation_font_color=tokens["warning"],
    )
    fig.update_layout(
        template=template_name,
        title=None,
        height=245,
        margin={"l": 16, "r": 24, "t": 24, "b": 16},
        xaxis={
            "title": {"text": "Elasticidade-Preço (β)", "standoff": 8},
            "range": [x_min, 0.08],
            "automargin": True,
        },
        yaxis={"title": None, "automargin": True},
    )
    return fig
