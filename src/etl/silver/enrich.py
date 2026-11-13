from __future__ import annotations

import hashlib
import random
from pathlib import Path
from typing import cast

import duckdb
import pandas as pd
from faker import Faker

from src.core.logging import get_logger
from src.core.paths import get_data_dir
from src.etl.contracts import (
    SilverCustomerSchema,
    SilverSalesRepSchema,
    validate_contract,
)
from src.etl.ingest.fixture import generate_fixture
from src.etl.silver.cnpj import (
    DEFAULT_GLOBAL_SEED,
    DEFAULT_NUM_REPS,
    RETAIL_SEGMENTS,
    UF_DDDS,
    compute_cnpj_dv,
    generate_geography,
    generate_valid_cnpj,
    validate_cnpj,
)

logger = get_logger(__name__)

__all__ = [
    "DEFAULT_GLOBAL_SEED",
    "DEFAULT_NUM_REPS",
    "RETAIL_SEGMENTS",
    "UF_DDDS",
    "compute_cnpj_dv",
    "enrich_silver_dimensions",
    "generate_customers",
    "generate_geography",
    "generate_sales_reps",
    "generate_valid_cnpj",
    "validate_cnpj",
]


def generate_sales_reps(
    num_reps: int = DEFAULT_NUM_REPS,
    global_seed: int = DEFAULT_GLOBAL_SEED,
) -> pd.DataFrame:
    """Gera a dimensão sintética de Representantes Comerciais Autônomos (RCAs)."""
    regions_quota = {
        "Sudeste": max(1, int(num_reps * 0.35)),
        "Sul": max(1, int(num_reps * 0.25)),
        "Nordeste": max(1, int(num_reps * 0.20)),
        "Centro-Oeste": max(1, int(num_reps * 0.12)),
        "Norte": max(1, int(num_reps * 0.08)),
    }
    diff = num_reps - sum(regions_quota.values())
    regions_quota["Sudeste"] += diff

    records: list[dict[str, object]] = []
    rep_idx = 1
    faker = Faker("pt_BR")

    for region, count in regions_quota.items():
        for _ in range(count):
            rep_seed = int(hashlib.sha256(f"{global_seed}:rep:{rep_idx}".encode()).hexdigest()[:12], 16)
            faker.seed_instance(rep_seed)
            rng = random.Random(rep_seed)

            sales_rep_id = f"RCA-{rep_idx:03d}"
            name = faker.name()
            commission_rate = round(rng.choice([0.035, 0.040, 0.045, 0.050, 0.055, 0.060, 0.065]), 4)

            records.append(
                {
                    "sales_rep_id": sales_rep_id,
                    "name": name,
                    "region": region,
                    "commission_rate": commission_rate,
                }
            )
            rep_idx += 1

    df_reps = pd.DataFrame(records)
    return validate_contract(df_reps, SilverSalesRepSchema, layer="Silver (dim_sales_rep)")


def _generate_single_customer_record(
    store_num: str,
    *,
    county: str,
    rev: float,
    q40: float,
    q80: float,
    geography_records: list[dict[str, object]],
    reps_by_region: dict[str, list[str]],
    default_reps: list[str],
    global_seed: int,
    faker: Faker,
) -> dict[str, object]:
    """Gera um único registro de cliente de forma determinística."""
    store_seed = int(hashlib.sha256(f"{global_seed}:store:{store_num}".encode()).hexdigest()[:12], 16)
    rng = random.Random(store_seed)
    faker.seed_instance(store_seed)

    county_seed = int(hashlib.sha256(f"{global_seed}:county:{county}".encode()).hexdigest()[:8], 16)
    mun_idx = (county_seed + (store_seed % 17)) % len(geography_records)
    mun = geography_records[mun_idx]

    city = str(mun["city"])
    state = str(mun["state"])
    region = str(mun["region"])

    candidate_reps = reps_by_region.get(region, default_reps)
    sales_rep_id = candidate_reps[store_seed % len(candidate_reps)]
    cnpj = generate_valid_cnpj(store_seed, formatted=True)

    if rev > q80:
        size = "G"
    elif rev > q40:
        size = "M"
    else:
        size = "P"

    segment = RETAIL_SEGMENTS[store_seed % len(RETAIL_SEGMENTS)]
    base_company = faker.company()
    suffix = rng.choice(["Ltda.", "S.A.", "- ME", "- EPP"])
    company_name = f"{base_company} {suffix}".strip()
    trade_name = f"{segment.split()[0]} {faker.first_name()} & {faker.last_name()}".strip()

    valid_ddds = UF_DDDS.get(state, [11])
    ddd = rng.choice(valid_ddds)
    phone_part1 = rng.randint(91000, 99999)
    phone_part2 = rng.randint(1000, 9999)
    whatsapp = f"+55 {ddd} {phone_part1}-{phone_part2}"

    slug = "".join(c for c in trade_name.lower() if c.isalnum() or c == " ").replace(" ", "")[:15]
    email = f"compras@{slug}.com.br"
    customer_id = f"CLI-{int(store_num):04d}" if store_num.isdigit() else f"CLI-{store_num}"

    return {
        "customer_id": customer_id,
        "store_number": store_num,
        "cnpj": cnpj,
        "company_name": company_name,
        "trade_name": trade_name,
        "segment": segment,
        "size": size,
        "city": city,
        "state": state,
        "region": region,
        "sales_rep_id": sales_rep_id,
        "whatsapp": whatsapp,
        "email": email,
    }


def generate_customers(
    stores_df: pd.DataFrame,
    geography_df: pd.DataFrame,
    sales_reps_df: pd.DataFrame,
    global_seed: int = DEFAULT_GLOBAL_SEED,
) -> pd.DataFrame:
    """Gera a dimensão sintética de clientes (lojistas / CNPJs) a partir de lojas de vendas reais."""
    if "store_number" not in stores_df.columns:
        raise ValueError("DataFrame de lojas deve conter a coluna 'store_number'.")

    unique_stores = (
        stores_df[["store_number", "county", "revenue"]]
        if {"county", "revenue"}.issubset(stores_df.columns)
        else stores_df[["store_number"]].drop_duplicates()
    )

    if "revenue" in unique_stores.columns:
        stores_summary = (
            unique_stores.groupby("store_number")
            .agg(
                county=("county", "first"),
                total_revenue=("revenue", "sum"),
            )
            .reset_index()
        )
    else:
        stores_summary = unique_stores.drop_duplicates(subset=["store_number"]).copy()
        stores_summary["county"] = stores_summary["county"] if "county" in stores_summary.columns else "Polk"
        stores_summary["total_revenue"] = 10000.0

    stores_summary = stores_summary.sort_values("store_number").reset_index(drop=True)
    q40 = float(stores_summary["total_revenue"].quantile(0.40))
    q80 = float(stores_summary["total_revenue"].quantile(0.80))

    reps_by_region: dict[str, list[str]] = {
        r: sales_reps_df[sales_reps_df["region"] == r]["sales_rep_id"].tolist()
        for r in sales_reps_df["region"].unique()
    }
    geography_records = cast(list[dict[str, object]], geography_df.to_dict(orient="records"))
    default_reps = sales_reps_df["sales_rep_id"].tolist()

    records: list[dict[str, object]] = []
    faker = Faker("pt_BR")

    for _, row in stores_summary.iterrows():
        store_num = str(row["store_number"]).strip()
        county = str(row["county"]).strip()
        rev = float(row["total_revenue"])

        rec = _generate_single_customer_record(
            store_num=store_num,
            county=county,
            rev=rev,
            q40=q40,
            q80=q80,
            geography_records=geography_records,
            reps_by_region=reps_by_region,
            default_reps=default_reps,
            global_seed=global_seed,
            faker=faker,
        )
        records.append(rec)

    df_customers = pd.DataFrame(records)
    return validate_contract(df_customers, SilverCustomerSchema, layer="Silver (dim_customer)")


def enrich_silver_dimensions(
    duckdb_path: Path | None = None,
    silver_dir: Path | None = None,
    global_seed: int = DEFAULT_GLOBAL_SEED,
) -> dict[str, int]:
    """Orquestra a criação, validação e persistência das dimensões enriquecidas na camada Silver."""
    db_file = duckdb_path or (get_data_dir() / "kyberna.duckdb")
    target_silver = silver_dir or (get_data_dir() / "silver")
    target_silver.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(db_file))

    has_silver = False
    try:
        tables = con.execute("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]
        if "sales" in table_names:
            has_silver = True
    except Exception:
        has_silver = False

    if has_silver:
        logger.info("Lendo lojas a partir da tabela silver.sales no DuckDB...")
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
    else:
        sample_path = get_data_dir().parent / "tests" / "fixtures" / "iowa_sample.parquet"
        if not sample_path.exists():
            generate_fixture(output_path=sample_path)
        logger.info("Lendo lojas a partir da fixture sintética %s...", sample_path)
        sample_sql_path = str(sample_path).replace("\\", "/")
        stores_df = con.execute(
            f"""
            SELECT
                store_number,
                FIRST(county) AS county,
                SUM(sale_dollars::DOUBLE) AS revenue
            FROM read_parquet('{sample_sql_path}')
            GROUP BY store_number
            """
        ).df()

    logger.info("Gerando dimensão de representantes comerciais (RCAs)...")
    df_sales_rep = generate_sales_reps(num_reps=DEFAULT_NUM_REPS, global_seed=global_seed)

    logger.info("Gerando dimensão de geografia brasileira...")
    df_geography = generate_geography()

    logger.info("Gerando dimensão sintética de clientes (lojistas)...")
    df_customer = generate_customers(
        stores_df=stores_df,
        geography_df=df_geography,
        sales_reps_df=df_sales_rep,
        global_seed=global_seed,
    )

    path_sales_rep = target_silver / "dim_sales_rep.parquet"
    path_geography = target_silver / "dim_geography.parquet"
    path_customer = target_silver / "dim_customer.parquet"

    df_sales_rep.to_parquet(path_sales_rep, index=False, compression="zstd")
    df_geography.to_parquet(path_geography, index=False, compression="zstd")
    df_customer.to_parquet(path_customer, index=False, compression="zstd")

    con.execute("CREATE SCHEMA IF NOT EXISTS silver")
    con.register("df_sales_rep_mem", df_sales_rep)
    con.register("df_geography_mem", df_geography)
    con.register("df_customer_mem", df_customer)

    con.execute("CREATE OR REPLACE TABLE silver.dim_sales_rep AS SELECT * FROM df_sales_rep_mem")
    con.execute("CREATE OR REPLACE TABLE silver.dim_geography AS SELECT * FROM df_geography_mem")
    con.execute("CREATE OR REPLACE TABLE silver.dim_customer AS SELECT * FROM df_customer_mem")

    con.close()

    result = {
        "sales_reps": len(df_sales_rep),
        "geography": len(df_geography),
        "customers": len(df_customer),
    }
    logger.info("Dimensões da camada Silver enriquecidas com sucesso: %s", result)
    return result
