from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

import streamlit as st

from src.core.types import ScenarioId
from src.ui.period_engine import (
    COMPARISON_MODE_LABELS,
    DEFAULT_MAX_DATE,
    MONTH_LABELS,
    PERIOD_PRESETS,
    ComparisonMode,
    PeriodBounds,
    build_month_options,
    build_quarter_options,
    build_semester_options,
    fetch_date_bounds,
    resolve_period_bounds,
)

__all__ = [
    "COMPARISON_MODE_LABELS",
    "DEFAULT_MAX_DATE",
    "MONTH_LABELS",
    "PERIOD_PRESETS",
    "AppState",
    "ComparisonMode",
    "FilterLayout",
    "PeriodBounds",
    "ThemeMode",
    "build_month_options",
    "build_quarter_options",
    "build_semester_options",
    "fetch_date_bounds",
    "get_app_state",
    "init_app_state",
    "on_comparison_mode_change",
    "on_custom_date_range_change",
    "on_families_change",
    "on_filter_layout_toggle",
    "on_period_preset_change",
    "on_regiao_change",
    "on_sales_reps_change",
    "on_scenario_change",
    "on_selected_month_change",
    "on_selected_quarter_change",
    "on_selected_semester_change",
    "on_theme_toggle",
    "on_uf_change",
    "resolve_period_bounds",
    "set_scenario",
]

ThemeMode = Literal["light", "dark"]
FilterLayout = Literal["sidebar", "top"]


@dataclass(frozen=True)
class AppState:
    """Representação imutável e fortemente tipada do estado global da aplicação Kyberna.

    Centraliza os parâmetros de visualização, o cenário de negócio ativo,
    o motor temporal (`period_preset`, `comparison_mode`) e os filtros em cascata
    para que sejam persistentes durante a navegação multipage.
    """

    theme_mode: ThemeMode = "light"
    filter_layout: FilterLayout = "sidebar"
    scenario_id: ScenarioId = "c1_toys"
    period_preset: str = "all"
    comparison_mode: ComparisonMode = "pop"
    selected_month: str | None = None
    selected_quarter: str = "2024-Q4"
    selected_semester: str = "2024-S2"
    custom_start_date: str | None = None
    custom_end_date: str | None = None
    regiao: str = "Todas"
    uf: str = "Todas"
    families: tuple[str, ...] = ()
    sales_reps: tuple[str, ...] = ()
    selected_abc_xyz_cell: str | None = None
    pending_month: str | None = None
    presentation_mode: bool = False


def init_app_state() -> AppState:
    """Inicializa as chaves essenciais em `st.session_state` caso ainda não existam."""
    defaults: dict[str, object] = {
        "theme_mode": "light",
        "filter_layout": "sidebar",
        "scenario_id": "c1_toys",
        "period_preset": "all",
        "comparison_mode": "pop",
        "selected_month": "2024-12",
        "selected_quarter": "2024-Q4",
        "selected_semester": "2024-S2",
        "custom_start_date": "2024-10-01",
        "custom_end_date": "2024-12-31",
        "regiao": "Todas",
        "uf": "Todas",
        "families": (),
        "sales_reps": (),
        "selected_abc_xyz_cell": None,
        "pending_month": None,
        "presentation_mode": False,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

    return get_app_state()


def get_app_state() -> AppState:
    """Lê `st.session_state` e retorna um snapshot imutável `AppState`."""
    raw_families = st.session_state.get("families", ())
    if isinstance(raw_families, list | set):
        families_tuple = tuple(raw_families)
    elif isinstance(raw_families, tuple):
        families_tuple = raw_families
    else:
        families_tuple = ()

    raw_reps = st.session_state.get("sales_reps", ())
    if isinstance(raw_reps, list | set):
        reps_tuple = tuple(raw_reps)
    elif isinstance(raw_reps, tuple):
        reps_tuple = raw_reps
    else:
        reps_tuple = ()

    raw_comp = st.session_state.get("comparison_mode", "pop")
    comp_mode: ComparisonMode = "yoy" if raw_comp == "yoy" else "pop"
    raw_layout = st.session_state.get("filter_layout", "sidebar")
    f_layout: FilterLayout = "top" if raw_layout == "top" else "sidebar"

    return AppState(
        theme_mode=st.session_state.get("theme_mode", "light"),
        filter_layout=f_layout,
        scenario_id=st.session_state.get("scenario_id", "c1_toys"),
        period_preset=st.session_state.get("period_preset", "all"),
        comparison_mode=comp_mode,
        selected_month=st.session_state.get("selected_month", "2024-12"),
        selected_quarter=st.session_state.get("selected_quarter", "2024-Q4"),
        selected_semester=st.session_state.get("selected_semester", "2024-S2"),
        custom_start_date=st.session_state.get("custom_start_date", "2024-10-01"),
        custom_end_date=st.session_state.get("custom_end_date", "2024-12-31"),
        regiao=st.session_state.get("regiao", "Todas"),
        uf=st.session_state.get("uf", "Todas"),
        families=families_tuple,
        sales_reps=reps_tuple,
        selected_abc_xyz_cell=st.session_state.get("selected_abc_xyz_cell"),
        pending_month=st.session_state.get("pending_month"),
        presentation_mode=bool(st.session_state.get("presentation_mode", False)),
    )


def set_scenario(scenario_id: ScenarioId) -> None:
    """Atualiza o cenário ativo e reseta seleções dependentes do cenário anterior."""
    st.session_state.scenario_id = scenario_id
    st.session_state.families = ()
    st.session_state.sales_reps = ()
    st.session_state.selected_abc_xyz_cell = None
    st.session_state.pending_month = None

    # Limpa o estado interno dos widgets de famílias e representantes
    if "_families_select" in st.session_state:
        st.session_state._families_select = []
    if "_sales_reps_select" in st.session_state:
        st.session_state._sales_reps_select = []


def on_scenario_change() -> None:
    """Callback acionado ao alterar o selectbox de cenário na barra lateral."""
    val = st.session_state.get("_scenario_select")
    if val and val != st.session_state.get("scenario_id"):
        set_scenario(val)


def on_theme_toggle() -> None:
    """Callback acionado ao alternar o toggle de tema na barra lateral."""
    is_dark = bool(st.session_state.get("_theme_toggle", False))
    st.session_state.theme_mode = "dark" if is_dark else "light"


def on_filter_layout_toggle() -> None:
    """Callback acionado ao alternar a posição dos filtros (Sidebar vs. Topo)."""
    is_top = bool(st.session_state.get("_filter_layout_toggle", False))
    st.session_state.filter_layout = "top" if is_top else "sidebar"


def on_period_preset_change() -> None:
    """Callback acionado ao alterar o preset de período na barra lateral."""
    val = st.session_state.get("_period_preset_select", "all")
    st.session_state.period_preset = val


def on_comparison_mode_change() -> None:
    """Callback acionado ao alternar a base comparativa (`PoP` vs. `YoY`)."""
    val = st.session_state.get("_comparison_mode_radio", "pop")
    st.session_state.comparison_mode = "yoy" if val == "yoy" else "pop"


def on_selected_month_change() -> None:
    """Callback acionado ao alterar o mês específico na barra lateral."""
    val = st.session_state.get("_selected_month_select", "2024-12")
    st.session_state.selected_month = val


def on_selected_quarter_change() -> None:
    """Callback acionado ao alterar o trimestre calendário na barra lateral."""
    val = st.session_state.get("_selected_quarter_select", "2024-Q4")
    st.session_state.selected_quarter = val


def on_selected_semester_change() -> None:
    """Callback acionado ao alterar o semestre calendário na barra lateral."""
    val = st.session_state.get("_selected_semester_select", "2024-S2")
    st.session_state.selected_semester = val


def on_custom_date_range_change() -> None:
    """Callback acionado ao alterar o intervalo personalizado via calendário."""
    val = st.session_state.get("_custom_date_range")
    if isinstance(val, tuple | list) and len(val) >= 2:
        start_d, end_d = val[0], val[1]
    elif isinstance(val, tuple | list) and len(val) == 1:
        start_d = end_d = val[0]
    elif isinstance(val, date):
        start_d = end_d = val
    else:
        return

    if not isinstance(start_d, date) or not isinstance(end_d, date):
        return
    if start_d > end_d:
        start_d, end_d = end_d, start_d
    st.session_state.custom_start_date = start_d.isoformat()
    st.session_state.custom_end_date = end_d.isoformat()


def on_regiao_change() -> None:
    """Callback acionado ao alterar a região geográfica: reseta automaticamente a UF para 'Todas'."""
    val = st.session_state.get("_regiao_select", "Todas")
    st.session_state.regiao = val
    st.session_state.uf = "Todas"
    if "_uf_select" in st.session_state:
        st.session_state._uf_select = "Todas"


def on_uf_change() -> None:
    """Callback acionado ao alterar a UF na barra lateral."""
    val = st.session_state.get("_uf_select", "Todas")
    st.session_state.uf = val


def on_families_change() -> None:
    """Callback acionado ao selecionar famílias no multiselect."""
    val = st.session_state.get("_families_select", [])
    st.session_state.families = tuple(val)


def on_sales_reps_change() -> None:
    """Callback acionado ao selecionar representantes no multiselect."""
    val = st.session_state.get("_sales_reps_select", [])
    st.session_state.sales_reps = tuple(val)
