from __future__ import annotations

import html

from streamlit.testing.v1 import AppTest

from src.core.paths import get_project_root


def test_executive_page_full_render() -> None:
    """Valida Página 1 (1. Prudência — 100% Portfólio, Estoque & PCP) estilo PowerBI."""
    page_path = get_project_root() / "src" / "ui" / "pages" / "1_executive.py"
    at = AppTest.from_file(str(page_path), default_timeout=15)
    at.run()

    assert not at.exception
    # Exatamente 3 abas de página estilo PowerBI (zero sub-abas internas)
    assert len(at.tabs) == 3

    all_markdown = html.unescape(" ".join(m.value for m in at.markdown))
    assert "cockpit-header" in all_markdown
    assert "1. Prudência" in all_markdown
    assert "Visão Administrativa & Operações" in all_markdown
    assert "kyb-info-icon" in all_markdown
    assert "kyb-tooltip-popover" in all_markdown

    # KPIs das 3 Abas Administrativas / PCP (sem tautologia 80% nem vazamento comercial)
    assert "SKUs Ativos no Portfólio" in all_markdown
    assert "Margem de Contribuição Total" in all_markdown
    assert "SKUs na Curva A" in all_markdown
    assert "Margem na Curva A" not in all_markdown
    assert "Ticket Médio por Pedido" not in all_markdown
    assert "Capital Travado (>120d)" in all_markdown
    assert "Ruptura Iminente (Curva A)" in all_markdown
    assert "Projeção de Demanda (30d)" in all_markdown
    assert "Acurácia do Motor (WAPE)" in all_markdown
    assert "Variação Projetada (vs. 30d)" in all_markdown
    assert "Necessidade Líquida de Compra" in all_markdown
    assert "SKUs com Pico Sazonal" in all_markdown

    # Fragmento de Forecast 30d + Treemap reconciliado
    all_captions = " ".join(c.value for c in at.caption)
    assert "Capital Travado Excedente (>120d)" in all_captions
    assert "Modelo:" in all_captions

    sku_selectors = [sb for sb in at.selectbox if sb.key == "temperance_forecast_sku"]
    assert len(sku_selectors) == 1
    options = list(sku_selectors[0].options)
    if len(options) > 1:
        sku_selectors[0].set_value(options[1]).run()
        assert not at.exception


def test_executive_page_supply_boundaries_and_no_commercial_leak() -> None:
    """Valida fronteira 100% Supply/PCP na Página 1 (sem descontos comerciais, alçadas ou churn)."""
    page_path = get_project_root() / "src" / "ui" / "pages" / "1_executive.py"
    at = AppTest.from_file(str(page_path), default_timeout=15)
    at.run()

    assert not at.exception
    all_markdown = html.unescape(" ".join(m.value for m in at.markdown))
    assert "Matriz Estratégica ABC/XYZ 3x3" in all_markdown
    assert "Receita em Risco de Ruptura por Família" in all_markdown
    assert "Demanda Prevista 30d vs. Estoque Atual por Família" in all_markdown
    assert "Plano de Necessidade de Compra/Produção (por SKU)" in all_markdown
    assert "Radar de Anomalias de Supply" in all_markdown

    # Zero vazamento de tópicos de Fortaleza/Temperança na Página 1
    assert "Decomposição de Custos & Erosão" not in all_markdown
    assert "Descontos Fora" not in all_markdown
    assert "Auditoria de Alçadas" not in all_markdown
    assert "WhatsApp" not in all_markdown
    assert "Elasticidade-Preço" not in all_markdown
    assert len(at.get("plotly_chart")) >= 6
