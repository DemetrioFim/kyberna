from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, Literal

import duckdb
import pandas as pd

from src.core.logging import get_logger
from src.core.paths import get_duckdb_path, gold_snapshot_path
from src.core.types import GoldTable, ScenarioId

logger = get_logger(__name__)

DEFAULT_SCENARIO: Final[ScenarioId] = "c1_toys"


def _resolve_source_table(
    con: duckdb.DuckDBPyConnection,
    db_path: Path,
    name: GoldTable,
    scenario_id: ScenarioId,
) -> tuple[str, bool]:
    """Determina a tabela de origem (schema DuckDB ou Parquet snapshot) e se possui coluna scenario_id."""
    if db_path.exists():
        try:
            tables_df = con.execute(
                f"SELECT table_schema FROM information_schema.tables WHERE table_name = '{name}'"
            ).df()
            schemas = tables_df["table_schema"].tolist()
            if scenario_id in schemas:
                return f"{scenario_id}.{name}", False
            if "gold" in schemas:
                return f"gold.{name}", True
        except Exception as exc:
            logger.debug("Erro ao consultar information_schema no DuckDB: %s", exc)

    parquet_p = gold_snapshot_path(scenario=scenario_id, table=name)
    if not parquet_p.exists():
        msg = f"Tabela Gold '{name}' não encontrada no DuckDB e snapshot '{parquet_p}' inexistente."
        raise FileNotFoundError(msg)

    return f"read_parquet('{parquet_p.as_posix()}')", False


def _build_where_clause(
    has_scenario_col: bool,
    scenario_id: ScenarioId,
    filters: Mapping[str, Any] | None,
) -> tuple[str, list[Any]]:
    """Gera cláusula WHERE parametrizada e lista de parâmetros associados."""
    where_parts: list[str] = []
    params: list[Any] = []

    if has_scenario_col:
        where_parts.append("scenario_id = ?")
        params.append(scenario_id)

    if filters:
        for col_name, val in filters.items():
            if isinstance(val, list | tuple | set):
                val_list = list(val)
                if val_list:
                    placeholders = ", ".join(["?"] * len(val_list))
                    where_parts.append(f'"{col_name}" IN ({placeholders})')
                    params.extend(val_list)
            elif val is not None:
                where_parts.append(f'"{col_name}" = ?')
                params.append(val)

    where_sql = f" WHERE {' AND '.join(where_parts)}" if where_parts else ""
    return where_sql, params


class DuckDBRepository:
    """Repositório de dados in-process baseado em DuckDB e snapshots Parquet.

    Fornece consultas ultrarrápidas (< 100 ms) sobre o catálogo local `data/kyberna.duckdb`
    com fallback transparente para arquivos Parquet da camada Gold (`data/gold/snapshot/`).
    Utiliza conexões curtas e modo `read_only=True` para garantir concorrência segura.
    """

    backend: Literal["duckdb"] = "duckdb"

    def __init__(
        self,
        db_path: Path | str | None = None,
        fallback_reason: str | None = None,
        read_only: bool = False,
    ) -> None:
        self.db_path = Path(db_path) if db_path else get_duckdb_path()
        self.fallback_reason = fallback_reason
        self.read_only = read_only

    def ping(self) -> bool:
        """Verifica se o banco DuckDB ou o diretório de dados está acessível."""
        try:
            con = duckdb.connect(str(self.db_path), read_only=self.read_only)
            con.execute("SELECT 1")
            con.close()
            return True
        except Exception as exc:
            logger.debug("Falha no ping do DuckDBRepository: %s", exc)
            snapshots_dir = self.db_path.parent / "gold" / "snapshot"
            return snapshots_dir.exists()

    def query(
        self,
        sql: str,
        params: Mapping[str, Any] | Sequence[Any] | None = None,
    ) -> pd.DataFrame:
        """Executa uma consulta SQL no DuckDB e retorna o resultado em pd.DataFrame."""
        con = duckdb.connect(str(self.db_path), read_only=self.read_only)
        try:
            if params is not None:
                return con.execute(sql, params).df()
            return con.execute(sql).df()
        finally:
            con.close()

    def table(
        self,
        name: GoldTable,
        scenario_id: ScenarioId = DEFAULT_SCENARIO,
        columns: Sequence[str] | None = None,
        filters: Mapping[str, Any] | None = None,
    ) -> pd.DataFrame:
        """Lê uma tabela Gold por cenário, com projeção opcional de colunas e filtros.

        Busca prioritariamente no schema `{scenario_id}` ou `gold` de `kyberna.duckdb`.
        Se a tabela não estiver registrada no banco local, lê diretamente do snapshot
        Parquet em `data/gold/snapshot/<scenario_id>/<tabela>.parquet`.

        Args:
            name: Nome canônico da tabela Gold (ex: 'fact_sales', 'mart_margin_monthly').
            scenario_id: Identificador do cenário de negócio (default: 'c1_toys').
            columns: Subconjunto opcional de colunas a projetar.
            filters: Dicionário de filtros de igualdade ou pertinência ({'state': 'SP'}).

        Returns:
            pd.DataFrame com os dados filtrados.
        """
        cols_sql = ", ".join(f'"{c}"' for c in columns) if columns else "*"

        con = duckdb.connect(str(self.db_path), read_only=self.read_only)
        try:
            source_table, has_scenario_col = _resolve_source_table(con, self.db_path, name, scenario_id)
            where_sql, query_params = _build_where_clause(has_scenario_col, scenario_id, filters)
            sql = f"SELECT {cols_sql} FROM {source_table}{where_sql}"

            if query_params:
                return con.execute(sql, query_params).df()
            return con.execute(sql).df()
        finally:
            con.close()

    def close(self) -> None:
        """Libera recursos (DuckDB usa conexões curtas in-process por consulta)."""
