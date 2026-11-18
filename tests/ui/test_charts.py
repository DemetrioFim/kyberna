from __future__ import annotations

import pandas as pd

from src.ui.components.apriori_charts import (
    apriori_rules_scatter,
    white_space_heatmap_v2,
)
from src.ui.components.charts import (
    dual_trend,
    quadrant_scatter,
    waterfall_margin,
)
from src.ui.components.inventory_charts import abc_xyz_heatmap


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


def test_white_space_heatmap_v2_and_apriori_scatter_light_dark() -> None:
    """Valida heatmap aprimorado (9 segmentos RFM) e bolhas Apriori em light/dark mode."""
    ws_df = pd.DataFrame(
        [
            {
                "recommended_family": "Pelúcias",
                "rfm_segment": "Fiéis",
                "opportunities_count": 12,
                "potential_revenue_brl": 48000.0,
                "potential_margin_brl": 12000.0,
                "avg_confidence_pct": 28.5,
                "avg_lift": 1.18,
            },
            {
                "recommended_family": "Pelúcias",
                "rfm_segment": "Campeões",
                "opportunities_count": 8,
                "potential_revenue_brl": 32000.0,
                "potential_margin_brl": 9000.0,
                "avg_confidence_pct": 31.0,
                "avg_lift": 1.24,
            },
        ]
    )
    for mode in ("light", "dark"):
        fig_hm = white_space_heatmap_v2(ws_df, theme_mode=mode)
        assert len(fig_hm.data) == 1
        assert fig_hm.data[0].type == "heatmap"
        # Campeões deve vir antes de Fiéis na ordenação lógica RFM
        assert list(fig_hm.data[0].x) == ["Campeões", "Fiéis"]
        assert len(fig_hm.layout.annotations) == 2

    rules_df = pd.DataFrame(
        [
            {
                "rule_level": "sku",
                "antecedent_name": "Produto A",
                "consequent_name": "Produto B",
                "pair_baskets": 40,
                "support_pct": 2.1,
                "confidence_pct": 33.5,
                "lift": 1.38,
            },
            {
                "rule_level": "family",
                "antecedent_name": "Pelúcias",
                "consequent_name": "Quebra-Cabeças",
                "pair_baskets": 500,
                "support_pct": 15.8,
                "confidence_pct": 75.2,
                "lift": 1.02,
            },
        ]
    )
    for mode in ("light", "dark"):
        fig_sc = apriori_rules_scatter(rules_df, rule_level="sku", theme_mode=mode)
        assert len(fig_sc.data) == 1
        assert fig_sc.data[0].type == "scatter"
        assert list(fig_sc.data[0].x) == [2.1]

    # DataFrames vazios não lançam erro
    assert len(white_space_heatmap_v2(pd.DataFrame()).data) == 0
    assert len(apriori_rules_scatter(pd.DataFrame()).data) == 0
