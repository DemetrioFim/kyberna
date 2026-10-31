from __future__ import annotations

import hashlib
import random
from pathlib import Path
from typing import Final, cast

import duckdb
import pandas as pd
from faker import Faker

from src.core.logging import get_logger
from src.core.paths import get_data_dir
from src.etl.contracts import (
    SilverCustomerSchema,
    SilverGeographySchema,
    SilverSalesRepSchema,
    validate_contract,
)
from src.etl.ingest.fixture import generate_fixture
from src.etl.silver.reference import load_municipios

logger = get_logger(__name__)

# ==============================================================================
# Mapeamento Oficial de DDDs por UF (ANATEL)
# ==============================================================================

UF_DDDS: Final[dict[str, list[int]]] = {
    "SP": [11, 12, 13, 14, 15, 16, 17, 18, 19],
    "RJ": [21, 22, 24],
    "ES": [27, 28],
    "MG": [31, 32, 33, 34, 35, 37, 38],
    "PR": [41, 42, 43, 44, 45, 46],
    "SC": [47, 48, 49],
    "RS": [51, 53, 54, 55],
    "DF": [61],
    "GO": [62, 64],
    "TO": [63],
    "MT": [65, 66],
    "MS": [67],
    "AC": [68],
    "RO": [69],
    "BA": [71, 73, 74, 75, 77],
    "SE": [79],
    "PE": [81, 87],
    "AL": [82],
    "PB": [83],
    "RN": [84],
    "CE": [85, 88],
    "PI": [86, 89],
    "MA": [98, 99],
    "PA": [91, 93, 94],
    "AP": [96],
    "AM": [92, 97],
    "RR": [95],
}

RETAIL_SEGMENTS: Final[list[str]] = [
    "Papelaria e Bazar",
    "Loja de Brinquedos",
    "Magazine e Variedades",
    "Livraria e Papelaria",
    "Atacadista Regional",
    "Supermercado Regional",
]

DEFAULT_NUM_REPS: Final[int] = 30
DEFAULT_GLOBAL_SEED: Final[int] = 42


# ==============================================================================
# Funções de Módulo 11 e Geração de CNPJ Válido
# ==============================================================================


def compute_cnpj_dv(digits: list[int]) -> tuple[int, int]:
    """Calcula os dois dígitos verificadores (DVs) de um CNPJ brasileiro pelo algoritmo Módulo 11.

    Args:
        digits: Lista contendo os 12 primeiros dígitos numéricos do CNPJ.

    Returns:
        Tupla (dv1, dv2) correspondente aos dois dígitos verificadores.
    """
    weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    s1 = sum(d * w for d, w in zip(digits[:12], weights1, strict=False))
    r1 = s1 % 11
    dv1 = 0 if r1 < 2 else 11 - r1

    weights2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    first13 = [*digits[:12], dv1]
    s2 = sum(d * w for d, w in zip(first13, weights2, strict=False))
    r2 = s2 % 11
    dv2 = 0 if r2 < 2 else 11 - r2

    return dv1, dv2


def generate_valid_cnpj(seed_key: str | int, formatted: bool = True) -> str:
    """Gera um número de CNPJ brasileiro 100% válido determinístico a partir de uma semente.

    Args:
        seed_key: Semente determinística (número ou string).
        formatted: Se True, retorna 'XX.XXX.XXX/0001-YY'; se False, 14 dígitos 'XXXXXXXX0001YY'.

    Returns:
        String contendo o CNPJ válido formatado ou numérico.
    """
    seed_int = (
        int(hashlib.sha256(str(seed_key).encode()).hexdigest()[:12], 16)
        if isinstance(seed_key, str)
        else int(seed_key)
    )
    rng = random.Random(seed_int)

    # 8 dígitos aleatórios para o número de inscrição base
    base_digits = [rng.randint(0, 9) for _ in range(8)]
    # Evita que todos os dígitos sejam iguais
    if len(set(base_digits)) == 1:
        base_digits[0] = (base_digits[0] + 1) % 10

    branch_digits = [0, 0, 0, 1]  # Matriz
    first12 = base_digits + branch_digits
    dv1, dv2 = compute_cnpj_dv(first12)
    all14 = [*first12, dv1, dv2]

    digits_str = "".join(str(d) for d in all14)
    if formatted:
        return f"{digits_str[0:2]}.{digits_str[2:5]}.{digits_str[5:8]}/{digits_str[8:12]}-{digits_str[12:14]}"
    return digits_str


def validate_cnpj(cnpj: str) -> bool:
    """Valida se uma string representa um CNPJ brasileiro válido via cálculo de dígitos verificadores.

    Args:
        cnpj: String com CNPJ formatado ou apenas numérico.

    Returns:
        True se o CNPJ for válido e seus DVs conferirem; False caso contrário.
    """
    clean_digits = [int(c) for c in str(cnpj) if c.isdigit()]
    if len(clean_digits) != 14:
        return False
    if len(set(clean_digits)) == 1:
        return False

    dv1, dv2 = compute_cnpj_dv(clean_digits[:12])
    return clean_digits[12] == dv1 and clean_digits[13] == dv2


# ==============================================================================
# Geradores das Dimensões Sintéticas (RCAs, Geografia e Clientes)
# ==============================================================================


def generate_sales_reps(
    num_reps: int = DEFAULT_NUM_REPS,
    global_seed: int = DEFAULT_GLOBAL_SEED,
) -> pd.DataFrame:
    """Gera a dimensão sintética de Representantes Comerciais Autônomos (RCAs).

    Distribui os RCAs pelas 5 macrorregiões brasileiras com nomes gerados via Faker pt_BR
    e taxas de comissão entre 3,0% e 7,0%.

    Args:
        num_reps: Quantidade total de representantes a gerar (padrão: 30).
        global_seed: Semente global para determinismo estrito.

    Returns:
        pd.DataFrame validado contra `SilverSalesRepSchema`.
    """
    regions_quota = {
        "Sudeste": max(1, int(num_reps * 0.35)),
        "Sul": max(1, int(num_reps * 0.25)),
        "Nordeste": max(1, int(num_reps * 0.20)),
        "Centro-Oeste": max(1, int(num_reps * 0.12)),
        "Norte": max(1, int(num_reps * 0.08)),
    }
    # Ajusta eventual diferença de arredondamento no Sudeste
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
            # Comissão entre 3,5% e 6,5% em passos de 0,5%
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


def generate_geography(municipios_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Padroniza a tabela de municípios de referência na dimensão canônica de geografia brasileira.

    Args:
        municipios_df: DataFrame opcional retornado por `load_municipios()`.

    Returns:
        pd.DataFrame padronizado e validado contra `SilverGeographySchema`.
    """
    df = municipios_df if municipios_df is not None else load_municipios()
    df_geo = df.rename(columns={"nome": "city", "uf": "state", "regiao": "region"})[
        [
            "codigo_ibge",
            "city",
            "state",
            "region",
            "latitude",
            "longitude",
            "populacao",
            "capital",
        ]
    ].copy()

    df_geo["codigo_ibge"] = df_geo["codigo_ibge"].astype("int64")
    df_geo["populacao"] = df_geo["populacao"].astype("int64")
    df_geo["latitude"] = df_geo["latitude"].astype("float64")
    df_geo["longitude"] = df_geo["longitude"].astype("float64")
    df_geo["capital"] = df_geo["capital"].astype("boolean")

    return validate_contract(df_geo, SilverGeographySchema, layer="Silver (dim_geography)")


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
    # Semente estritamente derivada de store_number + global_seed
    store_seed = int(hashlib.sha256(f"{global_seed}:store:{store_num}".encode()).hexdigest()[:12], 16)
    rng = random.Random(store_seed)
    faker.seed_instance(store_seed)

    # 1. Atribuição geográfica de município
    county_seed = int(hashlib.sha256(f"{global_seed}:county:{county}".encode()).hexdigest()[:8], 16)
    mun_idx = (county_seed + (store_seed % 17)) % len(geography_records)
    mun = geography_records[mun_idx]

    city = str(mun["city"])
    state = str(mun["state"])
    region = str(mun["region"])

    # 2. Atribuição de RCA coerente com a região
    candidate_reps = reps_by_region.get(region, default_reps)
    sales_rep_id = candidate_reps[store_seed % len(candidate_reps)]

    # 3. CNPJ 100% válido com DVs
    cnpj = generate_valid_cnpj(store_seed, formatted=True)

    # 4. Porte ('P', 'M', 'G')
    if rev > q80:
        size = "G"
    elif rev > q40:
        size = "M"
    else:
        size = "P"

    # 5. Segmento comercial B2B
    segment = RETAIL_SEGMENTS[store_seed % len(RETAIL_SEGMENTS)]

    # 6. Razão Social e Nome Fantasia em português
    base_company = faker.company()
    suffix = rng.choice(["Ltda.", "S.A.", "- ME", "- EPP"])
    company_name = f"{base_company} {suffix}".strip()
    trade_name = f"{segment.split()[0]} {faker.first_name()} & {faker.last_name()}".strip()

    # 7. WhatsApp com DDD compatível com o Estado
    valid_ddds = UF_DDDS.get(state, [11])
    ddd = rng.choice(valid_ddds)
    phone_part1 = rng.randint(91000, 99999)
    phone_part2 = rng.randint(1000, 9999)
    whatsapp = f"+55 {ddd} {phone_part1}-{phone_part2}"

    # 8. E-mail de compras corporativo
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
    """Gera a dimensão sintética de clientes (lojistas / CNPJs) a partir de lojas de vendas reais.

    Garante determinismo absoluto por chave natural:
    - CNPJ 100% válido com DVs;
    - 1 município brasileiro atribuído por loja (ponderado pela relevância do condado/população);
    - 1 RCA responsável alinhado à região geográfica do cliente;
    - DDD do WhatsApp compatível com a UF do cliente;
    - Porte ('P', 'M', 'G') derivado do faturamento acumulado.

    Args:
        stores_df: DataFrame contendo ao menos a coluna `store_number` (e opcionalmente `county`, `revenue`).
        geography_df: Dimensão de geografia brasileira gerada por `generate_geography()`.
        sales_reps_df: Dimensão de RCAs gerada por `generate_sales_reps()`.
        global_seed: Semente pseudo-aleatória determinística.

    Returns:
        pd.DataFrame validado contra `SilverCustomerSchema`.
    """
    if "store_number" not in stores_df.columns:
        raise ValueError("DataFrame de lojas deve conter a coluna 'store_number'.")

    # Garante lojas únicas ordenadas para consistência
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

    # Classificação de porte (P/M/G) baseada em percentis de receita
    q40 = float(stores_summary["total_revenue"].quantile(0.40))
    q80 = float(stores_summary["total_revenue"].quantile(0.80))

    # Agrupa RCAs e municípios por região para matching instantâneo
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


# ==============================================================================
# Pipeline Orquestrador e Registro no DuckDB / Parquet
# ==============================================================================


def enrich_silver_dimensions(
    duckdb_path: Path | None = None,
    silver_dir: Path | None = None,
    global_seed: int = DEFAULT_GLOBAL_SEED,
) -> dict[str, int]:
    """Orquestra a criação, validação e persistência das dimensões enriquecidas na camada Silver.

    Gera e salva em Parquet e no DuckDB local:
    - `silver.dim_sales_rep`
    - `silver.dim_geography`
    - `silver.dim_customer`

    Args:
        duckdb_path: Caminho opcional do arquivo `kyberna.duckdb`.
        silver_dir: Diretório de saída opcional para os arquivos Parquet.
        global_seed: Semente pseudo-aleatória determinística.

    Returns:
        Dicionário com a contagem de registros gerados por dimensão.
    """
    db_file = duckdb_path or (get_data_dir() / "kyberna.duckdb")
    target_silver = silver_dir or (get_data_dir() / "silver")
    target_silver.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(db_file))

    # 1. Recupera as lojas e condados existentes a partir de silver.sales
    # Se a tabela não existir, faz fallback para a fixture iowa_sample.parquet
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

    # 2. Gera dimensões sintéticas
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

    # 3. Exporta arquivos Parquet em data/silver/
    path_sales_rep = target_silver / "dim_sales_rep.parquet"
    path_geography = target_silver / "dim_geography.parquet"
    path_customer = target_silver / "dim_customer.parquet"

    df_sales_rep.to_parquet(path_sales_rep, index=False, compression="zstd")
    df_geography.to_parquet(path_geography, index=False, compression="zstd")
    df_customer.to_parquet(path_customer, index=False, compression="zstd")

    # 4. Registra no schema silver do DuckDB
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
