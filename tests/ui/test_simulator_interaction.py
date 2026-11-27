from __future__ import annotations

import time

from streamlit.testing.v1 import AppTest

from src.core.paths import get_project_root


def test_simulator_zero_levers_and_controls_present() -> None:
    """DoD M4-V2: Alavancas zeradas mostram delta 0 exato e todos os controles estão ativos."""
    page_path = get_project_root() / "src" / "ui" / "pages" / "3_inventory_demand.py"
    at = AppTest.from_file(str(page_path), default_timeout=15)
    at.run()

    assert not at.exception

    slider_keys = {s.key for s in at.slider}
    assert {"_what_if_price", "_what_if_disc", "_what_if_cost", "sim_comm_pp"}.issubset(slider_keys)

    toggle_keys = {t.key for t in at.toggle}
    assert "sim_use_elasticity" in toggle_keys

    sb_keys = {sb.key for sb in at.selectbox}
    assert "sim_scope_family" in sb_keys

    all_markdown = " ".join(m.value for m in at.markdown)
    assert "Neutro (Baseline)" in all_markdown
    assert "Volume de Equilíbrio (Breakeven):" in all_markdown
    assert "Volume Projetado (β):" in all_markdown
    assert "Receita Bruta Simulada" in all_markdown
    assert "Impacto Direto no Lucro" in all_markdown
    assert "Ajuste Ideal (" in all_markdown
    assert "Elasticidade Real (β =" in all_markdown
    assert any(b.key == "sim_apply_optimal_btn" for b in at.button)

    # Botão de 1 clique aplica o Ajuste Ideal diretamente no slider de preço
    apply_btn = next(b for b in at.button if b.key == "sim_apply_optimal_btn")
    apply_btn.click().run()
    assert not at.exception
    assert any("Simulador" in str(m.value) for m in at.markdown)


def test_simulator_slider_latency_and_scenario_comparison() -> None:
    """DoD M4-V2: Mover slider responde em < 300 ms e comparador salva até 3 cenários."""
    page_path = get_project_root() / "src" / "ui" / "pages" / "3_inventory_demand.py"
    at = AppTest.from_file(str(page_path), default_timeout=15)
    at.run()
    assert not at.exception

    # Aquecimento + medição de interação de slider (< 300 ms)
    price_slider = next(s for s in at.slider if s.key == "_what_if_price")
    t0 = time.perf_counter()
    price_slider.set_value(10.0).run()
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert not at.exception
    assert elapsed_ms < 300.0

    # Salvar 4 vezes seguidas deve manter limite máximo de 3 cenários na sessão
    for idx in range(4):
        p_sl = next(s for s in at.slider if s.key == "_what_if_price")
        p_sl.set_value(float(idx + 1) * 2.0)
        save_btn = next(b for b in at.button if b.key == "sim_save_btn")
        save_btn.click().run()
        assert not at.exception

    assert len(at.session_state.saved_simulations) == 3

    # Limpar comparação zera a lista
    clear_btn = next(b for b in at.button if b.key == "sim_clear_btn")
    clear_btn.click().run()
    assert not at.exception
    assert len(at.session_state.saved_simulations) == 0


def test_simulator_price_band_warning_and_tactical_sku_mode() -> None:
    """Valida alerta de saída da Banda Ideal e alternância para modo Tático por SKU."""
    page_path = get_project_root() / "src" / "ui" / "pages" / "3_inventory_demand.py"
    at = AppTest.from_file(str(page_path), default_timeout=15)
    at.run()
    assert not at.exception

    # Slider para +25% deve disparar alerta de saída da Banda Ideal
    price_slider = next(s for s in at.slider if s.key == "_what_if_price")
    price_slider.set_value(25.0).run()
    assert not at.exception
    all_markdown = " ".join(m.value for m in at.markdown)
    assert "Fora da Banda Ideal" in all_markdown
    assert "Nova Margem Contr. %" in all_markdown

    # Alternar para Tático por SKU
    mode_radio = next(r for r in at.radio if r.key == "sim_scope_mode")
    mode_radio.set_value("Tático por SKU").run()
    assert not at.exception
    sb_keys = {sb.key for sb in at.selectbox}
    assert "sim_scope_sku" in sb_keys
