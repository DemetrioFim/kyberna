from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest
from streamlit.testing.v1 import AppTest

from src.core.paths import get_project_root
from src.core.scenarios import load_scenario_config
from src.db.azure_sql_repo import AzureSQLRepository
from src.db.duckdb_repo import DuckDBRepository
from src.ui.components.sidebar import _render_data_source_badge
from src.ui.period_options import DEFAULT_MAX_DATE, DEFAULT_MIN_DATE, get_default_date_bounds
from src.ui.state import (
    AppState,
    ComparisonMode,
    build_month_options,
    build_quarter_options,
    build_semester_options,
    fetch_date_bounds,
    resolve_period_bounds,
)


def _sidebar_entrypoint() -> None:
    """Script isolado de teste para exercitar o ciclo de vida completo da sidebar."""
    import src.ui.components.sidebar as st_sidebar
    import src.ui.state as st_state
    from src.db.duckdb_repo import DuckDBRepository

    st_state.init_app_state()
    st_sidebar.render_sidebar(repo=DuckDBRepository())


def test_app_state_defaults() -> None:
    """Verifica os valores padrão da estrutura imutável AppState."""
    state = AppState()
    assert state.theme_mode == "light"
    assert state.scenario_id == "c1_toys"
    assert state.period_preset == "all"
    assert state.comparison_mode == "pop"
    assert state.selected_quarter == "2024-Q4"
    assert state.selected_semester == "2024-S2"
    assert state.regiao == "Todas"
    assert state.uf == "Todas"
    assert state.families == ()
    assert state.sales_reps == ()
    assert state.selected_abc_xyz_cell is None
    assert state.pending_month is None
    assert not state.presentation_mode


def test_default_date_bounds_two_full_years_plus_current() -> None:
    """Garante fallback dinâmico com D-1 (ontem) e 01/01 do segundo ano anterior."""
    from datetime import timedelta

    expected_max = date.today() - timedelta(days=1)
    assert expected_max == DEFAULT_MAX_DATE
    assert date(expected_max.year - 2, 1, 1) == DEFAULT_MIN_DATE

    assert get_default_date_bounds(date(2026, 11, 14)) == (date(2024, 1, 1), date(2026, 11, 14))
    assert get_default_date_bounds(date(2027, 3, 10)) == (date(2025, 1, 1), date(2027, 3, 10))


def test_dynamic_date_option_builders_and_bounds() -> None:
    """Verifica descoberta dinâmica de limites e geração de opções mês/trimestre/semestre."""
    repo = DuckDBRepository()
    min_d, max_d = fetch_date_bounds(repo, "c1_toys")
    assert min_d == date(2023, 1, 1)
    assert max_d == date(2024, 12, 31)

    shifted_min = date(2024, 11, 10)
    shifted_max = date(2026, 11, 10)
    months = build_month_options(shifted_min, shifted_max)
    assert next(iter(months)) == "2026-11"
    assert "2026-08" in months
    assert len(months) == 25

    quarters = build_quarter_options(shifted_min, shifted_max)
    assert next(iter(quarters)) == "2026-Q4"
    assert "2025-Q2" in quarters
    assert "2024-Q4" in quarters

    semesters = build_semester_options(shifted_min, shifted_max)
    assert next(iter(semesters)) == "2026-S2"
    assert "2025-S1" in semesters


@pytest.mark.parametrize(
    "preset",
    [
        "all",
        "ytd",
        "fixed_quarter",
        "rolling_quarter",
        "fixed_semester",
        "custom_month",
        "custom_range",
        "last_12m",
        "last_6m",
        "last_3m",
        "last_month",
        "s2",
        "q4",
    ],
)
@pytest.mark.parametrize("mode", ["pop", "yoy"])
def test_resolve_period_bounds_matrix(preset: str, mode: ComparisonMode) -> None:
    """Valida todos os presets temporais (incluindo aliases legados) x modos PoP e YoY."""
    bounds = resolve_period_bounds(
        preset,
        selected_month="2024-11",
        comparison_mode=mode,
        selected_quarter="2024-Q2",
        selected_semester="2024-S2",
        rolling_end_month="2024-04",
        custom_start="2024-05-01",
        custom_end="2024-06-15",
        min_date=date(2023, 1, 1),
        max_date=date(2024, 12, 31),
    )
    if preset == "all":
        assert bounds.start_date_key is None
        assert bounds.end_date_key is None
        return

    assert bounds.start_date_key is not None
    assert bounds.end_date_key is not None
    assert bounds.start_date_key <= bounds.end_date_key
    assert bounds.comparison_start_date_key is not None
    assert bounds.comparison_end_date_key is not None
    assert bounds.comparison_start_date_key <= bounds.comparison_end_date_key
    assert bounds.comparison_end_date_key < bounds.end_date_key


def test_resolve_period_bounds_exact_pop_vs_yoy_semantics() -> None:
    """Confere regras exatas de YTD parcial, trimestre fixo, trimestre móvel e intervalo livre."""
    # YTD parcial vs YTD anterior (ex.: Jan-Ago/2026 vs Jan-Ago/2025)
    ytd_yoy = resolve_period_bounds(
        "ytd",
        comparison_mode="yoy",
        min_date=date(2024, 8, 20),
        max_date=date(2026, 8, 20),
    )
    assert ytd_yoy.start_date_key == 20260101
    assert ytd_yoy.end_date_key == 20260820
    assert ytd_yoy.comparison_start_date_key == 20250101
    assert ytd_yoy.comparison_end_date_key == 20250820

    # Trimestre Fixo 2º Tri/24: PoP vs 1º Tri/24 | YoY vs 2º Tri/23
    q2_pop = resolve_period_bounds("fixed_quarter", selected_quarter="2024-Q2", comparison_mode="pop")
    assert (q2_pop.start_date_key, q2_pop.end_date_key) == (20240401, 20240630)
    assert (q2_pop.comparison_start_date_key, q2_pop.comparison_end_date_key) == (20240101, 20240331)

    q2_yoy = resolve_period_bounds("fixed_quarter", selected_quarter="2024-Q2", comparison_mode="yoy")
    assert (q2_yoy.comparison_start_date_key, q2_yoy.comparison_end_date_key) == (20230401, 20230630)

    # Trimestre Móvel Fev-Abr/24: PoP vs Nov/23-Jan/24 | YoY vs Fev-Abr/23
    roll_pop = resolve_period_bounds("rolling_quarter", rolling_end_month="2024-04", comparison_mode="pop")
    assert (roll_pop.start_date_key, roll_pop.end_date_key) == (20240201, 20240430)
    assert (roll_pop.comparison_start_date_key, roll_pop.comparison_end_date_key) == (20231101, 20240131)


def test_data_source_badge_rendering() -> None:
    """Testa a geração do HTML do badge para diferentes backends e cenários de fallback."""
    html_none = _render_data_source_badge(None)
    assert "Fonte: Snapshot Local" in html_none
    assert "badge-source" in html_none

    mock_azure = MagicMock(spec=AzureSQLRepository)
    mock_azure.backend = "azure_sql"
    mock_azure.fallback_reason = None
    html_azure = _render_data_source_badge(mock_azure)
    assert "Fonte: Azure SQL" in html_azure
    assert "badge-positive" in html_azure

    mock_fallback = MagicMock(spec=DuckDBRepository)
    mock_fallback.backend = "duckdb"
    mock_fallback.fallback_reason = "Banco Azure SQL em auto-pause (40613)"
    html_fallback = _render_data_source_badge(mock_fallback)
    assert "Fonte: Snapshot Local (Fallback)" in html_fallback
    assert "badge-warning" in html_fallback

    mock_duck = MagicMock(spec=DuckDBRepository)
    mock_duck.backend = "duckdb"
    mock_duck.fallback_reason = None
    html_duck = _render_data_source_badge(mock_duck)
    assert "Fonte: Snapshot Local (DuckDB)" in html_duck
    assert "badge-source" in html_duck


def test_sidebar_scenario_label_switching_and_bottom_order() -> None:
    """AppTest: Cenário fica no final da sidebar e alterna o vocabulário dinamicamente."""
    at = AppTest.from_function(_sidebar_entrypoint)
    at.run()
    assert not at.exception

    # Ordem ergonômica: Período no topo, Cenário no final (antes apenas do badge)
    assert at.sidebar.selectbox[0].key == "_period_preset_select"
    assert at.sidebar.selectbox[-1].key == "_scenario_select"
    assert at.session_state.scenario_id == "c1_toys"

    c1_cfg = load_scenario_config("c1_toys")
    assert any(c1_cfg.labels.product_family in ms.label for ms in at.sidebar.multiselect)
    assert any(c1_cfg.labels.sales_rep in ms.label for ms in at.sidebar.multiselect)

    at.sidebar.selectbox(key="_scenario_select").set_value("c2_beverages").run()
    assert not at.exception
    assert at.session_state.scenario_id == "c2_beverages"

    at.sidebar.selectbox(key="_scenario_select").set_value("c3_retail_chain").run()
    assert not at.exception
    assert at.session_state.scenario_id == "c3_retail_chain"

    at.sidebar.selectbox(key="_scenario_select").set_value("c4_single_store").run()
    assert not at.exception
    assert at.session_state.scenario_id == "c4_single_store"
    assert len(at.sidebar.multiselect) == 1


def test_sidebar_cascade_and_progressive_period_controls() -> None:
    """AppTest: Progressive disclosure de Trimestre/Semestre/Calendário e cascata UF."""
    at = AppTest.from_function(_sidebar_entrypoint)
    at.run()

    # Trimestre Fixo abre apenas _selected_quarter_select
    at.sidebar.selectbox(key="_period_preset_select").set_value("fixed_quarter").run()
    assert not at.exception
    assert any(sb.key == "_selected_quarter_select" for sb in at.sidebar.selectbox)
    at.sidebar.selectbox(key="_selected_quarter_select").set_value("2024-Q2").run()
    assert at.session_state.selected_quarter == "2024-Q2"

    # Intervalo Personalizado abre st.date_input
    at.sidebar.selectbox(key="_period_preset_select").set_value("custom_range").run()
    assert not at.exception
    assert len(at.sidebar.date_input) == 1

    # Retorna para Histórico Completo e testa cascata Região -> UF
    at.sidebar.selectbox(key="_period_preset_select").set_value("all").run()
    at.sidebar.selectbox(key="_regiao_select").set_value("Sul").run()
    assert at.session_state.regiao == "Sul"

    at.sidebar.selectbox(key="_uf_select").set_value("PR").run()
    assert at.session_state.uf == "PR"

    at.sidebar.selectbox(key="_regiao_select").set_value("Sudeste").run()
    assert at.session_state.regiao == "Sudeste"
    assert at.session_state.uf == "Todas"


def test_executive_pop_yoy_toggle_and_app_render() -> None:
    """AppTest: Toggle global YoY na Sidebar e Barra Superior alterna comparison_mode e app.py renderiza."""
    at_side = AppTest.from_function(_sidebar_entrypoint, default_timeout=15)
    at_side.run()
    assert not at_side.exception

    comp_toggle = next(t for t in at_side.sidebar.toggle if t.key == "_comparison_mode_toggle")
    assert comp_toggle.value is False
    comp_toggle.set_value(True).run()
    assert not at_side.exception
    assert at_side.session_state.comparison_mode == "yoy"

    app_path = get_project_root() / "src" / "ui" / "app.py"
    at_app = AppTest.from_file(str(app_path), default_timeout=15)
    at_app.run()
    assert not at_app.exception
    assert at_app.session_state.comparison_mode == "pop"
    assert len(at_app.sidebar.selectbox) >= 4
    assert at_app.sidebar.selectbox[-1].key == "_scenario_select"
    assert "Fonte:" in at_app.sidebar.markdown[-1].value

    # Alternância para Opção B (Filtros no Topo estilo PowerBI) inclui toggle YoY global
    def _top_filter_entrypoint() -> None:
        import src.ui.components.filter_controls as fc
        import src.ui.components.sidebar as st_sidebar
        import src.ui.state as st_state
        from src.core.scenarios import load_scenario_config
        from src.db.duckdb_repo import DuckDBRepository

        repo_local = DuckDBRepository()
        st_state.init_app_state()
        st_local = st_sidebar.render_sidebar(repo=repo_local)
        if st_local.filter_layout == "top":
            fc.render_top_filter_bar(repo_local, load_scenario_config(st_local.scenario_id))

    at_top = AppTest.from_function(_top_filter_entrypoint, default_timeout=15)
    at_top.run()
    assert not at_top.exception
    layout_toggle = next(t for t in at_top.sidebar.toggle if t.key == "_filter_layout_toggle")
    layout_toggle.set_value(True).run()
    assert not at_top.exception
    assert at_top.session_state.filter_layout == "top"
    assert any(sb.key == "_period_preset_select" for sb in at_top.main.selectbox)
    assert any(t.key == "_comparison_mode_toggle" for t in at_top.main.toggle)
    assert not any(sb.key == "_period_preset_select" for sb in at_top.sidebar.selectbox)
