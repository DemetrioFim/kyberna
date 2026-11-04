from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import streamlit as st

from src.core.types import ScenarioId

ThemeMode = Literal["light", "dark"]


@dataclass(frozen=True)
class AppState:
    """Representação imutável e fortemente tipada do estado global da aplicação Kyberna.

    Centraliza os parâmetros de visualização, o cenário de negócio ativo,
    os filtros em cascata e as seleções de drill-down para que sejam persistentes
    durante a navegação multipage.
    """

    theme_mode: ThemeMode = "light"
    scenario_id: ScenarioId = "c1_toys"
    regiao: str = "Todas"
    uf: str = "Todas"
    families: tuple[str, ...] = ()
    sales_reps: tuple[str, ...] = ()
    selected_abc_xyz_cell: str | None = None
    pending_month: str | None = None
    presentation_mode: bool = False


def init_app_state() -> AppState:
    """Inicializa as chaves essenciais em `st.session_state` caso ainda não existam."""
    if "theme_mode" not in st.session_state:
        st.session_state.theme_mode = "light"

    if "scenario_id" not in st.session_state:
        st.session_state.scenario_id = "c1_toys"

    if "regiao" not in st.session_state:
        st.session_state.regiao = "Todas"

    if "uf" not in st.session_state:
        st.session_state.uf = "Todas"

    if "families" not in st.session_state:
        st.session_state.families = ()

    if "sales_reps" not in st.session_state:
        st.session_state.sales_reps = ()

    if "selected_abc_xyz_cell" not in st.session_state:
        st.session_state.selected_abc_xyz_cell = None

    if "pending_month" not in st.session_state:
        st.session_state.pending_month = None

    if "presentation_mode" not in st.session_state:
        st.session_state.presentation_mode = False

    return get_app_state()


def get_app_state() -> AppState:
    """Lê `st.session_state` e retorna um snapshot imutável `AppState`."""
    raw_families = st.session_state.get("families", ())
    if isinstance(raw_families, (list, set)):
        families_tuple = tuple(raw_families)
    elif isinstance(raw_families, tuple):
        families_tuple = raw_families
    else:
        families_tuple = ()

    raw_reps = st.session_state.get("sales_reps", ())
    if isinstance(raw_reps, (list, set)):
        reps_tuple = tuple(raw_reps)
    elif isinstance(raw_reps, tuple):
        reps_tuple = raw_reps
    else:
        reps_tuple = ()

    return AppState(
        theme_mode=st.session_state.get("theme_mode", "light"),
        scenario_id=st.session_state.get("scenario_id", "c1_toys"),
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
