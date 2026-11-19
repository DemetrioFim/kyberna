from __future__ import annotations

import html

from streamlit.testing.v1 import AppTest

from src.core.paths import get_project_root


def test_commercial_page_full_render() -> None:
    """Valida Página 3 (3. Justiça — Visão Financeira) com 3 abas PowerBI sem sub-abas."""
    page_path = get_project_root() / "src" / "ui" / "pages" / "2_commercial_radar.py"
    at = AppTest.from_file(str(page_path), default_timeout=15)
    at.run()

    assert not at.exception
    assert len(at.tabs) == 3

    all_markdown = html.unescape(" ".join(m.value for m in at.markdown))
    assert "cockpit-header" in all_markdown
    assert "3. Justiça" in all_markdown
    assert "Governança Financeira" in all_markdown
    assert "kyb-info-icon" in all_markdown
    assert "kyb-tooltip-popover" in all_markdown

    # Aba 1: DRE Gerencial & Margem Real + Toggle PoP/YoY
    assert any(r.key == "_comparison_mode_radio" for r in at.radio)
    assert "Faturamento Bruto" in all_markdown
    assert "Receita Líquida" in all_markdown
    assert "Margem Contribuição" in all_markdown
    assert "Margem Líquida %" in all_markdown

    # Aba 2: Fluxo de Caixa, Runway & Ciclo (NCG)
    assert "Runway de Caixa" in all_markdown
    assert "Break-Even Mensal" in all_markdown
    assert "Ciclo Financeiro & NCG" in all_markdown

    # Aba 3: Aging de Recebíveis & Concentração Pareto
    assert "Carteira em Atraso (>1,5x)" in all_markdown
    assert "Concentração Top 5 Clientes" in all_markdown

    assert len(at.dataframe) >= 4
    assert len(at.get("plotly_chart")) >= 6


def test_justice_page_all_period_pop_vs_yoy_toggle() -> None:
    """Alternar PoP vs YoY em Histórico Completo atualiza o rótulo comparativo e os deltas reais."""
    page_path = get_project_root() / "src" / "ui" / "pages" / "2_commercial_radar.py"
    at = AppTest.from_file(str(page_path), default_timeout=15)
    at.run()
    assert not at.exception

    radios = [r for r in at.radio if r.key == "_comparison_mode_radio"]
    assert len(radios) == 1
    radios[0].set_value("yoy").run()
    assert not at.exception

    all_markdown = html.unescape(" ".join(m.value for m in at.markdown))
    assert "YoY · Base 12m" in all_markdown
    assert "-1,8%" in all_markdown
