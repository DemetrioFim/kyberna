from __future__ import annotations

from datetime import date, timedelta
from typing import Final

import streamlit as st

from src.core.logging import get_logger
from src.core.scenarios import ScenarioConfig
from src.core.types import ScenarioId
from src.db.repository import DataRepository
from src.ui.cache import get_cached_date_bounds
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
    on_selected_month_change,
    on_selected_quarter_change,
    on_selected_semester_change,
    on_uf_change,
    resolve_period_bounds,
)
from src.ui.theme import REGIOES_BR, get_ufs_for_regiao

logger = get_logger(__name__)

_PRESET_UI_MAP: Final[dict[str, str]] = {
    "last_12m": "ytd",
    "s2": "fixed_semester",
    "last_6m": "fixed_semester",
    "q4": "fixed_quarter",
    "last_3m": "fixed_quarter",
    "last_month": "custom_month",
}


def get_available_families(repo: DataRepository | None, scenario_id: ScenarioId) -> list[str]:
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


def get_available_sales_reps(repo: DataRepository | None, scenario_id: ScenarioId) -> list[str]:
    """Retorna lista ordenada dos responsáveis comerciais para o cenário ativo."""
    if repo is not None:
        try:
            df = repo.table("dim_sales_rep", scenario_id=scenario_id, columns=["name"])
            if not df.empty and "name" in df.columns:
                return sorted([str(r) for r in df["name"].dropna().unique()])
        except Exception as exc:
            logger.debug("Não foi possível carregar representantes de dim_sales_rep: %s", exc)
    return []


def _clamp_date(value: str | None, fallback: date, min_d: date, max_d: date) -> date:
    """Converte ISO string para `date` garantindo limites dentro de `[min_d, max_d]`."""
    parsed = fallback
    if value:
        try:
            parsed = date.fromisoformat(value[:10])
        except ValueError:
            parsed = fallback
    return min(max(parsed, min_d), max_d)


def render_period_controls(
    repo: DataRepository | None,
    state: AppState,
    *,
    show_caption: bool = True,
) -> None:
    """Renderiza seletor de Período de Análise com progressive disclosure."""
    try:
        min_d, max_d = (
            fetch_date_bounds(repo, state.scenario_id)
            if repo is not None
            else get_cached_date_bounds(state.scenario_id)
        )
    except Exception:
        min_d, max_d = fetch_date_bounds(repo, state.scenario_id)

    preset_keys = list(PERIOD_PRESETS.keys())
    mapped_preset = _PRESET_UI_MAP.get(state.period_preset, state.period_preset)
    current_preset_idx = preset_keys.index(mapped_preset) if mapped_preset in preset_keys else 0

    st.selectbox(
        "Período de Análise",
        options=preset_keys,
        format_func=lambda p: PERIOD_PRESETS[p],
        index=current_preset_idx,
        key="_period_preset_select",
        on_change=on_period_preset_change,
        help="Descobre automaticamente o intervalo disponível e calcula comparativos PoP/YoY.",
    )

    month_options = build_month_options(min_d, max_d)
    quarter_options = build_quarter_options(min_d, max_d)
    semester_options = build_semester_options(min_d, max_d)
    eff_month = state.selected_month
    eff_quarter = state.selected_quarter
    eff_semester = state.selected_semester
    eff_start, eff_end = state.custom_start_date, state.custom_end_date

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
            "Mês Final (Trim. Móvel)",
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
            eff_start, eff_end = picked[0].isoformat(), picked[1].isoformat()

    if show_caption:
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
        st.caption(f"{bounds.period_label} · {bounds.comparison_label}")


def render_geo_controls(state: AppState, *, side_by_side: bool = True) -> None:
    """Renderiza cascata Região -> Estado (UF) de forma compacta."""
    regioes = ["Todas", *REGIOES_BR]
    ufs_disponiveis = ["Todas", *get_ufs_for_regiao(state.regiao)]
    idx_reg = regioes.index(state.regiao) if state.regiao in regioes else 0
    idx_uf = ufs_disponiveis.index(state.uf) if state.uf in ufs_disponiveis else 0

    if side_by_side:
        c_reg, c_uf = st.columns([1.25, 0.85])
        with c_reg:
            st.selectbox(
                "Região",
                options=regioes,
                index=idx_reg,
                key="_regiao_select",
                on_change=on_regiao_change,
            )
        with c_uf:
            st.selectbox(
                "UF",
                options=ufs_disponiveis,
                index=idx_uf,
                key="_uf_select",
                on_change=on_uf_change,
            )
    else:
        st.selectbox(
            "Região",
            options=regioes,
            index=idx_reg,
            key="_regiao_select",
            on_change=on_regiao_change,
        )
        st.selectbox(
            "Estado (UF)",
            options=ufs_disponiveis,
            index=idx_uf,
            key="_uf_select",
            on_change=on_uf_change,
        )


def render_family_controls(repo: DataRepository | None, state: AppState, scenario: ScenarioConfig) -> None:
    """Renderiza multiselect de Famílias de Produtos."""
    available_families = get_available_families(repo, state.scenario_id)
    default_families = [f for f in state.families if f in available_families]
    st.multiselect(
        scenario.labels.product_family,
        options=available_families,
        default=default_families,
        key="_families_select",
        on_change=on_families_change,
        placeholder="Todas as famílias",
    )


def render_rep_controls(repo: DataRepository | None, state: AppState, scenario: ScenarioConfig) -> None:
    """Renderiza multiselect de RCAs / Representantes."""
    available_reps = get_available_sales_reps(repo, state.scenario_id)
    default_reps = [r for r in state.sales_reps if r in available_reps]
    st.multiselect(
        scenario.labels.sales_rep,
        options=available_reps,
        default=default_reps,
        key="_sales_reps_select",
        on_change=on_sales_reps_change,
        placeholder="Todos os RCAs",
    )


def render_top_filter_bar(repo: DataRepository | None, scenario: ScenarioConfig) -> None:
    """Renderiza barra horizontal superior estilo PowerBI com os filtros globais."""
    state = get_app_state()
    has_geo = scenario.filters.has_geographic_filter
    has_fam = scenario.filters.has_family_filter
    has_rep = scenario.filters.has_rep_filter and scenario.capabilities.rep_efficiency

    st.markdown('<div class="top-filter-bar-anchor"></div>', unsafe_allow_html=True)
    cols = st.columns([1.25, 1.35 if has_geo else 0.01, 1.15 if has_fam else 0.01, 1.15 if has_rep else 0.01])
    with cols[0]:
        render_period_controls(repo, state, show_caption=False)
    if has_geo:
        with cols[1]:
            render_geo_controls(state, side_by_side=True)
    if has_fam:
        with cols[2]:
            render_family_controls(repo, state, scenario)
    if has_rep:
        with cols[3]:
            render_rep_controls(repo, state, scenario)
