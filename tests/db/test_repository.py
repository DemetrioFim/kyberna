from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import duckdb
import pandas as pd
import pytest

from src.core.paths import get_project_root
from src.core.settings import Settings
from src.db.azure_sql_repo import AzureSQLRepository
from src.db.duckdb_repo import DuckDBRepository
from src.db.repository import get_repository
from src.etl.gold.marts import build_gold_marts
from src.etl.gold.star_schema import build_gold_star_schema
from src.etl.scenarios.c1_toys import C1ToysScenarioBuilder


@pytest.fixture
def populated_c1_db(tmp_path: Path) -> tuple[duckdb.DuckDBPyConnection, Path]:
    """Cria banco DuckDB temporário populado com Star Schema e Marts do C1."""
    db_path = tmp_path / "test_repo.duckdb"
    con = duckdb.connect(str(db_path))

    sample_path = get_project_root() / "tests" / "fixtures" / "iowa_sample.parquet"
    if not sample_path.exists():
        from src.etl.ingest.fixture import generate_fixture

        generate_fixture(output_path=sample_path)

    builder = C1ToysScenarioBuilder(duckdb_path=db_path, global_seed=42)
    builder.build(con)

    build_gold_star_schema(con, scenario_id="c1_toys")
    build_gold_marts(con, scenario_id="c1_toys")
    con.close()

    return con, db_path


def test_duckdb_repository_ping_and_query(
    populated_c1_db: tuple[duckdb.DuckDBPyConnection, Path],
) -> None:
    """Valida ping de conectividade e consultas SQL parametrizadas no DuckDBRepository."""
    _, db_path = populated_c1_db
    repo = DuckDBRepository(db_path=db_path)

    # 1. Ping
    assert repo.ping() is True
    assert repo.backend == "duckdb"
    assert repo.fallback_reason is None

    # 2. Query simples
    df = repo.query("SELECT 42 AS answer, 'Kyberna' AS name")
    assert len(df) == 1
    assert df["answer"].iloc[0] == 42
    assert df["name"].iloc[0] == "Kyberna"

    # 3. Query parametrizada
    df_params = repo.query(
        "SELECT ?::INTEGER AS num, ?::VARCHAR AS str",
        [99, "ParamTest"],
    )
    assert len(df_params) == 1
    assert df_params["num"].iloc[0] == 99


def test_duckdb_repository_table_projection_and_filters(
    populated_c1_db: tuple[duckdb.DuckDBPyConnection, Path],
) -> None:
    """Valida leitura da API repo.table() com projeção de colunas e múltiplos filtros."""
    _, db_path = populated_c1_db
    repo = DuckDBRepository(db_path=db_path)

    # Leitura completa
    full_df = repo.table("dim_customer", scenario_id="c1_toys")
    assert len(full_df) == 300

    # Leitura com projeção de colunas
    cols = ["customer_id", "trade_name", "state", "size"]
    proj_df = repo.table("dim_customer", scenario_id="c1_toys", columns=cols)
    assert list(proj_df.columns) == cols
    assert len(proj_df) == 300

    # Leitura com filtro de valor único
    sp_df = repo.table("dim_customer", scenario_id="c1_toys", filters={"state": "SP"})
    assert len(sp_df) > 0
    assert (sp_df["state"] == "SP").all()

    # Leitura com filtro de lista (IN)
    multi_df = repo.table(
        "dim_customer",
        scenario_id="c1_toys",
        filters={"state": ["SP", "RJ", "MG"]},
    )
    assert len(multi_df) > 0
    assert set(multi_df["state"].unique()).issubset({"SP", "RJ", "MG"})


def test_duckdb_repository_table_fallback_to_parquet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Garante que repo.table() lê diretamente do Parquet snapshot se a tabela não estiver no .duckdb."""
    # Cria Parquet de teste
    fake_data = pd.DataFrame(
        {
            "scenario_id": ["c1_toys", "c1_toys"],
            "item_code": ["SKU-01", "SKU-02"],
            "value": [10.5, 20.0],
        }
    )
    snapshot_dir = tmp_path / "data" / "gold" / "snapshot" / "c1_toys"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    parquet_file = snapshot_dir / "fact_sales.parquet"
    fake_data.to_parquet(parquet_file)

    monkeypatch.setattr(
        "src.db.duckdb_repo.gold_snapshot_path",
        lambda scenario, table: parquet_file,
    )

    empty_db = tmp_path / "empty.duckdb"
    repo = DuckDBRepository(db_path=empty_db)

    # A tabela não existe no empty.duckdb, mas o snapshot parquet existe
    df = repo.table("fact_sales", scenario_id="c1_toys")
    assert len(df) == 2
    assert "item_code" in df.columns


def test_mart_query_latency_under_100ms(
    populated_c1_db: tuple[duckdb.DuckDBPyConnection, Path],
) -> None:
    """DoD: Garante que uma consulta típica de mart analítico responda em <= 100 ms localmente."""
    _, db_path = populated_c1_db
    repo = DuckDBRepository(db_path=db_path)

    # Aquece cache de metadados
    repo.table("mart_margin_monthly", scenario_id="c1_toys")

    # Mede tempo de execução
    t0 = time.perf_counter()
    df = repo.table(
        "mart_margin_monthly",
        scenario_id="c1_toys",
        filters={"family": "Quebra-Cabeças"},
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert len(df) > 0
    assert (
        elapsed_ms < 100.0
    ), f"Consulta ao mart levou {elapsed_ms:.2f} ms, acima do limite de 100 ms do DoD."


def test_get_repository_explicit_duckdb(tmp_path: Path) -> None:
    """Verifica que backend='duckdb' instancia DuckDBRepository."""
    cfg = Settings(data_backend="duckdb", duckdb_path=tmp_path / "test.duckdb")
    repo = get_repository(settings=cfg)

    assert isinstance(repo, DuckDBRepository)
    assert repo.backend == "duckdb"
    assert repo.fallback_reason is None


def test_get_repository_explicit_azure_sql_validation() -> None:
    """Verifica que backend='azure_sql' valida parâmetros obrigatórios."""
    cfg = Settings(data_backend="azure_sql", azure_sql_server=None, azure_sql_database=None)
    with pytest.raises(ValueError, match="Parâmetros 'server' e 'database' são obrigatórios"):
        get_repository(settings=cfg)


def test_get_repository_auto_fallback_missing_credentials(tmp_path: Path) -> None:
    """DoD: Modo auto sem credenciais Azure SQL ativa fallback imediato para DuckDB."""
    cfg = Settings(
        data_backend="auto",
        azure_sql_server=None,
        azure_sql_database=None,
        duckdb_path=tmp_path / "test.duckdb",
    )
    repo = get_repository(settings=cfg)

    assert isinstance(repo, DuckDBRepository)
    assert repo.backend == "duckdb"
    assert repo.fallback_reason is not None
    assert "Azure SQL não configurado" in repo.fallback_reason


def test_get_repository_auto_fallback_paused_database_40613(tmp_path: Path) -> None:
    """DoD: Simula falha 40613 (banco pausado) e comprova fallback com motivo amigável."""
    cfg = Settings(
        data_backend="auto",
        azure_sql_server="demo-server.database.windows.net",
        azure_sql_database="kyberna_db",
        duckdb_path=tmp_path / "test.duckdb",
    )

    mock_error = Exception(
        "('42000', '[42000] [Microsoft][ODBC Driver 18 for SQL Server][SQL Server]40613: "
        "Database is currently not available because it is paused.')"
    )

    with patch.object(AzureSQLRepository, "ping", side_effect=mock_error):
        repo = get_repository(settings=cfg)

    assert isinstance(repo, DuckDBRepository)
    assert repo.backend == "duckdb"
    assert repo.fallback_reason is not None
    assert "40613" in repo.fallback_reason
    assert "pausado" in repo.fallback_reason.lower()


def test_get_repository_auto_fallback_timeout(tmp_path: Path) -> None:
    """DoD: Simula timeout na conexão com Azure SQL e comprova ativação do fallback."""
    cfg = Settings(
        data_backend="auto",
        azure_sql_server="slow-server.database.windows.net",
        azure_sql_database="kyberna_db",
        duckdb_path=tmp_path / "test.duckdb",
    )

    mock_error = Exception(
        "('HYT00', '[HYT00] [Microsoft][ODBC Driver 18 for SQL Server]Login timeout expired')"
    )

    with patch.object(AzureSQLRepository, "ping", side_effect=mock_error):
        repo = get_repository(settings=cfg)

    assert isinstance(repo, DuckDBRepository)
    assert repo.backend == "duckdb"
    assert repo.fallback_reason is not None
    assert "HYT00" in repo.fallback_reason or "timeout" in repo.fallback_reason.lower()


def test_get_repository_auto_success_when_azure_sql_available(tmp_path: Path) -> None:
    """Comprova que quando Azure SQL responde com sucesso ao ping, AzureSQLRepository é retornado."""
    cfg = Settings(
        data_backend="auto",
        azure_sql_server="active-server.database.windows.net",
        azure_sql_database="kyberna_db",
        duckdb_path=tmp_path / "test.duckdb",
    )

    with patch.object(AzureSQLRepository, "ping", return_value=True):
        repo = get_repository(settings=cfg)

    assert isinstance(repo, AzureSQLRepository)
    assert repo.backend == "azure_sql"
    assert repo.fallback_reason is None
