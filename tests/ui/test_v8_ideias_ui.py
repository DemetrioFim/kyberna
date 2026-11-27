from __future__ import annotations

import pandas as pd
from streamlit.testing.v1 import AppTest

from src.core.paths import get_project_root
from src.ui.components.executive_charts import pvm_bridge_chart


def test_pvm_bridge_chart_light_dark_and_empty() -> None:
    """Garante renderizacao limpa do Bridge PVM em Light/Dark e com DataFrame vazio."""
    empty_fig = pvm_bridge_chart(pd.DataFrame(), theme_mode="light")
    assert empty_fig.layout.height == 245
    assert empty_fig.layout.title.text is None

    sample_df = pd.DataFrame(
        [
            {"step_key": "mc_base", "label": "MC Base (Ant.)", "amount": 100000.0, "measure": "absolute"},
            {"step_key": "volume", "label": "Efeito Volume", "amount": 15000.0, "measure": "relative"},
            {"step_key": "price", "label": "Preço Tabela", "amount": 8000.0, "measure": "relative"},
            {"step_key": "mix", "label": "Mix Produtos", "amount": -3000.0, "measure": "relative"},
            {"step_key": "disc_cost", "label": "Desc. & Custos", "amount": -2000.0, "measure": "relative"},
            {"step_key": "mc_final", "label": "MC Atual", "amount": 118000.0, "measure": "total"},
        ]
    )
    for mode in ("light", "dark"):
        fig = pvm_bridge_chart(sample_df, theme_mode=mode)
        assert len(fig.data) == 1
        assert fig.data[0].type == "waterfall"
        assert fig.layout.height == 245
        assert fig.layout.title.text is None


def test_pvm_bridge_toggle_in_justice_dre() -> None:
    """Toggle dre_pvm_toggle alterna entre Waterfall DRE e Bridge PVM sem excecoes."""
    page_path = get_project_root() / "src" / "ui" / "pages" / "2_commercial_radar.py"

    # 1. Com comparison_mode='yoy' ha janela comparativa ativa
    at_yoy = AppTest.from_file(str(page_path), default_timeout=30)
    at_yoy.session_state["scenario_id"] = "c1_toys"
    at_yoy.session_state["comparison_mode"] = "yoy"
    at_yoy.run()
    assert not at_yoy.exception
    pvm_toggle = next(t for t in at_yoy.toggle if t.key == "dre_pvm_toggle")
    pvm_toggle.set_value(True).run()
    assert not at_yoy.exception
    all_md_yoy = " ".join(m.value for m in at_yoy.markdown)
    assert "Bridge PVM" in all_md_yoy

    # 2. Com all + pop exibe st.info instrutivo sem quebrar
    at_all = AppTest.from_file(str(page_path), default_timeout=30)
    at_all.session_state["scenario_id"] = "c1_toys"
    at_all.session_state["period_preset"] = "all"
    at_all.session_state["comparison_mode"] = "pop"
    at_all.run()
    assert not at_all.exception
    pvm_toggle_all = next(t for t in at_all.toggle if t.key == "dre_pvm_toggle")
    pvm_toggle_all.set_value(True).run()
    assert not at_all.exception
    assert any("Bridge PVM" in str(info.value) for info in at_all.info)


def test_fortaleza_xray_prompt_and_components() -> None:
    """Valida tabela selecionavel na Aba 2 de Fortaleza e renderizacao de Raio-X + Churn Silencioso."""
    page_path = get_project_root() / "src" / "ui" / "pages" / "4_simulator.py"
    at = AppTest.from_file(str(page_path), default_timeout=30)
    at.run()
    assert not at.exception
    all_captions = " ".join(c.value for c in at.caption)
    assert "Raio-X 360°" in all_captions

    def _run_xray_and_silent() -> None:
        import pandas as _pd

        from src.ui.components.customer_xray import render_customer_xray_card
        from src.ui.components.tables import render_silent_churn_expander

        row = _pd.Series(
            {
                "customer_id": "CUST-01",
                "customer_name": "Brinquedos Alpha",
                "state": "SP",
                "sales_rep_name": "Carlos Silva",
                "rfm_segment": "Em Risco",
                "risk_status": "Em Risco Imediato",
                "delay_ratio": 1.85,
                "annual_revenue_at_risk": 92000.0,
                "whatsapp_link": "https://wa.me/5511999999999?text=Oi",
            }
        )
        ws_df = _pd.DataFrame(
            [
                {
                    "customer_id": "CUST-01",
                    "recommended_family": "Jogos Educativos",
                    "potential_revenue_brl": 18500.0,
                    "apriori_lift": 1.45,
                }
            ]
        )
        render_customer_xray_card(row, ws_df, "Lojista")
        sc_df = _pd.DataFrame(
            [
                {
                    "customer_id": "CUST-02",
                    "customer_name": "Mundo Kids",
                    "state": "MG",
                    "sales_rep_name": "Ana Paula",
                    "delay_ratio": 0.95,
                    "rev_prev_90d": 50000.0,
                    "rev_curr_90d": 22000.0,
                    "drop_pct": -56.0,
                    "fams_prev": 5,
                    "fams_curr": 3,
                    "whatsapp": "5531988887777",
                }
            ]
        )
        render_silent_churn_expander(sc_df, "Lojista")

    at_comp = AppTest.from_function(_run_xray_and_silent, default_timeout=15)
    at_comp.run()
    assert not at_comp.exception
    md_text = " ".join(m.value for m in at_comp.markdown)
    assert "Raio-X 360°" in md_text
    assert "Brinquedos Alpha" in md_text
    assert "Jogos Educativos" in md_text


def test_prudence_unlock_cash_combos_expander_renders() -> None:
    """Valida renderizacao do expander de Combos Destrava-Caixa em 1. Prudencia Aba 2."""
    page_path = get_project_root() / "src" / "ui" / "pages" / "1_executive.py"
    at = AppTest.from_file(str(page_path), default_timeout=30)
    at.run()
    assert not at.exception
    exp_labels = " ".join(str(e.label) for e in at.expander)
    assert "Combos Destrava-Caixa" in exp_labels
