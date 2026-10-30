from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

import duckdb

from src.core.logging import logger, timed_step
from src.core.paths import silver_path
from src.core.settings import get_settings
from src.etl.contracts import SilverSalesSchema, validate_contract
from src.etl.lake import get_duckdb_connection, write_parquet


def compute_weekly_time_shift(max_date: datetime.date, reference_date: datetime.date) -> int:
    """Calcula o offset inteiro em semanas (dias múltiplos de 7) para ancoragem temporal.

    Garante matematicamente que:
    1. shift_days % 7 == 0 (preserva o dia da semana e a sazonalidade semanal).
    2. max_shifted_date = max_date + shift_days está dentro do intervalo
       [reference_date - 6 dias, reference_date] (mesma semana da data de referência).

    Args:
        max_date: Data máxima presente no dataset original.
        reference_date: Data âncora desejada (geralmente ontem).

    Returns:
        Offset inteiro em dias (múltiplo de 7).
    """
    raw_diff = (reference_date - max_date).days
    # Divisão inteira (floor) por 7 vezes 7 garante k inteiro de semanas
    weeks = raw_diff // 7
    return weeks * 7


def apply_time_anchor(
    db_con: duckdb.DuckDBPyConnection | None = None,
    reference_date: datetime.date | str | None = None,
    no_shift: bool = False,
    base_dir: Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Aplica o deslocamento temporal por semanas na tabela `silver.sales` no DuckDB.

    Atualiza a tabela no banco `kyberna.duckdb`, salva o Parquet `data/silver/sales.parquet`
    e valida o contrato `SilverSalesSchema`.

    Args:
        db_con: Conexão ativa ao DuckDB. Se None, conecta ao banco padrão.
        reference_date: Data âncora de referência. Se omitida, usa settings.reference_date.
        no_shift: Se True, preserva as datas originais (shift_days = 0).
        base_dir: Diretório raiz customizado (para testes unitários).

    Returns:
        Tupla com (caminho do parquet gerado, metadados do time shift).
    """
    settings = get_settings()
    con = db_con or get_duckdb_connection(settings.duckdb_path)
    target_parquet = silver_path("sales", base=base_dir)
    target_parquet.parent.mkdir(parents=True, exist_ok=True)

    with timed_step("silver_time_anchor"):
        # 1. Verifica existência da tabela silver.sales
        table_check = con.execute("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema = 'silver' AND table_name = 'sales';
        """).fetchone()

        if not table_check or table_check[0] == 0:
            raise RuntimeError(
                "Tabela silver.sales não encontrada no DuckDB. Execute 'kyberna silver build' primeiro."
            )

        # 2. Determina a data de referência
        if reference_date is None:
            ref_date = settings.effective_reference_date
        elif isinstance(reference_date, str):
            ref_date = datetime.date.fromisoformat(reference_date)
        else:
            ref_date = reference_date

        # 3. Lê datas mínimas e máximas originais
        # Usa original_date se existir; caso contrário date
        orig_col_check = con.execute("""
            SELECT COUNT(*) FROM information_schema.columns
            WHERE table_schema = 'silver' AND table_name = 'sales' AND column_name = 'original_date';
        """).fetchone()
        has_orig_col = bool(orig_col_check and orig_col_check[0] > 0)

        orig_col_sql = "original_date" if has_orig_col else "date"

        date_bounds = con.execute(f"""
            SELECT
                MIN({orig_col_sql})::DATE,
                MAX({orig_col_sql})::DATE,
                COUNT(*)
            FROM silver.sales;
        """).fetchone()

        if not date_bounds or date_bounds[2] == 0:
            logger.warning("Tabela silver.sales está vazia. Nenhum time-shift aplicado.")
            return target_parquet, {"total_rows": 0, "time_shift_days": 0}

        min_orig_date: datetime.date = date_bounds[0]
        max_orig_date: datetime.date = date_bounds[1]
        total_rows: int = date_bounds[2]

        # 4. Calcula o shift
        if no_shift:
            shift_days = 0
            logger.info("Time-shift desabilitado (--no-shift). Mantendo datas originais.")
        else:
            shift_days = compute_weekly_time_shift(max_orig_date, ref_date)
            logger.info(
                f"Time-shift calculado: {shift_days} dias ({shift_days // 7} semanas) | "
                f"Original max={max_orig_date} -> Ref={ref_date}"
            )

        # 5. Aplica a transformação SQL no DuckDB de forma atômica
        sql_shift = f"""
        CREATE OR REPLACE TABLE silver.sales AS
        SELECT
            invoice_line_id,
            ({orig_col_sql} + INTERVAL ({shift_days}) DAY)::DATE AS date,
            {orig_col_sql} AS original_date,
            {shift_days} AS time_shift_days,
            store_number,
            store_name,
            city,
            county,
            zip_code,
            chain_name,
            category_name,
            vendor_number,
            vendor_name,
            item_number,
            item_description,
            pack,
            bottle_volume_ml,
            unit_cost,
            unit_price,
            units,
            sale_amount
        FROM silver.sales;
        """
        con.execute(sql_shift)

        # 6. Lê novas datas para os metadados
        new_bounds = con.execute("""
            SELECT
                MIN(date)::DATE,
                MAX(date)::DATE
            FROM silver.sales;
        """).fetchone()

        min_shifted_date: datetime.date = new_bounds[0]  # type: ignore[index]
        max_shifted_date: datetime.date = new_bounds[1]  # type: ignore[index]

        metadata: dict[str, Any] = {
            "reference_date": str(ref_date),
            "no_shift": no_shift,
            "time_shift_days": shift_days,
            "weeks_shifted": shift_days // 7,
            "min_original_date": str(min_orig_date),
            "max_original_date": str(max_orig_date),
            "min_shifted_date": str(min_shifted_date),
            "max_shifted_date": str(max_shifted_date),
            "total_rows": total_rows,
        }

        logger.info(
            f"Âncora temporal aplicada: {total_rows:,} linhas atualizadas. "
            f"Nova janela: {min_shifted_date} a {max_shifted_date} (shift de {shift_days} dias)."
        )

        # 7. Validação do contrato Pandera
        df_silver = con.execute("SELECT * FROM silver.sales;").df()
        validate_contract(df_silver, SilverSalesSchema, layer="silver")

        # 8. Exportação atômica para Parquet
        write_parquet(df_silver, target_parquet, compression="zstd")
        logger.info(f"Parquet Silver atualizado em {target_parquet}.")

        return target_parquet, metadata
