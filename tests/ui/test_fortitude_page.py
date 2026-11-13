from __future__ import annotations

import html

from streamlit.testing.v1 import AppTest

from src.core.paths import get_project_root


def test_fortitude_page_full_render() -> None:
    """Valida a renderização isolada da Página 2 (Fortaleza — Solvência & Resiliência)."""
    page_path = get_project_root() / "src" / "ui" / "pages" / "4_simulator.py"
    at = AppTest.from_file(str(page_path), default_timeout=10)
    at.run()

    assert not at.exception

    raw_markdown = " ".join(m.value for m in at.markdown)
    all_markdown = html.unescape(raw_markdown)

    # Cabeçalho Cockpit e Design System Kyberna
    assert "cockpit-header" in all_markdown
    assert "Fortaleza" in all_markdown
    assert "kyb-info-icon" in all_markdown
    assert "kyb-tooltip-popover" in all_markdown

    # 5 KPI Cards do Topo (DAR Strip 1)
    assert "Runway de Caixa" in all_markdown
    assert "Break-Even Mensal" in all_markdown
    assert "Ciclo Financeiro & NCG" in all_markdown
    assert "Concentração Top 5" in all_markdown
    assert "Carteira em Risco" in all_markdown

    # Seções Estruturais Cockpit e Veredito
    assert "Fôlego Financeiro & Equilíbrio" in all_markdown
    assert "Risco de Carteira & Concentração" in all_markdown
    assert "Auditoria de Vencimentos & Pareto" in all_markdown
    assert "Veredito da Fortaleza" in all_markdown

    # Tabelas operacionais com scroll interno
    assert len(at.dataframe) >= 2
