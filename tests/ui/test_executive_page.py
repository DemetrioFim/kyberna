from __future__ import annotations

from streamlit.testing.v1 import AppTest

from src.core.paths import get_project_root


def test_executive_page_full_render() -> None:
    """Valida renderização isolada da Tela 1 (Visão Executiva & Margem Real)."""
    page_path = get_project_root() / "src" / "ui" / "pages" / "1_executive.py"
    at = AppTest.from_file(str(page_path))
    at.run()

    assert not at.exception
    assert len(at.title) == 1
    assert "Visão Executiva & Margem Real" in at.title[0].value

    # Confere presença das abas de Produtos e Clientes
    assert len(at.tabs) >= 2

    # Confere presença dos ícones azuis de ajuda em cards e seções
    all_markdown = " ".join(m.value for m in at.markdown)
    assert "kyb-info-icon" in all_markdown
    assert "kyb-tooltip-popover" in all_markdown
    assert "Faturamento Bruto" in all_markdown
    assert "Receita Líquida" in all_markdown
    assert "Margem Contribuição" in all_markdown
    assert "Margem Líquida %" in all_markdown


def test_executive_page_abc_xyz_cell_selection() -> None:
    """Valida a interação de seleção de célula na Matriz ABC/XYZ."""
    page_path = get_project_root() / "src" / "ui" / "pages" / "1_executive.py"
    at = AppTest.from_file(str(page_path))
    at.run()

    assert not at.exception
    # Seleciona célula AX no selectbox da matriz
    assert len(at.selectbox) >= 1
    at.selectbox[0].set_value("AX").run()

    assert not at.exception
    assert at.session_state.selected_abc_xyz_cell == "AX"
