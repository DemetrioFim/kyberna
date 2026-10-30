from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import duckdb
import pandas as pd

from src.core.logging import logger
from src.core.paths import get_data_dir, get_duckdb_path
from src.core.settings import get_settings


def get_duckdb_connection(
    db_path: Path | str | None = None,
    read_only: bool = False,
) -> duckdb.DuckDBPyConnection:
    """Retorna uma conexão gerenciada ao banco DuckDB local unificado (`kyberna.duckdb`).

    Garante que os schemas medallion (`bronze`, `silver`, `gold`) existam quando em modo escrita.

    Args:
        db_path: Caminho do arquivo .duckdb. Se omitido, usa get_duckdb_path().
        read_only: Se True, abre conexão somente leitura (evita locks concorrentes).

    Returns:
        Conexão DuckDBPyConnection ativa.
    """
    resolved_path = Path(db_path) if db_path is not None else get_duckdb_path()

    if not read_only:
        resolved_path.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(database=str(resolved_path), read_only=read_only)

    if not read_only:
        con.execute("CREATE SCHEMA IF NOT EXISTS bronze;")
        con.execute("CREATE SCHEMA IF NOT EXISTS silver;")
        con.execute("CREATE SCHEMA IF NOT EXISTS gold;")

    return con


def write_parquet(
    df: pd.DataFrame,
    dest_path: Path | str,
    compression: Literal["snappy", "gzip", "brotli", "lz4", "zstd"] | None = "zstd",
) -> Path:
    """Salva um DataFrame em Parquet de forma atômica (escrita temporária + replace).

    Args:
        df: DataFrame do Pandas a ser persistido.
        dest_path: Caminho de destino do arquivo Parquet.
        compression: Algoritmo de compressão (padrão 'zstd').

    Returns:
        Path absoluto do arquivo gravado com sucesso.
    """
    target = Path(dest_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    # Escrita atômica usando arquivo temporário no mesmo diretório
    temp_file = target.with_suffix(f".tmp_{os.getpid()}_{target.name}")
    try:
        df.to_parquet(temp_file, index=False, compression=compression)
        temp_file.replace(target)
    finally:
        if temp_file.exists():
            temp_file.unlink(missing_ok=True)

    return target


def read_parquet(source_path: Path | str) -> pd.DataFrame:
    """Lê um arquivo Parquet retornando um DataFrame Pandas.

    Args:
        source_path: Caminho do arquivo Parquet a carregar.

    Returns:
        DataFrame com os dados lidos.
    """
    target = Path(source_path)
    if not target.exists():
        raise FileNotFoundError(f"Arquivo Parquet não encontrado: {target}")
    return pd.read_parquet(target)


def register_bronze_view(
    con: duckdb.DuckDBPyConnection | None = None,
    base_dir: Path | None = None,
) -> None:
    """Registra ou atualiza a view `bronze.sales_raw` sobre os Parquets particionados.

    Se nenhum arquivo particionado existir ainda, cria uma tabela vazia com o schema canônico.
    """
    settings = get_settings()
    db_con = con or get_duckdb_connection(settings.duckdb_path)

    # Diretório base bronze de vendas
    bronze_sales_dir = get_data_dir(base_dir) / "bronze" / "sales"
    parquet_files = list(bronze_sales_dir.glob("**/*.parquet")) if bronze_sales_dir.exists() else []

    if parquet_files:
        # Usa glob formatado com barras normais para compatibilidade DuckDB no Windows
        glob_pattern = f"{bronze_sales_dir.as_posix()}/**/*.parquet"
        db_con.execute(f"""
            CREATE OR REPLACE VIEW bronze.sales_raw AS
            SELECT * FROM read_parquet('{glob_pattern}', hive_partitioning=true);
        """)
        logger.info(
            "View bronze.sales_raw registrada com sucesso no DuckDB apontando para os arquivos particionados."
        )
    else:
        # Fallback para schema vazio se ainda não houver dados baixados
        db_con.execute("""
            CREATE TABLE IF NOT EXISTS bronze.sales_raw (
                invoice_and_item_number VARCHAR,
                date VARCHAR,
                store_number VARCHAR,
                store_name VARCHAR,
                address VARCHAR,
                city VARCHAR,
                zip_code VARCHAR,
                store_location VARCHAR,
                county_number VARCHAR,
                county VARCHAR,
                category VARCHAR,
                category_name VARCHAR,
                vendor_number VARCHAR,
                vendor_name VARCHAR,
                item_number VARCHAR,
                item_description VARCHAR,
                pack VARCHAR,
                bottle_volume_ml VARCHAR,
                state_bottle_cost VARCHAR,
                state_bottle_retail VARCHAR,
                bottles_sold VARCHAR,
                sale_dollars VARCHAR,
                volume_sold_liters VARCHAR,
                volume_sold_gallons VARCHAR,
                _ingested_at VARCHAR,
                _batch_id VARCHAR,
                _source VARCHAR
            );
        """)
