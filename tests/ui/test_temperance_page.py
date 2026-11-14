from __future__ import annotations

from streamlit.testing.v1 import AppTest

from src.core.paths import get_project_root


def test_temperance_page_full_render() -> None:
    """Valida a renderização isolada da Página 4 (Temperança — Eficiência & Capital de Giro)."""
    page_path = get_project_root() / "src" / "ui" / "pages" / "3_inventory_demand.py"
    at = AppTest.from_file(str(page_path), default_timeout=10)
    at.run()

    assert not at.exception

    all_markdown = " ".join(m.value for m in at.markdown)

    # Design System Kyberna e Ícones de Informação
    assert "kyb-info-icon" in all_markdown
    assert "kyb-tooltip-popover" in all_markdown

    # Título e Cabeçalho Cockpit de Temperança
    assert "cockpit-header" in all_markdown
    assert "Eficiência Operacional" in all_markdown
    assert "4. Temperança" in all_markdown

    # 5 KPI Cards
    assert "Erosão Comercial Total" in all_markdown
    assert "Descontos Fora de Tabela" in all_markdown
    assert "Custo de Prazo Esticado" in all_markdown
    assert "Capital Travado" in all_markdown
    assert "Ruptura Iminente (Curva A)" in all_markdown

    # Seções Estruturais e Veredito
    assert "Decomposição da Erosão Comercial" in all_markdown
    assert "Auditoria de Política Comercial" in all_markdown
    assert "Gestão Prescritiva de Estoque" in all_markdown
    assert "Veredito de Temperança" in all_markdown

    # Integração M4-V1: Reconciliação de Capital Travado, seletor de SKU no fragmento e gráficos
    all_captions = " ".join(c.value for c in at.caption)
    assert "Capital Travado Excedente (>120d)" in all_captions
    assert "Modelo:" in all_captions
    assert len(at.dataframe) >= 2
    assert len(at.get("plotly_chart")) >= 4

    sku_selectors = [sb for sb in at.selectbox if sb.key == "temperance_forecast_sku"]
    assert len(sku_selectors) == 1
    options = list(sku_selectors[0].options)
    if len(options) > 1:
        sku_selectors[0].set_value(options[1]).run()
        assert not at.exception
