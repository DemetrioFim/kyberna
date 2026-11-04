from __future__ import annotations

from collections.abc import Generator

import pytest

from src.core.settings import get_settings


@pytest.fixture(autouse=True)
def force_ui_duckdb_backend(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Garante que todos os testes de UI executem instantaneamente no backend local DuckDB."""
    get_settings.cache_clear()
    monkeypatch.setenv("KYBERNA_DATA_BACKEND", "duckdb")
    yield
    get_settings.cache_clear()
