from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final, Literal, Protocol

import pandas as pd

from src.core.logging import get_logger
from src.core.settings import Settings, get_settings
from src.core.types import DataBackend, GoldTable, ScenarioId
from src.db.azure_sql_repo import _CONN_ERROR_CODES, AzureSQLRepository
from src.db.duckdb_repo import DuckDBRepository

logger = get_logger(__name__)

DEFAULT_SCENARIO: Final[ScenarioId] = "c1_toys"


class DataRepository(Protocol):
    """Protocolo de abstração do repositório de dados da Kyberna.

    Permite que os serviços puros da UI (`src/services/`) consultem dados
    de forma agnóstica em relação ao banco físico subjacente (Azure SQL ou DuckDB local).
    """

    @property
    def backend(self) -> Literal["azure_sql", "duckdb"]: ...

    @property
    def fallback_reason(self) -> str | None: ...

    def ping(self) -> bool:
        """Verifica se o backend de dados está operacional."""
        ...

    def query(
        self,
        sql: str,
        params: Mapping[str, Any] | Sequence[Any] | None = None,
    ) -> pd.DataFrame:
        """Executa uma consulta SQL parametrizada e retorna um pd.DataFrame."""
        ...

    def table(
        self,
        name: GoldTable,
        scenario_id: ScenarioId = DEFAULT_SCENARIO,
        columns: Sequence[str] | None = None,
        filters: Mapping[str, Any] | None = None,
    ) -> pd.DataFrame:
        """Lê uma tabela Gold por cenário, com projeção opcional de colunas e filtros."""
        ...

    def close(self) -> None:
        """Libera conexões e recursos associados."""
        ...


def _parse_azure_sql_error(exc: Exception) -> str:
    """Extrai uma mensagem amigável em português a partir de exceções de conexão do Azure SQL."""
    exc_str = str(exc)

    for code in _CONN_ERROR_CODES:
        if code in exc_str:
            if code == "40613":
                return "Banco de dados Azure SQL pausado ou retomando (erro 40613)"
            if code in ("HYT00", "08S01", "08001", "08007"):
                return f"Timeout ou falha de rede na conexão com Azure SQL (código {code})"
            if code in ("40197", "10054"):
                return f"Conexão interrompida pelo servidor Azure SQL (código {code})"

    if "timeout" in exc_str.lower():
        return "Timeout na conexão com o Azure SQL (> 8s)"
    if "driver" in exc_str.lower() or "odbc" in exc_str.lower():
        return "Driver ODBC para SQL Server não encontrado ou inválido"

    return f"Falha na conexão com Azure SQL: {exc_str[:120]}"


def get_repository(
    settings: Settings | None = None,
    force_backend: DataBackend | None = None,
) -> DataRepository:
    """Factory do repositório de dados com política de auto-fallback e resiliência.

    Políticas de seleção (`KYBERNA_DATA_BACKEND`):
        - `duckdb`: Conexão direta e in-process com o DuckDB local (`data/kyberna.duckdb`)
          ou leitura direta dos snapshots Parquet da camada Gold (`data/gold/snapshot/`).
        - `azure_sql`: Força conexão com o Azure SQL Database. Em caso de falha, lança exceção.
        - `auto` (padrão): Tenta conectar ao Azure SQL com timeout curto (<= 8s). Se o banco
          estiver pausado (erro 40613), offline, atingir timeout ou se as credenciais não estiverem
          configuradas, realiza o **fallback instantâneo para o DuckDB local**, registrando
          o motivo em `fallback_reason` para exibição de badge amigável na UI.

    Args:
        settings: Instância tipada de Settings (se None, obtém via singleton `get_settings()`).
        force_backend: Sobrescreve pontualmente a política de backend configurada.

    Returns:
        Instância que implementa `DataRepository` (`DuckDBRepository` ou `AzureSQLRepository`).
    """
    cfg = settings or get_settings()
    backend_mode: DataBackend = force_backend or cfg.data_backend

    # 1. Modo explícito DuckDB
    if backend_mode == "duckdb":
        return DuckDBRepository(db_path=cfg.duckdb_path)

    # 2. Modo explícito Azure SQL
    if backend_mode == "azure_sql":
        repo = AzureSQLRepository(
            server=cfg.azure_sql_server,
            database=cfg.azure_sql_database,
            auth=cfg.azure_sql_auth,
            timeout_s=cfg.azure_sql_connect_timeout_s,
            user=cfg.azure_sql_user,
            password=cfg.azure_sql_password,
        )
        return repo

    # 3. Modo Auto (Tentativa Azure SQL -> Fallback DuckDB)
    if not cfg.azure_sql_server or not cfg.azure_sql_database:
        fallback_msg = "Azure SQL não configurado (KYBERNA_AZURE_SQL_SERVER ausente)"
        logger.info("%s. Ativando repositório DuckDB local com snapshot Gold.", fallback_msg)
        return DuckDBRepository(db_path=cfg.duckdb_path, fallback_reason=fallback_msg)

    try:
        azure_repo = AzureSQLRepository(
            server=cfg.azure_sql_server,
            database=cfg.azure_sql_database,
            auth=cfg.azure_sql_auth,
            timeout_s=cfg.azure_sql_connect_timeout_s,
            user=cfg.azure_sql_user,
            password=cfg.azure_sql_password,
        )

        if azure_repo.ping():
            logger.info(
                "Conexão com Azure SQL estabelecida com sucesso: %s/%s.",
                cfg.azure_sql_server,
                cfg.azure_sql_database,
            )
            return azure_repo

        fallback_msg = "Azure SQL inacessível (ping sem resposta dentro do timeout de 8s)"
        logger.warning("%s. Ativando fallback para DuckDB local.", fallback_msg)
        return DuckDBRepository(db_path=cfg.duckdb_path, fallback_reason=fallback_msg)

    except Exception as exc:
        fallback_msg = _parse_azure_sql_error(exc)
        logger.warning(
            "Falha ao conectar no Azure SQL (%s). Ativando fallback instantâneo para DuckDB.",
            fallback_msg,
        )
        return DuckDBRepository(db_path=cfg.duckdb_path, fallback_reason=fallback_msg)
