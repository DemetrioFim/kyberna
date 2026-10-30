from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from src.core.logging import logger
from src.core.paths import bronze_path, get_data_dir
from src.etl.contracts import BronzeSalesSchema, validate_contract
from src.etl.lake import read_parquet, register_bronze_view, write_parquet

BRONZE_COLUMNS = [
    "invoice_and_item_number",
    "date",
    "store_number",
    "store_name",
    "address",
    "city",
    "zip_code",
    "store_location",
    "county_number",
    "county",
    "category",
    "category_name",
    "vendor_number",
    "vendor_name",
    "item_number",
    "item_description",
    "pack",
    "bottle_volume_ml",
    "state_bottle_cost",
    "state_bottle_retail",
    "bottles_sold",
    "sale_dollars",
    "volume_sold_liters",
    "volume_sold_gallons",
]


def _is_store_sampled(store_id: str, sample_frac: float) -> bool:
    """Função determinística de amostragem de lojas usando MD5 hash."""
    h = int(hashlib.md5(store_id.encode("utf-8")).hexdigest()[:8], 16)
    return (h % 10000) < int(sample_frac * 10000)


def convert_raw_csv_to_bronze(
    raw_csv_path: Path | str,
    year: int,
    month: int,
    *,
    base_dir: Path | None = None,
    sample_frac: float | None = None,
    batch_id: str | None = None,
    db_con: duckdb.DuckDBPyConnection | None = None,
) -> Path:
    """Converte um arquivo CSV raw de vendas em Parquet Bronze particionado.

    Adiciona metadados de ingestão (_ingested_at, _batch_id, _source) e aplica
    amostragem estratificada por loja se solicitado.
    """
    csv_file = Path(raw_csv_path)
    if not csv_file.exists():
        raise FileNotFoundError(f"Arquivo CSV não encontrado: {csv_file}")

    target_parquet = bronze_path("sales", year=year, month=month, base=base_dir)
    target_parquet.parent.mkdir(parents=True, exist_ok=True)

    b_id = batch_id or str(uuid.uuid4())
    ingested_at = datetime.now(UTC).isoformat()
    source = "socrata_api"

    # Leitura usando DuckDB com all_varchar=True para fidelidade total ao contrato Bronze
    con = db_con or duckdb.connect()
    try:
        # Lê todas as colunas como VARCHAR
        df_raw = con.execute(
            "SELECT * FROM read_csv(?, all_varchar=true, header=true);",
            [str(csv_file)],
        ).df()

        # Garante a presença de todas as colunas canônicas
        for col in BRONZE_COLUMNS:
            if col not in df_raw.columns:
                df_raw[col] = ""
            else:
                df_raw[col] = df_raw[col].fillna("").astype(str)

        # Seleciona apenas as colunas canônicas
        df_clean = df_raw[BRONZE_COLUMNS].copy()

        # Amostragem estratificada por loja se especificada
        if sample_frac is not None and 0.0 < sample_frac < 1.0:
            mask = df_clean["store_number"].apply(lambda s: _is_store_sampled(s, sample_frac))
            df_clean = df_clean[mask].copy()

        # Adiciona metadados de linhagem
        df_clean["_ingested_at"] = ingested_at
        df_clean["_batch_id"] = b_id
        df_clean["_source"] = source

        # Validação do Contrato Pandera
        validate_contract(df_clean, BronzeSalesSchema, layer="bronze")

        # Escrita atômica em Parquet comprimido com Zstandard
        write_parquet(df_clean, target_parquet, compression="zstd")
        logger.info(
            f"Bronze particionado gerado: {target_parquet} ({len(df_clean):,} linhas, lote {b_id[:8]})."
        )
        return target_parquet
    finally:
        if db_con is None:
            con.close()


def convert_all_raw_to_bronze(
    base_dir: Path | None = None,
    sample_frac: float | None = None,
    db_con: duckdb.DuckDBPyConnection | None = None,
) -> list[Path]:
    """Varre data/raw/sales/ e converte todos os CSVs encontrados para Parquet Bronze.

    Ao final, atualiza a view `bronze.sales_raw` no banco `kyberna.duckdb`.
    """
    raw_root = get_data_dir(base_dir) / "raw" / "sales"
    if not raw_root.exists():
        logger.warning(f"Diretório raw não encontrado: {raw_root}")
        return []

    csv_files = list(raw_root.glob("year=*/month=*/data.csv"))
    if not csv_files:
        logger.warning("Nenhum arquivo CSV encontrado em data/raw/sales/year=*/month=*/data.csv")
        return []

    batch_id = str(uuid.uuid4())
    bronze_files: list[Path] = []

    for csv_file in csv_files:
        # Extrai ano e mês do caminho da partição
        try:
            year_part = csv_file.parent.parent.name  # year=YYYY
            month_part = csv_file.parent.name  # month=MM
            year = int(year_part.split("=")[1])
            month = int(month_part.split("=")[1])
        except (IndexError, ValueError):
            logger.error(f"Caminho de partição inválido para {csv_file}")
            continue

        p = convert_raw_csv_to_bronze(
            raw_csv_path=csv_file,
            year=year,
            month=month,
            base_dir=base_dir,
            sample_frac=sample_frac,
            batch_id=batch_id,
            db_con=db_con,
        )
        bronze_files.append(p)

    # Registra no catálogo DuckDB
    register_bronze_view(con=db_con, base_dir=base_dir)
    return bronze_files


def populate_bronze_from_sample_fixture(
    fixture_path: Path | str,
    base_dir: Path | None = None,
    db_con: duckdb.DuckDBPyConnection | None = None,
) -> Path:
    """Carrega a fixture sintética direta para data/bronze/sales/ e registra no DuckDB.

    Utilizado para testes e modo offline sem necessidade de download via internet.
    """
    f_path = Path(fixture_path)
    if not f_path.exists():
        raise FileNotFoundError(f"Fixture não encontrada: {f_path}")

    df = read_parquet(f_path)
    # Valida contrato
    validate_contract(df, BronzeSalesSchema, layer="bronze")

    # Salva na partição 2024-12
    target_parquet = bronze_path("sales", year=2024, month=12, base=base_dir)
    write_parquet(df, target_parquet, compression="zstd")

    # Registra no DuckDB
    register_bronze_view(con=db_con, base_dir=base_dir)
    logger.info(f"Bronze populado com fixture em {target_parquet} ({len(df):,} linhas).")
    return target_parquet
