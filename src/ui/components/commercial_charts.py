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

    # Limita o eixo X ao intervalo operacional [0, 95d] para evitar achatamento por outliers
    p95_x = float(np.percentile(df["expected_cycle_days"], 95))
    cap_x = min(max(60.0, p95_x * 1.15), 95.0)
    outliers_count = int((df["expected_cycle_days"] > cap_x).sum())
    max_val = min(max(float(df["expected_cycle_days"].max()), float(df["recency_days"].max()), 60.0), cap_x)
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

    if outliers_count > 0:
        fig.add_annotation(
            text=f"+{outliers_count} cliente(s) com ciclo > {cap_x:.0f}d (ver tabela)",
            x=0.98,
            y=0.04,
            xref="paper",
            yref="paper",
            showarrow=False,
            font={"size": 10, "color": tokens["text_muted"]},
        )

    fig.update_layout(
        template=template_name,
        title=None,
        xaxis={
            "title": {"text": "Ciclo Médio Histórico (dias)", "standoff": 8},
            "range": [0, cap_x],
            "automargin": True,
        },
        yaxis={"title": {"text": "Dias sem Comprar (Recência)", "standoff": 8}, "automargin": True},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        height=245,
        margin={"l": 24, "r": 24, "t": 28, "b": 28},
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
    else:
        plot_df["size_val"] = np.maximum(plot_df["gross_revenue"], 1.0)

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
        title=None,
        coloraxis_colorbar={"title": "Margem %", "thickness": 12},
        height=245,
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
    )

    hovertemplate = (
        "<b>Segmento: %{label}</b><br>Margem Líquida: R$ %{value:,.2f}<br>Margem %: %{color:.1f}%<br>"
    )
    if has_ltv:
        hovertemplate += "LTV Estimado Médio: R$ %{customdata[5]:,.2f}<br>"
    hovertemplate += "<extra></extra>"

    fig.update_traces(
        texttemplate="<b>%{label}</b><br>R$ %{value:,.0f}<br>%{percentRoot:.1%}",
        textposition="middle center",
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
        title=None,
        xaxis={"title": "Participação na Base (%)", "range": [0, 100]},
        yaxis={"showticklabels": False},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.05, "xanchor": "center", "x": 0.5},
        height=220,
        margin={"l": 30, "r": 30, "t": 38, "b": 30},
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
        title=None,
        xaxis_title="Segmento RFM do Lojista",
        yaxis_title="Família Recomendada",
        height=245,
        margin={"l": 24, "r": 24, "t": 12, "b": 28},
    )
    return fig


def white_space_family_chart(
    df: pd.DataFrame,
    theme_mode: str = "light",
) -> go.Figure:
    """Gráfico adjacente ao Modelo Apriori: potencial incremental (R$) por família recomendada."""
    tokens = get_theme_tokens(theme_mode)
    template_name = "kyberna_dark" if theme_mode == "dark" else "kyberna_light"
    if df.empty or "recommended_family" not in df.columns:
        fig = go.Figure()
        fig.update_layout(template=template_name, title="Sem dados de White Space por família")
        return fig

    agg = (
        df.groupby("recommended_family", as_index=False)
        .agg({"potential_revenue_brl": "sum"})
        .sort_values("potential_revenue_brl", ascending=True)
        .reset_index(drop=True)
    )
    texts = [format_brl(float(v), compact=True, decimals=1) for v in agg["potential_revenue_brl"]]
    max_x = max(float(agg["potential_revenue_brl"].max()) * 1.28, 1.0)
    fig = go.Figure(
        go.Bar(
            y=agg["recommended_family"].tolist(),
            x=agg["potential_revenue_brl"].tolist(),
            orientation="h",
            marker_color=tokens["teal_500"],
            text=texts,
            textposition="outside",
            cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>Potencial White Space: R$ %{x:,.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        template=template_name,
        title=None,
        xaxis={"title": "Potencial Incremental (R$)", "range": [0, max_x]},
        yaxis={"title": None},
        height=245,
        margin={"l": 16, "r": 24, "t": 12, "b": 28},
    )
    return fig
