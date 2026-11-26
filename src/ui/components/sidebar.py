from __future__ import annotations

import html
from typing import Final

import streamlit as st

from src.core.logging import get_logger
from src.core.scenarios import load_scenario_config
from src.core.types import ScenarioId
from src.db.repository import DataRepository
from src.ui.cache import get_cached_repository
from src.ui.components.filter_controls import (
    render_family_controls,
    render_geo_controls,
    render_period_controls,
    render_rep_controls,
)
from src.ui.state import (
    AppState,
    get_app_state,
    on_filter_layout_toggle,
    on_scenario_change,
    on_theme_toggle,
)

logger = get_logger(__name__)

SCENARIO_OPTIONS: Final[dict[ScenarioId, str]] = {
    "c1_toys": "C1 — Indústria de Brinquedos",
    "c2_beverages": "C2 — Distribuidora Bebidas",
    "c3_retail_chain": "C3 — Rede de Varejo",
    "c4_single_store": "C4 — Varejo Loja Única",
}


def _render_data_source_badge(repo: DataRepository | None) -> str:
    """Gera o HTML do badge visual indicativo da fonte de dados conectada."""
    if repo is None:
        return (
            '<div style="text-align: center; margin-top: 0.25rem;">'
            '<span class="badge badge-source" title="Repositório não inicializado">'
            "Fonte: Snapshot Local (DuckDB)"
            "</span>"
            "</div>"
        )

    if repo.backend == "azure_sql":
        return (
            '<div style="text-align: center; margin-top: 0.25rem;">'
            '<span class="badge badge-positive" '
            'title="Conexão direta com Azure SQL Database (Serverless Gen5)">'
            "Fonte: Azure SQL"
            "</span>"
            "</div>"
        )

    if repo.fallback_reason:
        escaped_reason = html.escape(repo.fallback_reason)
        return (
            '<div style="text-align: center; margin-top: 0.25rem;">'
            f'<span class="badge badge-warning" title="{escaped_reason}">'
            "Fonte: Snapshot Local (Fallback)"
            "</span>"
            "</div>"
        )

    return (
        '<div style="text-align: center; margin-top: 0.25rem;">'
        '<span class="badge badge-source" title="Operação local sobre snapshot DuckDB e Parquet">'
        "Fonte: Snapshot Local (DuckDB)"
        "</span>"
        "</div>"
    )


def render_sidebar(repo: DataRepository | None = None) -> AppState:
    """Renderiza a barra lateral compacta (sem scroll em 1080p) ou modo com filtros no topo."""
    if repo is None:
        try:
            repo = get_cached_repository()
        except Exception as exc:
            logger.debug("Falha ao obter repositório em cache: %s", exc)
            repo = None

    state = get_app_state()
    scenario = load_scenario_config(state.scenario_id)

    with st.sidebar:
        c_theme, c_layout = st.columns(2)
        with c_theme:
            st.toggle(
                "Modo Escuro",
                value=(state.theme_mode == "dark"),
                key="_theme_toggle",
                on_change=on_theme_toggle,
                help="Alterna entre o visual executivo claro e o cockpit escuro.",
            )
        with c_layout:
            st.toggle(
                "Filtros Topo",
                value=(state.filter_layout == "top"),
                key="_filter_layout_toggle",
                on_change=on_filter_layout_toggle,
                help="Move Período, Região/UF, Família e RCA para uma barra superior estilo PowerBI.",
            )

        if state.filter_layout == "sidebar":
            render_period_controls(repo, state, show_caption=True)
            if scenario.filters.has_geographic_filter:
                render_geo_controls(state, side_by_side=True)
            if scenario.filters.has_family_filter:
                render_family_controls(repo, state, scenario)
            if scenario.filters.has_rep_filter and scenario.capabilities.rep_efficiency:
                render_rep_controls(repo, state, scenario)

        scenario_keys = list(SCENARIO_OPTIONS.keys())
        current_scenario_index = (
            scenario_keys.index(state.scenario_id) if state.scenario_id in scenario_keys else 0
        )
        st.selectbox(
            "Cenário de Negócio",
            options=scenario_keys,
            format_func=lambda s: SCENARIO_OPTIONS[s],
            index=current_scenario_index,
            key="_scenario_select",
            on_change=on_scenario_change,
            help="Altera o vocabulário, lógica de margem e matrizes analíticas da demonstração.",
        )
        st.markdown(_render_data_source_badge(repo), unsafe_allow_html=True)

    return get_app_state()
