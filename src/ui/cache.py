from __future__ import annotations

import streamlit as st

from src.db.repository import DataRepository, get_repository


@st.cache_resource(show_spinner=False)
def get_cached_repository() -> DataRepository:
    """Retorna uma instância singleton em cache do repositório de dados.

    Utiliza `@st.cache_resource` para manter a conexão/pool ativa e evitar
    re-testes repetidos de ping contra o Azure SQL durante interações de tela.
    """
    return get_repository()
