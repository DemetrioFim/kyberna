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

    # Textos dos valores para exibição direta nas barras
    text_values: list[str] = []
    for _, row in steps_df.iterrows():
        val = float(row["amount"])
        compact_str = format_brl(val, compact=True, decimals=1)
        text_values.append(compact_str)

    fig = go.Figure(
        go.Waterfall(
            name="Waterfall",
            orientation="v",
            measure=steps_df["measure"].tolist(),
            x=steps_df["label"].tolist(),
            y=steps_df["amount"].tolist(),
            text=text_values,
            textposition="outside",
            connector={"line": {"color": tokens["border_subtle"], "width": 1.5, "dash": "dot"}},
            increasing={"marker": {"color": tokens["teal_500"]}},
            decreasing={"marker": {"color": tokens["negative"]}},
            totals={"marker": {"color": tokens["brass_500"]}},
        )
    )

    fig.update_layout(
        template=template_name,
        title="<b>Decomposição Contábil da Margem de Contribuição Líquida</b>",
        yaxis_title="Valor (R$)",
        showlegend=False,
        margin={"l": 40, "r": 40, "t": 60, "b": 40},
        waterfallgap=0.3,
    )
    return fig


def dual_trend(
    monthly_df: pd.DataFrame,
    theme_mode: str = "light",
) -> go.Figure:
    """Gera o gráfico de Tendência Dupla: Faturamento Bruto (Barras) x Margem Líquida % (Linha).

    Evidencia visualmente o 'efeito boca de jacaré' (quando a receita cresce mas a margem percentual cai).
    Espera colunas:
        - `month_label`: Rótulo do mês (ex: 'Jan/24', 'Fev/24').
        - `gross_revenue`: Receita bruta mensal (R$).
        - `margin_pct`: Margem de contribuição líquida percentual (ex: 27.5).
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
    )

    # Linha: Margem Líquida % (Eixo Secundário Y2)
    line_trace = go.Scatter(
        x=x_vals,
        y=monthly_df["margin_pct"].tolist(),
        name="Margem Líquida (%)",
        mode="lines+markers",
        line={"color": tokens["brass_500"], "width": 3},
        marker={"size": 8, "color": tokens["brass_500"]},
        yaxis="y2",
    )

    fig = go.Figure(data=[bar_trace, line_trace])

    fig.update_layout(
        template=template_name,
        title="<b>Evolução Mensal: Volume Faturado vs. Margem Real (%)</b>",
        yaxis={"title": "Faturamento Bruto (R$)", "side": "left", "showgrid": True},
        yaxis2={
            "title": "Margem Líquida (%)",
            "side": "right",
            "overlaying": "y",
            "ticksuffix": "%",
            "showgrid": False,
        },
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        margin={"l": 40, "r": 50, "t": 60, "b": 40},
    )
    return fig


def abc_xyz_heatmap(
    matrix_df: pd.DataFrame,
    theme_mode: str = "light",
    selected_cell: str | None = None,
) -> go.Figure:
    """Gera o mapa de calor da Matriz 3x3 ABC/XYZ com políticas prescritivas operacionais.

    Espera DataFrame com colunas:
        - `abc_class`: 'A', 'B', 'C'.
        - `xyz_class`: 'X', 'Y', 'Z'.
        - `sku_count`: Quantidade de produtos na célula.
        - `margin_share_pct`: Participação percentual na margem de contribuição.
        - `recommended_policy`: Política operacional resumida.
    """
    template_name = "kyberna_dark" if theme_mode == "dark" else "kyberna_light"

    abc_classes = ["A", "B", "C"]
    xyz_classes = ["X", "Y", "Z"]

    # Cria matrizes 3x3 para z (valores de cor) e texto anotado
    z_values: list[list[float]] = []
    text_matrix: list[list[str]] = []

    for abc in abc_classes:
        z_row: list[float] = []
        text_row: list[str] = []
        for xyz in xyz_classes:
            cell_code = f"{abc}{xyz}"
            match = matrix_df[(matrix_df["abc_class"] == abc) & (matrix_df["xyz_class"] == xyz)]
            if not match.empty:
                sku_cnt = int(match["sku_count"].iloc[0])
                m_share = float(match["margin_share_pct"].iloc[0])
                policy = str(match["recommended_policy"].iloc[0])
                # Trunca política longa para exibição compacta
                short_policy = policy.split("/", maxsplit=1)[0].strip() if "/" in policy else policy[:30]

                is_sel = selected_cell == cell_code
                sel_marker = " 👈" if is_sel else ""

                text_row.append(
                    f"<b>{cell_code}</b>{sel_marker}<br>"
                    f"<b>{sku_cnt} SKUs</b> ({m_share:.1f}% MC)<br>"
                    f"<i>{short_policy}</i>"
                )
                z_row.append(m_share)
            else:
                text_row.append(f"<b>{cell_code}</b><br>0 SKUs<br>—")
                z_row.append(0.0)

        z_values.append(z_row)
        text_matrix.append(text_row)

    fig = go.Figure(
        data=go.Heatmap(
            z=z_values,
            x=xyz_classes,
            y=abc_classes,
            text=text_matrix,
            texttemplate="%{text}",
            colorscale="Teal" if theme_mode == "light" else "Blues",
            showscale=False,
            hoverongaps=False,
        )
    )

    fig.update_layout(
        template=template_name,
        title="<b>Matriz ABC/XYZ (Relevância Financeira x Previsibilidade da Demanda)</b>",
        xaxis_title="<b>Volatilidade da Demanda (XYZ)</b> → X (Regular) | Y (Sazonal) | Z (Errático)",
        yaxis_title="<b>Relevância de Margem (ABC)</b> → A (80%) | B (15%) | C (5%)",
        margin={"l": 40, "r": 40, "t": 60, "b": 40},
    )
    return fig


def quadrant_scatter(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    *,
    label_col: str,
    size_col: str | None = None,
    theme_mode: str = "light",
) -> go.Figure:
    """Gera gráfico de dispersão em 4 quadrantes (ex: Eficiência Comercial de Representantes)."""
    tokens = get_theme_tokens(theme_mode)
    template_name = "kyberna_dark" if theme_mode == "dark" else "kyberna_light"

    if df.empty:
        fig = go.Figure()
        fig.update_layout(template=template_name, title="Sem dados para o quadrante")
        return fig

    med_x = float(df[x_col].median())
    med_y = float(df[y_col].median())

    marker_kwargs: dict[str, object] = {
        "color": tokens["teal_500"],
        "opacity": 0.85,
        "line": {"width": 1, "color": tokens["border_subtle"]},
    }
    if size_col and size_col in df.columns:
        marker_kwargs["size"] = df[size_col]
        marker_kwargs["sizemode"] = "area"
        marker_kwargs["sizeref"] = 2.0 * max(df[size_col]) / (40.0**2)
        marker_kwargs["sizemin"] = 6
    else:
        marker_kwargs["size"] = 12

    scatter_trace = go.Scatter(
        x=df[x_col],
        y=df[y_col],
        mode="markers+text",
        text=df[label_col],
        textposition="top center",
        marker=marker_kwargs,
    )

    fig = go.Figure(data=[scatter_trace])

    # Linhas de quadrante nas medianas
    fig.add_vline(x=med_x, line_dash="dash", line_color=tokens["chart_zero_line"], opacity=0.8)
    fig.add_hline(y=med_y, line_dash="dash", line_color=tokens["chart_zero_line"], opacity=0.8)

    fig.update_layout(
        template=template_name,
        title="<b>Quadrante de Eficiência Comercial (Cortes nas Medianas)</b>",
        xaxis_title=x_col.replace("_", " ").title(),
        yaxis_title=y_col.replace("_", " ").title(),
        showlegend=False,
        margin={"l": 40, "r": 40, "t": 60, "b": 40},
    )
    return fig
