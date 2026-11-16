from __future__ import annotations

import html

from streamlit.testing.v1 import AppTest

from src.core.paths import get_project_root


def test_temperance_page_full_render() -> None:
    """Valida Página 4 (4. Temperança — Visão Integrada 360 Admin+Comercial+Finanças)."""
    page_path = get_project_root() / "src" / "ui" / "pages" / "3_inventory_demand.py"
    at = AppTest.from_file(str(page_path), default_timeout=15)
    at.run()

    assert not at.exception
    # Exatamente 3 abas de página estilo PowerBI (zero sub-abas internas)
    assert len(at.tabs) == 3

    all_markdown = html.unescape(" ".join(m.value for m in at.markdown))
    assert "kyb-info-icon" in all_markdown
    assert "kyb-tooltip-popover" in all_markdown
    assert "cockpit-header" in all_markdown
    assert "4. Temperança" in all_markdown
    assert "Síntese Executiva 360°" in all_markdown

    # Aba 1: Termômetro Executivo 360° (Mix dos 3 pilares)
    assert "[Finanças] Margem Líquida" in all_markdown
    assert "[Finanças] Ciclo & NCG" in all_markdown
    assert "[Comercial] Risco vs. Mix" in all_markdown
    assert "[Admin] Capital Travado" in all_markdown
    assert "[Síntese] Erosão Recuperável" in all_markdown
    assert "Veredito Integrado de Temperança" in all_markdown

    # Aba 2: Simulador Estratégico What-If
    slider_keys = {s.key for s in at.slider}
    assert {"_what_if_price", "_what_if_disc", "_what_if_cost", "sim_comm_pp"}.issubset(slider_keys)

    # Aba 3: Matriz Campeões vs. Vampiros 360°
    assert "Top 10 SKUs Campeões" in all_markdown
    assert "Top 10 SKUs Vampiros" in all_markdown

    assert len(at.dataframe) >= 5
    assert len(at.get("plotly_chart")) >= 4
