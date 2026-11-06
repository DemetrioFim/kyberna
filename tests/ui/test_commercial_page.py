from __future__ import annotations

from streamlit.testing.v1 import AppTest

from src.core.paths import get_project_root


def test_commercial_page_full_render() -> None:
    """Valida a renderização isolada da Tela 2 (Radar Comercial, RFM & Antecipação de Churn)."""
    page_path = get_project_root() / "src" / "ui" / "pages" / "2_commercial_radar.py"
    at = AppTest.from_file(str(page_path))
    at.run()

    assert not at.exception

    # Confere presença de tooltips e design system Kyberna
    all_markdown = " ".join(m.value for m in at.markdown)
    assert "kyb-info-icon" in all_markdown
    assert "kyb-tooltip-popover" in all_markdown
    assert "Radar Comercial" in all_markdown
    assert "Clientes em Risco" in all_markdown
    assert "Receita Anual em Risco" in all_markdown
    assert "Oportunidade White Space" in all_markdown
    assert "Positivação de Carteira" in all_markdown

    # Confere presença das seções analíticas e dataframes
    assert len(at.dataframe) >= 1
