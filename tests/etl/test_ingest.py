from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from src.cli import app
from src.etl.contracts import BronzeSalesSchema, validate_contract
from src.etl.ingest.raw_to_bronze import (
    convert_all_raw_to_bronze,
    convert_raw_csv_to_bronze,
)
from src.etl.ingest.socrata_client import SocrataClient
from src.etl.lake import get_duckdb_connection, read_parquet

runner = CliRunner()

CSV_HEADER = (
    "invoice_and_item_number,date,store_number,store_name,address,city,zip_code,"
    "store_location,county_number,county,category,category_name,vendor_number,vendor_name,"
    "item_number,item_description,pack,bottle_volume_ml,state_bottle_cost,state_bottle_retail,"
    "bottles_sold,sale_dollars,volume_sold_liters,volume_sold_gallons"
)

SAMPLE_ROW_1 = (
    "INV-0001,2024-01-10,2500,Hy-Vee #1,100 Main St,Des Moines,50309,"
    "POINT (-93.62 41.58),77,Polk,1011100,Vodka,260,Diageo,11223,Smirnoff 80,"
    "12,750,7.50,11.25,12,135.00,9.0,2.37"
)
SAMPLE_ROW_2 = (
    "INV-0002,2024-01-15,2501,Fareway #2,200 Elm St,Ames,50010,"
    "POINT (-93.63 42.03),85,Story,1011200,Whiskey,260,Diageo,44556,Crown Royal,"
    "12,750,15.00,22.50,6,135.00,4.5,1.18"
)
SAMPLE_ROW_3 = (
    "INV-0003,2024-01-20,2502,Casey's #3,300 Pine St,Cedar Rapids,52401,"
    ",57,Linn,1031100,Rum,370,Bacardi,77889,Bacardi Superior,12,1000,9.00,13.50,24,324.00,24.0,6.34"
)


def test_socrata_client_pagination(tmp_path: Path) -> None:
    """Verifica se o cliente Socrata pagina corretamente e grava CSV consolidado com cabeçalho único."""
    request_count = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        offset = request.url.params.get("$offset", "0")

        if offset == "0":
            # Página 1 com 2 linhas
            content = f"{CSV_HEADER}\n{SAMPLE_ROW_1}\n{SAMPLE_ROW_2}\n"
            return httpx.Response(200, text=content)
        elif offset == "2":
            # Página 2 com 1 linha
            content = f"{CSV_HEADER}\n{SAMPLE_ROW_3}\n"
            return httpx.Response(200, text=content)
        else:
            # Página 3 vazia
            return httpx.Response(200, text=f"{CSV_HEADER}\n")

    transport = httpx.MockTransport(mock_handler)
    client = SocrataClient(transport=transport)

    csv_file = client.download_month(
        year=2024,
        month=1,
        base_dir=tmp_path,
        page_size=2,  # Força quebra de página a cada 2 registros
    )

    assert csv_file.exists()
    assert request_count >= 2

    # Confere o conteúdo final gravado
    lines = csv_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 4  # 1 cabeçalho + 3 linhas de dados
    assert lines[0] == CSV_HEADER
    assert "INV-0001" in lines[1]
    assert "INV-0002" in lines[2]
    assert "INV-0003" in lines[3]


def test_socrata_client_retry_on_rate_limit(tmp_path: Path) -> None:
    """Verifica se retry com backoff é acionado em HTTP 429 / 503."""
    attempts = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(429, text="Rate limit exceeded")
        return httpx.Response(200, text=f"{CSV_HEADER}\n{SAMPLE_ROW_1}\n")

    transport = httpx.MockTransport(mock_handler)
    client = SocrataClient(transport=transport)

    csv_file = client.download_month(year=2024, month=2, base_dir=tmp_path, page_size=10)
    assert csv_file.exists()
    assert attempts == 3


def test_socrata_client_idempotency(tmp_path: Path) -> None:
    """Verifica se arquivos de meses já existentes não são baixados novamente sem --force."""
    call_count = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, text=f"{CSV_HEADER}\n{SAMPLE_ROW_1}\n")

    transport = httpx.MockTransport(mock_handler)
    client = SocrataClient(transport=transport)

    # Primeira execução: faz download
    p1 = client.download_month(year=2024, month=3, base_dir=tmp_path)
    assert call_count == 1
    assert p1.exists()

    # Segunda execução sem force: pula sem chamar HTTP
    p2 = client.download_month(year=2024, month=3, base_dir=tmp_path, force=False)
    assert call_count == 1
    assert p2 == p1

    # Terceira execução com force: baixa novamente
    p3 = client.download_month(year=2024, month=3, base_dir=tmp_path, force=True)
    assert call_count == 2
    assert p3 == p1


def test_convert_raw_to_bronze_and_duckdb_view(tmp_path: Path) -> None:
    """Valida conversão de CSV para Parquet Bronze, metadados e view no DuckDB."""
    # Cria arquivo CSV simulado
    raw_dir = tmp_path / "data" / "raw" / "sales" / "year=2024" / "month=01"
    raw_dir.mkdir(parents=True, exist_ok=True)
    csv_file = raw_dir / "data.csv"
    csv_file.write_text(f"{CSV_HEADER}\n{SAMPLE_ROW_1}\n{SAMPLE_ROW_2}\n", encoding="utf-8")

    db_path = tmp_path / "data" / "kyberna.duckdb"
    db_con = get_duckdb_connection(db_path=db_path)

    try:
        # Converte para Bronze
        parquet_p = convert_raw_csv_to_bronze(
            raw_csv_path=csv_file,
            year=2024,
            month=1,
            base_dir=tmp_path,
            db_con=db_con,
        )

        assert parquet_p.exists()
        df_bronze = read_parquet(parquet_p)

        # Checa presença das colunas e metadados
        assert len(df_bronze) == 2
        assert "_ingested_at" in df_bronze.columns
        assert "_batch_id" in df_bronze.columns
        assert "_source" in df_bronze.columns
        assert df_bronze["_source"].iloc[0] == "socrata_api"

        # Validação do Contrato Pandera
        validated_df = validate_contract(df_bronze, BronzeSalesSchema, layer="bronze")
        assert len(validated_df) == 2

        # Registra e consulta no DuckDB
        convert_all_raw_to_bronze(base_dir=tmp_path, db_con=db_con)
        res = db_con.execute("SELECT COUNT(*) FROM bronze.sales_raw").fetchone()
        assert res is not None
        assert res[0] == 2
    finally:
        db_con.close()


def test_stratified_store_sampling(tmp_path: Path) -> None:
    """Verifica se amostragem estratificada por loja filtra consistentemente."""
    raw_dir = tmp_path / "data" / "raw" / "sales" / "year=2024" / "month=02"
    raw_dir.mkdir(parents=True, exist_ok=True)
    csv_file = raw_dir / "data.csv"

    # Cria 50 linhas com 10 lojas distintas
    rows = []
    for store_idx in range(10):
        for line_idx in range(5):
            rows.append(
                f"INV-{store_idx}-{line_idx},2024-02-01,{store_idx},Store {store_idx},,"
                f"Des Moines,50309,,77,Polk,1011100,Vodka,260,Diageo,100,Vodka,"
                f"12,750,5.00,8.00,1,8.00,0.75,0.2"
            )
    csv_file.write_text(f"{CSV_HEADER}\n" + "\n".join(rows) + "\n", encoding="utf-8")

    # Amostragem de 30% das lojas
    parquet_p = convert_raw_csv_to_bronze(
        raw_csv_path=csv_file,
        year=2024,
        month=2,
        base_dir=tmp_path,
        sample_frac=0.3,
    )
    df = read_parquet(parquet_p)

    # Todas as transações das lojas selecionadas devem estar presentes (múltiplos de 5)
    assert len(df) > 0
    assert len(df) < 50
    assert len(df) % 5 == 0


def test_cli_bronze_build_sample(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica se o comando CLI 'kyberna bronze build --sample' funciona ponta a ponta."""
    monkeypatch.setenv("KYBERNA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("KYBERNA_DUCKDB_PATH", str(tmp_path / "data" / "kyberna.duckdb"))

    result = runner.invoke(app, ["bronze", "build", "--sample"])
    assert result.exit_code == 0
    assert "Bronze construída a partir da amostra fixture" in result.output
