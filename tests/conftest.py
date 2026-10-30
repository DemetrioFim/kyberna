from __future__ import annotations

import tempfile
from collections.abc import Generator
from pathlib import Path

import pandas as pd
import pytest

from src.core.paths import get_project_root


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
