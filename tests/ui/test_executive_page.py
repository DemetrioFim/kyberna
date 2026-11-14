from __future__ import annotations

from streamlit.testing.v1 import AppTest

from src.core.paths import get_project_root


def test_executive_page_full_render() -> None:
    """Valida renderização isolada da Tela 1 (Visão Executiva & Margem Real)."""
    page_path = get_project_root() / "src" / "ui" / "pages" / "1_executive.py"
    at = AppTest.from_file(str(page_path), default_timeout=10)
    at.run()

    assert not at.exception

    # Confere presença das abas de Produtos e Clientes e dos 3 sliders What-If
    assert len(at.tabs) >= 2
    slider_keys = {s.key for s in at.slider}
    assert {"_what_if_price", "_what_if_disc", "_what_if_cost"}.issubset(slider_keys)

    # Confere cabeçalho Cockpit e ícones azuis de ajuda em cards e seções
    all_markdown = " ".join(m.value for m in at.markdown)
    assert "cockpit-header" in all_markdown
    assert (
        "Visão Executiva &amp; Margem Real" in all_markdown or "Visão Executiva & Margem Real" in all_markdown
    )
    assert "kyb-info-icon" in all_markdown
    assert "kyb-tooltip-popover" in all_markdown
    assert "Faturamento Bruto" in all_markdown
    assert "Receita Líquida" in all_markdown
    assert "Margem Contribuição" in all_markdown
    assert "Margem Líquida %" in all_markdown


def test_executive_page_elasticity_section_rendered() -> None:
    """Valida a seção exclusiva de Elasticidade-Preço por Família na Página 1 — Prudência."""
    page_path = get_project_root() / "src" / "ui" / "pages" / "1_executive.py"
    at = AppTest.from_file(str(page_path), default_timeout=10)
    at.run()

    assert not at.exception
    all_markdown = " ".join(m.value for m in at.markdown)
    assert "Elasticidade-Preço por Família" in all_markdown
    assert len(at.get("plotly_chart")) >= 2
