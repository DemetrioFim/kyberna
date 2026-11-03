from __future__ import annotations

from pathlib import Path
from typing import Final, Literal

import duckdb
import pandas as pd
import yaml
from pydantic import BaseModel, ConfigDict, Field

from src.core.logging import get_logger
from src.core.paths import config_path, get_data_dir
from src.core.types import ScenarioId
from src.etl.contracts import GoldFactSalesSchema, validate_contract
from src.etl.finance.taxes import TaxRulesConfig, build_total_tax_sql

logger = get_logger(__name__)

DEFAULT_SCENARIO: Final[ScenarioId] = "c1_toys"


# ==============================================================================
# Modelos Pydantic das Configurações Financeiras
# ==============================================================================


class FreightConfig(BaseModel):
    """Configuração da tabela de frete CIF por região brasileira."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    cost_per_box_by_region: dict[str, float] = Field(
        default_factory=lambda: {
            "Sudeste": 3.50,
            "Sul": 4.80,
            "Centro-Oeste": 6.20,
            "Nordeste": 8.50,
            "Norte": 11.00,
        }
    )
    default_cost_per_box: float = Field(5.00, ge=0.0)


class CommissionConfig(BaseModel):
    """Configuração dos parâmetros de comissão de vendas."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    min_rate: float = Field(0.035, ge=0.0, le=0.20)
    max_rate: float = Field(0.065, ge=0.0, le=0.20)
    default_rate: float = Field(0.050, ge=0.0, le=0.20)
    basis: Literal["net_price_revenue", "net_revenue"] = Field("net_price_revenue")


class RepBiasConfig(BaseModel):
    """Viés de negociação por perfil de representante comercial."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    high_discount_reps: list[str] = Field(default_factory=list)
    extra_discount: float = Field(0.045, ge=0.0, le=0.15)
    disciplined_reps: list[str] = Field(default_factory=list)
    discount_reduction: float = Field(-0.020, le=0.0, ge=-0.10)


class DiscountsConfig(BaseModel):
    """Política comercial de descontos por porte e RCA."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    size_baseline: dict[str, float] = Field(default_factory=lambda: {"P": 0.030, "M": 0.065, "G": 0.105})
    rep_bias: RepBiasConfig = Field(default_factory=RepBiasConfig)
    max_allowed_discount: float = Field(0.220, ge=0.0, le=0.50)
    min_allowed_discount: float = Field(0.000, ge=0.0)


# ==============================================================================
# Loaders de Configurações Financeiras
# ==============================================================================


def load_freight_config(
    config_file: str = "freight.yaml",
    base_dir: Path | None = None,
) -> FreightConfig:
    """Carrega as regras de frete CIF a partir do YAML."""
    path = (base_dir or config_path("finance")) / config_file
    if not path.exists():
        raise FileNotFoundError(f"Arquivo de frete não encontrado: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return FreightConfig.model_validate(raw)


def load_commission_config(
    config_file: str = "commission.yaml",
    base_dir: Path | None = None,
) -> CommissionConfig:
    """Carrega as regras de comissão a partir do YAML."""
    path = (base_dir or config_path("finance")) / config_file
    if not path.exists():
        raise FileNotFoundError(f"Arquivo de comissão não encontrado: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return CommissionConfig.model_validate(raw)


def load_discounts_config(
    config_file: str = "discounts.yaml",
    base_dir: Path | None = None,
) -> DiscountsConfig:
    """Carrega as regras de desconto comercial a partir do YAML."""
    path = (base_dir or config_path("finance")) / config_file
    if not path.exists():
        raise FileNotFoundError(f"Arquivo de descontos não encontrado: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return DiscountsConfig.model_validate(raw)


# ==============================================================================
# Geradores de Expressões SQL para o DuckDB
# ==============================================================================


def build_freight_case_when_sql(
    region_col: str = "c.region",
    config: FreightConfig | None = None,
) -> str:
    """Gera cláusula SQL CASE WHEN para custo unitário de frete por caixa master."""
    cfg = config or load_freight_config()
    lines = [f"WHEN {region_col} = '{reg}' THEN {cost}" for reg, cost in cfg.cost_per_box_by_region.items()]
    clauses = "\n            ".join(lines)
    return f"""CASE
            {clauses}
            ELSE {cfg.default_cost_per_box}
        END"""


def build_discount_rate_sql(
    size_col: str = "c.size",
    rep_col: str = "s.sales_rep_id",
    store_col: str = "s.store_number",
    config: DiscountsConfig | None = None,
) -> str:
    """Gera expressão SQL composta para a taxa de desconto comercial efetiva."""
    cfg = config or load_discounts_config()

    # 1. Baseline por porte do cliente
    size_lines = [f"WHEN {size_col} = '{sz}' THEN {rate}" for sz, rate in cfg.size_baseline.items()]
    size_clauses = "\n                ".join(size_lines)
    size_base_sql = f"""CASE
                {size_clauses}
                ELSE 0.05
            END"""

    # 2. Viés comportamental por RCA
    high_reps = ", ".join(f"'{r}'" for r in cfg.rep_bias.high_discount_reps)
    disc_reps = ", ".join(f"'{r}'" for r in cfg.rep_bias.disciplined_reps)

    rep_bias_sql = f"""CASE
                WHEN {rep_col} IN ({high_reps}) THEN {cfg.rep_bias.extra_discount}
                WHEN {rep_col} IN ({disc_reps}) THEN {cfg.rep_bias.discount_reduction}
                ELSE 0.0
            END"""

    # 3. Pequeno ruído determinístico por loja (-0.010 a +0.010)
    # Nota: hash() no DuckDB retorna UINT64; cast para BIGINT antes da subtração evita overflow de UINT64
    store_noise_sql = f"((CAST(hash({store_col}) % 21 AS BIGINT) - 10) / 1000.0)"

    # Soma bruta e restrição aos limites [min_discount, max_discount]
    raw_sum_sql = f"({size_base_sql} + {rep_bias_sql} + {store_noise_sql})"
    return f"GREATEST({cfg.min_allowed_discount}, LEAST({cfg.max_allowed_discount}, {raw_sum_sql}))"


# ==============================================================================
# Motor Principal do Waterfall da Margem de Contribuição
# ==============================================================================


def build_margin_waterfall_sql(
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
    *,
    sales_table: str = "c1_toys.sales_remapped",
    customer_table: str = "silver.dim_customer",
    rep_table: str = "silver.dim_sales_rep",
    tax_config: TaxRulesConfig | None = None,
    freight_config: FreightConfig | None = None,
    discounts_config: DiscountsConfig | None = None,
) -> str:
    """Gera a consulta SQL completa do Waterfall canônico da Margem de Contribuição.

    A consulta implementa a definição canônica (§4.3 do GEMINI.md):
        gross_revenue        = units * unit_list_price
        discount_amount      = gross_revenue * discount_rate
        net_price_revenue    = gross_revenue - discount_amount
        tax_amount           = net_price_revenue * (icms + pis + cofins)
        net_revenue          = net_price_revenue - tax_amount
        cogs                 = units * unit_cost
        commission_amount    = net_price_revenue * commission_rate
        freight_amount       = boxes * freight_per_box
        contribution_margin  = net_revenue - cogs - commission_amount - freight_amount
    """
    total_tax_sql = build_total_tax_sql("c.state", config=tax_config)
    freight_unit_sql = build_freight_case_when_sql("c.region", config=freight_config)
    discount_rate_sql = build_discount_rate_sql(
        size_col="c.size",
        rep_col="s.sales_rep_id",
        store_col="s.store_number",
        config=discounts_config,
    )

    return f"""
    WITH pre_calc AS (
        SELECT
            '{scenario_id}' AS scenario_id,
            s.order_id,
            s.date_key,
            s.customer_id,
            s.product_id,
            s.sales_rep_id,
            s.branch_id,
            s.units,
            s.boxes,
            s.unit_list_price,
            s.unit_cost,
            ROUND(s.units * s.unit_list_price, 2) AS gross_revenue,
            ROUND({discount_rate_sql}, 4) AS discount_rate,
            ROUND({total_tax_sql}, 4) AS tax_rate,
            COALESCE(r.commission_rate, 0.050) AS commission_rate,
            ROUND({freight_unit_sql}, 2) AS freight_per_box
        FROM {sales_table} s
        LEFT JOIN {customer_table} c ON s.store_number = c.store_number
        LEFT JOIN {rep_table} r ON s.sales_rep_id = r.sales_rep_id
    ),
    waterfall_stage1 AS (
        SELECT
            scenario_id,
            order_id,
            date_key,
            customer_id,
            product_id,
            sales_rep_id,
            branch_id,
            units,
            boxes,
            unit_list_price,
            gross_revenue,
            ROUND(gross_revenue * discount_rate, 2) AS discount_amount,
            ROUND(gross_revenue - ROUND(gross_revenue * discount_rate, 2), 2) AS net_price_revenue,
            tax_rate,
            commission_rate,
            unit_cost,
            freight_per_box
        FROM pre_calc
    ),
    waterfall_stage2 AS (
        SELECT
            scenario_id,
            order_id,
            date_key,
            customer_id,
            product_id,
            sales_rep_id,
            branch_id,
            units,
            boxes,
            unit_list_price,
            ROUND(net_price_revenue / units, 4) AS unit_net_price,
            gross_revenue,
            discount_amount,
            ROUND(net_price_revenue * tax_rate, 2) AS tax_amount,
            ROUND(net_price_revenue - ROUND(net_price_revenue * tax_rate, 2), 2) AS net_revenue,
            ROUND(units * unit_cost, 2) AS cogs,
            ROUND(net_price_revenue * commission_rate, 2) AS commission_amount,
            ROUND(boxes * freight_per_box, 2) AS freight_amount
        FROM waterfall_stage1
    )
    SELECT
        scenario_id,
        order_id,
        date_key,
        customer_id,
        product_id,
        sales_rep_id,
        branch_id,
        units,
        boxes,
        unit_list_price,
        unit_net_price,
        gross_revenue,
        discount_amount,
        tax_amount,
        net_revenue,
        cogs,
        commission_amount,
        freight_amount,
        -- Identidade canônica: contribution_margin = net_revenue - cogs - commission - freight
        ROUND(net_revenue - cogs - commission_amount - freight_amount, 2) AS contribution_margin
    FROM waterfall_stage2
    """


def compute_margin_waterfall(
    con: duckdb.DuckDBPyConnection,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
    output_table: str = "c1_toys.fact_sales",
) -> pd.DataFrame:
    """Executa o cálculo do waterfall financeiro no DuckDB e valida o contrato Gold.

    Gera e salva:
    - Tabela no DuckDB (ex: `c1_toys.fact_sales` e `gold.fact_sales`)
    - Snapshot em Parquet em `data/gold/snapshot/<scenario_id>/fact_sales.parquet`

    Args:
        con: Conexão ativa com o DuckDB.
        scenario_id: Identificador do cenário (ex: 'c1_toys').
        output_table: Nome qualificado da tabela de saída no DuckDB.

    Returns:
        pd.DataFrame validado contra `GoldFactSalesSchema`.
    """
    logger.info("Iniciando cálculo do Waterfall financeiro para cenário '%s'...", scenario_id)

    # 1. Garante schemas no DuckDB
    con.execute("CREATE SCHEMA IF NOT EXISTS gold")
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {scenario_id}")

    # 2. Executa a query SQL do waterfall e materializa
    waterfall_sql = build_margin_waterfall_sql(scenario_id=scenario_id)
    con.execute(f"CREATE OR REPLACE TABLE {output_table} AS {waterfall_sql}")
    con.execute(f"CREATE OR REPLACE TABLE gold.fact_sales AS SELECT * FROM {output_table}")

    # 3. Extrai DataFrame para validação de contrato
    df_fact = con.execute(f"SELECT * FROM {output_table}").df()
    validated_df = validate_contract(df_fact, GoldFactSalesSchema, layer="Gold (fact_sales)")

    # 4. Salva snapshot Parquet
    snapshot_dir = get_data_dir() / "gold" / "snapshot" / scenario_id
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    parquet_p = snapshot_dir / "fact_sales.parquet"
    con.execute(f"COPY {output_table} TO '{parquet_p.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)")

    logger.info(
        "Waterfall financeiro concluído: %d linhas materializadas em %s e %s.",
        len(validated_df),
        output_table,
        parquet_p,
    )

    return validated_df
