from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from src.ui.formatting import format_brl
from src.ui.theme import get_theme_tokens


def cycle_delay_scatter(
    df: pd.DataFrame,
    theme_mode: str = "light",
) -> go.Figure:
    """Gera o gráfico de dispersão: Dias sem Comprar vs. Ciclo Médio Histórico com linha de 45°.

    Destaque visual do atraso relativo (delay ratio) de recompra com cores por status de risco.
    """
    tokens = get_theme_tokens(theme_mode)
    template_name = "kyberna_dark" if theme_mode == "dark" else "kyberna_light"

    if df.empty:
        fig = go.Figure()
        fig.update_layout(template=template_name, title="Sem clientes no radar de ciclo")
        return fig

    status_colors = {
        "No Ciclo": tokens["positive"],
        "Atenção": tokens["warning"],
        "Em Risco Imediato": "#f97316",  # Laranja de alta visibilidade
        "Adormecido / Perdido": tokens["negative"],
    }

    fig = go.Figure()

    # Linha guia de 45 graus (y = x) e linha de risco crítico (y = 1.5x)
    max_val = max(float(df["expected_cycle_days"].max()), float(df["recency_days"].max()), 100.0)
    line_x = [0, max_val]

    fig.add_trace(
        go.Scatter(
            x=line_x,
            y=line_x,
            mode="lines",
            line={"color": tokens["border_subtle"], "dash": "dash", "width": 1.5},
            name="No Ciclo (y = x)",
            hoverinfo="skip",
        )
    )

    fig.add_trace(
        go.Scatter(
            x=line_x,
            y=[val * 1.5 for val in line_x],
            mode="lines",
            line={"color": "#f97316", "dash": "dot", "width": 1.5},
            name="Risco Crítico (y = 1.5x)",
            hoverinfo="skip",
        )
    )

    for status, color in status_colors.items():
        subset = df[df["risk_status"] == status]
        if subset.empty:
            continue

        hover_texts = [
            f"<b>{row['customer_name']}</b><br>"
            f"UF: {row['state']} | RCA: {row['sales_rep_name']}<br>"
            f"Dias sem comprar: {int(row['recency_days'])}d<br>"
            f"Ciclo esperado: {float(row['expected_cycle_days']):.1f}d<br>"
            f"Atraso (Delay Ratio): {float(row['delay_ratio']):.2f}x<br>"
            f"R$ em Risco: {format_brl(float(row['annual_revenue_at_risk']))}"
            for _, row in subset.iterrows()
        ]

        fig.add_trace(
            go.Scatter(
                x=subset["expected_cycle_days"],
                y=subset["recency_days"],
                mode="markers",
                name=status,
                text=hover_texts,
                hoverinfo="text",
                marker={
                    "color": color,
                    "size": 10,
                    "opacity": 0.85,
                    "line": {"color": tokens["card_bg"], "width": 1},
                },
            )
        )

    fig.update_layout(
        template=template_name,
        title="<b>Dispersão de Recência vs. Ciclo Médio (Atraso de Recompra)</b>",
        xaxis_title="Ciclo Médio Histórico (dias)",
        yaxis_title="Dias sem Comprar (Recência)",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        margin={"l": 40, "r": 40, "t": 60, "b": 40},
    )
    return fig


def rfm_treemap(
    df: pd.DataFrame,
    theme_mode: str = "light",
) -> go.Figure:
    """Gera o Treemap de valor e participação dos 9 segmentos RFM B2B."""
    template_name = "kyberna_dark" if theme_mode == "dark" else "kyberna_light"

    if df.empty:
        fig = go.Figure()
        fig.update_layout(template=template_name, title="Sem dados para o mapa RFM")
        return fig

    # Garante valores positivos para o tamanho dos blocos
    plot_df = df.copy()
    plot_df["size_val"] = np.maximum(plot_df["gross_revenue"], 1.0)

    fig = px.treemap(
        plot_df,
        path=["rfm_segment"],
        values="size_val",
        color="margin_pct",
        color_continuous_scale="Tealgrn",
        hover_data={
            "size_val": False,
            "customer_count": True,
            "gross_revenue": ":,.2f",
            "contribution_margin": ":,.2f",
            "margin_pct": ":.1f",
            "avg_ticket": ":,.2f",
        },
    )

    fig.update_layout(
        template=template_name,
        title="<b>Mapa de Segmentação RFM B2B (Tamanho = Faturamento | Cor = Margem %)</b>",
        margin={"l": 20, "r": 20, "t": 50, "b": 20},
    )
    fig.update_traces(
        textinfo="label+value+percent root",
        hovertemplate=(
            "<b>Segmento: %{label}</b><br>"
            "Faturamento: R$ %{value:,.2f}<br>"
            "Margem Líquida: %{color:.1f}%<br>"
            "<extra></extra>"
        ),
    )
    return fig


def white_space_heatmap(
    df: pd.DataFrame,
    theme_mode: str = "light",
) -> go.Figure:
    """Gera o Heatmap de potencial financeiro da Matriz White Space (Família x Segmento RFM)."""
    tokens = get_theme_tokens(theme_mode)
    template_name = "kyberna_dark" if theme_mode == "dark" else "kyberna_light"

    if df.empty:
        fig = go.Figure()
        fig.update_layout(template=template_name, title="Sem oportunidades White Space no filtro")
        return fig

    pivot = df.pivot_table(
        index="recommended_family",
        columns="rfm_segment",
        values="potential_revenue_brl",
        aggfunc="sum",
        fill_value=0.0,
    )

    z_values = pivot.to_numpy()
    x_labels = list(pivot.columns)
    y_labels = list(pivot.index)

    # Textos formatados para hover e exibição interna
    custom_text = [
        [format_brl(val, compact=True, decimals=1) if val > 0 else "-" for val in row]
        for row in z_values
    ]

    fig = go.Figure(
        data=go.Heatmap(
            z=z_values,
            x=x_labels,
            y=y_labels,
            text=custom_text,
            texttemplate="%{text}",
            textfont={"size": 11},
            colorscale="Teal",
            colorbar={"title": "Potencial R$"},
            hoverongaps=False,
            hovertemplate=(
                "Família: %{y}<br>"
                "Segmento: %{x}<br>"
                "Potencial Estimado: R$ %{z:,.2f}<br>"
                "<extra></extra>"
            ),
        )
    )

    fig.update_layout(
        template=template_name,
        title="<b>Matriz White Space: Potencial de Cross-Sell por Família e Segmento RFM</b>",
        xaxis_title="Segmento RFM do Lojista",
        yaxis_title="Família Recomendada (Cross-Sell)",
        margin={"l": 40, "r": 40, "t": 60, "b": 40},
    )
    return fig
