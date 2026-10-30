from __future__ import annotations

import pytest
from typer.testing import CliRunner

from src.cli import app

runner = CliRunner()

COMMAND_GROUPS = [
    "ingest",
    "fixture",
    "bronze",
    "silver",
    "gold",
    "ml",
    "audit",
    "load",
    "pipeline",
]


def test_cli_version() -> None:
    """Verifica se kyberna --version exibe a versão esperada com código 0."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "Kyberna CLI v0.1.0" in result.output


def test_cli_root_help() -> None:
    """Verifica se kyberna --help lista todos os 9 grupos de comando."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for group in COMMAND_GROUPS:
        assert group in result.output


@pytest.mark.parametrize("group", COMMAND_GROUPS)
def test_cli_group_help(group: str) -> None:
    """Verifica se kyberna <grupo> --help executa com sucesso e exibe comandos do grupo."""
    result = runner.invoke(app, [group, "--help"])
    assert result.exit_code == 0
    assert "Usage:" in result.output


def test_cli_stub_command_raises_not_implemented() -> None:
    """Garante que stubs informam a tarefa responsável ao serem chamados."""
    result = runner.invoke(app, ["silver", "build"])
    assert result.exit_code != 0
    assert "M1-D5" in str(result.exception) or "M1-D5" in result.output
