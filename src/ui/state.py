from __future__ import annotations

import calendar
from dataclasses import dataclass
from typing import Final, Literal

import streamlit as st

from src.core.types import ScenarioId

ThemeMode = Literal["light", "dark"]

PERIOD_PRESETS: Final[dict[str, str]] = {
    "all": "Histórico Completo (24 Meses)",
    "ytd": "Últimos 12 Meses / Ano 2024",
    "s2": "Últimos 6 Meses (2º Sem/24)",
    "q4": "Últimos 3 Meses (4º Tri/24)",
    "last_month": "Último Mês Fechado (Dez/24)",
    "custom_month": "Mês Específico...",
}

MONTH_LABELS: Final[dict[str, str]] = {
    "2024-12": "Dezembro / 2024",
    "2024-11": "Novembro / 2024",
    "2024-10": "Outubro / 2024",
    "2024-09": "Setembro / 2024",
    "2024-08": "Agosto / 2024",
    "2024-07": "Julho / 2024",
    "2024-06": "Junho / 2024",
    "2024-05": "Maio / 2024",
    "2024-04": "Abril / 2024",
    "2024-03": "Março / 2024",
    "2024-02": "Fevereiro / 2024",
    "2024-01": "Janeiro / 2024",
    "2023-12": "Dezembro / 2023",
    "2023-11": "Novembro / 2023",
    "2023-10": "Outubro / 2023",
    "2023-09": "Setembro / 2023",
    "2023-08": "Agosto / 2023",
    "2023-07": "Julho / 2023",
    "2023-06": "Junho / 2023",
    "2023-05": "Maio / 2023",
    "2023-04": "Abril / 2023",
    "2023-03": "Março / 2023",
    "2023-02": "Fevereiro / 2023",
    "2023-01": "Janeiro / 2023",
}


@dataclass(frozen=True)
class PeriodBounds:
    """Delimitação de datas inteiras (YYYYMMDD) e rótulos de apresentação."""

    preset: str
    start_date_key: int | None
    end_date_key: int | None
    comparison_start_date_key: int | None
    comparison_end_date_key: int | None
    period_label: str
    comparison_label: str
    as_of_date_label: str = "31/12/2024"


def resolve_period_bounds(preset: str = "all", selected_month: str | None = None) -> PeriodBounds:
    """Calcula os limites temporais do período ativo e de seu comparativo equivalente."""
    if preset == "ytd":
        return PeriodBounds(
            preset="ytd",
            start_date_key=20240101,
            end_date_key=20241231,
            comparison_start_date_key=20230101,
            comparison_end_date_key=20231231,
            period_label="01/01/2024 a 31/12/2024 (Ano Atual / 12m)",
            comparison_label="vs. 01/01/2023 a 31/12/2023 (Ano Anterior - YoY)",
        )
    if preset == "s2":
        return PeriodBounds(
            preset="s2",
            start_date_key=20240701,
            end_date_key=20241231,
            comparison_start_date_key=20240101,
            comparison_end_date_key=20240630,
            period_label="01/07/2024 a 31/12/2024 (2º Semestre / 6m)",
            comparison_label="vs. 01/01/2024 a 30/06/2024 (Semestre Anterior - PoP)",
        )
    if preset == "q4":
        return PeriodBounds(
            preset="q4",
            start_date_key=20241001,
            end_date_key=20241231,
            comparison_start_date_key=20240701,
            comparison_end_date_key=20240930,
            period_label="01/10/2024 a 31/12/2024 (4º Trimestre / 3m)",
            comparison_label="vs. 01/07/2024 a 30/09/2024 (Trimestre Anterior - PoP)",
        )
    if preset == "last_month":
        return PeriodBounds(
            preset="last_month",
            start_date_key=20241201,
            end_date_key=20241231,
            comparison_start_date_key=20241101,
            comparison_end_date_key=20241130,
            period_label="01/12/2024 a 31/12/2024 (Dezembro/2024)",
            comparison_label="vs. 01/11/2024 a 30/11/2024 (Mês Anterior - MoM)",
        )
    if preset == "custom_month" and selected_month:
        try:
            year, month = (int(p) for p in selected_month.split("-"))
            _, last_day = calendar.monthrange(year, month)
            start_k = year * 10000 + month * 100 + 1
            end_k = year * 10000 + month * 100 + last_day

            # Mês anterior
            if month == 1:
                prev_y, prev_m = year - 1, 12
            else:
                prev_y, prev_m = year, month - 1
            _, prev_last_day = calendar.monthrange(prev_y, prev_m)
            prev_start_k = prev_y * 10000 + prev_m * 100 + 1
            prev_end_k = prev_y * 10000 + prev_m * 100 + prev_last_day

            label_name = MONTH_LABELS.get(selected_month, f"{month:02d}/{year}")
            prev_label_name = MONTH_LABELS.get(f"{prev_y}-{prev_m:02d}", f"{prev_m:02d}/{prev_y}")

            return PeriodBounds(
                preset="custom_month",
                start_date_key=start_k,
                end_date_key=end_k,
                comparison_start_date_key=prev_start_k,
                comparison_end_date_key=prev_end_k,
                period_label=f"01/{month:02d}/{year} a {last_day:02d}/{month:02d}/{year} ({label_name})",
                comparison_label=(
                    f"vs. 01/{prev_m:02d}/{prev_y} a {prev_last_day:02d}/{prev_m:02d}/{prev_y} "
                    f"({prev_label_name} - MoM)"
                ),
            )
        except Exception:
            pass

    # Default: all
    return PeriodBounds(
        preset="all",
        start_date_key=None,
        end_date_key=None,
        comparison_start_date_key=None,
        comparison_end_date_key=None,
        period_label="01/01/2023 a 31/12/2024 (24 Meses)",
        comparison_label="Histórico Global Consolidado",
    )


@dataclass(frozen=True)
class AppState:
    """Representação imutável e fortemente tipada do estado global da aplicação Kyberna.

    Centraliza os parâmetros de visualização, o cenário de negócio ativo,
    os filtros em cascata e as seleções de drill-down para que sejam persistentes
    durante a navegação multipage.
    """

    theme_mode: ThemeMode = "light"
    scenario_id: ScenarioId = "c1_toys"
    period_preset: str = "all"
    selected_month: str | None = None
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

    if "period_preset" not in st.session_state:
        st.session_state.period_preset = "all"

    if "selected_month" not in st.session_state:
        st.session_state.selected_month = "2024-12"

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

    return AppState(
        theme_mode=st.session_state.get("theme_mode", "light"),
        scenario_id=st.session_state.get("scenario_id", "c1_toys"),
        period_preset=st.session_state.get("period_preset", "all"),
        selected_month=st.session_state.get("selected_month", "2024-12"),
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


def on_period_preset_change() -> None:
    """Callback acionado ao alterar o preset de período na barra lateral."""
    val = st.session_state.get("_period_preset_select", "all")
    st.session_state.period_preset = val


def on_selected_month_change() -> None:
    """Callback acionado ao alterar o mês específico na barra lateral."""
    val = st.session_state.get("_selected_month_select", "2024-12")
    st.session_state.selected_month = val


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
