from __future__ import annotations

from streamlit.testing.v1 import AppTest

from src.core.paths import get_project_root


def test_app_initial_render() -> None:
    """Verifica se o app Streamlit renderiza a página padrão (Visão Executiva) sem exceções."""
    app_path = get_project_root() / "src" / "ui" / "app.py"
    at = AppTest.from_file(str(app_path))
    at.run()
    assert not at.exception
    assert at.session_state.theme_mode == "light"
    assert at.session_state.scenario_id == "c1_toys"
    assert at.session_state.regiao == "Todas"
    assert at.session_state.uf == "Todas"

    # Confere se o título da página executiva está presente
    assert len(at.title) >= 1
    assert "Visão Executiva" in at.title[0].value


def test_app_theme_toggle_interaction() -> None:
    """Verifica se alternar para o tema escuro altera o estado global theme_mode."""
    app_path = get_project_root() / "src" / "ui" / "app.py"
    at = AppTest.from_file(str(app_path))
    at.run()
    assert at.session_state.theme_mode == "light"

    # Ativa o toggle de tema escuro na sidebar
    assert len(at.sidebar.toggle) >= 1
    at.sidebar.toggle[0].set_value(True).run()
    assert not at.exception
    assert at.session_state.theme_mode == "dark"


def test_app_geographic_cascade_interaction() -> None:
    """Verifica se a seleção de região na sidebar atualiza o estado e reflete na página ativa."""
    app_path = get_project_root() / "src" / "ui" / "app.py"
    at = AppTest.from_file(str(app_path))
    at.run()

    # Na inicialização ("Todas"), todas as 27 UFs estão disponíveis
    assert len(at.sidebar.selectbox) >= 3
    assert at.sidebar.selectbox[1].options == ["Todas", "Sudeste", "Sul", "Nordeste", "Centro-Oeste", "Norte"]
    assert len(at.sidebar.selectbox[2].options) == 28  # "Todas" + 27 UFs

    # Muda a região para "Sul"
    at.sidebar.selectbox[1].set_value("Sul").run()
    assert not at.exception
    assert at.session_state.regiao == "Sul"
    assert at.session_state.uf == "Todas"

    # Confere se a página re-renderizou com o filtro de Região Sul
    assert len(at.info) >= 1
    assert "Região:** `Sul`" in at.info[0].value


def test_pages_render_without_exception() -> None:
    """Garante que as 4 páginas do app renderizam isoladamente sem erros."""
    pages = [
        "1_executive.py",
        "2_commercial_radar.py",
        "3_inventory_demand.py",
        "4_simulator.py",
    ]
    for page_name in pages:
        page_path = get_project_root() / "src" / "ui" / "pages" / page_name
        at = AppTest.from_file(str(page_path))
        at.run()
        assert not at.exception, f"Erro ao renderizar a página {page_name}"
        assert len(at.title) >= 1
