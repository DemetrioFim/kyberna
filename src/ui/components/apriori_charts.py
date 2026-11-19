from __future__ import annotations

from typing import Final

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from src.ui.formatting import format_brl
from src.ui.theme import get_theme_tokens

__all__ = [
    "RFM_SEGMENT_ORDER",
    "apriori_rules_scatter",
    "white_space_heatmap_v2",
]

RFM_SEGMENT_ORDER: Final[list[str]] = [
    "Campeões",
    "Fiéis",
    "Promissores",
    "Novos Clientes",
    "Precisam de Atenção",
    "Em Risco",
    "Não Pode Perder",
    "Hibernando",
    "Perdidos",
]


def _empty_apriori_fig(message: str, *, theme_mode: str = "light", height: int = 250) -> go.Figure:
    """Retorna figura Plotly vazia padronizada sem poluição visual."""
    tokens = get_theme_tokens(theme_mode)
    template_name = "kyberna_dark" if theme_mode == "dark" else "kyberna_light"
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
        font={"size": 12, "color": tokens["text_muted"]},
    )
    fig.update_layout(
        template=template_name,
        title=None,
        height=height,
        margin={"l": 12, "r": 12, "t": 12, "b": 12},
        xaxis={"visible": False},
        yaxis={"visible": False},
    )
    return fig


def white_space_heatmap_v2(
    df: pd.DataFrame,
    theme_mode: str = "light",
) -> go.Figure:
    """Heatmap aprimorado Familia x 9 Segmentos RFM com R$, lojas e contraste adaptativo."""
    if df.empty or "recommended_family" not in df.columns or "rfm_segment" not in df.columns:
        return _empty_apriori_fig("Sem oportunidades White Space no filtro atual.", theme_mode=theme_mode)

    tokens = get_theme_tokens(theme_mode)
    template_name = "kyberna_dark" if theme_mode == "dark" else "kyberna_light"

    present_segs = [str(s) for s in df["rfm_segment"].dropna().unique().tolist()]
    ordered_segs = [s for s in RFM_SEGMENT_ORDER if s in present_segs]
    extra_segs = sorted(s for s in present_segs if s not in RFM_SEGMENT_ORDER)
    x_labels = ordered_segs + extra_segs

    fam_order = (
        df.groupby("recommended_family")["potential_revenue_brl"]
        .sum()
        .sort_values(ascending=True)
        .index.astype(str)
        .tolist()
    )

    rev_piv = df.pivot_table(
        index="recommended_family",
        columns="rfm_segment",
        values="potential_revenue_brl",
        aggfunc="sum",
        fill_value=0.0,
    ).reindex(index=fam_order, columns=x_labels, fill_value=0.0)
    cnt_piv = (
        df.pivot_table(
            index="recommended_family",
            columns="rfm_segment",
            values="opportunities_count",
            aggfunc="sum",
            fill_value=0,
        ).reindex(index=fam_order, columns=x_labels, fill_value=0)
        if "opportunities_count" in df.columns
        else pd.DataFrame(0, index=fam_order, columns=x_labels)
    )
    margin_piv = (
        df.pivot_table(
            index="recommended_family",
            columns="rfm_segment",
            values="potential_margin_brl",
            aggfunc="sum",
            fill_value=0.0,
        ).reindex(index=fam_order, columns=x_labels, fill_value=0.0)
        if "potential_margin_brl" in df.columns
        else pd.DataFrame(0.0, index=fam_order, columns=x_labels)
    )
    conf_piv = (
        df.pivot_table(
            index="recommended_family",
            columns="rfm_segment",
            values="avg_confidence_pct",
            aggfunc="mean",
            fill_value=0.0,
        ).reindex(index=fam_order, columns=x_labels, fill_value=0.0)
        if "avg_confidence_pct" in df.columns
        else pd.DataFrame(0.0, index=fam_order, columns=x_labels)
    )
    lift_piv = (
        df.pivot_table(
            index="recommended_family",
            columns="rfm_segment",
            values="avg_lift",
            aggfunc="mean",
            fill_value=1.0,
        ).reindex(index=fam_order, columns=x_labels, fill_value=1.0)
        if "avg_lift" in df.columns
        else pd.DataFrame(1.0, index=fam_order, columns=x_labels)
    )

    z_values = rev_piv.to_numpy(dtype=float)
    cnt_values = cnt_piv.to_numpy(dtype=int)
    margin_values = margin_piv.to_numpy(dtype=float)
    conf_values = conf_piv.to_numpy(dtype=float)
    lift_values = lift_piv.to_numpy(dtype=float)
    max_z = max(float(z_values.max()) if z_values.size > 0 else 0.0, 1.0)

    hover_matrix: list[list[str]] = []
    annotations: list[dict[str, object]] = []
    for i, fam in enumerate(fam_order):
        hover_row: list[str] = []
        for j, seg in enumerate(x_labels):
            val = float(z_values[i, j])
            cnt = int(cnt_values[i, j])
            mrg = float(margin_values[i, j])
            cnf = float(conf_values[i, j])
            lft = float(lift_values[i, j])

            if val > 0.0:
                val_txt = format_brl(val, compact=True, decimals=1).replace("R$ ", "")
                cell_txt = f"<b>{val_txt}</b><br><span style='font-size:8px'>{cnt} lojas</span>"
                font_color = "#FFFFFF" if (val / max_z) >= 0.42 else tokens["text_primary"]
            else:
                cell_txt = "-"
                font_color = tokens["text_muted"]

            annotations.append(
                {
                    "x": seg,
                    "y": fam,
                    "text": cell_txt,
                    "showarrow": False,
                    "font": {"size": 9.5, "color": font_color},
                }
            )
            hover_row.append(
                f"<b>{fam}</b> · {seg}<br>"
                f"Potencial Receita: {format_brl(val)}<br>"
                f"Margem Est.: {format_brl(mrg)}<br>"
                f"Lojas Elegíveis: {cnt}<br>"
                f"Confiança Média Apriori: {cnf:.1f}%<br>"
                f"Lift Médio: {lft:.2f}x"
            )
        hover_matrix.append(hover_row)

    colorscale = (
        [[0.0, "#1E293B"], [0.35, "#0F4C5C"], [0.7, "#1F7A8C"], [1.0, "#38BDF8"]]
        if theme_mode == "dark"
        else "Teal"
    )
    fig = go.Figure(
        data=go.Heatmap(
            z=z_values,
            x=x_labels,
            y=fam_order,
            customdata=hover_matrix,
            texttemplate=None,
            hovertemplate="%{customdata}<extra></extra>",
            colorscale=colorscale,
            showscale=False,
            hoverongaps=False,
            xgap=1,
            ygap=2,
        )
    )
    fig.update_layout(
        template=template_name,
        title=None,
        annotations=annotations,
        xaxis={"title": None, "tickangle": -25, "automargin": True},
        yaxis={"title": None, "automargin": True},
        height=275,
        margin={"l": 12, "r": 12, "t": 10, "b": 24},
    )
    return fig


def apriori_rules_scatter(
    rules_df: pd.DataFrame,
    *,
    rule_level: str = "sku",
    theme_mode: str = "light",
) -> go.Figure:
    """Gráfico de bolhas Apriori: Suporte (%) x Confiança (%) colorido e dimensionado por Lift."""
    if rules_df.empty or "rule_level" not in rules_df.columns:
        return _empty_apriori_fig("Nenhuma regra Apriori disponível para o filtro.", theme_mode=theme_mode)

    sub = rules_df[rules_df["rule_level"] == rule_level].copy()
    if sub.empty:
        sub = rules_df.copy()

    tokens = get_theme_tokens(theme_mode)
    template_name = "kyberna_dark" if theme_mode == "dark" else "kyberna_light"

    sub = sub.sort_values(by=["lift", "confidence_pct"], ascending=False).head(40).reset_index(drop=True)
    lifts = sub["lift"].astype(float).to_numpy()
    min_l = float(lifts.min()) if len(lifts) > 0 else 1.0
    max_l = max(float(lifts.max()) if len(lifts) > 0 else 1.2, min_l + 0.05)
    sizes = (10.0 + ((lifts - min_l) / (max_l - min_l)) * 20.0).tolist()

    hover_texts = [
        f"<b>Se compra:</b> {ant}<br>"
        f"<b>Ofertar:</b> {con}<br>"
        f"Suporte: {sup:.2f}% ({pb} cestas)<br>"
        f"Confiança: {conf:.1f}%<br>"
        f"Lift (Alavancagem): {lft:.2f}x"
        for ant, con, sup, pb, conf, lft in zip(
            sub["antecedent_name"],
            sub["consequent_name"],
            sub["support_pct"],
            sub["pair_baskets"],
            sub["confidence_pct"],
            sub["lift"],
            strict=False,
        )
    ]

    fig = go.Figure(
        go.Scatter(
            x=sub["support_pct"].tolist(),
            y=sub["confidence_pct"].tolist(),
            mode="markers",
            text=hover_texts,
            hoverinfo="text",
            marker={
                "size": sizes,
                "color": lifts.tolist(),
                "colorscale": "Tealgrn",
                "showscale": True,
                "colorbar": {"title": "Lift (x)", "thickness": 12},
                "line": {"color": tokens["surface_card"], "width": 1},
                "opacity": 0.9,
            },
        )
    )

    # Anota apenas as Top 3 regras com vetores distintos e fundo sólido (anti-colisão)
    offsets = [(38, -28), (-46, 22), (46, 26)]
    annotations: list[dict[str, object]] = []
    for idx in range(min(3, len(sub))):
        row = sub.iloc[idx]
        short_ant = str(row["antecedent_name"])[:16]
        short_con = str(row["consequent_name"])[:16]
        ax_off, ay_off = offsets[idx % len(offsets)]
        annotations.append(
            {
                "x": float(row["support_pct"]),
                "y": float(row["confidence_pct"]),
                "text": f"{short_ant} → {short_con} ({float(row['lift']):.2f}x)",
                "showarrow": True,
                "arrowhead": 0,
                "arrowcolor": tokens["text_muted"],
                "ax": ax_off,
                "ay": ay_off,
                "bgcolor": tokens["surface_card"],
                "bordercolor": tokens["border_subtle"],
                "borderpad": 2,
                "font": {"size": 9, "color": tokens["text_primary"]},
            }
        )

    med_conf = float(np.median(sub["confidence_pct"])) if not sub.empty else 0.0
    fig.add_hline(y=med_conf, line_dash="dot", line_width=1, line_color=tokens["border_subtle"])
    fig.update_layout(
        template=template_name,
        title=None,
        annotations=annotations,
        xaxis={"title": "Suporte (%) — Frequência nas Cestas", "automargin": True},
        yaxis={"title": "Confiança (%) — Prob. P(B|A)", "automargin": True},
        height=255,
        margin={"l": 12, "r": 12, "t": 14, "b": 24},
    )
    return fig
