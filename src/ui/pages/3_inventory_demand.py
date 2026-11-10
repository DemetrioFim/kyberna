from __future__ import annotations

import streamlit as st

from src.core.scenarios import load_scenario_config
from src.ui.cache import cached_temperance_dashboard
from src.ui.components.temperance_inventory_section import (
    render_temperance_inventory_section,
)
from src.ui.components.temperance_sections import (
    render_commercial_erosion_and_policy_section,
    render_temperance_banner,
    render_temperance_headline,
    render_temperance_kpi_cards,
    render_temperance_verdict_section,
)
from src.ui.state import get_app_state


def render_page() -> None:
    """Entrypoint da Página 4 — Temperança (Eficiência Operacional & Capital de Giro)."""
    state = get_app_state()
    scenario_cfg = load_scenario_config(state.scenario_id)

    st.title("Eficiência Operacional & Capital de Giro")
    st.caption(
        f"Auditoria de erosão comercial, disciplina de descontos e destravamento de capital em estoque: "
        f"**{scenario_cfg.display_name}** ({scenario_cfg.company_profile})."
    )

    dto = cached_temperance_dashboard(
        state.scenario_id,
        regiao=state.regiao,
        uf=state.uf,
        families=tuple(state.families),
        sales_reps=tuple(state.sales_reps),
    )

    render_temperance_banner(dto)
    render_temperance_headline(dto)
    render_temperance_kpi_cards(dto)
    render_commercial_erosion_and_policy_section(dto, theme_mode=state.theme_mode)
    render_temperance_inventory_section(dto, theme_mode=state.theme_mode)
    render_temperance_verdict_section(dto)


render_page()
