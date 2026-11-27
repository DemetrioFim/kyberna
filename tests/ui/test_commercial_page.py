from __future__ import annotations

import html

from streamlit.testing.v1 import AppTest

from src.core.paths import get_project_root


def test_commercial_page_full_render() -> None:
    """Valida Página 3 (3. Justiça — DRE, Caixa & Precificação) com 3 abas PowerBI."""
    page_path = get_project_root() / "src" / "ui" / "pages" / "2_commercial_radar.py"
    at = AppTest.from_file(str(page_path), default_timeout=15)
    at.run()

    assert not at.exception
    assert len(at.tabs) == 3

    all_markdown = html.unescape(" ".join(m.value for m in at.markdown))
    assert "cockpit-header" in all_markdown
    assert "3. Justiça" in all_markdown
    assert "Governança Financeira, Caixa & Precificação" in all_markdown
    assert "kyb-info-icon" in all_markdown
    assert "kyb-tooltip-popover" in all_markdown

    # Aba 1: DRE Gerencial & Margem Real + Base comparativa global no header
    assert "Base:" in all_markdown
    assert "Faturamento Bruto" in all_markdown
    assert "Receita Líquida" in all_markdown
    assert "Margem Contribuição" in all_markdown
    assert "Margem de Contribuição %" in all_markdown
    assert "Deduções & Descontos" in all_markdown
    assert "Margem Líquida %" not in all_markdown

    # Aba 2: Fluxo de Caixa, Runway & Ciclo (NCG)
    assert "Runway de Caixa" in all_markdown
    assert "Break-Even Mensal" in all_markdown
    assert "Ciclo Financeiro & NCG" in all_markdown
    assert "Custo Financeiro de Prazo" in all_markdown
    assert "Concentração Top 10" in all_markdown
    assert "Receita Líq. em Atraso" not in all_markdown

    # Aba 3: Precificação, Banda Ideal & Drivers (SHAP)
    assert "Índice de Realização" in all_markdown
    assert "Dispersão de Preço (CV%)" in all_markdown
    assert "Vendas Abaixo da Banda" in all_markdown
    assert "Vazamento Subprecificação" in all_markdown
    assert "Potencial Reajuste (Inelást.)" in all_markdown
    assert "Aging de Recebíveis" not in all_markdown

    assert len(at.dataframe) >= 3
    assert len(at.get("plotly_chart")) >= 6


def test_justice_page_all_period_pop_vs_yoy_toggle() -> None:
    """Alternar comparison_mode para YoY em Histórico Completo atualiza o rótulo e os deltas reais."""
    page_path = get_project_root() / "src" / "ui" / "pages" / "2_commercial_radar.py"
    at = AppTest.from_file(str(page_path), default_timeout=15)
    at.session_state["comparison_mode"] = "yoy"
    at.run()
    assert not at.exception

    all_markdown = html.unescape(" ".join(m.value for m in at.markdown))
    assert "YoY · Base 12m" in all_markdown
    assert "-1,8%" in all_markdown
