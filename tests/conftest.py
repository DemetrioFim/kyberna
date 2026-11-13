from __future__ import annotations

import tempfile
from collections.abc import Generator
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from src.core.paths import get_duckdb_path, get_project_root
from src.core.settings import get_settings

REQUIRED_GOLD_TABLES: tuple[str, ...] = (
    "fact_sales",
    "inventory_snapshot",
    "mart_abc_xyz",
    "mart_rfm",
    "mart_customer_risk",
    "mart_white_space",
    "mart_rep_performance",
)


def _has_required_gold_tables(db_path: Path) -> bool:
    """Verifica em modo somente leitura se todas as tabelas Gold requeridas existem no DuckDB."""
    if not db_path.exists():
        return False

    con: duckdb.DuckDBPyConnection | None = None
    try:
        con = duckdb.connect(str(db_path), read_only=True)
        rows = con.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'gold'
            """
        ).fetchall()
        existing = {str(r[0]) for r in rows}
        return all(tbl in existing for tbl in REQUIRED_GOLD_TABLES)
    except duckdb.Error:
        return False
    finally:
        if con is not None:
            con.close()


def _bootstrap_local_duckdb(db_path: Path) -> None:
    """Executa bootstrap completo da amostra para popular `data/kyberna.duckdb` em checkout limpo."""
    from src.etl.gold.inventory_snapshot import build_inventory_snapshot
    from src.etl.gold.marts import build_gold_marts
    from src.etl.gold.star_schema import build_gold_star_schema
    from src.etl.ingest.fixture import generate_fixture
    from src.etl.ingest.raw_to_bronze import populate_bronze_from_sample_fixture
    from src.etl.scenarios.c1_toys import C1ToysScenarioBuilder
    from src.etl.silver.clean import build_silver_sales
    from src.etl.silver.enrich import enrich_silver_dimensions
    from src.etl.silver.price_events import apply_price_events
    from src.etl.silver.time_anchor import apply_time_anchor

    fixture_path = get_project_root() / "tests" / "fixtures" / "iowa_sample.parquet"
    if not fixture_path.exists():
        generate_fixture(output_path=fixture_path)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    populate_bronze_from_sample_fixture(fixture_path)
    build_silver_sales(sample=True)
    apply_time_anchor(no_shift=True)
    apply_price_events()
    enrich_silver_dimensions()

    con = duckdb.connect(str(db_path))
    try:
        C1ToysScenarioBuilder(duckdb_path=db_path).build(con)
        build_gold_star_schema(con, scenario_id="c1_toys")
        build_inventory_snapshot(con, scenario_id="c1_toys")
        build_gold_marts(con, scenario_id="c1_toys")
    finally:
        con.close()


@pytest.fixture(scope="session", autouse=True)
def ensure_local_duckdb_seeded() -> None:
    """Garante que `data/kyberna.duckdb` e os marts Gold existam antes da execução da suíte."""
    db_path = get_duckdb_path()
    if _has_required_gold_tables(db_path):
        return
    _bootstrap_local_duckdb(db_path)


@pytest.fixture(autouse=True)
def reset_settings_cache() -> Generator[None, None, None]:
    """Limpa o cache de Settings para que monkeypatch de variáveis de ambiente funcione nos testes."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def tmp_data_dir() -> Generator[Path, None, None]:
    """Cria um diretório temporário para dados de teste e limpa após o término."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


@pytest.fixture
def iowa_sample_path() -> Path:
    """Retorna o caminho do arquivo Parquet da fixture sintética de vendas."""
    path = get_project_root() / "tests" / "fixtures" / "iowa_sample.parquet"
    assert path.exists(), f"Fixture não encontrada em {path}. Execute 'kyberna fixture generate'."
    return path


@pytest.fixture
def iowa_sample_df(iowa_sample_path: Path) -> pd.DataFrame:
    """Carrega o DataFrame da fixture sintética oficial para testes."""
    return pd.read_parquet(iowa_sample_path)
