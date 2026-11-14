from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from src.ui.formatting import format_brl
from src.ui.theme import get_theme_tokens


def waterfall_margin(
    steps_df: pd.DataFrame,
    theme_mode: str = "light",
) -> go.Figure:
    """Gera o gráfico Waterfall de decomposição completa da Margem de Contribuição Líquida.

    Espera DataFrame com as colunas:
        - `label`: Nome descritivo da etapa (ex: 'Faturamento Bruto', 'Descontos').
        - `amount`: Valor monetário em R$ (positivo para ganhos, negativo para deduções).
        - `measure`: 'absolute', 'relative' ou 'total'.
    """
    tokens = get_theme_tokens(theme_mode)
    template_name = "kyberna_dark" if theme_mode == "dark" else "kyberna_light"

    if steps_df.empty:
        fig = go.Figure()
        fig.update_layout(template=template_name, title="Sem dados para o Waterfall")
        return fig

    text_values = [format_brl(float(val), compact=True, decimals=1) for val in steps_df["amount"]]
    if "pct_of_gross" in steps_df.columns:
        hover_extra = [
            f"{abs(float(pct)):.1f}% do Faturamento Bruto" if m == "relative" else "Marco DRE"
            for pct, m in zip(steps_df["pct_of_gross"], steps_df["measure"], strict=False)
        ]
    else:
        hover_extra = ["Subtotal / Base" if m != "relative" else "Dedução" for m in steps_df["measure"]]

    short_x_map = {
        "1. Faturamento Bruto": "1. Fat.<br>Bruto",
        "2. Descontos Comerciais": "2. Desc.",
        "3. Receita Faturada": "3. Rec.<br>Faturada",
        "4. Impostos (ICMS/PIS/COFINS)": "4. Impostos",
        "5. Receita Líquida": "5. Rec.<br>Líquida",
        "6. CPV (Custo Mercadoria)": "6. CPV",
        "7. Comissões RCA": "7. Comiss.",
        "8. Frete CIF Expedição": "8. Frete<br>CIF",
        "9. Margem Contribuição": "9. Margem<br>Contrib.",
    }
    x_labels = [short_x_map.get(str(lbl), str(lbl)) for lbl in steps_df["label"].tolist()]

    fig = go.Figure(
        go.Waterfall(
            name="Waterfall",
            orientation="v",
            measure=steps_df["measure"].tolist(),
            x=x_labels,
            y=steps_df["amount"].tolist(),
            text=text_values,
            customdata=hover_extra,
            textposition="outside",
            textfont={"size": 11},
            cliponaxis=False,
            hovertemplate="<b>%{x}</b><br>Valor: R$ %{y:,.2f}<br>%{customdata}<extra></extra>",
            connector={"line": {"color": tokens["border_subtle"], "width": 1.5, "dash": "dot"}},
            increasing={"marker": {"color": tokens["teal_500"]}},
            decreasing={"marker": {"color": tokens["negative"]}},
            totals={"marker": {"color": tokens["brass_500"]}},
        )
    )

    fig.update_layout(
        template=template_name,
        title=None,
        showlegend=False,
        height=245,
        margin={"l": 16, "r": 16, "t": 22, "b": 24},
        xaxis={"tickangle": 0, "tickfont": {"size": 10}},
        yaxis={"showgrid": False, "showticklabels": False, "title": ""},
        waterfallgap=0.25,
    )
    return fig


def dual_trend(
    monthly_df: pd.DataFrame,
    theme_mode: str = "light",
    target_margin_pct: float | None = 26.0,
) -> go.Figure:
    """Gera o gráfico de Tendência Dupla: Faturamento Bruto (Barras) x Margem Líquida % (Linha).

    Evidencia visualmente o 'efeito boca de jacaré' (quando a receita cresce mas a margem percentual cai).
    Espera colunas:
        - `month_label`: Rótulo do mês (ex: 'Jan/24', 'Fev/24').
        - `gross_revenue`: Receita bruta mensal (R$).
        - `margin_pct`: Margem de contribuição líquida percentual (ex: 27.5).
        - `avg_discount_pct` (opcional): Desconto médio praticado no mês.
    """
    tokens = get_theme_tokens(theme_mode)
    template_name = "kyberna_dark" if theme_mode == "dark" else "kyberna_light"

    if monthly_df.empty:
        fig = go.Figure()
        fig.update_layout(template=template_name, title="Sem dados de tendência")
        return fig

    x_vals = monthly_df["month_label"].tolist()

    # Barra: Faturamento Bruto (Eixo Primário Y1)
    bar_trace = go.Bar(
        x=x_vals,
        y=monthly_df["gross_revenue"].tolist(),
        name="Faturamento Bruto (R$)",
        marker_color=tokens["teal_500"],
        opacity=0.85,
        yaxis="y",
        hovertemplate="<b>%{x}</b><br>Faturamento: R$ %{y:,.2f}<extra></extra>",
    )

    # Linha: Margem Líquida % (Eixo Secundário Y2)
    has_disc = "avg_discount_pct" in monthly_df.columns
    hover_line = (
        "<b>%{x}</b><br>Margem: %{y:.1f}%<br>Desconto Médio: %{customdata:.1f}%<extra></extra>"
        if has_disc
        else "<b>%{x}</b><br>Margem Líquida: %{y:.1f}%<extra></extra>"
    )
    custom_d = monthly_df["avg_discount_pct"].tolist() if has_disc else None

    line_trace = go.Scatter(
        x=x_vals,
        y=monthly_df["margin_pct"].tolist(),
        customdata=custom_d,
        name="Margem Líquida (%)",
        mode="lines+markers",
        line={"color": tokens["brass_500"], "width": 3},
        marker={"size": 8, "color": tokens["brass_500"]},
        yaxis="y2",
        hovertemplate=hover_line,
    )

    fig = go.Figure(data=[bar_trace, line_trace])

    if target_margin_pct is not None:
        fig.add_hline(
            y=target_margin_pct,
            yref="y2",
            line_dash="dash",
            line_color=tokens["warning"],
            line_width=2,
            annotation_text=f"Meta: {target_margin_pct:.1f}%",
            annotation_position="top left",
            annotation_yshift=8,
            annotation_bgcolor=tokens["surface_card"],
            annotation_borderpad=2,
            annotation_font_color=tokens["warning"],
        )

    m_min = float(monthly_df["margin_pct"].min())
    m_max = float(monthly_df["margin_pct"].max())
    y2_low = min(15.0, m_min - 3.0)
    y2_high = max(35.0, m_max + 3.0)

    fig.update_layout(
        template=template_name,
        title=None,
        yaxis={"title": "Faturamento (R$)", "side": "left", "showgrid": True},
        yaxis2={
            "title": "Margem (%)",
            "side": "right",
            "overlaying": "y",
            "range": [y2_low, y2_high],
            "tickformat": ".1f",
            "ticksuffix": "%",
            "showgrid": False,
        },
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        height=245,
        margin={"l": 24, "r": 32, "t": 28, "b": 18},
    )
    return fig


def family_margin_chart(
    skus_df: pd.DataFrame,
    theme_mode: str = "light",
) -> go.Figure:
    """Gera barras horizontais de Margem de Contribuição (R$ e %) por Família (Tela 1)."""
    tokens = get_theme_tokens(theme_mode)
    template_name = "kyberna_dark" if theme_mode == "dark" else "kyberna_light"
    if skus_df.empty or "family" not in skus_df.columns:
        fig = go.Figure()
        fig.update_layout(template=template_name, title=None, height=245)
        return fig

    agg = skus_df.groupby("family", as_index=False).agg(
        gross_revenue=("gross_revenue", "sum"),
        contribution_margin=("contribution_margin", "sum"),
    )
    agg["margin_pct"] = (
        agg["contribution_margin"] / agg["gross_revenue"].replace(0.0, float("nan")) * 100.0
    ).fillna(0.0)
    agg = agg.sort_values("contribution_margin", ascending=True).reset_index(drop=True)

    texts = [
        f"{format_brl(float(cm), compact=True, decimals=1)} ({float(mp):.1f}%)"
        for cm, mp in zip(agg["contribution_margin"], agg["margin_pct"], strict=False)
    ]
    fig = go.Figure(
        go.Bar(
            y=agg["family"].tolist(),
            x=agg["contribution_margin"].tolist(),
            orientation="h",
            marker_color=tokens["teal_500"],
            text=texts,
            textposition="outside",
            cliponaxis=False,
            customdata=agg["gross_revenue"].tolist(),
            hovertemplate=(
                "<b>%{y}</b><br>Margem Contrib.: R$ %{x:,.2f}"
                "<br>Fat. Bruto: R$ %{customdata:,.2f}<extra></extra>"
            ),
        )
    )
    max_x = max(float(agg["contribution_margin"].max()) * 1.32, 1.0)
    fig.update_layout(
        template=template_name,
        title=None,
        height=245,
        margin={"l": 16, "r": 24, "t": 14, "b": 18},
        xaxis={"title": "Margem de Contribuição (R$)", "range": [0, max_x]},
        yaxis={"title": None},
    )
    return fig


def quadrant_scatter(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    *,
    label_col: str,
    size_col: str | None = None,
    x_title: str | None = None,
    y_title: str | None = None,
    theme_mode: str = "light",
) -> go.Figure:
    """Gera gráfico de dispersão em 4 quadrantes com cortes nas medianas e coloração por quadrante."""
    tokens = get_theme_tokens(theme_mode)
    template_name = "kyberna_dark" if theme_mode == "dark" else "kyberna_light"

    if df.empty:
        fig = go.Figure()
        fig.update_layout(template=template_name, title="Sem dados para o quadrante")
        return fig

    med_x = float(df[x_col].median())
    med_y = float(df[y_col].median())

    # Coloração temática dos 4 quadrantes
    x_vals = df[x_col].to_numpy()
    y_vals = df[y_col].to_numpy()

    c_star = tokens.get("positive", "#0d9488")
    c_vol_no_margin = tokens.get("negative", "#e11d48")
    c_margin_no_vol = tokens.get("brass_500", "#0284c7")
    c_warning = tokens.get("warning", "#f59e0b")

    point_colors = [
        c_star
        if (x >= med_x and y >= med_y)
        else c_vol_no_margin
        if (x >= med_x and y < med_y)
        else c_margin_no_vol
        if (x < med_x and y >= med_y)
        else c_warning
        for x, y in zip(x_vals, y_vals, strict=False)
    ]

    marker_kwargs: dict[str, object] = {
        "color": point_colors,
        "opacity": 0.90,
        "line": {"width": 1, "color": tokens.get("border_subtle", "#e2e8f0")},
    }
    if size_col and size_col in df.columns:
        max_s = float(df[size_col].max())
        marker_kwargs["size"] = df[size_col]
        marker_kwargs["sizemode"] = "area"
        marker_kwargs["sizeref"] = 2.0 * max_s / (36.0**2) if max_s > 0 else 1.0
        marker_kwargs["sizemin"] = 8
    else:
        marker_kwargs["size"] = 12

    extreme_idxs: set[object] = {
        df[x_col].idxmax(),
        df[y_col].idxmin(),
        df[y_col].idxmax(),
    }
    if size_col and size_col in df.columns:
        extreme_idxs.add(df[size_col].idxmax())

    display_labels = [
        str(lbl)[:18] if idx in extreme_idxs else ""
        for idx, lbl in zip(df.index, df[label_col], strict=False)
    ]

    scatter_trace = go.Scatter(
        x=df[x_col],
        y=df[y_col],
        mode="markers+text",
        text=display_labels,
        textposition="top center",
        textfont={"size": 10, "color": tokens["text_primary"]},
        customdata=df[label_col],
        marker=marker_kwargs,
        hovertemplate=(
            f"<b>%{{customdata}}</b><br>{x_col}: %{{x:,.2f}}<br>{y_col}: %{{y:,.1f}}%<br><extra></extra>"
        ),
    )

    fig = go.Figure(data=[scatter_trace])

    # Linhas de quadrante nas medianas
    fig.add_vline(x=med_x, line_dash="dash", line_color=tokens["chart_zero_line"], opacity=0.8)
    fig.add_hline(y=med_y, line_dash="dash", line_color=tokens["chart_zero_line"], opacity=0.8)

    # Rótulos em pt-BR
    axis_pt_br: dict[str, str] = {
        "gross_revenue": "Faturamento Bruto (R$)",
        "revenue": "Faturamento Bruto (R$)",
        "net_revenue": "Receita Líquida (R$)",
        "contribution_margin": "Margem de Contribuição (R$)",
        "margin_pct": "Margem Líquida (%)",
        "avg_discount_pct": "Desconto Médio (%)",
        "revenue_at_risk_brl": "Risco de Carteira (R$)",
        "positivation_pct": "Positivação (%)",
    }
    final_x_title = x_title or axis_pt_br.get(x_col, x_col.replace("_", " ").title())
    final_y_title = y_title or axis_pt_br.get(y_col, y_col.replace("_", " ").title())

    # Anotações sutis de cada quadrante
    text_color = tokens.get("text_muted", "#64748b")
    quadrant_labels = (
        (0.98, 0.98, "right", "top", "Estrela", "Alto Vol. · Alta Margem"),
        (0.98, 0.02, "right", "bottom", "Volume sem Margem", "Alto Vol. · Baixa Margem"),
        (0.02, 0.98, "left", "top", "Margem sem Volume", "Baixo Vol. · Alta Margem"),
        (0.02, 0.02, "left", "bottom", "Atenção", "Baixo Vol. · Baixa Margem"),
    )
    annotations = [
        go.layout.Annotation(
            xref="paper",
            yref="paper",
            x=qx,
            y=qy,
            xanchor=x_anchor,
            yanchor=y_anchor,
            text=f"<b>{q_title}</b><br><span style='font-size:10px;'>{q_sub}</span>",
            showarrow=False,
            opacity=0.62,
            font={"size": 11, "color": text_color},
        )
        for qx, qy, x_anchor, y_anchor, q_title, q_sub in quadrant_labels
    ]

    fig.update_layout(
        template=template_name,
        title=None,
        xaxis_title=final_x_title,
        yaxis_title=final_y_title,
        annotations=annotations,
        showlegend=False,
        height=245,
        margin={"l": 24, "r": 24, "t": 14, "b": 28},
    )
    return fig
