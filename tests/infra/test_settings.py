from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from src.core.paths import (
    audit_report_path,
    bronze_path,
    config_path,
    get_data_dir,
    get_duckdb_path,
    get_project_root,
    gold_snapshot_path,
    raw_path,
    reference_data_path,
    silver_path,
)
from src.core.settings import Settings, get_settings


def test_default_settings() -> None:
    """Verifica se os valores padrão de Settings respeitam o modelo do projeto."""
    settings = Settings(_env_file=None)  # ignora .env local para testar defaults puros
    assert settings.env == "dev"
    assert settings.data_backend == "auto"
    assert settings.azure_sql_auth == "token"
    assert settings.azure_sql_connect_timeout_s == 8
    assert settings.app_password == "kyberna2026"
    assert isinstance(settings.effective_reference_date, date)
    assert settings.effective_reference_date < date.today()


def test_settings_from_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica se variáveis de ambiente com prefixo KYBERNA_ sobrescrevem configurações."""
    monkeypatch.setenv("KYBERNA_ENV", "prod")
    monkeypatch.setenv("KYBERNA_DATA_BACKEND", "duckdb")
    monkeypatch.setenv("KYBERNA_AZURE_SQL_CONNECT_TIMEOUT_S", "12")
    monkeypatch.setenv("KYBERNA_REFERENCE_DATE", "2026-05-15")
    monkeypatch.setenv("KYBERNA_APP_PASSWORD", "custom_secret_123")

    settings = Settings(_env_file=None)
    assert settings.env == "prod"
    assert settings.data_backend == "duckdb"
    assert settings.azure_sql_connect_timeout_s == 12
    assert settings.reference_date == date(2026, 5, 15)
    assert settings.effective_reference_date == date(2026, 5, 15)
    assert settings.app_password == "custom_secret_123"


def test_settings_validation_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica se valores inválidos em enums ou ranges disparam erro de validação do Pydantic."""
    monkeypatch.setenv("KYBERNA_ENV", "invalid_env")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)

    monkeypatch.delenv("KYBERNA_ENV")
    monkeypatch.setenv("KYBERNA_DATA_BACKEND", "invalid_backend")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)

    monkeypatch.delenv("KYBERNA_DATA_BACKEND")
    monkeypatch.setenv("KYBERNA_AZURE_SQL_CONNECT_TIMEOUT_S", "120")  # acima do le=60
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_get_settings_cached() -> None:
    """Verifica se get_settings() retorna a mesma instância via lru_cache."""
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2


def test_paths_helpers(tmp_path: Path) -> None:
    """Verifica se os geradores de caminhos em paths.py geram as estruturas esperadas."""
    root = get_project_root()
    assert root.exists()
    assert (root / "pyproject.toml").exists()

    data_dir = get_data_dir(tmp_path)
    assert data_dir == tmp_path / "data"

    duckdb_file = get_duckdb_path(tmp_path)
    assert duckdb_file == tmp_path / "data" / "kyberna.duckdb"

    # Raw
    r_simple = raw_path("sales", base=tmp_path)
    assert r_simple == tmp_path / "data" / "raw" / "sales" / "data.csv"

    r_part = raw_path("sales", year=2024, month=5, base=tmp_path)
    assert r_part == tmp_path / "data" / "raw" / "sales" / "year=2024" / "month=05" / "data.csv"

    # Bronze
    b_simple = bronze_path("sales", base=tmp_path)
    assert b_simple == tmp_path / "data" / "bronze" / "sales" / "data.parquet"

    b_part = bronze_path("sales", year=2024, month=5, base=tmp_path)
    assert b_part == tmp_path / "data" / "bronze" / "sales" / "year=2024" / "month=05" / "data.parquet"

    # Silver
    s_path = silver_path("sales", base=tmp_path)
    assert s_path == tmp_path / "data" / "silver" / "sales.parquet"

    # Gold
    g_path = gold_snapshot_path("c1_toys", "fact_sales", base=tmp_path)
    assert g_path == tmp_path / "data" / "gold" / "snapshot" / "c1_toys" / "fact_sales.parquet"

    # Audit & Reference
    a_path = audit_report_path("c1_toys", base=tmp_path)
    assert a_path == tmp_path / "data" / "reports" / "conciliacao_c1_toys.xlsx"

    ref_path = reference_data_path("municipios_br.csv", base=tmp_path)
    assert ref_path == tmp_path / "data" / "reference" / "municipios_br.csv"


def test_pipeline_config_yaml_is_valid() -> None:
    """Garante que config/pipeline.yaml existe e contém todas as seções canônicas."""
    cfg_file = config_path("pipeline.yaml")
    assert cfg_file.exists()

    with cfg_file.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert "seeds" in data
    assert data["seeds"]["faker"] == 42
    assert "ingestion" in data
    assert data["ingestion"]["socrata_dataset_id"] == "m3tr-qhgy"
    assert "thresholds" in data
    assert data["thresholds"]["abc_a_cutoff"] == 0.80
    assert data["thresholds"]["churn_inactivity_days"] == 120
