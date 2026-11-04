from __future__ import annotations

import pandas as pd

from src.ui.components.charts import (
    abc_xyz_heatmap,
    dual_trend,
    quadrant_scatter,
    waterfall_margin,
)


def test_waterfall_margin_figure_light_and_dark() -> None:
    """Gera figura Waterfall nos modos claro e escuro e valida traces."""
    steps = pd.DataFrame(
        [
            {"label": "Fat. Bruto", "amount": 100000.0, "measure": "absolute"},
            {"label": "Descontos", "amount": -10000.0, "measure": "relative"},
            {"label": "Rec. Líquida", "amount": 90000.0, "measure": "total"},
            {"label": "CMV", "amount": -50000.0, "measure": "relative"},
            {"label": "Margem Líquida", "amount": 40000.0, "measure": "total"},
        ]
    )

    fig_light = waterfall_margin(steps, theme_mode="light")
    assert "Inter" in fig_light.layout.template.layout.font.family
    assert len(fig_light.data) == 1
    assert fig_light.data[0].type == "waterfall"

    fig_dark = waterfall_margin(steps, theme_mode="dark")
    assert len(fig_dark.data) == 1

    # DataFrame vazio não lança erro
    fig_empty = waterfall_margin(pd.DataFrame(), theme_mode="light")
    assert len(fig_empty.data) == 0


def test_dual_trend_figure_light_and_dark() -> None:
    """Gera figura de Tendência Dupla (Barras + Linha) e valida layout com 2 eixos Y."""
    monthly = pd.DataFrame(
        [
            {"month_label": "Jan/24", "gross_revenue": 500000.0, "margin_pct": 28.5},
            {"month_label": "Fev/24", "gross_revenue": 520000.0, "margin_pct": 27.2},
            {"month_label": "Mar/24", "gross_revenue": 580000.0, "margin_pct": 25.1},
        ]
    )

    fig = dual_trend(monthly, theme_mode="light")
    assert len(fig.data) == 2
    assert fig.data[0].type == "bar"
    assert fig.data[1].type == "scatter"
    assert fig.layout.yaxis2.overlaying == "y"


def test_abc_xyz_heatmap_figure() -> None:
    """Gera mapa de calor da Matriz 3x3 ABC/XYZ e confere anotações de célula."""
    matrix_data = []
    for abc in ["A", "B", "C"]:
        for xyz in ["X", "Y", "Z"]:
            matrix_data.append(
                {
                    "abc_class": abc,
                    "xyz_class": xyz,
                    "sku_count": 10,
                    "margin_share_pct": 11.1,
                    "recommended_policy": "Ruptura zero / JIT",
                }
            )
    matrix_df = pd.DataFrame(matrix_data)

    fig = abc_xyz_heatmap(matrix_df, theme_mode="dark", selected_cell="AX")
    assert len(fig.data) == 1
    assert fig.data[0].type == "heatmap"
    assert list(fig.data[0].x) == ["X", "Y", "Z"]
    assert list(fig.data[0].y) == ["A", "B", "C"]


def test_quadrant_scatter_figure() -> None:
    """Gera gráfico de dispersão com linhas de quadrante nas medianas."""
    reps_data = pd.DataFrame(
        [
            {"name": "RCA 1", "revenue": 100000.0, "margin_pct": 32.0, "risk_val": 5000.0},
            {"name": "RCA 2", "revenue": 150000.0, "margin_pct": 22.0, "risk_val": 12000.0},
            {"name": "RCA 3", "revenue": 80000.0, "margin_pct": 29.0, "risk_val": 3000.0},
            {"name": "RCA 4", "revenue": 200000.0, "margin_pct": 19.0, "risk_val": 25000.0},
        ]
    )

    fig = quadrant_scatter(
        reps_data,
        x_col="revenue",
        y_col="margin_pct",
        label_col="name",
        size_col="risk_val",
        theme_mode="light",
    )
    assert len(fig.data) == 1
    assert fig.data[0].type == "scatter"
    # Confere se as linhas divisórias de quadrante (shapes) foram adicionadas
    assert len(fig.layout.shapes) >= 2
