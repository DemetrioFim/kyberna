from __future__ import annotations

from pathlib import Path

from src.core.types import GoldTable, ScenarioId

# Diretório raiz do projeto (onde está pyproject.toml)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def get_project_root() -> Path:
    """Retorna o diretório raiz absoluto do projeto Kyberna."""
    return PROJECT_ROOT


def get_data_dir(base: Path | None = None) -> Path:
    """Retorna o diretório base de dados local (`data/`)."""
    return (base or PROJECT_ROOT) / "data"


def get_duckdb_path(base: Path | None = None) -> Path:
    """Retorna o caminho do banco unificado `kyberna.duckdb`."""
    return get_data_dir(base) / "kyberna.duckdb"


def bronze_path(
    table: str, year: int | None = None, month: int | None = None, base: Path | None = None
) -> Path:
    """Retorna o caminho do Parquet da camada Bronze, opcionalmente particionado."""
    folder = get_data_dir(base) / "bronze" / table
    if year is not None and month is not None:
        return folder / f"year={year}" / f"month={month:02d}" / "data.parquet"
    if year is not None:
        return folder / f"year={year}" / "data.parquet"
    return folder / "data.parquet"


def silver_path(table: str, base: Path | None = None) -> Path:
    """Retorna o caminho do Parquet da camada Silver (modelo canônico limpo)."""
    return get_data_dir(base) / "silver" / f"{table}.parquet"


def gold_snapshot_path(scenario: ScenarioId, table: GoldTable, base: Path | None = None) -> Path:
    """Retorna o caminho do Parquet da camada Gold para o cenário e tabela informados."""
    return get_data_dir(base) / "gold" / "snapshot" / scenario / f"{table}.parquet"


def audit_report_path(scenario: ScenarioId, base: Path | None = None) -> Path:
    """Retorna o caminho do relatório Excel de conciliação financeira do cenário."""
    return get_data_dir(base) / "reports" / f"conciliacao_{scenario}.xlsx"


def reference_data_path(filename: str, base: Path | None = None) -> Path:
    """Retorna o caminho de um arquivo estático de referência versionado (`data/reference/`)."""
    return get_data_dir(base) / "reference" / filename


def config_path(relative_path: str, base: Path | None = None) -> Path:
    """Retorna o caminho de um arquivo de configuração (`config/`)."""
    return (base or PROJECT_ROOT) / "config" / relative_path
