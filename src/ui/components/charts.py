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

    # Textos dos valores para exibição direta nas barras (vetorizado com suporte a % de receita bruta)
    if "pct_of_gross" in steps_df.columns:
        text_values = [
            f"{format_brl(float(val), compact=True, decimals=1)} ({float(pct):.1f}%)"
            if m == "relative"
            else format_brl(float(val), compact=True, decimals=1)
            for val, pct, m in zip(
                steps_df["amount"],
                steps_df["pct_of_gross"],
                steps_df["measure"],
                strict=False,
            )
        ]
    else:
        text_values = [format_brl(float(val), compact=True, decimals=1) for val in steps_df["amount"]]

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
            annotation_position="top right",
            annotation_font_color=tokens["warning"],
        )

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
                sel_marker = " (Selecionado)" if is_sel else ""

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

    scatter_trace = go.Scatter(
        x=df[x_col],
        y=df[y_col],
        mode="markers+text",
        text=df[label_col],
        textposition="top center",
        marker=marker_kwargs,
        hovertemplate=(
            f"<b>%{{text}}</b><br>{x_col}: %{{x:,.2f}}<br>{y_col}: %{{y:,.1f}}%<br><extra></extra>"
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
    annotations = [
        go.layout.Annotation(
            xref="paper",
            yref="paper",
            x=0.98,
            y=0.98,
            xanchor="right",
            yanchor="top",
            text="<b>Estrela</b><br><span style='font-size:10px;'>Alto Vol. · Alta Margem</span>",
            showarrow=False,
            font={"size": 11, "color": text_color},
        ),
        go.layout.Annotation(
            xref="paper",
            yref="paper",
            x=0.98,
            y=0.02,
            xanchor="right",
            yanchor="bottom",
            text="<b>Volume sem Margem</b><br><span style='font-size:10px;'>Alto Vol. · Baixa Margem</span>",
            showarrow=False,
            font={"size": 11, "color": text_color},
        ),
        go.layout.Annotation(
            xref="paper",
            yref="paper",
            x=0.02,
            y=0.98,
            xanchor="left",
            yanchor="top",
            text="<b>Margem sem Volume</b><br><span style='font-size:10px;'>Baixo Vol. · Alta Margem</span>",
            showarrow=False,
            font={"size": 11, "color": text_color},
        ),
        go.layout.Annotation(
            xref="paper",
            yref="paper",
            x=0.02,
            y=0.02,
            xanchor="left",
            yanchor="bottom",
            text="<b>Atenção</b><br><span style='font-size:10px;'>Baixo Vol. · Baixa Margem</span>",
            showarrow=False,
            font={"size": 11, "color": text_color},
        ),
    ]

    fig.update_layout(
        template=template_name,
        title="<b>Quadrante de Eficiência Comercial (Cortes nas Medianas)</b>",
        xaxis_title=final_x_title,
        yaxis_title=final_y_title,
        annotations=annotations,
        showlegend=False,
        margin={"l": 40, "r": 40, "t": 60, "b": 40},
    )
    return fig
