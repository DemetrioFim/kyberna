from __future__ import annotations

from datetime import date

import streamlit as st

from src.core.types import ScenarioId
from src.db.repository import DataRepository, get_repository
from src.services.pricing_dto import PricingPageDTO, PricingShapDTO
from src.services.pricing_service import build_pricing_dashboard, get_pricing_shap_waterfall
from src.ui.state import ComparisonMode, PeriodBounds, fetch_date_bounds, resolve_period_bounds


@st.cache_resource(show_spinner=False)
def get_cached_repository() -> DataRepository:
    """Retorna uma instancia singleton em cache do repositorio de dados."""
    return get_repository()


@st.cache_data(ttl=1800, show_spinner=False)
def get_cached_date_bounds(scenario_id: ScenarioId) -> tuple[date, date]:
    """Retorna `(min_date, max_date)` reais disponiveis para o cenario em cache."""
    repo = get_cached_repository()
    return fetch_date_bounds(repo, scenario_id)


def resolve_cached_bounds(
    scenario_id: ScenarioId,
    *,
    period_preset: str,
    comparison_mode: ComparisonMode,
    selected_month: str | None,
    selected_quarter: str | None,
    selected_semester: str | None,
    custom_start_date: str | None,
    custom_end_date: str | None,
) -> PeriodBounds:
    """Resolve limites temporais usando a janela em cache do cenario."""
    min_d, max_d = get_cached_date_bounds(scenario_id)
    return resolve_period_bounds(
        period_preset,
        selected_month,
        comparison_mode=comparison_mode,
        selected_quarter=selected_quarter,
        selected_semester=selected_semester,
        rolling_end_month=selected_month,
        custom_start=custom_start_date,
        custom_end=custom_end_date,
        min_date=min_d,
        max_date=max_d,
    )


@st.cache_data(ttl=300, show_spinner=False)
def cached_pricing_dashboard(
    scenario_id: ScenarioId,
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    families: tuple[str, ...] = (),
    sales_reps: tuple[str, ...] = (),
    period_preset: str = "all",
    comparison_mode: ComparisonMode = "pop",
    selected_month: str | None = None,
    selected_quarter: str | None = None,
    selected_semester: str | None = None,
    custom_start_date: str | None = None,
    custom_end_date: str | None = None,
) -> PricingPageDTO:
    """Consulta e agrega os dados de Precificacao Contextual com cache (TTL 5 min)."""
    repo = get_cached_repository()
    bounds = resolve_cached_bounds(
        scenario_id,
        period_preset=period_preset,
        comparison_mode=comparison_mode,
        selected_month=selected_month,
        selected_quarter=selected_quarter,
        selected_semester=selected_semester,
        custom_start_date=custom_start_date,
        custom_end_date=custom_end_date,
    )
    return build_pricing_dashboard(
        repo,
        scenario_id,
        regiao=regiao,
        uf=uf,
        families=families,
        sales_reps=sales_reps,
        start_date_key=bounds.start_date_key,
        end_date_key=bounds.end_date_key,
        comp_start_date_key=bounds.comparison_start_date_key,
        comp_end_date_key=bounds.comparison_end_date_key,
        comparison_mode=comparison_mode,
        comparison_label=bounds.comparison_label,
    )


@st.cache_data(ttl=300, show_spinner=False)
def cached_pricing_shap(
    scenario_id: ScenarioId,
    *,
    scope_type: str,
    scope_id: str,
    regiao: str = "Todas",
    uf: str = "Todas",
    families: tuple[str, ...] = (),
    sales_reps: tuple[str, ...] = (),
    period_preset: str = "all",
    comparison_mode: str = "pop",
    selected_month: str | None = None,
    selected_quarter: str = "2024-Q4",
    selected_semester: str = "2024-S2",
    custom_start_date: str | None = None,
    custom_end_date: str | None = None,
) -> PricingShapDTO:
    """Carrega os 5 drivers Linear SHAP (% e R$) de um escopo respeitando os filtros globais."""
    repo = get_cached_repository()
    bounds = resolve_cached_bounds(
        scenario_id,
        period_preset=period_preset,
        comparison_mode=comparison_mode,  # type: ignore[arg-type]
        selected_month=selected_month,
        selected_quarter=selected_quarter,
        selected_semester=selected_semester,
        custom_start_date=custom_start_date,
        custom_end_date=custom_end_date,
    )
    return get_pricing_shap_waterfall(
        repo,
        scenario_id,
        scope_type=scope_type,
        scope_id=scope_id,
        regiao=regiao,
        uf=uf,
        families=families,
        sales_reps=sales_reps,
        start_date_key=bounds.start_date_key,
        end_date_key=bounds.end_date_key,
    )
