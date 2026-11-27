from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from src.core.paths import get_project_root
from src.core.settings import get_settings


def test_auth_gate_none_mode_allows_direct_access(monkeypatch: pytest.MonkeyPatch) -> None:
    """Com KYBERNA_AUTH_MODE=none, a aplicação abre direto sem formulário de senha."""
    monkeypatch.setenv("KYBERNA_AUTH_MODE", "none")
    get_settings.cache_clear()
    try:
        app_path = get_project_root() / "src" / "ui" / "app.py"
        at = AppTest.from_file(str(app_path), default_timeout=15)
        at.run()
        assert not at.exception
        assert not any(t.key == "auth_password_input" for t in at.text_input)
    finally:
        get_settings.cache_clear()


def test_auth_gate_demo_password_success_and_lockout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Valida sucesso, erro e bloqueio após 5 tentativas inválidas em demo_password."""
    monkeypatch.setenv("KYBERNA_AUTH_MODE", "demo_password")
    monkeypatch.setenv("KYBERNA_APP_PASSWORD", "segredo-virtus")
    get_settings.cache_clear()
    try:
        app_path = get_project_root() / "src" / "ui" / "app.py"

        # 1. Tentativa correta libera a aplicação
        at_ok = AppTest.from_file(str(app_path), default_timeout=15)
        at_ok.run()
        assert not at_ok.exception
        assert any(t.key == "auth_password_input" for t in at_ok.text_input)

        at_ok.text_input(key="auth_password_input").set_value("segredo-virtus")
        at_ok.button[0].click().run()
        assert not at_ok.exception
        assert bool(at_ok.session_state["auth_authenticated"]) is True
        assert not any(t.key == "auth_password_input" for t in at_ok.text_input)

        # 2. Cinco tentativas inválidas bloqueiam novas submissões na sessão
        at_lock = AppTest.from_file(str(app_path), default_timeout=15)
        at_lock.run()
        for attempt in range(5):
            at_lock.text_input(key="auth_password_input").set_value(f"errada-{attempt}")
            at_lock.button[0].click().run()
            assert not at_lock.exception

        assert int(at_lock.session_state["auth_failed_attempts"]) == 5
        assert not any(t.key == "auth_password_input" for t in at_lock.text_input)
        assert any("bloqueado" in err.value.lower() for err in at_lock.error)
    finally:
        get_settings.cache_clear()


def test_auth_gate_entra_id_blocks_without_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sem cabeçalhos de Easy Auth, KYBERNA_AUTH_MODE=entra_id bloqueia acesso sem exceção."""
    monkeypatch.setenv("KYBERNA_AUTH_MODE", "entra_id")
    get_settings.cache_clear()
    try:
        app_path = get_project_root() / "src" / "ui" / "app.py"
        at = AppTest.from_file(str(app_path), default_timeout=15)
        at.run()
        assert not at.exception
        assert any("entra id" in err.value.lower() for err in at.error)
    finally:
        get_settings.cache_clear()


def test_all_four_pages_smoke_filters_simulator_and_exports() -> None:
    """Smoke integrado nas 4 telas Virtus, filtros, slider What-If e botões de exportação."""
    pages_dir = get_project_root() / "src" / "ui" / "pages"
    page_expectations = [
        ("1_executive.py", "1. Prudência"),
        ("4_simulator.py", "2. Fortaleza"),
        ("2_commercial_radar.py", "3. Justiça"),
        ("3_inventory_demand.py", "4. Temperança"),
    ]
    for filename, badge_text in page_expectations:
        at = AppTest.from_file(str(pages_dir / filename), default_timeout=15)
        at.run()
        assert not at.exception, f"Erro ao renderizar {filename}: {at.exception}"
        all_md = " ".join(m.value for m in at.markdown)
        assert badge_text in all_md

    # Interação com slider no simulador What-If (4. Temperança - Aba 2)
    at_temp = AppTest.from_file(str(pages_dir / "3_inventory_demand.py"), default_timeout=15)
    at_temp.run()
    price_slider = next(s for s in at_temp.slider if s.key == "_what_if_price")
    price_slider.set_value(5.0).run()
    assert not at_temp.exception

    # Presença de botões de exportação Excel e CSV na Tela 2 (Fortaleza Comercial)
    at_comm = AppTest.from_file(str(pages_dir / "4_simulator.py"), default_timeout=15)
    at_comm.run()
    assert not at_comm.exception
    dl_buttons = at_comm.get("download_button")
    button_labels = " ".join(str(getattr(b, "label", "")) for b in dl_buttons)
    assert "xlsx" in button_labels.lower()
    assert "csv" in button_labels.lower()

    # Troca de cenário no final da sidebar do app principal
    app_path = get_project_root() / "src" / "ui" / "app.py"
    at_app = AppTest.from_file(str(app_path), default_timeout=15)
    at_app.run()
    assert not at_app.exception
    if at_app.sidebar.selectbox:
        at_app.sidebar.selectbox(key="_scenario_select").set_value("c1_toys").run()
        assert not at_app.exception


def test_powerbi_single_page_tabs_and_no_nested_subtabs() -> None:
    """Garante 1 barra de abas PowerBI por página e zero sub-abas aninhadas em componentes."""
    ui_root = get_project_root() / "src" / "ui"
    for page_file in sorted((ui_root / "pages").glob("*.py")):
        if page_file.name == "__init__.py":
            continue
        content = page_file.read_text(encoding="utf-8")
        assert content.count("st.tabs(") == 1, f"{page_file.name} deve ter exatamente 1 st.tabs("

    for comp_file in sorted((ui_root / "components").glob("*.py")):
        content = comp_file.read_text(encoding="utf-8")
        assert "st.tabs(" not in content, f"Sub-aba proibida encontrada em {comp_file.name}"


def test_empty_filtered_slice_renders_without_exception_across_all_pages() -> None:
    """Combinações de filtros sem interseção de vendas devem renderizar zeradas sem quebrar."""
    pages_dir = get_project_root() / "src" / "ui" / "pages"
    for filename in (
        "1_executive.py",
        "4_simulator.py",
        "2_commercial_radar.py",
        "3_inventory_demand.py",
    ):
        at = AppTest.from_file(str(pages_dir / filename), default_timeout=30)
        at.session_state["scenario_id"] = "c1_toys"
        at.session_state["regiao"] = "Sudeste"
        at.session_state["sales_reps"] = ("Ana Júlia Martins",)
        at.run()
        assert not at.exception, f"Exceção com recorte vazio em {filename}: {at.exception}"


def test_yoy_comparison_badges_render_across_all_four_pages() -> None:
    """Ativar comparison_mode='yoy' exibe Base comparativa no header e badges nos KPIs das 4 telas."""
    pages_dir = get_project_root() / "src" / "ui" / "pages"
    for filename in (
        "1_executive.py",
        "4_simulator.py",
        "2_commercial_radar.py",
        "3_inventory_demand.py",
    ):
        at = AppTest.from_file(str(pages_dir / filename), default_timeout=30)
        at.session_state["scenario_id"] = "c1_toys"
        at.session_state["comparison_mode"] = "yoy"
        at.run()
        assert not at.exception, f"Exceção com comparison_mode='yoy' em {filename}: {at.exception}"
        all_md = " ".join(m.value for m in at.markdown)
        assert "Base:" in all_md
        assert "badge-positive" in all_md or "badge-negative" in all_md
