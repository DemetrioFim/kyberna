from __future__ import annotations

import html
from datetime import date, timedelta
from typing import Final

import streamlit as st

from src.core.logging import get_logger
from src.core.scenarios import load_scenario_config
from src.core.types import ScenarioId
from src.db.repository import DataRepository
from src.ui.cache import get_cached_date_bounds, get_cached_repository
from src.ui.state import (
    PERIOD_PRESETS,
    AppState,
    build_month_options,
    build_quarter_options,
    build_semester_options,
    fetch_date_bounds,
    get_app_state,
    on_custom_date_range_change,
    on_families_change,
    on_period_preset_change,
    on_regiao_change,
    on_sales_reps_change,
    on_scenario_change,
    on_selected_month_change,
    on_selected_quarter_change,
    on_selected_semester_change,
    on_theme_toggle,
    on_uf_change,
    resolve_period_bounds,
)
from src.ui.theme import REGIOES_BR, get_ufs_for_regiao

logger = get_logger(__name__)

SCENARIO_OPTIONS: Final[dict[ScenarioId, str]] = {
    "c1_toys": "C1 — Indústria de Brinquedos",
    "c2_beverages": "C2 — Distribuidora Bebidas",
    "c3_retail_chain": "C3 — Rede de Varejo",
    "c4_single_store": "C4 — Varejo Loja Única",
}

_PRESET_UI_MAP: Final[dict[str, str]] = {
    "last_12m": "ytd",
    "s2": "fixed_semester",
    "last_6m": "fixed_semester",
    "q4": "fixed_quarter",
    "last_3m": "fixed_quarter",
    "last_month": "custom_month",
}


def _get_available_families(repo: DataRepository | None, scenario_id: ScenarioId) -> list[str]:
    """Retorna lista ordenada das famílias de produtos para o cenário ativo."""
    if repo is not None:
        try:
            df = repo.table("dim_product", scenario_id=scenario_id, columns=["family"])
            if not df.empty and "family" in df.columns:
                return sorted([str(f) for f in df["family"].dropna().unique()])
        except Exception as exc:
            logger.debug("Não foi possível carregar famílias de dim_product: %s", exc)

    fallbacks: dict[str, list[str]] = {
        "c1_toys": [
            "Brinquedos de Madeira",
            "Jogos Educativos",
            "Linha Escolar",
            "Pelúcias",
            "Primeira Infância",
            "Quebra-Cabeças",
        ],
        "c2_beverages": [
            "Cachaças e Destilados",
            "Gin",
            "Licores",
            "Quebra-Cabeças",
            "Rum",
            "Tequila",
            "Vodka",
            "Whisky",
        ],
        "c3_retail_chain": ["Bebidas", "Brinquedos e Jogos", "Conveniência", "Mercearia"],
        "c4_single_store": ["Balcão", "Frios", "Gôndola A", "Gôndola B"],
    }
    return fallbacks.get(scenario_id, [])


def _get_available_sales_reps(repo: DataRepository | None, scenario_id: ScenarioId) -> list[str]:
    """Retorna lista ordenada dos responsáveis comerciais para o cenário ativo."""
    if repo is not None:
        try:
            df = repo.table("dim_sales_rep", scenario_id=scenario_id, columns=["name"])
            if not df.empty and "name" in df.columns:
                return sorted([str(r) for r in df["name"].dropna().unique()])
        except Exception as exc:
            logger.debug("Não foi possível carregar representantes de dim_sales_rep: %s", exc)
    return []


def _render_data_source_badge(repo: DataRepository | None) -> str:
    """Gera o HTML do badge visual indicativo da fonte de dados conectada."""
    if repo is None:
        return (
            '<div style="text-align: center; margin-top: 0.75rem;">'
            '<span class="badge badge-source" title="Repositório não inicializado">'
            "Fonte: Snapshot Local (DuckDB)"
            "</span>"
            "</div>"
        )

    if repo.backend == "azure_sql":
        return (
            '<div style="text-align: center; margin-top: 0.75rem;">'
            '<span class="badge badge-positive" '
            'title="Conexão direta com Azure SQL Database (Serverless Gen5)">'
            "Fonte: Azure SQL"
            "</span>"
            "</div>"
        )

    if repo.fallback_reason:
        escaped_reason = html.escape(repo.fallback_reason)
        return (
            '<div style="text-align: center; margin-top: 0.75rem;">'
            f'<span class="badge badge-warning" title="{escaped_reason}">'
            "Fonte: Snapshot Local (Fallback)"
            "</span>"
            "</div>"
        )

    return (
        '<div style="text-align: center; margin-top: 0.75rem;">'
        '<span class="badge badge-source" title="Operação local sobre snapshot DuckDB e Parquet">'
        "Fonte: Snapshot Local (DuckDB)"
        "</span>"
        "</div>"
    )


def _clamp_date(value: str | None, fallback: date, min_d: date, max_d: date) -> date:
    """Converte ISO string para `date` garantindo limites dentro de `[min_d, max_d]`."""
    parsed = fallback
    if value:
        try:
            parsed = date.fromisoformat(value[:10])
        except ValueError:
            parsed = fallback
    return min(max(parsed, min_d), max_d)


def _render_period_section(repo: DataRepository | None, state: AppState) -> None:
    """Renderiza o motor temporal dinâmico com *progressive disclosure* na sidebar."""
    try:
        min_d, max_d = (
            fetch_date_bounds(repo, state.scenario_id)
            if repo is not None
            else get_cached_date_bounds(state.scenario_id)
        )
    except Exception:
        min_d, max_d = fetch_date_bounds(repo, state.scenario_id)

    st.markdown("##### Período de Análise")
    preset_keys = list(PERIOD_PRESETS.keys())
    mapped_preset = _PRESET_UI_MAP.get(state.period_preset, state.period_preset)
    current_preset_idx = preset_keys.index(mapped_preset) if mapped_preset in preset_keys else 0

    st.selectbox(
        "Janela Temporal",
        options=preset_keys,
        format_func=lambda p: PERIOD_PRESETS[p],
        index=current_preset_idx,
        key="_period_preset_select",
        on_change=on_period_preset_change,
        help=(
            "Descobre automaticamente o intervalo disponível nos dados e calcula comparativos "
            "equivalentes em modo PoP ou YoY."
        ),
    )

    month_options = build_month_options(min_d, max_d)
    quarter_options = build_quarter_options(min_d, max_d)
    semester_options = build_semester_options(min_d, max_d)

    eff_month = state.selected_month
    eff_quarter = state.selected_quarter
    eff_semester = state.selected_semester
    eff_start = state.custom_start_date
    eff_end = state.custom_end_date

    if mapped_preset == "fixed_quarter" and quarter_options:
        q_keys = list(quarter_options.keys())
        eff_quarter = state.selected_quarter if state.selected_quarter in quarter_options else q_keys[0]
        st.selectbox(
            "Trimestre",
            options=q_keys,
            format_func=lambda q: quarter_options[q],
            index=q_keys.index(eff_quarter),
            key="_selected_quarter_select",
            on_change=on_selected_quarter_change,
        )
    elif mapped_preset == "rolling_quarter" and month_options:
        m_keys = list(month_options.keys())
        eff_month = state.selected_month if state.selected_month in month_options else m_keys[0]
        st.selectbox(
            "Mês Final (Trimestre Móvel)",
            options=m_keys,
            format_func=lambda m: month_options[m],
            index=m_keys.index(eff_month),
            key="_selected_month_select",
            on_change=on_selected_month_change,
        )
    elif mapped_preset == "fixed_semester" and semester_options:
        s_keys = list(semester_options.keys())
        eff_semester = state.selected_semester if state.selected_semester in semester_options else s_keys[0]
        st.selectbox(
            "Semestre",
            options=s_keys,
            format_func=lambda s: semester_options[s],
            index=s_keys.index(eff_semester),
            key="_selected_semester_select",
            on_change=on_selected_semester_change,
        )
    elif mapped_preset == "custom_month" and month_options:
        m_keys = list(month_options.keys())
        eff_month = state.selected_month if state.selected_month in month_options else m_keys[0]
        st.selectbox(
            "Mês Específico",
            options=m_keys,
            format_func=lambda m: month_options[m],
            index=m_keys.index(eff_month),
            key="_selected_month_select",
            on_change=on_selected_month_change,
        )
    elif mapped_preset == "custom_range":
        default_start = max(min_d, max_d - timedelta(days=89))
        start_val = _clamp_date(state.custom_start_date, default_start, min_d, max_d)
        end_val = _clamp_date(state.custom_end_date, max_d, min_d, max_d)
        if start_val > end_val:
            start_val, end_val = end_val, start_val
        picked = st.date_input(
            "Intervalo (Início - Fim)",
            value=(start_val, end_val),
            min_value=min_d,
            max_value=max_d,
            format="DD/MM/YYYY",
            key="_custom_date_range",
            on_change=on_custom_date_range_change,
        )
        if isinstance(picked, tuple) and len(picked) >= 2:
            eff_start = picked[0].isoformat()
            eff_end = picked[1].isoformat()

    bounds = resolve_period_bounds(
        state.period_preset,
        eff_month,
        comparison_mode=state.comparison_mode,
        selected_quarter=eff_quarter,
        selected_semester=eff_semester,
        rolling_end_month=eff_month,
        custom_start=eff_start,
        custom_end=eff_end,
        min_date=min_d,
        max_date=max_d,
    )
    st.caption(f"*{bounds.period_label}* · {bounds.comparison_label}")


def render_sidebar(repo: DataRepository | None = None) -> AppState:
    """Renderiza a barra lateral ergonômica da aplicação Kyberna.

    Ordem ergonômica:
        1. Alternador de tema (Modo Escuro).
        2. Período de Análise dinâmico (com progressive disclosure).
        3. Cascata Geográfica (Região -> UF), Famílias e Representantes.
        4. Seletor de Cenário de Negócio (ao final dos filtros) + Badge da Fonte.
    """
    if repo is None:
        try:
            repo = get_cached_repository()
        except Exception as exc:
            logger.debug("Falha ao obter repositório em cache: %s", exc)
            repo = None

    state = get_app_state()
    scenario = load_scenario_config(state.scenario_id)

    with st.sidebar:
        st.toggle(
            "Modo Escuro",
            value=(state.theme_mode == "dark"),
            key="_theme_toggle",
            on_change=on_theme_toggle,
            help="Alterna dinamicamente entre o visual executivo claro e o cockpit escuro de alto contraste.",
        )

        st.markdown("---")
        _render_period_section(repo, state)
        st.markdown("---")

        if scenario.filters.has_geographic_filter:
            st.markdown("##### Filtros Geográficos")
            regioes = ["Todas", *REGIOES_BR]
            current_regiao_index = regioes.index(state.regiao) if state.regiao in regioes else 0
            st.selectbox(
                "Região",
                options=regioes,
                index=current_regiao_index,
                key="_regiao_select",
                on_change=on_regiao_change,
            )

            ufs_disponiveis = ["Todas", *get_ufs_for_regiao(state.regiao)]
            current_uf_index = ufs_disponiveis.index(state.uf) if state.uf in ufs_disponiveis else 0
            st.selectbox(
                "Estado (UF)",
                options=ufs_disponiveis,
                index=current_uf_index,
                key="_uf_select",
                on_change=on_uf_change,
            )

        if scenario.filters.has_family_filter:
            st.markdown("---")
            st.markdown(f"##### {scenario.labels.product_family}")
            available_families = _get_available_families(repo, state.scenario_id)
            default_families = [f for f in state.families if f in available_families]
            st.multiselect(
                f"Filtrar {scenario.labels.product_family}",
                options=available_families,
                default=default_families,
                key="_families_select",
                on_change=on_families_change,
                placeholder="Todas as famílias",
            )

        if scenario.filters.has_rep_filter and scenario.capabilities.rep_efficiency:
            st.markdown("---")
            st.markdown(f"##### {scenario.labels.sales_rep}")
            available_reps = _get_available_sales_reps(repo, state.scenario_id)
            default_reps = [r for r in state.sales_reps if r in available_reps]
            st.multiselect(
                f"Filtrar {scenario.labels.sales_rep}",
                options=available_reps,
                default=default_reps,
                key="_sales_reps_select",
                on_change=on_sales_reps_change,
                placeholder="Todos os representantes",
            )

        st.markdown("---")
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
        st.caption(f"*{scenario.company_profile}*")

        st.markdown("---")
        st.markdown(_render_data_source_badge(repo), unsafe_allow_html=True)

    return get_app_state()
