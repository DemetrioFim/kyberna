from __future__ import annotations

from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal
from typer.testing import CliRunner

from src.cli import app
from src.etl.contracts import BronzeSalesSchema, validate_contract
from src.etl.ingest.fixture import generate_fixture

runner = CliRunner()


def test_fixture_structure_and_schema(iowa_sample_df: pd.DataFrame) -> None:
    """Verifica se a fixture oficial atende ao contrato Bronze e possui cardinalidades mínimas."""
    validated = validate_contract(iowa_sample_df, BronzeSalesSchema, layer="Bronze")
    assert len(validated) == 20000

    # Lojas distintas (~300)
    distinct_stores = validated["store_number"].nunique()
    assert distinct_stores >= 250, f"Lojas insuficientes: {distinct_stores}"

    # Itens distintos (~400)
    distinct_items = validated["item_number"].nunique()
    assert distinct_items >= 300, f"Itens insuficientes: {distinct_items}"

    # Fornecedores distintos (15)
    distinct_vendors = validated["vendor_name"].nunique()
    assert distinct_vendors == 15, f"Fornecedores incorretos: {distinct_vendors}"

    # Datas abrangendo 2023 e 2024
    dates = pd.to_datetime(validated["date"])
    assert dates.min().year == 2023
    assert dates.max().year == 2024


def test_fixture_determinism(tmp_path: Path) -> None:
    """Garante que a mesma semente produz datasets idênticos byte a byte."""
    f1 = tmp_path / "sample_1.parquet"
    f2 = tmp_path / "sample_2.parquet"

    df1 = generate_fixture(num_rows=1000, seed=99, output_path=f1)
    df2 = generate_fixture(num_rows=1000, seed=99, output_path=f2)

    assert_frame_equal(df1, df2)
    assert f1.read_bytes() == f2.read_bytes()


def test_fixture_sleeping_stores(iowa_sample_df: pd.DataFrame) -> None:
    """Garante a existência de lojas adormecidas/inativas no último trimestre de 2024."""
    df = iowa_sample_df.copy()
    df["order_date"] = pd.to_datetime(df["date"])

    max_date_by_store = df.groupby("store_number")["order_date"].max()
    cutoff = pd.Timestamp("2024-09-01")

    # Quantidade de lojas que não compraram nada após setembro de 2024
    sleeping_stores = (max_date_by_store < cutoff).sum()
    assert sleeping_stores >= 20, f"Esperado ao menos 20 lojas adormecidas, encontrado: {sleeping_stores}"


def test_fixture_file_size(iowa_sample_path: Path) -> None:
    """DoD: tamanho da fixture deve ser estritamente menor ou igual a 2 MB."""
    size_bytes = iowa_sample_path.stat().st_size
    max_bytes = 2 * 1024 * 1024
    assert size_bytes <= max_bytes, f"Arquivo excede 2 MB: {size_bytes / 1024:.1f} KB"


def test_cli_fixture_generate_command(tmp_path: Path) -> None:
    """Verifica execução do comando CLI kyberna fixture generate."""
    out_file = tmp_path / "custom_sample.parquet"
    result = runner.invoke(
        app,
        ["fixture", "generate", "--rows", "100", "--seed", "42", "--output", str(out_file)],
    )
    assert result.exit_code == 0
    assert "Fixture gerada com sucesso: 100 linhas" in result.output
    assert out_file.exists()
