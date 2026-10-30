from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from src.cli import app
from src.etl.contracts import SilverSalesSchema, validate_contract
from src.etl.lake import get_duckdb_connection, read_parquet
from src.etl.silver.clean import build_silver_sales

runner = CliRunner()


def test_build_silver_from_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Garante que a construção Silver a partir da fixture passa no contrato e limpa corretamente."""
    monkeypatch.setenv("KYBERNA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("KYBERNA_DUCKDB_PATH", str(tmp_path / "data" / "kyberna.duckdb"))

    parquet_p, report = build_silver_sales(base_dir=tmp_path, sample=True)

    assert parquet_p.exists()
    assert report["total_bronze"] == 20000
    assert report["final_silver"] >= 19500  # ~98% de retenção (descarta apenas duplicatas e outliers)
    assert report["total_removed"] == report["total_bronze"] - report["final_silver"]

    # Carrega e valida contrato Pandera
    df_silver = read_parquet(parquet_p)
    validated = validate_contract(df_silver, SilverSalesSchema, layer="silver")
    assert len(validated) == report["final_silver"]
    assert "chain_name" in df_silver.columns


def test_silver_text_normalization_and_chain_derivation(tmp_path: Path) -> None:
    """Verifica limpeza de espaços duplicados, Title Case e derivação da rede varejista."""
    db_path = tmp_path / "test.duckdb"
    con = get_duckdb_connection(db_path=db_path)

    try:
        # Cria tabela bronze simulada com nomes sujos e várias redes
        con.execute("""
            CREATE OR REPLACE TABLE bronze.sales_raw AS
            SELECT
                'INV-001' AS invoice_and_item_number,
                '2024-01-15' AS date,
                '101' AS store_number,
                '  HY-VEE   FOOD   STORE  #1  ' AS store_name,
                '  DES   MOINES  ' AS city,
                'POLK' AS county,
                '50309' AS zip_code,
                'Vodka' AS category_name,
                '260' AS vendor_number,
                'DIAGEO AMERICAS' AS vendor_name,
                'ITEM-1' AS item_number,
                'SMIRNOFF 80 750ML' AS item_description,
                '12' AS pack,
                '750' AS bottle_volume_ml,
                '10.00' AS state_bottle_cost,
                '15.00' AS state_bottle_retail,
                '10' AS bottles_sold,
                '150.00' AS sale_dollars,
                '2024-01-15T10:00:00Z' AS _ingested_at
            UNION ALL
            SELECT
                'INV-002', '2024-01-16', '102', 'fareway stores #5', 'ames', 'story',
                '50010', 'Whiskey', '260', 'DIAGEO', 'ITEM-2', 'CROWN ROYAL',
                '12', '750', '20.00', '30.00', '5', '150.00', '2024-01-16T10:00:00Z'
            UNION ALL
            SELECT
                'INV-003', '2024-01-17', '103', 'CASEYS GENERAL STORE #10', 'ANKENY', 'POLK',
                '50021', 'Beer', '100', 'ANHEUSER', 'ITEM-3', 'BUD LIGHT',
                '24', '355', '12.00', '18.00', '10', '180.00', '2024-01-17T10:00:00Z'
            UNION ALL
            SELECT
                'INV-004', '2024-01-18', '104', 'BEVERAGE CORNER', 'WATERLOO', 'BLACK HAWK',
                '50701', 'Gin', '500', 'BEEFEATER', 'ITEM-4', 'BEEFEATER GIN',
                '12', '750', '14.00', '21.00', '6', '126.00', '2024-01-18T10:00:00Z';
        """)

        parquet_p, _ = build_silver_sales(
            db_con=con,
            source_table_or_parquet="bronze.sales_raw",
            base_dir=tmp_path,
        )

        df = read_parquet(parquet_p)
        assert len(df) == 4

        # Testa normalização
        row1 = df[df["invoice_line_id"] == "INV-001"].iloc[0]
        assert row1["store_name"] == "Hy-Vee Food Store #1"
        assert row1["city"] == "Des Moines"
        assert row1["chain_name"] == "Hy-Vee"

        row2 = df[df["invoice_line_id"] == "INV-002"].iloc[0]
        assert row2["chain_name"] == "Fareway"

        row3 = df[df["invoice_line_id"] == "INV-003"].iloc[0]
        assert row3["chain_name"] == "Casey's"

        row4 = df[df["invoice_line_id"] == "INV-004"].iloc[0]
        assert row4["chain_name"] == "Independente"
    finally:
        con.close()


def test_silver_deduplication_and_invalid_filtering(tmp_path: Path) -> None:
    """Verifica descarte de duplicatas e remoção de devoluções/valores inválidos."""
    db_path = tmp_path / "test_dedup.duckdb"
    con = get_duckdb_connection(db_path=db_path)

    try:
        con.execute("""
            CREATE OR REPLACE TABLE bronze.sales_raw AS
            -- Linha válida
            SELECT 'DUP-01' AS invoice_and_item_number, '2024-01-10' AS date, '10' AS store_number,
                   'Store A' AS store_name, 'Ames' AS city, 'Story' AS county, '50010' AS zip_code,
                   'Vodka' AS category_name, '1' AS vendor_number, 'V1' AS vendor_name,
                   'IT-1' AS item_number, 'Item 1' AS item_description, '12' AS pack,
                   '750' AS bottle_volume_ml, '10.0' AS state_bottle_cost,
                   '15.0' AS state_bottle_retail, '5' AS bottles_sold, '75.0' AS sale_dollars,
                   '2024-01-10T08:00:00Z' AS _ingested_at
            UNION ALL
            -- Duplicata da linha DUP-01 (mais recente no ingested_at)
            SELECT 'DUP-01', '2024-01-10', '10', 'Store A', 'Ames', 'Story', '50010',
                   'Vodka', '1', 'V1', 'IT-1', 'Item 1', '12', '750',
                   '10.0', '15.0', '5', '75.0', '2024-01-10T12:00:00Z'
            UNION ALL
            -- Devolução: units <= 0
            SELECT 'INV-NEG-UNITS', '2024-01-11', '10', 'Store A', 'Ames', 'Story', '50010',
                   'Vodka', '1', 'V1', 'IT-1', 'Item 1', '12', '750',
                   '10.0', '15.0', '-2', '-30.0', '2024-01-11T10:00:00Z'
            UNION ALL
            -- Preço de venda abusivamente abaixo do custo (< 50%)
            SELECT 'INV-DUMPING', '2024-01-12', '10', 'Store A', 'Ames', 'Story', '50010',
                   'Vodka', '1', 'V1', 'IT-1', 'Item 1', '12', '750',
                   '20.0', '5.0', '10', '50.0', '2024-01-12T10:00:00Z'
            UNION ALL
            -- Pack absurdo (> 96)
            SELECT 'INV-BAD-PACK', '2024-01-13', '10', 'Store A', 'Ames', 'Story', '50010',
                   'Vodka', '1', 'V1', 'IT-1', 'Item 1', '1000', '750',
                   '10.0', '15.0', '1', '15.0', '2024-01-13T10:00:00Z';
        """)

        parquet_p, report = build_silver_sales(
            db_con=con,
            source_table_or_parquet="bronze.sales_raw",
            base_dir=tmp_path,
        )

        assert report["total_bronze"] == 5
        assert report["final_silver"] == 1  # Apenas DUP-01 sobrevive
        assert report["total_removed"] == 4

        df = read_parquet(parquet_p)
        assert len(df) == 1
        assert df["invoice_line_id"].iloc[0] == "DUP-01"
    finally:
        con.close()


def test_silver_category_mode_imputation(tmp_path: Path) -> None:
    """Verifica se categoria nula é preenchida pela moda do item e fallback para 'Outros'."""
    db_path = tmp_path / "test_cat.duckdb"
    con = get_duckdb_connection(db_path=db_path)

    try:
        con.execute("""
            CREATE OR REPLACE TABLE bronze.sales_raw AS
            SELECT 'INV-1' AS invoice_and_item_number, '2024-01-01' AS date, '1' AS store_number,
                   'Store' AS store_name, 'City' AS city, 'County' AS county, '12345' AS zip_code,
                   'Tequila' AS category_name, '1' AS vendor_number, 'V' AS vendor_name,
                   'ITEM-A' AS item_number, 'Item A' AS item_description, '12' AS pack,
                   '750' AS bottle_volume_ml, '10.0' AS state_bottle_cost,
                   '15.0' AS state_bottle_retail, '1' AS bottles_sold, '15.0' AS sale_dollars,
                   '2024-01-01T00:00:00Z' AS _ingested_at
            UNION ALL
            SELECT 'INV-2', '2024-01-02', '1', 'Store', 'City', 'County', '12345',
                   'Tequila', '1', 'V', 'ITEM-A', 'Item A', '12', '750',
                   '10.0', '15.0', '1', '15.0', '2024-01-02T00:00:00Z'
            UNION ALL
            -- ITEM-A com categoria NULL (deve ser imputada como 'Tequila')
            SELECT 'INV-3', '2024-01-03', '1', 'Store', 'City', 'County', '12345',
                   NULL, '1', 'V', 'ITEM-A', 'Item A', '12', '750',
                   '10.0', '15.0', '1', '15.0', '2024-01-03T00:00:00Z'
            UNION ALL
            -- ITEM-B sem nenhuma categoria informada (fallback para 'Outros')
            SELECT 'INV-4', '2024-01-04', '1', 'Store', 'City', 'County', '12345',
                   NULL, '1', 'V', 'ITEM-B', 'Item B', '12', '750',
                   '10.0', '15.0', '1', '15.0', '2024-01-04T00:00:00Z';
        """)

        parquet_p, _ = build_silver_sales(
            db_con=con,
            source_table_or_parquet="bronze.sales_raw",
            base_dir=tmp_path,
        )

        df = read_parquet(parquet_p)
        assert len(df) == 4

        row_imputed = df[df["invoice_line_id"] == "INV-3"].iloc[0]
        assert row_imputed["category_name"] == "Tequila"

        row_fallback = df[df["invoice_line_id"] == "INV-4"].iloc[0]
        assert row_fallback["category_name"] == "Outros"
    finally:
        con.close()


def test_cli_silver_build_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica execução do comando CLI 'kyberna silver build --sample'."""
    monkeypatch.setenv("KYBERNA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("KYBERNA_DUCKDB_PATH", str(tmp_path / "data" / "kyberna.duckdb"))

    result = runner.invoke(app, ["silver", "build", "--sample"])
    assert result.exit_code == 0
    assert "Silver construída com sucesso" in result.output
