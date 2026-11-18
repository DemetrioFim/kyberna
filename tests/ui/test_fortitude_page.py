from __future__ import annotations

import html

from streamlit.testing.v1 import AppTest

from src.core.paths import get_project_root


def test_fortitude_page_full_render() -> None:
    """Valida Página 2 (2. Fortaleza — Visão Comercial) com 3 abas PowerBI sem sub-abas."""
    page_path = get_project_root() / "src" / "ui" / "pages" / "4_simulator.py"
    at = AppTest.from_file(str(page_path), default_timeout=15)
    at.run()

    assert not at.exception
    assert len(at.tabs) == 3

    all_markdown = html.unescape(" ".join(m.value for m in at.markdown))
    assert "cockpit-header" in all_markdown
    assert "2. Fortaleza" in all_markdown
    assert "Inteligência Comercial" in all_markdown
    assert "kyb-info-icon" in all_markdown
    assert "kyb-tooltip-popover" in all_markdown

    # Aba 1: Cross-Sell & Modelo Apriori (Suporte, Confiança, Lift) + RFM livre em "Todos"
    assert "Potencial White Space" in all_markdown
    assert "Confiança & Suporte (Apriori)" in all_markdown
    assert "Alavancagem Máx. (Lift)" in all_markdown
    assert "Cobertura de Oportunidades" in all_markdown
    assert "Mapa de Oportunidades: Família x Segmento RFM" in all_markdown
    assert "Regras de Associação Apriori (Suporte x Confiança x Lift)" in all_markdown
    assert any(r.key == "ws_apriori_level" for r in at.radio)
    rfm_sb = next(sb for sb in at.selectbox if sb.key == "ws_filter_rfm")
    fam_sb = next(sb for sb in at.selectbox if sb.key == "ws_filter_family")
    assert rfm_sb.value == "Todos"
    assert fam_sb.value == "Todas"

    # Aba 2: Risco / Churn & Oportunidades (sem KPI duplicado da Aba 1)
    assert "em Risco" in all_markdown
    assert "Receita Anual em Risco" in all_markdown
    assert "Clientes Vampiros (<15% MC)" in all_markdown
    assert "Positivação de Carteira" in all_markdown

    # Aba 3: Equipe Comercial (RCAs)
    assert "Equipe Ativa" in all_markdown
    assert "Top RCAs por Desconto Fora do Teto" in all_markdown

    # Tabelas e botões de exportação comercial (.xlsx e .csv)
    assert len(at.dataframe) >= 4
    assert len(at.get("download_button")) >= 2
    assert len(at.get("plotly_chart")) >= 6

    # Alternância Apriori SKU -> Family sem exceção
    at.radio(key="ws_apriori_level").set_value("family").run()
    assert not at.exception
