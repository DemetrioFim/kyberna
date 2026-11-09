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

    # Linha guia de 45 graus (y = x), linha de alerta ideal (y = 1.1x) e risco crítico (y = 1.5x)
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
            y=[val * 1.1 for val in line_x],
            mode="lines",
            line={"color": tokens["warning"], "dash": "dot", "width": 1.5},
            name="Janela Ideal Pré-Churn (y = 1.1x)",
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
            f"<b>{name}</b><br>"
            f"UF: {st} | RCA: {rep}<br>"
            f"Dias sem comprar: {int(rec)}d<br>"
            f"Ciclo esperado: {float(exp):.1f}d<br>"
            f"Atraso (Delay Ratio): {float(del_r):.2f}x<br>"
            f"R$ em Risco: {format_brl(float(at_risk))}"
            for name, st, rep, rec, exp, del_r, at_risk in zip(
                subset["customer_name"],
                subset["state"],
                subset["sales_rep_name"],
                subset["recency_days"],
                subset["expected_cycle_days"],
                subset["delay_ratio"],
                subset["annual_revenue_at_risk"],
                strict=False,
            )
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
                    "line": {"color": tokens.get("surface_card", "#ffffff"), "width": 1},
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

    # Ponderação preferencial por Margem Líquida (R$) com fallback para Faturamento
    plot_df = df.copy()
    if "contribution_margin" in plot_df.columns and (plot_df["contribution_margin"] > 0).any():
        plot_df["size_val"] = np.maximum(plot_df["contribution_margin"], 1.0)
        size_label = "Margem Líquida"
    else:
        plot_df["size_val"] = np.maximum(plot_df["gross_revenue"], 1.0)
        size_label = "Faturamento"

    has_ltv = "estimated_ltv_brl" in plot_df.columns

    hover_dict: dict[str, bool | str] = {
        "size_val": False,
        "customer_count": True,
        "gross_revenue": ":,.2f",
        "contribution_margin": ":,.2f",
        "margin_pct": ":.1f",
        "avg_ticket": ":,.2f",
    }
    if has_ltv:
        hover_dict["estimated_ltv_brl"] = ":,.2f"

    fig = px.treemap(
        plot_df,
        path=["rfm_segment"],
        values="size_val",
        color="margin_pct",
        color_continuous_scale="Tealgrn",
        hover_data=hover_dict,
    )

    fig.update_layout(
        template=template_name,
        title=f"<b>Mapa de Segmentação RFM B2B (Tamanho = {size_label} | Cor = Margem %)</b>",
        margin={"l": 20, "r": 20, "t": 50, "b": 20},
    )

    hovertemplate = (
        "<b>Segmento: %{label}</b><br>Margem Líquida: R$ %{value:,.2f}<br>Margem %: %{color:.1f}%<br>"
    )
    if has_ltv:
        hovertemplate += "LTV Estimado Médio: R$ %{customdata[5]:,.2f}<br>"
    hovertemplate += "<extra></extra>"

    fig.update_traces(
        textinfo="label+value+percent root",
        hovertemplate=hovertemplate,
    )
    return fig


def cycle_health_funnel_chart(
    df: pd.DataFrame,
    theme_mode: str = "light",
) -> go.Figure:
    """Gera o funil horizontal de saúde da carteira por estágios do ciclo de recompra."""
    tokens = get_theme_tokens(theme_mode)
    template_name = "kyberna_dark" if theme_mode == "dark" else "kyberna_light"

    if df.empty:
        fig = go.Figure()
        fig.update_layout(template=template_name, title="Sem dados de ciclo de recompra")
        return fig

    sorted_df = df.sort_values(by="order_seq", ascending=True) if "order_seq" in df.columns else df

    colors = [
        tokens.get("positive", "#0d9488"),
        tokens.get("warning", "#eab308"),
        "#f97316",
        tokens.get("negative", "#e11d48"),
    ]

    fig = go.Figure()

    lbl_col = (
        "label"
        if "label" in sorted_df.columns
        else "cycle_stage"
        if "cycle_stage" in sorted_df.columns
        else "stage"
        if "stage" in sorted_df.columns
        else None
    )
    cnt_col = (
        "customers_count"
        if "customers_count" in sorted_df.columns
        else "customer_count"
        if "customer_count" in sorted_df.columns
        else None
    )
    shr_col = (
        "share_pct"
        if "share_pct" in sorted_df.columns
        else "customer_share_pct"
        if "customer_share_pct" in sorted_df.columns
        else None
    )
    rv_col = (
        "revenue_brl"
        if "revenue_brl" in sorted_df.columns
        else "annual_revenue_brl"
        if "annual_revenue_brl" in sorted_df.columns
        else None
    )

    labels = sorted_df[lbl_col].tolist() if lbl_col else []
    counts = sorted_df[cnt_col].tolist() if cnt_col else []
    shares = sorted_df[shr_col].tolist() if shr_col else []
    revenues = sorted_df[rv_col].tolist() if rv_col else []

    for idx, (label, cust, share, rev) in enumerate(zip(labels, counts, shares, revenues, strict=False)):
        color = colors[idx % len(colors)]
        hover_txt = (
            f"<b>{label}</b><br>"
            f"Clientes: {int(cust):,} ({float(share):.1f}%)<br>"
            f"Faturamento Anual: {format_brl(float(rev))}<br>"
            "<extra></extra>"
        )

        fig.add_trace(
            go.Bar(
                y=["Carteira Ativa"],
                x=[share],
                name=label,
                orientation="h",
                marker={"color": color},
                text=f"{share:.1f}% ({cust})",
                textposition="inside",
                hovertemplate=hover_txt,
            )
        )

    fig.update_layout(
        template=template_name,
        barmode="stack",
        title="<b>Saúde da Carteira · Distribuição por Estágio do Ciclo de Recompra</b>",
        xaxis={"title": "Participação na Base (%)", "range": [0, 100]},
        yaxis={"showticklabels": False},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.05, "xanchor": "center", "x": 0.5},
        height=220,
        margin={"l": 30, "r": 30, "t": 60, "b": 30},
    )
    return fig


def white_space_heatmap(
    df: pd.DataFrame,
    theme_mode: str = "light",
) -> go.Figure:
    """Gera o Heatmap de potencial financeiro da Matriz White Space (Família x Segmento RFM)."""
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
        [format_brl(val, compact=True, decimals=1) if val > 0 else "-" for val in row] for row in z_values
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
                "Família: %{y}<br>Segmento: %{x}<br>Potencial Estimado: R$ %{z:,.2f}<br><extra></extra>"
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
