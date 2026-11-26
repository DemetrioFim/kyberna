from __future__ import annotations

import html

from streamlit.testing.v1 import AppTest

from src.core.paths import get_duckdb_path, get_project_root
from src.db.duckdb_repo import DuckDBRepository
from src.services.pricing_service import build_pricing_dashboard, get_pricing_shap_waterfall
from src.ui.components.pricing_charts import (
    price_band_boxplot_chart,
    pricing_shap_waterfall_chart,
)


def test_pricing_charts_render_light_and_dark() -> None:
    """Valida Boxplot contextual e SHAP Waterfall em Light e Dark Mode."""
    repo = DuckDBRepository(db_path=get_duckdb_path())
    pricing_dto = build_pricing_dashboard(repo, scenario_id="c1_toys")
    shap_dto = get_pricing_shap_waterfall(
        repo,
        scenario_id="c1_toys",
        scope_type="family",
        scope_id="Quebra-Cabeças",
    )

    for mode in ("light", "dark"):
        fig_box_pct = price_band_boxplot_chart(pricing_dto.boxplot_df, unit_mode="pct", theme_mode=mode)
        fig_box_brl = price_band_boxplot_chart(pricing_dto.boxplot_df, unit_mode="brl", theme_mode=mode)
        fig_shap_pct = pricing_shap_waterfall_chart(shap_dto, unit_mode="pct", theme_mode=mode)
        fig_shap_brl = pricing_shap_waterfall_chart(shap_dto, unit_mode="brl", theme_mode=mode)
        # Hover limpo: go.Bar e go.Box com hoverinfo='skip' + 1 Scatter de hover executivo
        assert len(fig_box_pct.data) == 3
        assert fig_box_pct.data[0].hoverinfo == "skip"
        assert fig_box_pct.data[1].hoverinfo == "skip"
        assert len(fig_box_brl.data) == 4
        assert len(fig_shap_pct.data) == 2
        assert len(fig_shap_brl.data) == 2
        assert fig_box_pct.layout.title.text is None
        assert fig_shap_pct.layout.title.text is None


def test_pricing_tab_shap_selector_interaction() -> None:
    """Valida interação no seletor SHAP de 3. Justiça Aba 3 via AppTest."""
    page_path = get_project_root() / "src" / "ui" / "pages" / "2_commercial_radar.py"
    at = AppTest.from_file(str(page_path), default_timeout=15)
    at.run()
    assert not at.exception

    all_markdown = html.unescape(" ".join(m.value for m in at.markdown))
    assert "Banda de Preço Realizado vs. Contextual (Boxplot)" in all_markdown
    assert "Drivers de Preço — SHAP Waterfall (Regressão)" in all_markdown
    assert "Auditoria de Desvios de Preço (Fora da Banda)" in all_markdown
    assert "Veredito de Política de Preços" in all_markdown

    shap_selectors = [sb for sb in at.selectbox if sb.key == "pricing_shap_scope_select"]
    assert len(shap_selectors) == 1
    options = list(shap_selectors[0].options)
    assert len(options) > 1
    shap_selectors[0].set_value(options[-1]).run()
    assert not at.exception

    # Alternância entre % Tabela e Valor Absoluto (R$) via st.toggle
    unit_toggles = [t for t in at.toggle if t.key == "pricing_unit_mode_toggle"]
    assert len(unit_toggles) == 1
    unit_toggles[0].set_value(True).run()
    assert not at.exception
