from __future__ import annotations

import struct
from collections.abc import Mapping, Sequence
from typing import Any, Final, Literal

import pandas as pd
import pyodbc
from azure.identity import DefaultAzureCredential

from src.core.logging import get_logger
from src.core.types import AzureSqlAuth, GoldTable, ScenarioId

logger = get_logger(__name__)

DEFAULT_SCENARIO: Final[ScenarioId] = "c1_toys"
SQL_COPT_SS_ACCESS_TOKEN: Final[int] = 1256

_CONN_ERROR_CODES: Final[tuple[str, ...]] = (
    "08S01",
    "HYT00",
    "08001",
    "08007",
    "40613",
    "40197",
    "10054",
)


def find_odbc_driver() -> str:
    """Detecta o driver ODBC instalado para SQL Server (preferindo Driver 18)."""
    installed = pyodbc.drivers()
    for preferred in ["ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "SQL Server"]:
        if preferred in installed:
            return preferred
    msg = (
        "Nenhum ODBC Driver para SQL Server encontrado no sistema. "
        f"Drivers instalados: {installed}. Instale 'ODBC Driver 18 for SQL Server'."
    )
    raise ConnectionError(msg)


class AzureSQLRepository:
    """Repositório de dados conectado ao Azure SQL Database (Free Tier Serverless).

    Regras de arquitetura e resiliência:
        - Conexões ultracurtas (abrir -> executar -> fechar): evita manter conexões ociosas
          que impedem o auto-pause de 60 min do Azure SQL Serverless.
        - Timeout curto configurável (padrão: 8s): evita travamento da UI em retornos ou pausas.
        - Autenticação dupla: token Entra ID via `azure.identity.DefaultAzureCredential`
          (produção / Managed Identity e az login) ou SQL auth (dev local via .env).
    """

    backend: Literal["azure_sql"] = "azure_sql"
    fallback_reason: str | None = None

    def __init__(
        self,
        server: str | None = None,
        database: str | None = None,
        *,
        auth: AzureSqlAuth = "token",
        timeout_s: int = 8,
        user: str | None = None,
        password: str | None = None,
        driver: str | None = None,
    ) -> None:
        if not server or not database:
            msg = "Parâmetros 'server' e 'database' são obrigatórios para AzureSQLRepository."
            raise ValueError(msg)

        self.server = server
        self.database = database
        self.auth = auth
        self.timeout_s = timeout_s
        self.user = user
        self.password = password
        self.driver = driver or find_odbc_driver()

    def _get_connection(self) -> pyodbc.Connection:
        """Abre conexão curta com o Azure SQL Database utilizando timeout configurado."""
        server_fqdn = self.server if "," in self.server else f"tcp:{self.server},1433"
        conn_str_parts = [
            f"Driver={{{self.driver}}}",
            f"Server={server_fqdn}",
            f"Database={self.database}",
            "Encrypt=yes",
            "TrustServerCertificate=no",
            f"Connection Timeout={self.timeout_s}",
        ]

        if self.auth == "sql":
            if not self.user or not self.password:
                msg = "Autenticação 'sql' requer 'user' e 'password' configurados."
                raise ValueError(msg)
            conn_str_parts.extend([f"UID={self.user}", f"PWD={self.password}"])
            conn_str = ";".join(conn_str_parts)
            return pyodbc.connect(conn_str, timeout=self.timeout_s)

        # Autenticação por token Entra ID (DefaultAzureCredential)
        credential = DefaultAzureCredential(exclude_interactive_browser_credential=False)
        token = credential.get_token("https://database.windows.net/.default")

        token_bytes = token.token.encode("utf-16-le")
        token_struct = struct.pack(f"=I{len(token_bytes)}s", len(token_bytes), token_bytes)

        conn_str = ";".join(conn_str_parts)
        return pyodbc.connect(
            conn_str,
            attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_struct},
            timeout=self.timeout_s,
        )

    def ping(self) -> bool:
        """Testa conectividade com o Azure SQL executando SELECT 1 com timeout curto."""
        try:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                row = cursor.fetchone()
                return bool(row and row[0] == 1)
            finally:
                conn.close()
        except Exception as exc:
            logger.debug("Falha no ping do AzureSQLRepository: %s", exc)
            return False

    def query(
        self,
        sql: str,
        params: Mapping[str, Any] | Sequence[Any] | None = None,
    ) -> pd.DataFrame:
        """Executa uma consulta SQL parametrizada no Azure SQL e fecha a conexão imediatamente."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            if params is not None:
                if isinstance(params, Mapping):
                    # Transforma mapping nomeado em tupla na ordem das interrogações se aplicável
                    cursor.execute(sql, tuple(params.values()))
                else:
                    cursor.execute(sql, tuple(params))
            else:
                cursor.execute(sql)

            if cursor.description is None:
                return pd.DataFrame()

            cols = [col[0] for col in cursor.description]
            rows = cursor.fetchall()
            return pd.DataFrame.from_records(rows, columns=cols)
        finally:
            conn.close()

    def table(
        self,
        name: GoldTable,
        scenario_id: ScenarioId = DEFAULT_SCENARIO,
        columns: Sequence[str] | None = None,
        filters: Mapping[str, Any] | None = None,
    ) -> pd.DataFrame:
        """Consulta uma tabela da camada Gold no schema `gold` do Azure SQL."""
        cols_sql = ", ".join(f"[{c}]" for c in columns) if columns else "*"
        where_clauses: list[str] = ["scenario_id = ?"]
        params: list[Any] = [scenario_id]

        if filters:
            for k, val in filters.items():
                if isinstance(val, list | tuple | set):
                    val_list = list(val)
                    if val_list:
                        placeholders = ", ".join(["?"] * len(val_list))
                        where_clauses.append(f"[{k}] IN ({placeholders})")
                        params.extend(val_list)
                elif val is not None:
                    where_clauses.append(f"[{k}] = ?")
                    params.append(val)

        where_sql = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        sql = f"SELECT {cols_sql} FROM [gold].[{name}]{where_sql}"
        return self.query(sql, params)

    def close(self) -> None:
        """Libera recursos (conexões com Azure SQL são sempre fechadas por consulta)."""
