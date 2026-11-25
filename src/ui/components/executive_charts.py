from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from src.ui.theme import get_theme_tokens

_AXIS_PT_BR: dict[str, str] = {
    "gross_revenue": "Faturamento Bruto (R$)",
    "revenue": "Faturamento Bruto (R$)",
    "net_revenue": "Receita Líquida (R$)",
    "contribution_margin": "Margem de Contribuição (R$)",
    "margin_pct": "Margem de Contribuição (%)",
    "avg_discount_pct": "Desconto Médio (%)",
    "revenue_at_risk_brl": "Risco de Carteira (R$)",
    "positivation_pct": "Positivação (%)",
}


def _build_quadrant_annotations(
    work: pd.DataFrame,
    *,
    x_col: str,
    y_col: str,
    label_col: str,
    size_col: str | None,
    med_x: float,
    med_y: float,
    tokens: dict[str, str],
) -> tuple[list[go.layout.Annotation], list[float], list[float]]:
    """Constroi anotacoes dos 4 quadrantes, callouts extremos sem colisao e limites de eixos."""
    text_color = tokens.get("text_muted", "#64748b")
    quadrant_labels = (
        (0.98, 0.98, "right", "top", "Estrela", "Alto Vol. · Alta Margem"),
        (0.98, 0.02, "right", "bottom", "Volume sem Margem", "Alto Vol. · Baixa Margem"),
        (0.02, 0.98, "left", "top", "Margem sem Volume", "Baixo Vol. · Alta Margem"),
        (0.02, 0.02, "left", "bottom", "Atenção", "Baixo Vol. · Baixa Margem"),
    )
    annotations: list[go.layout.Annotation] = [
        go.layout.Annotation(
            xref="paper",
            yref="paper",
            x=qx,
            y=qy,
            xanchor=x_anchor,
            yanchor=y_anchor,
            text=f"<b>{q_title}</b><br><span style='font-size:10px;'>{q_sub}</span>",
            showarrow=False,
            opacity=0.72,
            bgcolor=tokens["surface_card"],
            borderpad=1,
            font={"size": 10.5, "color": text_color},
        )
        for qx, qy, x_anchor, y_anchor, q_title, q_sub in quadrant_labels
    ]

    x_arr = work[x_col].to_numpy(dtype=float)
    y_arr = work[y_col].to_numpy(dtype=float)
    pos_candidates = [int(x_arr.argmax()), int(y_arr.argmax()), int(y_arr.argmin())]
    if size_col and size_col in work.columns:
        pos_candidates.append(int(work[size_col].to_numpy(dtype=float).argmax()))

    extreme_positions = list(dict.fromkeys(pos_candidates))
    labels_list = work[label_col].astype(str).tolist()
    for pos in extreme_positions:
        px_val = float(x_arr[pos])
        py_val = float(y_arr[pos])
        annotations.append(
            go.layout.Annotation(
                x=px_val,
                y=py_val,
                text=labels_list[pos][:18],
                showarrow=True,
                arrowhead=0,
                arrowwidth=1,
                arrowcolor=tokens["text_muted"],
                ax=-36 if px_val >= med_x else 36,
                ay=24 if py_val >= med_y else -24,
                bgcolor=tokens["surface_card"],
                bordercolor=tokens["border_subtle"],
                borderpad=2,
                font={"size": 9.5, "color": tokens["text_primary"]},
            )
        )

    x_min, x_max = float(x_arr.min()), float(x_arr.max())
    y_min, y_max = float(y_arr.min()), float(y_arr.max())
    x_span = max(x_max - x_min, x_max * 0.25, 1.0)
    y_span = max(y_max - y_min, 5.0)
    return (
        annotations,
        [max(0.0, x_min - x_span * 0.14), x_max + x_span * 0.16],
        [y_min - y_span * 0.24, y_max + y_span * 0.28],
    )


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
    """Gera gráfico de dispersão em 4 quadrantes com cortes nas medianas e rótulos sem colisão."""
    tokens = get_theme_tokens(theme_mode)
    template_name = "kyberna_dark" if theme_mode == "dark" else "kyberna_light"

    if df.empty:
        fig = go.Figure()
        fig.update_layout(template=template_name, title="Sem dados para o quadrante")
        return fig

    work = df.reset_index(drop=True)
    med_x = float(work[x_col].median())
    med_y = float(work[y_col].median())

    final_x_title = x_title or _AXIS_PT_BR.get(x_col, x_col.replace("_", " ").title())
    final_y_title = y_title or _AXIS_PT_BR.get(y_col, y_col.replace("_", " ").title())

    x_vals = work[x_col].to_numpy()
    y_vals = work[y_col].to_numpy()

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
    if size_col and size_col in work.columns:
        max_s = float(work[size_col].max())
        marker_kwargs["size"] = work[size_col]
        marker_kwargs["sizemode"] = "area"
        marker_kwargs["sizeref"] = 2.0 * max_s / (36.0**2) if max_s > 0 else 1.0
        marker_kwargs["sizemin"] = 8
    else:
        marker_kwargs["size"] = 12

    scatter_trace = go.Scatter(
        x=work[x_col],
        y=work[y_col],
        mode="markers",
        customdata=work[label_col],
        marker=marker_kwargs,
        hovertemplate=(
            f"<b>%{{customdata}}</b><br>{final_x_title}: %{{x:,.2f}}"
            f"<br>{final_y_title}: %{{y:,.1f}}%<extra></extra>"
        ),
    )

    fig = go.Figure(data=[scatter_trace])
    fig.add_vline(x=med_x, line_dash="dash", line_color=tokens["chart_zero_line"], opacity=0.8)
    fig.add_hline(y=med_y, line_dash="dash", line_color=tokens["chart_zero_line"], opacity=0.8)

    annotations, xaxis_range, yaxis_range = _build_quadrant_annotations(
        work,
        x_col=x_col,
        y_col=y_col,
        label_col=label_col,
        size_col=size_col,
        med_x=med_x,
        med_y=med_y,
        tokens=tokens,
    )

    fig.update_layout(
        template=template_name,
        title=None,
        xaxis={"title": final_x_title, "range": xaxis_range},
        yaxis={"title": final_y_title, "range": yaxis_range},
        annotations=annotations,
        showlegend=False,
        height=245,
        margin={"l": 24, "r": 24, "t": 14, "b": 28},
    )
    return fig
