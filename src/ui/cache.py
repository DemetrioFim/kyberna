from __future__ import annotations

import streamlit as st

from src.core.types import ScenarioId
from src.db.repository import DataRepository, get_repository
from src.services.dto import ExecutivePageDTO
from src.services.executive_service import (
    build_executive_dashboard,
    get_filter_options,
)


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
) -> ExecutivePageDTO:
    """Consulta e agrega os dados da Visão Executiva com cache em memória (TTL 5 min)."""
    repo = get_cached_repository()
    return build_executive_dashboard(
        repo,
        scenario_id,
        regiao=regiao,
        uf=uf,
        families=families,
        sales_reps=sales_reps,
        selected_cell=selected_cell,
    )
