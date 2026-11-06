from __future__ import annotations

from unittest.mock import MagicMock

from streamlit.testing.v1 import AppTest

from src.core.paths import get_project_root
from src.core.scenarios import load_scenario_config
from src.db.azure_sql_repo import AzureSQLRepository
from src.db.duckdb_repo import DuckDBRepository
from src.ui.components.sidebar import _render_data_source_badge
from src.ui.state import (
    AppState,
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
    assert state.regiao == "Todas"
    assert state.uf == "Todas"
    assert state.families == ()
    assert state.sales_reps == ()
    assert state.selected_abc_xyz_cell is None
    assert state.pending_month is None
    assert not state.presentation_mode


def test_data_source_badge_rendering() -> None:
    """Testa a geração do HTML do badge para diferentes backends e cenários de fallback."""
    # 1. Repositório nulo
    html_none = _render_data_source_badge(None)
    assert "Fonte: Snapshot Local" in html_none
    assert "badge-source" in html_none

    # 2. Azure SQL conectado
    mock_azure = MagicMock(spec=AzureSQLRepository)
    mock_azure.backend = "azure_sql"
    mock_azure.fallback_reason = None
    html_azure = _render_data_source_badge(mock_azure)
    assert "Fonte: Azure SQL" in html_azure
    assert "badge-positive" in html_azure

    # 3. DuckDB com auto-fallback ativo
    mock_fallback = MagicMock(spec=DuckDBRepository)
    mock_fallback.backend = "duckdb"
    mock_fallback.fallback_reason = "Banco Azure SQL em auto-pause (40613)"
    html_fallback = _render_data_source_badge(mock_fallback)
    assert "Fonte: Snapshot Local (Fallback)" in html_fallback
    assert "badge-warning" in html_fallback
    assert "Banco Azure SQL em auto-pause (40613)" in html_fallback

    # 4. DuckDB local explícito sem erro
    mock_duck = MagicMock(spec=DuckDBRepository)
    mock_duck.backend = "duckdb"
    mock_duck.fallback_reason = None
    html_duck = _render_data_source_badge(mock_duck)
    assert "Fonte: Snapshot Local (DuckDB)" in html_duck
    assert "badge-source" in html_duck


def test_sidebar_scenario_label_switching() -> None:
    """AppTest: Comprova a troca dinâmica de vocabulário e rótulos ao alternar cenários."""
    at = AppTest.from_function(_sidebar_entrypoint)
    at.run()
    assert not at.exception

    # Cenário 1 (Brinquedos)
    assert at.session_state.scenario_id == "c1_toys"
    c1_cfg = load_scenario_config("c1_toys")
    assert any(c1_cfg.labels.product_family in ms.label for ms in at.sidebar.multiselect)
    assert any(c1_cfg.labels.sales_rep in ms.label for ms in at.sidebar.multiselect)

    # Muda para Cenário 2 (Bebidas)
    at.sidebar.selectbox[0].set_value("c2_beverages").run()
    assert not at.exception
    assert at.session_state.scenario_id == "c2_beverages"
    c2_cfg = load_scenario_config("c2_beverages")
    assert any(c2_cfg.labels.product_family in ms.label for ms in at.sidebar.multiselect)
    assert any(c2_cfg.labels.sales_rep in ms.label for ms in at.sidebar.multiselect)

    # Muda para Cenário 3 (Rede de Varejo)
    at.sidebar.selectbox[0].set_value("c3_retail_chain").run()
    assert not at.exception
    assert at.session_state.scenario_id == "c3_retail_chain"
    c3_cfg = load_scenario_config("c3_retail_chain")
    assert any(c3_cfg.labels.product_family in ms.label for ms in at.sidebar.multiselect)
    assert any(c3_cfg.labels.sales_rep in ms.label for ms in at.sidebar.multiselect)

    # Muda para Cenário 4 (Loja Única PDV) — Não tem rep_efficiency
    at.sidebar.selectbox[0].set_value("c4_single_store").run()
    assert not at.exception
    assert at.session_state.scenario_id == "c4_single_store"
    # No C4, rep_efficiency é falso, então deve ter apenas o multiselect de produto
    assert len(at.sidebar.multiselect) == 1


def test_sidebar_cascade_and_filters_persistence() -> None:
    """AppTest: Garante que seleção temporal, geográfica e filtros persistem na sessão."""
    at = AppTest.from_function(_sidebar_entrypoint)
    at.run()

    # Seleciona Período YTD (selectbox 1)
    at.sidebar.selectbox[1].set_value("ytd").run()
    assert not at.exception
    assert at.session_state.period_preset == "ytd"

    # Seleciona Região Sul (selectbox 2)
    at.sidebar.selectbox[2].set_value("Sul").run()
    assert not at.exception
    assert at.session_state.regiao == "Sul"

    # Seleciona UF PR (selectbox 3)
    at.sidebar.selectbox[3].set_value("PR").run()
    assert not at.exception
    assert at.session_state.uf == "PR"

    # Muda Região para Sudeste -> Deve resetar UF para "Todas"
    at.sidebar.selectbox[2].set_value("Sudeste").run()
    assert not at.exception
    assert at.session_state.regiao == "Sudeste"
    assert at.session_state.uf == "Todas"


def test_app_main_renders_with_sidebar() -> None:
    """AppTest: Garante que app.py completo renderiza com a sidebar integrada."""
    app_path = get_project_root() / "src" / "ui" / "app.py"
    at = AppTest.from_file(str(app_path))
    at.run()
    assert not at.exception
    assert len(at.sidebar.selectbox) >= 3
    assert len(at.sidebar.toggle) >= 1
    assert "Fonte:" in at.sidebar.markdown[-1].value
