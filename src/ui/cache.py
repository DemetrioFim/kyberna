from __future__ import annotations

import pandas as pd
import streamlit as st

from src.core.types import ScenarioId
from src.db.repository import DataRepository, get_repository
from src.services.commercial_service import build_commercial_dashboard
from src.services.dto import (
    CommercialPageDTO,
    ExecutiveKpisDTO,
    ExecutivePageDTO,
    FortitudePageDTO,
    SimulationBaseline,
    TemperancePageDTO,
)
from src.services.executive_service import (
    build_executive_dashboard,
    get_filter_options,
)
from src.services.fortitude_service import build_fortitude_dashboard
from src.services.inventory_dto import (
    InventoryPageDTO,
    SkuForecastSeriesDTO,
)
from src.services.inventory_service import (
    build_inventory_dashboard,
    get_sku_forecast_series,
)
from src.services.simulator import query_family_elasticity
from src.services.temperance_service import build_temperance_dashboard
from src.ui.state import resolve_period_bounds


@st.cache_resource(show_spinner=False)
def get_cached_repository() -> DataRepository:
    """Retorna uma instância singleton em cache do repositório de dados.

    Utiliza `@st.cache_resource` para manter a conexão/pool ativa e evitar
    re-testes repetidos de ping contra o Azure SQL durante interações de tela.
    """
    return get_repository()


@st.cache_data(ttl=300, show_spinner=False)
def cached_filter_options(scenario_id: ScenarioId) -> dict[str, list[str]]:
    """Carrega as opções disponíveis de filtro para o cenário selecionado."""
    repo = get_cached_repository()
    return get_filter_options(repo, scenario_id)


@st.cache_data(ttl=300, show_spinner=False)
def cached_executive_dashboard(
    scenario_id: ScenarioId,
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    families: tuple[str, ...] = (),
    sales_reps: tuple[str, ...] = (),
    selected_cell: str | None = None,
    period_preset: str = "all",
    selected_month: str | None = None,
) -> ExecutivePageDTO:
    """Consulta e agrega os dados da Visão Executiva com cache em memória (TTL 5 min)."""
    repo = get_cached_repository()
    bounds = resolve_period_bounds(period_preset, selected_month)
    return build_executive_dashboard(
        repo,
        scenario_id,
        regiao=regiao,
        uf=uf,
        families=families,
        sales_reps=sales_reps,
        selected_cell=selected_cell,
        start_date_key=bounds.start_date_key,
        end_date_key=bounds.end_date_key,
        comp_start_date_key=bounds.comparison_start_date_key,
        comp_end_date_key=bounds.comparison_end_date_key,
        period_label=bounds.period_label,
        comparison_label=bounds.comparison_label,
        as_of_date_label=bounds.as_of_date_label,
    )


@st.cache_data(ttl=300, show_spinner=False)
def cached_commercial_dashboard(
    scenario_id: ScenarioId,
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    families: tuple[str, ...] = (),
    sales_reps: tuple[str, ...] = (),
    risk_status: str = "Todos",
    rfm_segment: str = "Todos",
    quadrant: str = "Todos",
    period_preset: str = "all",
    selected_month: str | None = None,
) -> CommercialPageDTO:
    """Consulta e agrega os dados do Radar de Justiça Comercial com cache em memória (TTL 5 min)."""
    repo = get_cached_repository()
    bounds = resolve_period_bounds(period_preset, selected_month)
    return build_commercial_dashboard(
        repo,
        scenario_id,
        regiao=regiao,
        uf=uf,
        families=families,
        sales_reps=sales_reps,
        risk_status=risk_status,
        rfm_segment=rfm_segment,
        quadrant=quadrant,
        start_date_key=bounds.start_date_key,
        end_date_key=bounds.end_date_key,
        as_of_date_label=bounds.as_of_date_label,
    )


@st.cache_data(ttl=300, show_spinner=False)
def cached_temperance_dashboard(
    scenario_id: ScenarioId,
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    families: tuple[str, ...] = (),
    sales_reps: tuple[str, ...] = (),
    period_preset: str = "all",
    selected_month: str | None = None,
) -> TemperancePageDTO:
    """Consulta e agrega os dados da Tela 4 (Temperança) com cache em memória (TTL 5 min)."""
    repo = get_cached_repository()
    bounds = resolve_period_bounds(period_preset, selected_month)
    return build_temperance_dashboard(
        repo,
        scenario_id,
        regiao=regiao,
        uf=uf,
        families=families,
        sales_reps=sales_reps,
        start_date_key=bounds.start_date_key,
        end_date_key=bounds.end_date_key,
        as_of_date_label=bounds.as_of_date_label,
    )


@st.cache_data(ttl=300, show_spinner=False)
def cached_fortitude_dashboard(
    scenario_id: ScenarioId,
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    families: tuple[str, ...] = (),
    sales_reps: tuple[str, ...] = (),
) -> FortitudePageDTO:
    """Consulta e agrega os dados da Tela 2 (Fortaleza) com cache em memória (TTL 5 min)."""
    repo = get_cached_repository()
    return build_fortitude_dashboard(
        repo,
        scenario_id,
        regiao=regiao,
        uf=uf,
        families=families,
        sales_reps=sales_reps,
    )


@st.cache_data(ttl=300, show_spinner=False)
def cached_inventory_dashboard(
    scenario_id: ScenarioId,
    *,
    families: tuple[str, ...] = (),
) -> InventoryPageDTO:
    """Consulta e agrega posição prescritiva de estoque e opções de forecast (TTL 5 min)."""
    repo = get_cached_repository()
    return build_inventory_dashboard(
        repo,
        scenario_id,
        families=families,
    )


@st.cache_data(ttl=300, show_spinner=False)
def cached_sku_forecast(
    scenario_id: ScenarioId,
    product_id: str,
) -> SkuForecastSeriesDTO:
    """Carrega a série histórica 90d + previsão 30d de um SKU com cache (TTL 5 min)."""
    repo = get_cached_repository()
    return get_sku_forecast_series(
        repo,
        scenario_id,
        product_id=product_id,
    )


@st.cache_data(ttl=300, show_spinner=False)
def cached_family_elasticity(scenario_id: ScenarioId) -> pd.DataFrame:
    """Carrega elasticidades-preço estimadas por família em `mart_price_elasticity`."""
    repo = get_cached_repository()
    return query_family_elasticity(repo, scenario_id)


def cached_simulation_baseline(
    kpis: ExecutiveKpisDTO,
    *,
    beta_elasticity: float = -1.2,
) -> SimulationBaseline:
    """Constrói o `SimulationBaseline` tipado a partir dos KPIs executivos e elasticidade."""
    return SimulationBaseline.from_executive_kpis(kpis, beta_elasticity=beta_elasticity)
