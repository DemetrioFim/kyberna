from __future__ import annotations

from typing import Literal

import pandas as pd
import plotly.graph_objects as go

from src.services.pricing_dto import PricingShapDTO
from src.ui.formatting import format_brl
from src.ui.theme import get_theme_tokens

UnitMode = Literal["pct", "brl"]


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


def _build_boxplot_hover_texts(df: pd.DataFrame) -> list[str]:
    """Monta cards de hover executivos limpos (1 card por linha) com % e R$/un."""
    cards: list[str] = []
    has_brl = "p50_brl" in df.columns and "avg_base_price_brl" in df.columns
    for row in df.to_dict(orient="records"):
        lbl = str(row["group_label"])
        leak = format_brl(float(row["price_leakage_brl"]), compact=True, decimals=1)
        if has_brl:
            base_u = format_brl(float(row["avg_base_price_brl"]))
            med_u = format_brl(float(row["p50_brl"]))
            p25_u = format_brl(float(row["p25_brl"]))
            p75_u = format_brl(float(row["p75_brl"]))
            b_lo_u = format_brl(float(row["band_low_brl"]))
            b_hi_u = format_brl(float(row["band_high_brl"]))
            floor_u = format_brl(float(row["min_healthy_brl"]))
            card = (
                f"<b>{lbl}</b><br>"
                f"Tabela Base: <b>{base_u}/un.</b><br>"
                f"Mediana Praticada: <b>{float(row['p50']):.1f}%</b> ({med_u})<br>"
                f"Quartis [P25-P75]: {float(row['p25']):.1f}% - {float(row['p75']):.1f}% "
                f"({p25_u} - {p75_u})<br>"
                f"Banda Justa [P25-P75]: <b>{float(row['band_low']):.1f}% - "
                f"{float(row['band_high']):.1f}%</b> ({b_lo_u} - {b_hi_u})<br>"
                f"Piso 15% MC: {float(row['min_healthy_idx']):.1f}% ({floor_u})<br>"
                f"Vazamento no recorte: <b>{leak}</b>"
            )
        else:
            card = (
                f"<b>{lbl}</b><br>"
                f"Mediana Praticada: <b>{float(row['p50']):.1f}%</b><br>"
                f"Quartis [P25-P75]: {float(row['p25']):.1f}% - {float(row['p75']):.1f}%<br>"
                f"Banda Justa [P25-P75]: <b>{float(row['band_low']):.1f}% - "
                f"{float(row['band_high']):.1f}%</b><br>"
                f"Vazamento no recorte: <b>{leak}</b>"
            )
        cards.append(card)
    return cards


def price_band_boxplot_chart(
    boxplot_df: pd.DataFrame,
    *,
    unit_mode: UnitMode = "pct",
    theme_mode: str = "light",
) -> go.Figure:
    """Boxplot horizontal de Preço Realizado vs. Banda Contextual [P25, P75] em % ou R$/un."""
    if boxplot_df.empty:
        return _empty_pricing_fig(
            "Sem dados de realização de preço para os filtros selecionados.",
            theme_mode=theme_mode,
        )

    tokens = get_theme_tokens(theme_mode)
    template_name = "kyberna_dark" if theme_mode == "dark" else "kyberna_light"
    use_brl = unit_mode == "brl" and "p50_brl" in boxplot_df.columns

    df = boxplot_df.sort_values("price_leakage_brl", ascending=True).copy()
    labels = [str(lbl)[:26] for lbl in df["group_label"].tolist()]

    if use_brl:
        c_p05, c_p25, c_p50, c_p75, c_p95 = "p05_brl", "p25_brl", "p50_brl", "p75_brl", "p95_brl"
        c_mean = "realized_mean_brl"
        c_blo, c_bhi, c_floor = "band_low_brl", "band_high_brl", "min_healthy_brl"
        x_title = "Preço Líquido Praticado (R$/unidade)"
    else:
        c_p05, c_p25, c_p50, c_p75, c_p95 = "p05", "p25", "p50", "p75", "p95"
        c_mean = "realized_mean"
        c_blo, c_bhi, c_floor = "band_low", "band_high", "min_healthy_idx"
        x_title = "Índice de Realização (% da Tabela Base)"

    band_low = [float(v) for v in df[c_blo]]
    band_width = [max(float(hi) - float(lo), 0.3) for lo, hi in zip(df[c_blo], df[c_bhi], strict=False)]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            y=labels,
            x=band_width,
            base=band_low,
            orientation="h",
            name="Banda Contextual [P25-P75]",
            marker={"color": "rgba(13, 148, 136, 0.22)", "line": {"width": 0}},
            hoverinfo="skip",
        )
    )

    fig.add_trace(
        go.Box(
            y=labels,
            lowerfence=[float(v) for v in df[c_p05]],
            q1=[float(v) for v in df[c_p25]],
            median=[float(v) for v in df[c_p50]],
            q3=[float(v) for v in df[c_p75]],
            upperfence=[float(v) for v in df[c_p95]],
            mean=[float(v) for v in df[c_mean]],
            orientation="h",
            name="Praticado (P05-P95)",
            marker={"color": tokens["teal_500"]},
            line={"color": tokens["teal_500"], "width": 1.6},
            fillcolor="rgba(13, 148, 136, 0.42)",
            boxmean=True,
            hoverinfo="skip",
        )
    )

    if use_brl and c_floor in df.columns:
        fig.add_trace(
            go.Scatter(
                x=[float(v) for v in df[c_floor]],
                y=labels,
                mode="markers",
                name="Piso 15% MC",
                marker={
                    "symbol": "line-ns-open",
                    "size": 13,
                    "line": {"width": 2.2, "color": tokens["negative"]},
                },
                hoverinfo="skip",
            )
        )
        x_min = max(min(float(df[c_p05].min()), float(df[c_floor].min())) * 0.92, 0.0)
        x_max = max(float(df[c_p95].max()), float(df[c_bhi].max())) * 1.06
    else:
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
        x_min = max(min(float(df[c_p05].min()) - 4.0, avg_floor - 3.0), 55.0)
        x_max = min(max(float(df[c_p95].max()) + 4.0, 104.0), 125.0)

    # Trace único de hover executivo limpo (substitui os 7 balões inclinados do go.Box)
    hover_cards = _build_boxplot_hover_texts(df)
    fig.add_trace(
        go.Scatter(
            x=[float(v) for v in df[c_p50]],
            y=labels,
            mode="markers",
            showlegend=False,
            marker={"size": 22, "color": "rgba(0,0,0,0.01)"},
            text=hover_cards,
            hovertemplate="%{text}<extra></extra>",
            hoverlabel={
                "bgcolor": tokens["surface_card"],
                "bordercolor": tokens["teal_500"],
                "font": {"size": 11.5, "color": tokens["text_primary"]},
                "align": "left",
            },
        )
    )

    fig.update_layout(
        template=template_name,
        title=None,
        height=245,
        hovermode="y",
        margin={"l": 12, "r": 16, "t": 18, "b": 16},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1.0},
        xaxis={"title": {"text": x_title, "standoff": 8}, "range": [x_min, x_max], "automargin": True},
        yaxis={"title": None, "automargin": True, "dtick": 1, "tickfont": {"size": 10}},
    )
    return fig


def pricing_shap_waterfall_chart(
    shap_dto: PricingShapDTO,
    *,
    unit_mode: UnitMode = "pct",
    theme_mode: str = "light",
) -> go.Figure:
    """SHAP Waterfall de formação de preço (Tabela -> Drivers -> Esperado vs. Praticado) em % ou R$."""
    if shap_dto.drivers_df.empty:
        return _empty_pricing_fig(
            "Sem drivers SHAP disponíveis para o escopo selecionado.",
            theme_mode=theme_mode,
        )

    tokens = get_theme_tokens(theme_mode)
    template_name = "kyberna_dark" if theme_mode == "dark" else "kyberna_light"
    df = shap_dto.drivers_df.sort_values("driver_order").copy()
    use_brl = unit_mode == "brl" and shap_dto.table_gross_brl > 0.0 and "shap_impact_brl" in df.columns

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
    if use_brl:
        impacts = [float(v) for v in df["shap_impact_brl"]]
        base_val = float(shap_dto.table_gross_brl)
        exp_val = float(shap_dto.expected_net_brl)
        real_val = float(shap_dto.realized_net_brl)
        y_vals = [base_val, *impacts, exp_val]
        texts = [format_brl(base_val, compact=True, decimals=1)]
        texts.extend(
            f"+{format_brl(v, compact=True, decimals=1)}"
            if v > 0
            else format_brl(v, compact=True, decimals=1)
            for v in impacts
        )
        texts.append(format_brl(exp_val, compact=True, decimals=1))
        real_lbl = f"Praticado: {format_brl(real_val, compact=True, decimals=1)}"
        gap_str = (
            f"+{format_brl(shap_dto.unjustified_gap_brl, compact=True, decimals=1)}"
            if shap_dto.unjustified_gap_brl > 0
            else format_brl(shap_dto.unjustified_gap_brl, compact=True, decimals=1)
        )
        y_title = "Receita no Recorte (R$)"
        y_lo = max(min(base_val, exp_val, real_val) * 0.72, 0.0)
        y_hi = max(base_val, exp_val, real_val) * 1.18
    else:
        impacts = [float(v) for v in df["shap_impact_pp"]]
        base_val = float(shap_dto.base_idx)
        exp_val = float(shap_dto.expected_idx)
        real_val = float(shap_dto.realized_idx)
        y_vals = [base_val, *impacts, exp_val]
        texts = [f"{base_val:.1f}%"]
        texts.extend(f"{v:+.1f} pp" for v in impacts)
        texts.append(f"{exp_val:.1f}%")
        real_lbl = f"Praticado: {real_val:.1f}%"
        gap_str = f"{shap_dto.unjustified_gap_pp:+.2f} pp"
        y_title = "Índice vs. Tabela (%)"
        y_lo = max(min(base_val, exp_val, real_val) - 14.0, 55.0)
        y_hi = min(max(base_val, exp_val, real_val) + 12.0, 118.0)

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
    real_text_color = "#FFFFFF" if theme_mode == "dark" else tokens["text_primary"]
    fig.add_trace(
        go.Scatter(
            x=["Esperado<br>(Modelo)"],
            y=[real_val],
            mode="markers+text",
            name=real_lbl,
            marker={
                "symbol": "diamond",
                "size": 11,
                "color": real_color,
                "line": {"width": 1.5, "color": "#FFFFFF"},
            },
            text=[real_lbl],
            textposition="bottom center",
            textfont={"size": 10, "color": real_text_color},
            hovertemplate=(
                f"<b>Praticado Real:</b> {texts[-1] if abs(real_val - exp_val) < 1e-3 else real_lbl}<br>"
                f"<b>Esperado (SHAP):</b> {texts[-1]}<br>"
                f"<b>Resíduo sem lastro:</b> {gap_str}<extra></extra>"
            ),
        )
    )

    fig.update_layout(
        template=template_name,
        title=None,
        height=245,
        margin={"l": 12, "r": 12, "t": 18, "b": 28},
        showlegend=False,
        xaxis={"title": None, "automargin": True, "tickfont": {"size": 10}},
        yaxis={"title": {"text": y_title, "standoff": 8}, "range": [y_lo, y_hi], "automargin": True},
    )
    return fig
