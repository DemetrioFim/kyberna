from __future__ import annotations

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest


@pytest.fixture
def tmp_data_dir() -> Generator[Path, None, None]:
    """Cria um diretório temporário para dados de teste e limpa após o término."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)
