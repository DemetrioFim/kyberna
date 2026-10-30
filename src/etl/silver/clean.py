from __future__ import annotations

from pathlib import Path

import duckdb

from src.core.logging import logger, timed_step
from src.core.paths import get_project_root, silver_path
from src.etl.contracts import SilverSalesSchema, validate_contract
from src.etl.ingest.fixture import generate_fixture
from src.etl.ingest.raw_to_bronze import populate_bronze_from_sample_fixture
from src.etl.lake import get_duckdb_connection, write_parquet


def build_silver_sales(
    db_con: duckdb.DuckDBPyConnection | None = None,
    source_table_or_parquet: str | None = None,
    base_dir: Path | None = None,
    sample: bool = False,
) -> tuple[Path, dict[str, int]]:
    """Executa a limpeza, tipagem, deduplicação e filtros da camada Bronze para Silver em SQL no DuckDB.

    Gera a tabela `silver.sales` no banco DuckDB e exporta o Parquet canônico `data/silver/sales.parquet`.
    Retorna o caminho do Parquet e o relatório estatístico de linhas processadas e descartadas.

    Args:
        db_con: Conexão DuckDB ativa opcional. Se None, usa conexão padrão.
        source_table_or_parquet: Nome da tabela/view (ex: 'bronze.sales_raw') ou caminho Parquet.
        base_dir: Diretório base customizado (para testes em tmp_path).
        sample: Se True e nenhuma fonte for passada, garante a presença da fixture de teste.

    Returns:
        Tupla com (caminho do arquivo parquet gerado, dicionário com métricas do relatório de limpeza).
    """
    con = db_con or get_duckdb_connection()
    target_parquet = silver_path("sales", base=base_dir)
    target_parquet.parent.mkdir(parents=True, exist_ok=True)

    with timed_step("silver_clean_pipeline"):
        # Determina a fonte Bronze
        if source_table_or_parquet is not None:
            source_ref = source_table_or_parquet
        elif sample:
            # Garante que a fixture sintética esteja carregada em Bronze
            fixture_p = get_project_root() / "tests" / "fixtures" / "iowa_sample.parquet"
            if not fixture_p.exists():
                generate_fixture(output_path=fixture_p)
            populate_bronze_from_sample_fixture(fixture_p, base_dir=base_dir, db_con=con)
            source_ref = "bronze.sales_raw"
        else:
            source_ref = "bronze.sales_raw"

        # 1. Contagem inicial na fonte Bronze
        total_bronze_rows = con.execute(f"SELECT COUNT(*) FROM {source_ref};").fetchone()[0]  # type: ignore[index]
        if total_bronze_rows == 0:
            logger.warning(f"Fonte Bronze ({source_ref}) vazia. Nenhum dado para processar.")
            return target_parquet, {"total_bronze": 0, "final_silver": 0}

        # 2. Registra macro para Title Case (palavras e hífens) e executa transformação SQL
        con.execute("""
            CREATE OR REPLACE MACRO title_case(s) AS (
                CASE
                    WHEN s IS NULL OR TRIM(s) = '' THEN s
                    ELSE list_aggregate(
                        list_transform(
                            str_split(REGEXP_REPLACE(TRIM(s), '\\s+', ' ', 'g'), ' '),
                            lambda w: list_aggregate(
                                list_transform(
                                    str_split(w, '-'),
                                    lambda part: CASE
                                        WHEN length(part) > 0 THEN upper(part[1]) || lower(part[2:])
                                        ELSE ''
                                    END
                                ),
                                'string_agg',
                                '-'
                            )
                        ),
                        'string_agg',
                        ' '
                    )
                END
            );
        """)

        # Usa CTEs claras para tipagem, enriquecimento de categoria, normalização, deduplicação e filtros
        sql_clean = f"""
        CREATE OR REPLACE TABLE silver.sales AS
        WITH parsed_types AS (
            SELECT
                TRIM(invoice_and_item_number) AS invoice_line_id,
                COALESCE(
                    TRY_CAST(date AS DATE),
                    TRY_STRPTIME(date, '%Y-%m-%d'),
                    TRY_STRPTIME(date, '%m/%d/%Y'),
                    TRY_CAST(date AS TIMESTAMP)::DATE
                ) AS order_date,
                TRIM(store_number) AS store_number,
                title_case(store_name) AS store_name,
                title_case(city) AS city,
                title_case(county) AS county,
                NULLIF(TRIM(zip_code), '') AS zip_code,
                NULLIF(TRIM(category_name), '') AS category_name,
                NULLIF(TRIM(vendor_number), '') AS vendor_number,
                title_case(vendor_name) AS vendor_name,
                TRIM(item_number) AS item_number,
                title_case(item_description) AS item_description,
                TRY_CAST(pack AS INTEGER) AS pack,
                TRY_CAST(bottle_volume_ml AS DOUBLE) AS bottle_volume_ml,
                TRY_CAST(state_bottle_cost AS DOUBLE) AS unit_cost,
                TRY_CAST(state_bottle_retail AS DOUBLE) AS unit_price,
                TRY_CAST(bottles_sold AS INTEGER) AS units,
                TRY_CAST(sale_dollars AS DOUBLE) AS sale_amount,
                _ingested_at
            FROM {source_ref}
            WHERE invoice_and_item_number IS NOT NULL AND TRIM(invoice_and_item_number) != ''
        ),
        category_modes AS (
            SELECT
                item_number,
                category_name,
                COUNT(*) AS cat_count,
                ROW_NUMBER() OVER (PARTITION BY item_number ORDER BY COUNT(*) DESC) AS mode_rank
            FROM parsed_types
            WHERE category_name IS NOT NULL
            GROUP BY item_number, category_name
        ),
        enriched_base AS (
            SELECT
                p.invoice_line_id,
                p.order_date AS date,
                p.store_number,
                p.store_name,
                p.city,
                p.county,
                p.zip_code,
                CASE
                    WHEN p.store_name ILIKE '%hy-vee%' THEN 'Hy-Vee'
                    WHEN p.store_name ILIKE '%fareway%' THEN 'Fareway'
                    WHEN p.store_name ILIKE '%casey%' THEN 'Casey''s'
                    WHEN p.store_name ILIKE '%kum & go%' OR p.store_name ILIKE '%kum and go%' THEN 'Kum & Go'
                    WHEN p.store_name ILIKE '%wal-mart%' OR p.store_name ILIKE '%walmart%' THEN 'Walmart'
                    WHEN p.store_name ILIKE '%target%' THEN 'Target'
                    WHEN p.store_name ILIKE '%smokin%' THEN 'Smokin'' Joe''s'
                    WHEN p.store_name ILIKE '%central city%' THEN 'Central City Liquor'
                    ELSE 'Independente'
                END AS chain_name,
                COALESCE(p.category_name, cm.category_name, 'Outros') AS category_name,
                p.vendor_number,
                p.vendor_name,
                p.item_number,
                p.item_description,
                p.pack,
                p.bottle_volume_ml,
                p.unit_cost,
                p.unit_price,
                p.units,
                p.sale_amount,
                ROW_NUMBER() OVER (
                    PARTITION BY p.invoice_line_id
                    ORDER BY p.order_date DESC, p._ingested_at DESC
                ) AS dedup_rank
            FROM parsed_types p
            LEFT JOIN category_modes cm ON p.item_number = cm.item_number AND cm.mode_rank = 1
        ),
        item_stats AS (
            SELECT
                item_number,
                COUNT(*) AS total_tx,
                PERCENTILE_CONT(0.001) WITHIN GROUP (ORDER BY unit_price) AS p001,
                PERCENTILE_CONT(0.999) WITHIN GROUP (ORDER BY unit_price) AS p999
            FROM enriched_base
            WHERE unit_price IS NOT NULL AND unit_price > 0
            GROUP BY item_number
        )
        SELECT
            e.invoice_line_id,
            e.date,
            e.date AS original_date,
            0 AS time_shift_days,
            e.store_number,
            e.store_name,
            e.city,
            e.county,
            e.zip_code,
            e.chain_name,
            e.category_name,
            e.vendor_number,
            e.vendor_name,
            e.item_number,
            e.item_description,
            e.pack,
            e.bottle_volume_ml,
            e.unit_cost,
            e.unit_price,
            e.units,
            e.sale_amount
        FROM enriched_base e
        LEFT JOIN item_stats ist ON e.item_number = ist.item_number
        WHERE e.dedup_rank = 1
          AND e.date IS NOT NULL
          AND e.units IS NOT NULL AND e.units > 0
          AND e.sale_amount IS NOT NULL AND e.sale_amount > 0
          AND e.unit_cost IS NOT NULL AND e.unit_cost > 0
          AND e.unit_price IS NOT NULL AND e.unit_price > 0
          AND e.unit_price >= (e.unit_cost * 0.5)
          AND e.pack IS NOT NULL AND e.pack BETWEEN 1 AND 96
          AND e.bottle_volume_ml IS NOT NULL AND e.bottle_volume_ml > 0
          AND (
              ist.total_tx < 10
              OR (e.unit_price >= ist.p001 AND e.unit_price <= ist.p999)
          );
        """
        con.execute(sql_clean)

        # 3. Estatísticas e Relatório de Remoções
        final_silver_rows = con.execute("SELECT COUNT(*) FROM silver.sales;").fetchone()[0]  # type: ignore[index]
        removed_rows = total_bronze_rows - final_silver_rows

        report = {
            "total_bronze": total_bronze_rows,
            "final_silver": final_silver_rows,
            "total_removed": removed_rows,
        }

        logger.info(
            f"Relatório de Limpeza Silver: "
            f"Bronze={total_bronze_rows:,} -> Silver={final_silver_rows:,} | "
            f"Descartados={removed_rows:,} ({removed_rows / max(total_bronze_rows, 1):.1%})"
        )

        # 4. Extrai DataFrame e valida contra Pandera SilverSalesSchema
        df_silver = con.execute("SELECT * FROM silver.sales;").df()
        validate_contract(df_silver, SilverSalesSchema, layer="silver")

        # 5. Persiste atômico em Parquet Zstandard
        write_parquet(df_silver, target_parquet, compression="zstd")
        logger.info(f"Parquet Silver gerado em {target_parquet} ({len(df_silver):,} linhas).")

        return target_parquet, report
