from __future__ import annotations

from datetime import date, datetime
from typing import Final

import duckdb
import numpy as np
import pandas as pd

from src.core.logging import get_logger, timed_step
from src.core.paths import gold_snapshot_path
from src.core.types import ScenarioId
from src.etl.contracts import GoldInventoryPositionSchema, validate_contract
from src.etl.gold.inventory_snapshot import build_inventory_snapshot
from src.ml.abc_xyz import build_abc_xyz_mart
from src.ml.features import resolve_as_of_date
from src.ml.forecast import build_forecast_30d_mart

logger = get_logger(__name__)

DEFAULT_SCENARIO: Final[ScenarioId] = "c1_toys"
SERVICE_LEVEL_Z: Final[dict[str, float]] = {"A": 1.65, "B": 1.28, "C": 0.84}
DEFAULT_SERVICE_Z: Final[float] = 0.84
MIN_DEMAND_FLOOR: Final[float] = 0.01
LOCKED_COVERAGE_THRESHOLD_DAYS: Final[float] = 120.0
MODERATE_EXCESS_THRESHOLD_DAYS: Final[float] = 60.0
MIN_TARGET_COVERAGE_DAYS: Final[int] = 30

OUTPUT_COLUMNS: Final[list[str]] = [
    "scenario_id",
    "branch_id",
    "product_id",
    "product_name",
    "family",
    "abc_class",
    "xyz_class",
    "abc_xyz_class",
    "pack",
    "unit_cost",
    "unit_list_price",
    "stock_units",
    "stock_boxes",
    "stock_value_brl",
    "forecast_daily_demand",
    "daily_demand_std",
    "lead_time_days",
    "safety_stock_units",
    "reorder_point_units",
    "coverage_days",
    "days_to_stockout",
    "stock_status",
    "suggested_order_boxes",
    "protected_revenue_brl",
    "locked_capital_brl",
    "action_prescription",
    "snapshot_date",
]


def _has_scenario_rows(
    con: duckdb.DuckDBPyConnection,
    qualified_table: str,
    scenario_id: ScenarioId,
) -> bool:
    """Verifica se uma tabela qualificada existe no DuckDB e possui linhas para o cenário."""
    schema, table = qualified_table.split(".", maxsplit=1)
    exists = con.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_schema = ? AND table_name = ?
        """,
        [schema, table],
    ).fetchone()
    if not exists or int(exists[0]) == 0:
        return False

    cnt = con.execute(
        f"SELECT COUNT(*) FROM {qualified_table} WHERE scenario_id = ?",
        [scenario_id],
    ).fetchone()
    return bool(cnt and int(cnt[0]) > 0)


def _ensure_prerequisites(
    con: duckdb.DuckDBPyConnection,
    *,
    as_of_date: date,
    scenario_id: ScenarioId,
) -> None:
    """Garante que snapshot de estoque, ABC/XYZ e forecast 30d existam antes da consolidação."""
    if not _has_scenario_rows(con, "gold.inventory_snapshot", scenario_id):
        logger.info(
            "`gold.inventory_snapshot` ausente para '%s'; gerando insumo automaticamente.", scenario_id
        )
        build_inventory_snapshot(con, scenario_id=scenario_id, as_of_date=as_of_date)

    if not _has_scenario_rows(con, "gold.mart_abc_xyz", scenario_id):
        logger.info("`gold.mart_abc_xyz` ausente para '%s'; gerando insumo automaticamente.", scenario_id)
        build_abc_xyz_mart(con, as_of_date=as_of_date, scenario_id=scenario_id)

    if not _has_scenario_rows(con, "gold.mart_forecast_30d", scenario_id):
        logger.info(
            "`gold.mart_forecast_30d` ausente para '%s'; gerando insumo automaticamente.", scenario_id
        )
        build_forecast_30d_mart(con, as_of_date=as_of_date, scenario_id=scenario_id)


def load_inventory_position_inputs(
    con: duckdb.DuckDBPyConnection,
    *,
    as_of_date: date | datetime | str | None = None,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
) -> tuple[pd.DataFrame, str]:
    """Carrega e cruza snapshot de estoque, produto, ABC/XYZ e forecast médio 30d em SQL."""
    resolved_date = resolve_as_of_date(con, as_of_date=as_of_date, scenario_id=scenario_id)
    _ensure_prerequisites(con, as_of_date=resolved_date, scenario_id=scenario_id)

    sql = """
    WITH forecast_daily AS (
        SELECT
            product_id,
            COALESCE(AVG(forecast_units), 0.0) AS fc_daily_demand
        FROM gold.mart_forecast_30d
        WHERE scenario_id = ?
          AND record_type = 'forecast'
        GROUP BY product_id
    )
    SELECT
        inv.scenario_id,
        inv.branch_id,
        inv.product_id,
        p.product_name,
        inv.family,
        COALESCE(abc.abc_class, 'C') AS abc_class,
        COALESCE(abc.xyz_class, 'Z') AS xyz_class,
        COALESCE(abc.abc_xyz_class, 'CZ') AS abc_xyz_class,
        inv.pack,
        inv.unit_cost,
        p.base_unit_price AS unit_list_price,
        inv.stock_units,
        inv.stock_boxes,
        inv.stock_value_brl,
        inv.avg_daily_demand_90d,
        COALESCE(fc.fc_daily_demand, 0.0) AS fc_daily_demand,
        COALESCE(abc.weekly_demand_std, 0.0) AS weekly_demand_std,
        inv.lead_time_days
    FROM gold.inventory_snapshot inv
    JOIN gold.dim_product p
      ON inv.product_id = p.product_id
    LEFT JOIN gold.mart_abc_xyz abc
      ON inv.product_id = abc.product_id
     AND inv.scenario_id = abc.scenario_id
    LEFT JOIN forecast_daily fc
      ON inv.product_id = fc.product_id
    WHERE inv.scenario_id = ?
    ORDER BY inv.product_id
    """
    df = con.execute(sql, [scenario_id, scenario_id]).df()
    if df.empty:
        msg = f"Nenhum registro encontrado em `gold.inventory_snapshot` para o cenário '{scenario_id}'."
        raise ValueError(msg)

    return df, resolved_date.strftime("%Y-%m-%d")


def _build_action_prescriptions(
    df: pd.DataFrame,
    *,
    is_rupture: np.ndarray,
    is_locked: np.ndarray,
    is_moderate_excess: np.ndarray,
    suggested_order_boxes: np.ndarray,
) -> np.ndarray:
    """Gera prescrições acionáveis vetorizadas conforme status de estoque e curva ABC/XYZ."""
    abc_arr = df["abc_class"].astype(str).to_numpy()
    xyz_arr = df["xyz_class"].astype(str).to_numpy()
    order_str = pd.Series(suggested_order_boxes, index=df.index).astype(str)

    rx_rupture_a = ("Compra Emergencial (Curva A): emitir OC imediata de " + order_str + " cx").to_numpy()
    rx_rupture_bc = (
        "Ressuprimento Preventivo: programar OC de " + order_str + " cx até estoque-alvo"
    ).to_numpy()
    rx_rop_exact = np.full(
        len(df),
        "Ponto de Pedido Atingido: preparar nova OC no próximo ciclo",
        dtype=object,
    )

    return np.select(
        [
            is_rupture & (suggested_order_boxes > 0) & (abc_arr == "A"),
            is_rupture & (suggested_order_boxes > 0),
            is_rupture,
            is_locked & ((abc_arr == "C") | (xyz_arr == "Z")),
            is_locked,
            is_moderate_excess,
        ],
        [
            rx_rupture_a,
            rx_rupture_bc,
            rx_rop_exact,
            "Liquidação / Queima de Lote (>120d): destravar caixa de cauda longa",
            "Kit Promocional / Bonificação em Combo (>120d): acelerar giro sem reduzir lista",
            "Frear Compras: segurar novas OCs até cobertura convergir para <= 60d",
        ],
        default="Manter Ciclo Regular: cobertura alinhada ao estoque de segurança",
    )


def compute_inventory_position(
    inputs_df: pd.DataFrame,
    *,
    snapshot_date: str,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
) -> pd.DataFrame:
    """Calcula métricas prescritivas de estoque (SS, ROP, cobertura e capital travado) vetorizadas."""
    if inputs_df.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    df = inputs_df.copy()

    fc_raw = df["fc_daily_demand"].to_numpy(dtype=np.float64)
    hist_90d = np.maximum(df["avg_daily_demand_90d"].to_numpy(dtype=np.float64), 0.0)
    forecast_daily_demand = np.where(fc_raw > 0.0, fc_raw, hist_90d)

    weekly_std = np.maximum(df["weekly_demand_std"].to_numpy(dtype=np.float64), 0.0)
    daily_demand_std = weekly_std / np.sqrt(7.0)

    lead_time = np.maximum(df["lead_time_days"].to_numpy(dtype=np.int64), 1)
    stock_units = np.maximum(df["stock_units"].to_numpy(dtype=np.int64), 0)
    pack = np.maximum(df["pack"].to_numpy(dtype=np.int64), 1)
    unit_cost = df["unit_cost"].to_numpy(dtype=np.float64)
    unit_list_price = df["unit_list_price"].to_numpy(dtype=np.float64)

    z_values = (
        df["abc_class"].astype(str).map(SERVICE_LEVEL_Z).fillna(DEFAULT_SERVICE_Z).to_numpy(dtype=np.float64)
    )

    safety_stock_units = np.ceil(z_values * daily_demand_std * np.sqrt(lead_time)).astype(int)
    reorder_point_units = np.ceil(forecast_daily_demand * lead_time + safety_stock_units).astype(int)

    safe_demand = np.maximum(forecast_daily_demand, MIN_DEMAND_FLOOR)
    coverage_days = np.round(stock_units / safe_demand, 2)
    days_to_stockout = np.maximum(0.0, coverage_days)

    is_rupture = (coverage_days <= lead_time) | (stock_units <= reorder_point_units)
    is_locked = (~is_rupture) & (coverage_days > LOCKED_COVERAGE_THRESHOLD_DAYS)
    is_moderate_excess = (
        (~is_rupture)
        & (coverage_days > MODERATE_EXCESS_THRESHOLD_DAYS)
        & (coverage_days <= LOCKED_COVERAGE_THRESHOLD_DAYS)
    )

    stock_status = np.select(
        [is_rupture, is_locked, is_moderate_excess],
        ["Ruptura Iminente", "Capital Travado", "Atenção (Excesso Moderado)"],
        default="Saudável",
    )

    needs_order = stock_units < reorder_point_units
    target_days = np.maximum(MIN_TARGET_COVERAGE_DAYS, lead_time * 2)
    target_units = np.ceil(forecast_daily_demand * target_days).astype(int)
    needed_units = np.where(needs_order, np.maximum(0, target_units - stock_units), 0)
    suggested_order_boxes = np.where(needs_order, np.ceil(needed_units / pack).astype(int), 0)
    protected_revenue_brl = np.round(suggested_order_boxes * pack * unit_list_price, 2)

    is_over_120 = coverage_days > LOCKED_COVERAGE_THRESHOLD_DAYS
    excess_units = np.where(
        is_over_120,
        np.maximum(
            0, stock_units - np.ceil(forecast_daily_demand * LOCKED_COVERAGE_THRESHOLD_DAYS).astype(int)
        ),
        0,
    )
    locked_capital_brl = np.round(excess_units * unit_cost, 2)

    action_prescription = _build_action_prescriptions(
        df,
        is_rupture=is_rupture,
        is_locked=is_locked,
        is_moderate_excess=is_moderate_excess,
        suggested_order_boxes=suggested_order_boxes,
    )

    df["scenario_id"] = scenario_id
    df["forecast_daily_demand"] = np.round(forecast_daily_demand, 4)
    df["daily_demand_std"] = np.round(daily_demand_std, 4)
    df["safety_stock_units"] = safety_stock_units
    df["reorder_point_units"] = reorder_point_units
    df["coverage_days"] = coverage_days
    df["days_to_stockout"] = days_to_stockout
    df["stock_status"] = stock_status
    df["suggested_order_boxes"] = suggested_order_boxes
    df["protected_revenue_brl"] = protected_revenue_brl
    df["locked_capital_brl"] = locked_capital_brl
    df["action_prescription"] = action_prescription
    df["snapshot_date"] = snapshot_date

    return df[OUTPUT_COLUMNS].sort_values(by="product_id").reset_index(drop=True)


def build_inventory_position_mart(
    con: duckdb.DuckDBPyConnection,
    *,
    as_of_date: date | datetime | str | None = None,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
) -> pd.DataFrame:
    """Materializa e valida o mart prescritivo `gold.mart_inventory_position` em DuckDB e Parquet."""
    with timed_step("build_inventory_position_mart"):
        inputs_df, snapshot_date = load_inventory_position_inputs(
            con,
            as_of_date=as_of_date,
            scenario_id=scenario_id,
        )
        raw_df = compute_inventory_position(
            inputs_df,
            snapshot_date=snapshot_date,
            scenario_id=scenario_id,
        )
        validated_df = validate_contract(
            raw_df,
            GoldInventoryPositionSchema,
            layer="Gold (mart_inventory_position)",
        )

        con.execute("CREATE SCHEMA IF NOT EXISTS gold")
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {scenario_id}")
        con.register("temp_mart_inventory_position", validated_df)
        con.execute(
            f"CREATE OR REPLACE TABLE {scenario_id}.mart_inventory_position "
            "AS SELECT * FROM temp_mart_inventory_position"
        )
        con.execute(
            "CREATE OR REPLACE TABLE gold.mart_inventory_position "
            "AS SELECT * FROM temp_mart_inventory_position"
        )
        con.unregister("temp_mart_inventory_position")

        parquet_p = gold_snapshot_path(scenario_id, "mart_inventory_position")
        parquet_p.parent.mkdir(parents=True, exist_ok=True)
        con.execute(
            f"COPY gold.mart_inventory_position TO '{parquet_p.as_posix()}' "
            "(FORMAT PARQUET, COMPRESSION ZSTD)"
        )

        locked_total = float(validated_df["locked_capital_brl"].sum())
        protected_total = float(validated_df["protected_revenue_brl"].sum())
        rupture_count = int((validated_df["stock_status"] == "Ruptura Iminente").sum())
        locked_count = int((validated_df["stock_status"] == "Capital Travado").sum())

        logger.info(
            "Mart `mart_inventory_position` materializado para '%s': %d SKUs "
            "(Ruptura=%d, Capital Travado=%d, Capital Travado=R$ %s, Receita Protegida=R$ %s) em %s.",
            scenario_id,
            len(validated_df),
            rupture_count,
            locked_count,
            f"{locked_total:,.2f}",
            f"{protected_total:,.2f}",
            parquet_p,
        )
        return validated_df


def compute_inventory_position_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Consolida distribuição de SKUs por `stock_status` para inspeção na CLI e auditoria."""
    if df.empty:
        return pd.DataFrame()

    total_skus = max(len(df), 1)
    summary = (
        df.groupby("stock_status", as_index=False)
        .agg(
            skus_count=("product_id", "nunique"),
            stock_value_brl=("stock_value_brl", "sum"),
            locked_capital_brl=("locked_capital_brl", "sum"),
            suggested_order_boxes=("suggested_order_boxes", "sum"),
            protected_revenue_brl=("protected_revenue_brl", "sum"),
            avg_coverage_days=("coverage_days", "mean"),
        )
        .sort_values("stock_value_brl", ascending=False)
        .reset_index(drop=True)
    )
    summary["skus_pct"] = (summary["skus_count"] / total_skus * 100.0).round(1)
    summary["avg_coverage_days"] = summary["avg_coverage_days"].round(1)
    return summary[
        [
            "stock_status",
            "skus_count",
            "skus_pct",
            "stock_value_brl",
            "locked_capital_brl",
            "suggested_order_boxes",
            "protected_revenue_brl",
            "avg_coverage_days",
        ]
    ]
