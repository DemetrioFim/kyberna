from __future__ import annotations

from typing import Final

import duckdb

from src.core.logging import get_logger
from src.core.paths import get_data_dir
from src.core.types import ScenarioId
from src.etl.finance.margin_waterfall import compute_margin_waterfall

logger = get_logger(__name__)

DEFAULT_SCENARIO: Final[ScenarioId] = "c1_toys"
DATE_START: Final[str] = "2022-01-01"
DATE_END: Final[str] = "2026-12-31"


def build_dim_date(
    con: duckdb.DuckDBPyConnection,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
    start_date: str = DATE_START,
    end_date: str = DATE_END,
) -> int:
    """Gera a dimensão de calendário brasileira dim_date no DuckDB.

    Atributos incluem chave inteira date_key (YYYYMMDD), data completa, ano, trimestre,
    mês, nome do mês em português, dia, dia da semana (0=Dom a 6=Sáb), nome do dia
    e flag is_weekend.

    Args:
        con: Conexão ativa com o DuckDB.
        scenario_id: Identificador do cenário.
        start_date: Data de início do calendário (ISO YYYY-MM-DD).
        end_date: Data de término do calendário (ISO YYYY-MM-DD).

    Returns:
        Número de dias gerados na dimensão.
    """
    logger.info("Gerando dimensão dim_date no DuckDB (%s a %s)...", start_date, end_date)

    con.execute("CREATE SCHEMA IF NOT EXISTS gold")
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {scenario_id}")

    dim_date_sql = f"""
    CREATE OR REPLACE TABLE gold.dim_date AS
    SELECT
        CAST(strftime(d, '%Y%m%d') AS INTEGER) AS date_key,
        CAST(d AS DATE) AS full_date,
        YEAR(d) AS year,
        QUARTER(d) AS quarter,
        MONTH(d) AS month,
        CASE MONTH(d)
            WHEN 1 THEN 'Janeiro'
            WHEN 2 THEN 'Fevereiro'
            WHEN 3 THEN 'Março'
            WHEN 4 THEN 'Abril'
            WHEN 5 THEN 'Maio'
            WHEN 6 THEN 'Junho'
            WHEN 7 THEN 'Julho'
            WHEN 8 THEN 'Agosto'
            WHEN 9 THEN 'Setembro'
            WHEN 10 THEN 'Outubro'
            WHEN 11 THEN 'Novembro'
            WHEN 12 THEN 'Dezembro'
        END AS month_name,
        DAY(d) AS day,
        DAYOFWEEK(d) AS day_of_week,
        CASE DAYOFWEEK(d)
            WHEN 0 THEN 'Domingo'
            WHEN 1 THEN 'Segunda-feira'
            WHEN 2 THEN 'Terça-feira'
            WHEN 3 THEN 'Quarta-feira'
            WHEN 4 THEN 'Quinta-feira'
            WHEN 5 THEN 'Sexta-feira'
            WHEN 6 THEN 'Sábado'
        END AS day_name,
        CASE WHEN DAYOFWEEK(d) IN (0, 6) THEN TRUE ELSE FALSE END AS is_weekend,
        strftime(d, '%Y-%m') AS year_month
    FROM generate_series(DATE '{start_date}', DATE '{end_date}', INTERVAL 1 DAY) t(d)
    ORDER BY date_key
    """
    con.execute(dim_date_sql)
    con.execute(f"CREATE OR REPLACE TABLE {scenario_id}.dim_date AS SELECT * FROM gold.dim_date")

    row = con.execute("SELECT COUNT(*) FROM gold.dim_date").fetchone()
    count = int(row[0]) if row else 0
    logger.info("Dimensão dim_date criada com %d registros.", count)
    return count


def build_dim_branch(
    con: duckdb.DuckDBPyConnection,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
) -> int:
    """Materializa a dimensão de filiais/fábricas dim_branch no DuckDB.

    Para o Cenário 1 (Indústria B2B de Brinquedos), a matriz fabril é FAB-SP01
    localizada em São Paulo - SP.

    Args:
        con: Conexão ativa com o DuckDB.
        scenario_id: Identificador do cenário.

    Returns:
        Número de filiais/fábricas cadastradas.
    """
    logger.info("Materializando dimensão dim_branch para cenário '%s'...", scenario_id)

    con.execute("CREATE SCHEMA IF NOT EXISTS gold")
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {scenario_id}")

    if scenario_id in ("c1_toys", "c1"):
        branch_sql = """
        CREATE OR REPLACE TABLE gold.dim_branch AS
        SELECT
            'FAB-SP01' AS branch_id,
            'Fábrica Matriz São Paulo' AS branch_name,
            'Fábrica' AS branch_type,
            'São Paulo' AS city,
            'SP' AS state,
            'Sudeste' AS region,
            3550308 AS codigo_ibge,
            -23.5505 AS latitude,
            -46.6333 AS longitude
        """
    else:
        # Padrão para outros cenários (pode ser sobrescrito pelos builders de C2, C3, C4)
        branch_sql = """
        CREATE OR REPLACE TABLE gold.dim_branch AS
        SELECT
            'MATRIZ-01' AS branch_id,
            'Centro de Distribuição Matriz' AS branch_name,
            'CD' AS branch_type,
            'São Paulo' AS city,
            'SP' AS state,
            'Sudeste' AS region,
            3550308 AS codigo_ibge,
            -23.5505 AS latitude,
            -46.6333 AS longitude
        """

    con.execute(branch_sql)
    con.execute(f"CREATE OR REPLACE TABLE {scenario_id}.dim_branch AS SELECT * FROM gold.dim_branch")

    row = con.execute("SELECT COUNT(*) FROM gold.dim_branch").fetchone()
    count = int(row[0]) if row else 0
    return count


def sync_gold_dimensions(
    con: duckdb.DuckDBPyConnection,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
) -> dict[str, int]:
    """Sincroniza as dimensões Silver e de Cenário para o schema gold unificado.

    Tabelas sincronizadas:
    - gold.dim_customer (a partir de silver.dim_customer)
    - gold.dim_sales_rep (a partir de silver.dim_sales_rep)
    - gold.dim_geography (a partir de silver.dim_geography)
    - gold.dim_product (a partir de <scenario_id>.dim_product)

    Args:
        con: Conexão ativa com o DuckDB.
        scenario_id: Identificador do cenário.

    Returns:
        Dicionário com contagens de linhas de cada dimensão.
    """
    logger.info("Sincronizando dimensões analíticas no schema gold...")

    con.execute("CREATE SCHEMA IF NOT EXISTS gold")
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {scenario_id}")

    counts: dict[str, int] = {}

    # 1. Clientes
    con.execute("CREATE OR REPLACE TABLE gold.dim_customer AS SELECT * FROM silver.dim_customer")
    con.execute(f"CREATE OR REPLACE TABLE {scenario_id}.dim_customer AS SELECT * FROM gold.dim_customer")
    row_c = con.execute("SELECT COUNT(*) FROM gold.dim_customer").fetchone()
    counts["dim_customer"] = int(row_c[0]) if row_c else 0

    # 2. Representantes Comerciais (RCAs)
    con.execute("CREATE OR REPLACE TABLE gold.dim_sales_rep AS SELECT * FROM silver.dim_sales_rep")
    con.execute(f"CREATE OR REPLACE TABLE {scenario_id}.dim_sales_rep AS SELECT * FROM gold.dim_sales_rep")
    row_r = con.execute("SELECT COUNT(*) FROM gold.dim_sales_rep").fetchone()
    counts["dim_sales_rep"] = int(row_r[0]) if row_r else 0

    # 3. Geografia
    con.execute("CREATE OR REPLACE TABLE gold.dim_geography AS SELECT * FROM silver.dim_geography")
    con.execute(f"CREATE OR REPLACE TABLE {scenario_id}.dim_geography AS SELECT * FROM gold.dim_geography")
    row_g = con.execute("SELECT COUNT(*) FROM gold.dim_geography").fetchone()
    counts["dim_geography"] = int(row_g[0]) if row_g else 0

    # 4. Produtos do Cenário
    con.execute(f"CREATE OR REPLACE TABLE gold.dim_product AS SELECT * FROM {scenario_id}.dim_product")
    row_p = con.execute("SELECT COUNT(*) FROM gold.dim_product").fetchone()
    counts["dim_product"] = int(row_p[0]) if row_p else 0

    return counts


def export_gold_snapshots(
    con: duckdb.DuckDBPyConnection,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
) -> list[str]:
    """Exporta todas as tabelas do Star Schema Gold em formato Parquet comprimido (ZSTD).

    Salva em: `data/gold/snapshot/<scenario_id>/<tabela>.parquet`

    Args:
        con: Conexão ativa com o DuckDB.
        scenario_id: Identificador do cenário.

    Returns:
        Lista de nomes de arquivos Parquet exportados.
    """
    snapshot_dir = get_data_dir() / "gold" / "snapshot" / scenario_id
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    tables = [
        "dim_date",
        "dim_product",
        "dim_customer",
        "dim_sales_rep",
        "dim_branch",
        "dim_geography",
        "fact_sales",
    ]

    exported: list[str] = []
    for tbl in tables:
        parquet_p = snapshot_dir / f"{tbl}.parquet"
        con.execute(f"COPY gold.{tbl} TO '{parquet_p.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)")
        exported.append(tbl)
        logger.debug("Snapshot Parquet gerado: %s", parquet_p)

    logger.info("Snapshots Parquet exportados com sucesso em %s: %s", snapshot_dir, exported)
    return exported


def validate_star_schema_integrity(
    con: duckdb.DuckDBPyConnection,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
) -> dict[str, int | float]:
    """Valida a integridade referencial estrita e conservação de faturamento do Star Schema.

    Checagens executadas:
    1. Chaves órfãs de produto (fact_sales -> dim_product): 0
    2. Chaves órfãs de cliente (fact_sales -> dim_customer): 0
    3. Chaves órfãs de RCA (fact_sales -> dim_sales_rep): 0
    4. Chaves órfãs de filial (fact_sales -> dim_branch): 0
    5. Chaves órfãs de data (fact_sales -> dim_date): 0
    6. Conservação de faturamento bruto (Gold fact_sales vs Cenário sales_remapped): desvio < 0.01%

    Args:
        con: Conexão ativa com o DuckDB.
        scenario_id: Identificador do cenário.

    Returns:
        Dicionário com contagens de erros e valores comparados.

    Raises:
        AssertionError: Caso qualquer invariante de integridade falhe.
    """
    logger.info("Auditando integridade referencial do Star Schema Gold...")

    # 1. Integridade referencial
    ref_query = """
    SELECT
        COUNT(CASE WHEN p.product_id IS NULL THEN 1 END) AS orphan_products,
        COUNT(CASE WHEN c.customer_id IS NULL THEN 1 END) AS orphan_customers,
        COUNT(CASE WHEN r.sales_rep_id IS NULL THEN 1 END) AS orphan_reps,
        COUNT(CASE WHEN b.branch_id IS NULL THEN 1 END) AS orphan_branches,
        COUNT(CASE WHEN d.date_key IS NULL THEN 1 END) AS orphan_dates
    FROM gold.fact_sales f
    LEFT JOIN gold.dim_product p ON f.product_id = p.product_id
    LEFT JOIN gold.dim_customer c ON f.customer_id = c.customer_id
    LEFT JOIN gold.dim_sales_rep r ON f.sales_rep_id = r.sales_rep_id
    LEFT JOIN gold.dim_branch b ON f.branch_id = b.branch_id
    LEFT JOIN gold.dim_date d ON f.date_key = d.date_key
    """
    ref_df = con.execute(ref_query).df()
    orphan_p = int(ref_df["orphan_products"].iloc[0])
    orphan_c = int(ref_df["orphan_customers"].iloc[0])
    orphan_r = int(ref_df["orphan_reps"].iloc[0])
    orphan_b = int(ref_df["orphan_branches"].iloc[0])
    orphan_d = int(ref_df["orphan_dates"].iloc[0])

    assert orphan_p == 0, f"Encontrados {orphan_p} produtos órfãos em fact_sales"
    assert orphan_c == 0, f"Encontrados {orphan_c} clientes órfãos em fact_sales"
    assert orphan_r == 0, f"Encontrados {orphan_r} RCAs órfãos em fact_sales"
    assert orphan_b == 0, f"Encontrados {orphan_b} filiais órfãs em fact_sales"
    assert orphan_d == 0, f"Encontrados {orphan_d} datas órfãs em fact_sales"

    # 2. Conservação de faturamento bruto
    gold_rev_row = con.execute("SELECT SUM(gross_revenue) FROM gold.fact_sales").fetchone()
    gold_gross = float(gold_rev_row[0]) if gold_rev_row and gold_rev_row[0] is not None else 0.0

    remap_rev_row = con.execute(f"SELECT SUM(gross_revenue) FROM {scenario_id}.sales_remapped").fetchone()
    remap_gross = float(remap_rev_row[0]) if remap_rev_row and remap_rev_row[0] is not None else 0.0

    diff = abs(gold_gross - remap_gross)
    diff_pct = (diff / remap_gross) * 100.0 if remap_gross > 0 else 0.0

    assert diff_pct < 0.01, (
        f"Desvio de faturamento bruto entre Gold (R$ {gold_gross:,.2f}) e "
        f"Remapped (R$ {remap_gross:,.2f}) foi {diff_pct:.4f}%, superior à tolerância de 0.01%."
    )

    logger.info(
        "Integridade 100%% APROVADA: Zero chaves órfãs. "
        "Faturamento Gold: R$ %s | Remapped: R$ %s (Desvio: %.4f%%).",
        f"{gold_gross:,.2f}",
        f"{remap_gross:,.2f}",
        diff_pct,
    )

    return {
        "orphan_products": orphan_p,
        "orphan_customers": orphan_c,
        "orphan_reps": orphan_r,
        "orphan_branches": orphan_b,
        "orphan_dates": orphan_d,
        "gold_gross_revenue": gold_gross,
        "remap_gross_revenue": remap_gross,
        "revenue_diff_pct": diff_pct,
    }


def build_gold_star_schema(
    con: duckdb.DuckDBPyConnection,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
) -> dict[str, int]:
    """Constrói, valida e materializa o Star Schema completo da camada Gold no DuckDB e Parquet.

    Pipeline executado:
    1. Cria dimensão de calendário `gold.dim_date`
    2. Cria dimensão de filiais/fábrica `gold.dim_branch`
    3. Sincroniza dimensões Silver e do Cenário (`dim_customer`, `dim_sales_rep`,
       `dim_geography`, `dim_product`)
    4. Computa o fato de vendas com decomposição do Waterfall financeiro (`gold.fact_sales`)
    5. Valida integridade referencial estrita e conservação de faturamento
    6. Exporta snapshots Parquet Zstandard em `data/gold/snapshot/<scenario_id>/`

    Args:
        con: Conexão ativa com o DuckDB.
        scenario_id: Identificador do cenário (ex: 'c1_toys').

    Returns:
        Dicionário com contagens de linhas de cada tabela do Star Schema.
    """
    logger.info("Iniciando construção do Star Schema Gold para o cenário '%s'...", scenario_id)

    counts: dict[str, int] = {}

    # 1. Dimensões estruturais
    counts["dim_date"] = build_dim_date(con, scenario_id=scenario_id)
    counts["dim_branch"] = build_dim_branch(con, scenario_id=scenario_id)

    # 2. Dimensões de negócio
    dim_counts = sync_gold_dimensions(con, scenario_id=scenario_id)
    counts.update(dim_counts)

    # 3. Fato de vendas com Waterfall
    df_fact = compute_margin_waterfall(con, scenario_id=scenario_id, output_table=f"{scenario_id}.fact_sales")
    counts["fact_sales"] = len(df_fact)

    # 4. Auditoria de integridade
    validate_star_schema_integrity(con, scenario_id=scenario_id)

    # 5. Exportação de Parquet
    export_gold_snapshots(con, scenario_id=scenario_id)

    logger.info("Star Schema Gold construído com sucesso para '%s': %s", scenario_id, counts)
    return counts
