from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from src.services.pricing_dto import PricingShapDTO
from src.ui.theme import get_theme_tokens


def _empty_pricing_fig(message: str, *, theme_mode: str = "light") -> go.Figure:
    """Retorna figura Plotly vazia padronizada para os gráficos de Precificação."""
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


def price_band_boxplot_chart(
    boxplot_df: pd.DataFrame,
    *,
    theme_mode: str = "light",
) -> go.Figure:
    """Boxplot horizontal de Preço Realizado vs. Banda Contextual [P25, P75] e Piso 15% MC."""
    if boxplot_df.empty:
        return _empty_pricing_fig(
            "Sem dados de realização de preço para os filtros selecionados.",
            theme_mode=theme_mode,
        )

    tokens = get_theme_tokens(theme_mode)
    template_name = "kyberna_dark" if theme_mode == "dark" else "kyberna_light"

    df = boxplot_df.sort_values("price_leakage_brl", ascending=True).copy()
    labels = [str(lbl)[:26] for lbl in df["group_label"].tolist()]
    band_low = [float(v) for v in df["band_low"]]
    band_width = [
        max(float(hi) - float(lo), 0.5) for lo, hi in zip(df["band_low"], df["band_high"], strict=False)
    ]

    fig = go.Figure()
    # Faixa sombreada da Banda Contextual Justa [P25, P75] por linha
    fig.add_trace(
        go.Bar(
            y=labels,
            x=band_width,
            base=band_low,
            orientation="h",
            name="Banda Contextual [P25-P75]",
            marker={"color": "rgba(13, 148, 136, 0.22)", "line": {"width": 0}},
            hovertemplate="<b>%{y}</b><br>Banda Justa: %{base:.1f}% + %{x:.1f} pp<extra></extra>",
        )
    )

    # Boxplot pré-calculado sobre quantis reais (P05..P95)
    fig.add_trace(
        go.Box(
            y=labels,
            lowerfence=[float(v) for v in df["p05"]],
            q1=[float(v) for v in df["p25"]],
            median=[float(v) for v in df["p50"]],
            q3=[float(v) for v in df["p75"]],
            upperfence=[float(v) for v in df["p95"]],
            mean=[float(v) for v in df["realized_mean"]],
            orientation="h",
            name="Praticado (P05-P95)",
            marker={"color": tokens["teal_500"]},
            line={"color": tokens["teal_500"], "width": 1.6},
            fillcolor="rgba(13, 148, 136, 0.42)",
            boxmean=True,
            hovertemplate=(
                "<b>%{y}</b><br>Mediana: %{median:.1f}% | P25: %{q1:.1f}% | P75: %{q3:.1f}%<extra></extra>"
            ),
        )
    )

    avg_floor = float(df["min_healthy_idx"].mean()) if "min_healthy_idx" in df.columns else 82.0
    fig.add_vline(
        x=avg_floor,
        line_dash="dash",
        line_color=tokens["negative"],
        line_width=1.8,
        annotation_text=f"Piso 15% MC ({avg_floor:.1f}%)",
        annotation_position="top right",
        annotation_bgcolor=tokens["surface_card"],
        annotation_borderpad=2,
        annotation_font_color=tokens["negative"],
        annotation_font_size=10,
    )

    x_min = max(min(float(df["p05"].min()) - 4.0, avg_floor - 3.0), 55.0)
    x_max = min(max(float(df["p95"].max()) + 4.0, 104.0), 125.0)
    fig.update_layout(
        template=template_name,
        title=None,
        height=245,
        margin={"l": 12, "r": 16, "t": 18, "b": 16},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1.0},
        xaxis={
            "title": {"text": "Índice de Realização (% da Tabela Base)", "standoff": 8},
            "range": [x_min, x_max],
            "automargin": True,
        },
        yaxis={"title": None, "automargin": True},
    )
    return fig


def pricing_shap_waterfall_chart(
    shap_dto: PricingShapDTO,
    *,
    theme_mode: str = "light",
) -> go.Figure:
    """SHAP Waterfall de formação de preço (Tabela 100% -> Drivers -> Esperado vs. Praticado)."""
    if shap_dto.drivers_df.empty:
        return _empty_pricing_fig(
            "Sem drivers SHAP disponíveis para o escopo selecionado.",
            theme_mode=theme_mode,
        )

    tokens = get_theme_tokens(theme_mode)
    template_name = "kyberna_dark" if theme_mode == "dark" else "kyberna_light"
    df = shap_dto.drivers_df.sort_values("driver_order").copy()

    short_names = {
        "Porte do Cliente": "Porte<br>Cliente",
        "Volume do Pedido": "Volume<br>Pedido",
        "Campanha & Sazonalidade": "Campanha<br>Sazon.",
        "Frete CIF & Prazo Porte": "Frete/Prazo<br>Porte",
        "Posicionamento SKU": "Mix<br>SKU",
    }
    x_labels = ["Tabela<br>Base"]
    x_labels.extend(short_names.get(str(n), str(n)) for n in df["driver_name"].tolist())
    x_labels.append("Esperado<br>(Modelo)")

    measures = ["absolute", *(["relative"] * len(df)), "total"]
    impacts = [float(v) for v in df["shap_impact_pp"]]
    y_vals = [float(shap_dto.base_idx), *impacts, float(shap_dto.expected_idx)]

    texts = [f"{shap_dto.base_idx:.1f}%"]
    texts.extend(f"{v:+.1f} pp" for v in impacts)
    texts.append(f"{shap_dto.expected_idx:.1f}%")

    fig = go.Figure(
        go.Waterfall(
            x=x_labels,
            y=y_vals,
            measure=measures,
            text=texts,
            textposition="outside",
            cliponaxis=False,
            connector={"line": {"color": tokens["border_subtle"], "width": 1.2}},
            increasing={"marker": {"color": tokens["positive"]}},
            decreasing={"marker": {"color": tokens["negative"]}},
            totals={"marker": {"color": tokens["teal_500"]}},
            hovertemplate="<b>%{x}</b><br>Impacto / Nível: %{text}<extra></extra>",
        )
    )

    real_color = tokens["negative"] if shap_dto.unjustified_gap_pp < -0.5 else tokens["positive"]
    fig.add_trace(
        go.Scatter(
            x=["Esperado<br>(Modelo)"],
            y=[float(shap_dto.realized_idx)],
            mode="markers+text",
            name=f"Praticado ({shap_dto.realized_idx:.1f}%)",
            marker={
                "symbol": "diamond",
                "size": 12,
                "color": real_color,
                "line": {"width": 1.5, "color": "#FFFFFF"},
            },
            text=[f"Praticado: {shap_dto.realized_idx:.1f}%"],
            textposition="bottom center",
            textfont={"size": 10.5, "color": real_color},
            hovertemplate=(
                f"<b>Praticado Real:</b> {shap_dto.realized_idx:.1f}%<br>"
                f"<b>Esperado (SHAP):</b> {shap_dto.expected_idx:.1f}%<br>"
                f"<b>Resíduo sem lastro:</b> {shap_dto.unjustified_gap_pp:+.2f} pp<extra></extra>"
            ),
        )
    )

    all_y = [shap_dto.base_idx, shap_dto.expected_idx, shap_dto.realized_idx]
    y_lo = max(min(all_y) - 12.0, 55.0)
    y_hi = min(max(all_y) + 8.0, 115.0)
    fig.update_layout(
        template=template_name,
        title=None,
        height=245,
        margin={"l": 12, "r": 12, "t": 16, "b": 28},
        showlegend=False,
        xaxis={"title": None, "automargin": True, "tickfont": {"size": 10}},
        yaxis={
            "title": {"text": "Índice vs. Tabela (%)", "standoff": 8},
            "range": [y_lo, y_hi],
            "automargin": True,
        },
    )
    return fig
