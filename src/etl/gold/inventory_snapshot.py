from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Final

import duckdb
import numpy as np
import pandas as pd
import yaml

from src.core.logging import get_logger, timed_step
from src.core.paths import get_project_root, gold_snapshot_path
from src.core.types import ScenarioId
from src.etl.contracts import GoldInventorySnapshotSchema, validate_contract
from src.etl.lake import write_parquet
from src.ml.features import resolve_as_of_date

logger = get_logger(__name__)

DEFAULT_SCENARIO: Final[ScenarioId] = "c1_toys"
DEFAULT_SEED: Final[int] = 42


def load_working_capital_config(scenario_id: str = DEFAULT_SCENARIO) -> dict[str, Any]:
    """Carrega os parâmetros de governança de capital de giro e estoque.

    Lê o arquivo `config/finance/working_capital.yaml` para o cenário fornecido,
    com fallback seguro para a chave 'defaults'.

    Args:
        scenario_id: Identificador do cenário (ex: 'c1_toys').

    Returns:
        Dicionário com parâmetros de custo fixo, PMR, PMP, lead times e taxas.
    """
    config_path = get_project_root() / "config" / "finance" / "working_capital.yaml"
    if not config_path.exists():
        logger.warning("Arquivo de configuração %s não encontrado. Usando defaults.", config_path)
        return {}

    with open(config_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    if scenario_id in data:
        return data[scenario_id]  # type: ignore[no-any-return]
    if "defaults" in data:
        return data["defaults"]  # type: ignore[no-any-return]
    return data


def compute_inventory_snapshot(
    con: duckdb.DuckDBPyConnection,
    *,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
    as_of_date: date | datetime | str | None = None,
    seed: int = DEFAULT_SEED,
) -> pd.DataFrame:
    """Calcula a posição física e contábil de estoque determinística para os SKUs do cenário.

    Avalia a demanda real dos últimos 90 dias em relação à `as_of_date` e distribui
    os SKUs em 4 faixas de cobertura logística:
      - ~10% em Ruptura Iminente (1.0 a 7.0 dias de cobertura)
      - ~60% em Estoque Saudável (20.0 a 55.0 dias de cobertura)
      - ~15% em Ponto de Atenção (60.1 a 110.0 dias de cobertura)
      - ~15% em Capital Travado (>120 dias, 130.0 a 260.0 dias)

    Args:
        con: Conexão ativa com o DuckDB.
        scenario_id: Cenário de negócio alvo (ex: 'c1_toys').
        as_of_date: Data de corte do snapshot (se None, usa a última faturada).
        seed: Semente pseudo-aleatória determinística.

    Returns:
        DataFrame com colunas e tipos em conformidade com `GoldInventorySnapshotSchema`.
    """
    resolved_date = resolve_as_of_date(con, as_of_date, scenario_id=scenario_id)
    as_of_str = resolved_date.strftime("%Y-%m-%d")

    start_date = resolved_date - timedelta(days=90)
    start_key = int(start_date.strftime("%Y%m%d"))
    end_key = int(resolved_date.strftime("%Y%m%d"))

    # 1. Carrega parâmetros de lead time do working_capital.yaml
    wc_cfg = load_working_capital_config(scenario_id)
    lead_time_map: dict[str, int] = wc_cfg.get("lead_time_days_by_family", {})
    default_lead_time: int = int(wc_cfg.get("lead_time_days_default", 14))

    # 2. Identifica branch_id do cenário
    branch_row = con.execute("SELECT branch_id FROM gold.dim_branch LIMIT 1").fetchone()
    branch_id = str(branch_row[0]) if branch_row and branch_row[0] else "FAB-SP01"

    # 3. Consulta catálogo de produtos e vendas dos últimos 90 dias
    demand_query = f"""
    WITH p AS (
        SELECT
            product_id,
            family,
            pack,
            base_unit_cost AS unit_cost
        FROM gold.dim_product
    ),
    d90 AS (
        SELECT
            product_id,
            COALESCE(SUM(units), 0) / 90.0 AS avg_daily_demand_90d
        FROM gold.fact_sales
        WHERE scenario_id = '{scenario_id}'
          AND date_key BETWEEN {start_key} AND {end_key}
        GROUP BY product_id
    )
    SELECT
        p.product_id,
        p.family,
        p.pack,
        p.unit_cost,
        COALESCE(d90.avg_daily_demand_90d, 0.0) AS avg_daily_demand_90d
    FROM p
    LEFT JOIN d90 ON p.product_id = d90.product_id
    ORDER BY p.product_id
    """
    df = con.execute(demand_query).df()
    n = len(df)
    if n == 0:
        msg = f"Nenhum produto encontrado em gold.dim_product para o cenário '{scenario_id}'."
        raise ValueError(msg)

    # 4. Distribuição determinística nas 4 faixas de cobertura
    # Ordena por demanda 90d descrescente para que o capital travado (>120d)
    # concentre SKUs de cauda longa, mantendo o valor travado entre 10% e 25% do total.
    df = df.sort_values(
        by=["avg_daily_demand_90d", "product_id"],
        ascending=[False, True],
    ).reset_index(drop=True)

    rng = np.random.default_rng(seed)
    n1 = round(n * 0.10)
    n2 = round(n * 0.60)
    n3 = round(n * 0.15)
    n4 = n - n1 - n2 - n3

    cov1 = rng.uniform(1.0, 7.0, size=n1)
    cov2 = rng.uniform(20.0, 55.0, size=n2)
    cov3 = rng.uniform(60.1, 110.0, size=n3)
    cov4 = rng.uniform(130.0, 260.0, size=n4)

    coverage = np.concatenate([cov1, cov2, cov3, cov4])
    df["coverage_days"] = np.round(coverage, 1)

    # 5. Cálculo físico e financeiro de estoque
    # Garante demanda mínima de 0.15 un/dia para SKUs sem venda recente terem estoque coerente
    base_demand = np.maximum(df["avg_daily_demand_90d"].to_numpy(), 0.15)
    df["stock_units"] = np.maximum(
        np.round(df["coverage_days"].to_numpy() * base_demand).astype(int),
        1,
    )
    df["stock_boxes"] = np.round(df["stock_units"] / df["pack"], 2)
    df["stock_value_brl"] = np.round(df["stock_units"] * df["unit_cost"], 2)

    # 6. Metadados e lead time
    df["scenario_id"] = scenario_id
    df["snapshot_date"] = as_of_str
    df["branch_id"] = branch_id
    df["lead_time_days"] = df["family"].map(lambda fam: int(lead_time_map.get(str(fam), default_lead_time)))

    # Data estimada do último recebimento (recuo de ~40% do ciclo de cobertura)
    receipt_deltas = [timedelta(days=int(c * 0.4)) for c in df["coverage_days"].to_numpy()]
    df["last_receipt_date"] = [(resolved_date - d).strftime("%Y-%m-%d") for d in receipt_deltas]

    # 7. Ordenação determinística e seleção canônica de colunas
    ordered_cols = [
        "scenario_id",
        "snapshot_date",
        "branch_id",
        "product_id",
        "family",
        "pack",
        "unit_cost",
        "avg_daily_demand_90d",
        "stock_units",
        "stock_boxes",
        "stock_value_brl",
        "coverage_days",
        "lead_time_days",
        "last_receipt_date",
    ]
    return df.sort_values(by="product_id").reset_index(drop=True)[ordered_cols].copy()


def build_inventory_snapshot(
    con: duckdb.DuckDBPyConnection,
    *,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
    as_of_date: date | datetime | str | None = None,
    seed: int = DEFAULT_SEED,
) -> pd.DataFrame:
    """Constrói, valida e persiste o snapshot diário de estoque no DuckDB e Parquet.

    Persiste em:
      - DuckDB: `{scenario_id}.inventory_snapshot` e `gold.inventory_snapshot`
      - Parquet: `data/gold/snapshot/{scenario_id}/inventory_snapshot.parquet`

    Args:
        con: Conexão ativa com o DuckDB.
        scenario_id: Cenário de negócio alvo (ex: 'c1_toys').
        as_of_date: Data de corte analítica (se None, última faturada).
        seed: Semente determinística (default: 42).

    Returns:
        DataFrame validado pelo contrato `GoldInventorySnapshotSchema`.
    """
    logger.info("Iniciando geração de `inventory_snapshot` para cenário '%s'...", scenario_id)

    with timed_step("compute_inventory_snapshot"):
        raw_df = compute_inventory_snapshot(
            con,
            scenario_id=scenario_id,
            as_of_date=as_of_date,
            seed=seed,
        )

    validated_df = validate_contract(
        raw_df,
        GoldInventorySnapshotSchema,
        layer="Gold (inventory_snapshot)",
    )

    # Persistência no DuckDB
    con.execute("CREATE SCHEMA IF NOT EXISTS gold")
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {scenario_id}")

    con.register("_tmp_inventory_df", validated_df)
    con.execute(
        f"CREATE OR REPLACE TABLE {scenario_id}.inventory_snapshot AS SELECT * FROM _tmp_inventory_df"
    )
    con.execute("CREATE OR REPLACE TABLE gold.inventory_snapshot AS SELECT * FROM _tmp_inventory_df")
    con.unregister("_tmp_inventory_df")

    # Persistência em Parquet (ZSTD)
    out_parquet = gold_snapshot_path(scenario=scenario_id, table="inventory_snapshot")
    out_parquet.parent.mkdir(parents=True, exist_ok=True)
    write_parquet(validated_df, out_parquet)

    total_value = float(validated_df["stock_value_brl"].sum())
    locked_mask = validated_df["coverage_days"] > 120.0
    locked_value = float(validated_df.loc[locked_mask, "stock_value_brl"].sum())
    locked_pct = (locked_value / total_value * 100.0) if total_value > 0 else 0.0

    logger.info(
        "Snapshot de estoque gerado com sucesso para '%s': %d SKUs, "
        "Estoque Total = R$ %s, Capital Travado (>120d) = R$ %s (%.1f%%).",
        scenario_id,
        len(validated_df),
        f"{total_value:,.2f}",
        f"{locked_value:,.2f}",
        locked_pct,
    )

    return validated_df
