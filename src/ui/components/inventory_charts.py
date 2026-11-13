from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from src.ui.theme import get_theme_tokens

__all__ = [
    "forecast_band_chart",
    "locked_capital_treemap",
]


def _empty_figure(message: str, *, theme_mode: str = "light", height: int = 280) -> go.Figure:
    """Retorna figura Plotly vazia padronizada com mensagem informativa."""
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
        height=height,
        margin={"l": 12, "r": 12, "t": 12, "b": 12},
        xaxis={"visible": False},
        yaxis={"visible": False},
    )
    return fig


def forecast_band_chart(series_df: pd.DataFrame, *, theme_mode: str = "light") -> go.Figure:
    """Gráfico de demanda diária (90d histórico + 30d forecast) com bandas IC 80% e 95%."""
    if series_df.empty:
        return _empty_figure(
            "Sem série de previsão disponível para o SKU selecionado.", theme_mode=theme_mode
        )

    tokens = get_theme_tokens(theme_mode)
    df = series_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")

    hist = df[df["record_type"] == "historical"]
    fc = df[df["record_type"] == "forecast"]

    fig = go.Figure()

    if not fc.empty:
        dates_fc = fc["date"].tolist()
        dates_poly = dates_fc + dates_fc[::-1]

        y_95 = fc["hi_95"].fillna(0.0).tolist() + fc["lo_95"].fillna(0.0).tolist()[::-1]
        fig.add_trace(
            go.Scatter(
                x=dates_poly,
                y=y_95,
                fill="toself",
                fillcolor="rgba(217, 119, 6, 0.12)",
                line={"color": "rgba(255,255,255,0)"},
                hoverinfo="skip",
                name="IC 95%",
                showlegend=True,
            )
        )

        y_80 = fc["hi_80"].fillna(0.0).tolist() + fc["lo_80"].fillna(0.0).tolist()[::-1]
        fig.add_trace(
            go.Scatter(
                x=dates_poly,
                y=y_80,
                fill="toself",
                fillcolor="rgba(217, 119, 6, 0.24)",
                line={"color": "rgba(255,255,255,0)"},
                hoverinfo="skip",
                name="IC 80%",
                showlegend=True,
            )
        )

    if not hist.empty:
        fig.add_trace(
            go.Scatter(
                x=hist["date"],
                y=hist["actual_units"],
                mode="lines",
                name="Histórico (90d)",
                line={"color": tokens["teal_500"], "width": 2.2},
                hovertemplate="<b>%{x|%d/%m/%Y}</b><br>Real: %{y:,.1f} un<extra></extra>",
            )
        )

    if not fc.empty:
        fig.add_trace(
            go.Scatter(
                x=fc["date"],
                y=fc["forecast_units"],
                mode="lines",
                name="Projeção (30d)",
                line={"color": tokens["brass_500"], "width": 2.4, "dash": "dash"},
                hovertemplate="<b>%{x|%d/%m/%Y}</b><br>Previsto: %{y:,.1f} un<extra></extra>",
            )
        )

    fig.update_layout(
        template="kyberna_dark" if theme_mode == "dark" else "kyberna_light",
        title=None,
        height=280,
        margin={"l": 12, "r": 12, "t": 16, "b": 12},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1.0},
        yaxis_title="Unidades / Dia",
        xaxis_title=None,
        hovermode="x unified",
    )
    return fig


def locked_capital_treemap(treemap_df: pd.DataFrame, *, theme_mode: str = "light") -> go.Figure:
    """Treemap hierárquico (Família -> SKU) de capital travado excedente (>120d)."""
    if treemap_df.empty or float(treemap_df["locked_capital_brl"].sum()) <= 0.0:
        return _empty_figure("Sem capital travado (> 120d) nos filtros atuais.", theme_mode=theme_mode)

    tokens = get_theme_tokens(theme_mode)
    df = treemap_df[treemap_df["locked_capital_brl"] > 0.0].copy()

    ids: list[str] = ["root"]
    labels: list[str] = ["Capital Travado"]
    parents: list[str] = [""]
    values: list[float] = [float(df["locked_capital_brl"].sum())]
    custom_text: list[str] = [f"Total: R$ {values[0]:,.2f}"]

    family_totals = df.groupby("family", as_index=False)["locked_capital_brl"].sum()
    for _, frow in family_totals.iterrows():
        fam = str(frow["family"])
        fval = float(frow["locked_capital_brl"])
        ids.append(f"fam::{fam}")
        labels.append(fam)
        parents.append("root")
        values.append(fval)
        custom_text.append(f"Família {fam}: R$ {fval:,.2f}")

    for _, row in df.iterrows():
        sku_label = f"{str(row['product_name'])[:28]} ({row['abc_xyz_class']})"
        sval = float(row["locked_capital_brl"])
        ids.append(f"sku::{row['product_id']}")
        labels.append(sku_label)
        parents.append(f"fam::{row['family']}")
        values.append(sval)
        custom_text.append(f"Cobertura: {float(row['coverage_days']):.0f}d | R$ {sval:,.2f}")

    fig = go.Figure(
        go.Treemap(
            ids=ids,
            labels=labels,
            parents=parents,
            values=values,
            branchvalues="total",
            text=custom_text,
            hovertemplate="<b>%{label}</b><br>%{text}<extra></extra>",
            textinfo="label+value",
            texttemplate="<b>%{label}</b><br>R$ %{value:,.0f}",
            marker={
                "colorscale": "YlOrRd" if theme_mode == "light" else "OrRd",
                "line": {"width": 1.2, "color": tokens["surface_card"]},
            },
        )
    )
    fig.update_layout(
        template="kyberna_dark" if theme_mode == "dark" else "kyberna_light",
        title=None,
        height=280,
        margin={"l": 6, "r": 6, "t": 8, "b": 6},
    )
    return fig
