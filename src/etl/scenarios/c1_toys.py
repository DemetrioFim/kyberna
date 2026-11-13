from __future__ import annotations

from pathlib import Path
from typing import Final

import duckdb
import pandas as pd

from src.core.logging import get_logger
from src.core.paths import get_data_dir
from src.core.scenarios import ScenarioConfig, load_scenario_config
from src.core.types import ScenarioId
from src.etl.ingest.fixture import generate_fixture
from src.etl.scenarios.base import ScenarioBuilder
from src.etl.scenarios.c1_toys_product import (
    build_c1_dim_product,
    compute_ean13_dv,
    generate_toy_name_and_description,
    generate_valid_ean13,
    validate_ean13,
)
from src.etl.scenarios.c1_toys_templates import (
    DEFAULT_BRANCH_ID,
    DEFAULT_GLOBAL_SEED,
    FAMILY_PRICE_MULTIPLIERS,
    FORBIDDEN_BEVERAGE_TERMS,
    TOY_BRANDS,
    TOY_TEMPLATES,
)
from src.etl.silver.enrich import (
    generate_customers,
    generate_geography,
    generate_sales_reps,
)
from src.etl.silver.reference import (
    build_category_case_when_sql,
    compile_category_rules,
    load_category_map,
)

logger = get_logger(__name__)

SCENARIO_ID: Final[ScenarioId] = "c1_toys"

__all__ = [
    "DEFAULT_BRANCH_ID",
    "DEFAULT_GLOBAL_SEED",
    "FAMILY_PRICE_MULTIPLIERS",
    "FORBIDDEN_BEVERAGE_TERMS",
    "SCENARIO_ID",
    "TOY_BRANDS",
    "TOY_TEMPLATES",
    "C1ToysScenarioBuilder",
    "build_c1_dim_product",
    "compute_ean13_dv",
    "generate_toy_name_and_description",
    "generate_valid_ean13",
    "validate_ean13",
]


class C1ToysScenarioBuilder(ScenarioBuilder):
    """Builder do Cenário 1 — Indústria B2B Nacional de Brinquedos (Caso Âncora).

    Materializa no DuckDB e em Parquet:
    - `c1_toys.dim_product` (e view `gold.dim_product` se aplicável)
    - `c1_toys.sales_remapped` (vendas remapeadas prontas para o motor de waterfall)
    """

    def __init__(
        self,
        config: ScenarioConfig | None = None,
        duckdb_path: Path | None = None,
        global_seed: int = DEFAULT_GLOBAL_SEED,
    ) -> None:
        cfg = config or load_scenario_config(SCENARIO_ID)
        super().__init__(config=cfg, duckdb_path=duckdb_path)
        self.global_seed = global_seed

    def _ensure_silver_sales(self, con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
        """Garante que a tabela silver.sales existe no DuckDB e retorna seus registros."""
        has_silver = False
        try:
            tables = con.execute("SHOW TABLES FROM silver").fetchall()
            if any(t[0] == "sales" for t in tables):
                has_silver = True
        except Exception:
            has_silver = False

        if has_silver:
            return con.execute("SELECT * FROM silver.sales").df()

        sample_path = get_data_dir().parent / "tests" / "fixtures" / "iowa_sample.parquet"
        if not sample_path.exists():
            generate_fixture(output_path=sample_path)

        sample_sql_p = str(sample_path).replace("\\", "/")
        con.execute("CREATE SCHEMA IF NOT EXISTS silver")
        con.execute(
            f"""
            CREATE OR REPLACE TABLE silver.sales AS
            SELECT
                invoice_and_item_number AS invoice_line_id,
                date::DATE AS date,
                store_number,
                store_name,
                city,
                county,
                zip_code,
                category_name,
                vendor_name,
                item_number,
                item_description,
                pack::INTEGER AS pack,
                state_bottle_cost::DOUBLE AS unit_cost,
                state_bottle_retail::DOUBLE AS unit_price,
                bottles_sold::INTEGER AS units,
                sale_dollars::DOUBLE AS sale_amount
            FROM read_parquet('{sample_sql_p}')
            """
        )
        return con.execute("SELECT * FROM silver.sales").df()

    def _ensure_silver_customers(self, con: duckdb.DuckDBPyConnection) -> None:
        """Garante que a tabela silver.dim_customer existe no DuckDB para enriquecimento."""
        has_customers = False
        try:
            cust_tables = con.execute("SHOW TABLES FROM silver").fetchall()
            if any(t[0] == "dim_customer" for t in cust_tables):
                has_customers = True
        except Exception:
            has_customers = False

        if not has_customers:
            stores_df = con.execute(
                """
                SELECT
                    store_number,
                    FIRST(county) AS county,
                    SUM(sale_amount) AS revenue
                FROM silver.sales
                GROUP BY store_number
                """
            ).df()
            reps_df = generate_sales_reps(global_seed=self.global_seed)
            geo_df = generate_geography()
            cust_df = generate_customers(stores_df, geo_df, reps_df, global_seed=self.global_seed)

            con.register("temp_dim_cust", cust_df)
            con.execute("CREATE OR REPLACE TABLE silver.dim_customer AS SELECT * FROM temp_dim_cust")
            con.register("temp_dim_rep", reps_df)
            con.execute("CREATE OR REPLACE TABLE silver.dim_sales_rep AS SELECT * FROM temp_dim_rep")
            con.register("temp_dim_geo", geo_df)
            con.execute("CREATE OR REPLACE TABLE silver.dim_geography AS SELECT * FROM temp_dim_geo")

    def build(self, con: duckdb.DuckDBPyConnection) -> dict[str, int]:
        """Executa a transformação semântica do Caso Âncora no DuckDB.

        Args:
            con: Conexão ativa com o banco DuckDB.

        Returns:
            Dicionário com a contagem de registros em cada tabela gerada.
        """
        logger.info("Iniciando build do Cenário 1 (%s)...", self.config.display_name)

        cat_map_df = load_category_map(self.config.id)
        silver_df = self._ensure_silver_sales(con)

        df_product = build_c1_dim_product(
            silver_sales_df=silver_df,
            category_map_df=cat_map_df,
            global_seed=self.global_seed,
        )

        con.execute("CREATE SCHEMA IF NOT EXISTS c1_toys")
        con.execute("CREATE SCHEMA IF NOT EXISTS gold")
        con.register("temp_c1_dim_product", df_product)
        con.execute("CREATE OR REPLACE TABLE c1_toys.dim_product AS SELECT * FROM temp_c1_dim_product")
        con.execute("CREATE OR REPLACE TABLE gold.dim_product AS SELECT * FROM temp_c1_dim_product")

        rules = compile_category_rules(cat_map_df)
        case_sql = build_category_case_when_sql(rules, "s.category_name")
        self._ensure_silver_customers(con)

        silver_cols = {str(r[1]) for r in con.execute("PRAGMA table_info('silver.sales')").fetchall()}
        has_price_events = "original_unit_price" in silver_cols and "promo_flag" in silver_cols
        unit_price_expr = (
            "ROUND(p.base_unit_price * (CASE WHEN COALESCE(s.original_unit_price, 0.0) > 0.0 "
            "THEN s.unit_price / s.original_unit_price ELSE 1.0 END), 2)"
            if has_price_events
            else "p.base_unit_price"
        )
        promo_expr = "COALESCE(s.promo_flag, FALSE)" if has_price_events else "FALSE"

        remapped_query = f"""
        CREATE OR REPLACE TABLE c1_toys.sales_remapped AS
        SELECT
            s.invoice_line_id,
            s.invoice_line_id AS order_id,
            s.date,
            CAST(strftime(s.date, '%Y%m%d') AS INTEGER) AS date_key,
            s.store_number,
            COALESCE(c.customer_id, 'CLI-' || s.store_number) AS customer_id,
            COALESCE(c.sales_rep_id, 'RCA-001') AS sales_rep_id,
            '{DEFAULT_BRANCH_ID}' AS branch_id,
            p.product_id,
            p.product_name,
            p.brand_name,
            {case_sql} AS family,
            s.pack,
            s.units,
            ROUND(CAST(s.units AS DOUBLE) / CAST(s.pack AS DOUBLE), 2) AS boxes,
            {unit_price_expr} AS unit_list_price,
            p.base_unit_cost AS unit_cost,
            ROUND(s.units * ({unit_price_expr}), 2) AS gross_revenue,
            ROUND(s.units * p.base_unit_cost, 2) AS cogs,
            {promo_expr} AS promo_flag
        FROM silver.sales s
        JOIN c1_toys.dim_product p ON s.item_number = p.item_number
        LEFT JOIN silver.dim_customer c ON s.store_number = c.store_number
        """
        con.execute(remapped_query)

        snapshot_dir = (
            (self.duckdb_path.parent / "gold" / "snapshot" / SCENARIO_ID)
            if self.duckdb_path
            else (get_data_dir() / "gold" / "snapshot" / SCENARIO_ID)
        )
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        product_parquet = snapshot_dir / "dim_product.parquet"
        sales_parquet = snapshot_dir / "sales_remapped.parquet"

        con.execute(
            f"COPY c1_toys.dim_product TO '{product_parquet.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)"
        )
        con.execute(
            f"COPY c1_toys.sales_remapped TO '{sales_parquet.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)"
        )

        n_products = len(df_product)
        res_sales = con.execute("SELECT COUNT(*) FROM c1_toys.sales_remapped").fetchone()
        n_sales = int(res_sales[0]) if res_sales else 0

        logger.info(
            "Build do Cenário C1 concluído: %d produtos e %d transações remapeadas.",
            n_products,
            n_sales,
        )

        return {
            "dim_product": n_products,
            "sales_remapped": n_sales,
        }
