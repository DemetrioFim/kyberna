from __future__ import annotations

from datetime import date, datetime
from typing import Final

import duckdb
import numpy as np
import pandas as pd

from src.core.logging import get_logger, timed_step
from src.core.paths import gold_snapshot_path
from src.core.types import GoldTable, ScenarioId
from src.etl.contracts import (
    GoldPriceRealizationSchema,
    GoldPricingDriversSchema,
    validate_contract,
)
from src.etl.finance.margin_waterfall import load_freight_config
from src.etl.gold.inventory_snapshot import load_working_capital_config
from src.ml.features import resolve_as_of_date
from src.ml.pricing_models import (
    build_driver_rows_for_scope,
    fit_family_pricing_models,
    prepare_pricing_features,
)

logger = get_logger(__name__)

DEFAULT_SCENARIO: Final[ScenarioId] = "c1_toys"
TARGET_MIN_MC_RATIO: Final[float] = 0.15


def load_pricing_sales_frame(
    con: duckdb.DuckDBPyConnection,
    *,
    as_of_date: date | datetime | str | None = None,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
) -> tuple[pd.DataFrame, str]:
    """Carrega transações Gold com preços de tabela/líquido e atributos comerciais."""
    resolved_date = resolve_as_of_date(con, as_of_date=as_of_date, scenario_id=scenario_id)
    as_of_key = int(resolved_date.strftime("%Y%m%d"))

    sql = """
    SELECT
        f.scenario_id,
        f.order_id,
        f.product_id,
        p.product_name,
        p.family,
        COALESCE(a.abc_class, 'C') AS abc_class,
        d.full_date,
        c.size AS customer_size,
        c.region,
        f.sales_rep_id,
        f.units,
        f.boxes,
        p.base_unit_price,
        f.unit_list_price,
        f.unit_net_price,
        f.gross_revenue,
        f.tax_amount,
        f.net_revenue,
        f.cogs,
        f.commission_amount,
        f.freight_amount,
        COALESCE(f.promo_flag, FALSE) AS promo_flag
    FROM gold.fact_sales f
    JOIN gold.dim_product p ON f.product_id = p.product_id
    JOIN gold.dim_customer c ON f.customer_id = c.customer_id
    JOIN gold.dim_date d ON f.date_key = d.date_key
    LEFT JOIN gold.mart_abc_xyz a
      ON f.scenario_id = a.scenario_id AND f.product_id = a.product_id
    WHERE f.scenario_id = ?
      AND f.date_key <= ?
      AND f.units > 0
      AND p.base_unit_price > 0
    ORDER BY d.full_date, f.product_id, f.order_id
    """
    df = con.execute(sql, [scenario_id, as_of_key]).df()
    if df.empty:
        msg = f"Nenhuma transação encontrada para precificação no cenário '{scenario_id}'."
        raise ValueError(msg)
    return df, resolved_date.strftime("%Y-%m-%d")


def _load_elasticity_map(con: duckdb.DuckDBPyConnection, scenario_id: ScenarioId) -> dict[str, float]:
    """Carrega beta_hat por família se `gold.mart_price_elasticity` já existir."""
    exists = con.execute(
        """
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = 'gold' AND table_name = 'mart_price_elasticity'
        """
    ).fetchone()
    if not exists or int(exists[0]) == 0:
        return {}
    df = con.execute(
        "SELECT family, beta_hat FROM gold.mart_price_elasticity WHERE scenario_id = ?",
        [scenario_id],
    ).df()
    return {str(fam): float(beta) for fam, beta in zip(df["family"], df["beta_hat"], strict=False)}


def _build_sku_realization_df(
    scored_df: pd.DataFrame,
    *,
    scenario_id: ScenarioId,
    snapshot_date: str,
    elasticity_map: dict[str, float],
) -> pd.DataFrame:
    """Agrega predições contextuais e vazamento financeiro por SKU."""
    df = scored_df.copy()
    p_floor = (df["pred_band_low_idx"] / 100.0) * df["base_unit_price"]
    df["line_leakage_brl"] = np.maximum(0.0, p_floor - df["unit_net_price"]) * df["units"]
    df["is_below_band"] = (df["realized_idx"] < df["pred_band_low_idx"]).astype(np.float64)
    df["net_price_rev"] = df["unit_net_price"] * df["units"]

    rep_leak = (
        df.groupby(["product_id", "sales_rep_id"], as_index=False)[["line_leakage_brl"]]
        .sum()
        .sort_values(
            by=["product_id", "line_leakage_brl", "sales_rep_id"],
            ascending=[True, False, True],
        )
        .drop_duplicates("product_id")
    )
    offender_map = {
        str(pid): (str(rep) if float(lk) > 0.0 else "Sem desvio")
        for pid, rep, lk in zip(
            rep_leak["product_id"], rep_leak["sales_rep_id"], rep_leak["line_leakage_brl"], strict=False
        )
    }

    grouped = df.groupby(["product_id", "product_name", "family", "abc_class"], as_index=False).agg(
        units_sold=("units", "sum"),
        orders_count=("order_id", "nunique"),
        base_unit_price=("base_unit_price", "first"),
        avg_list_price=("unit_list_price", "mean"),
        avg_net_price=("unit_net_price", "mean"),
        realized_idx_mean=("realized_idx", "mean"),
        realized_idx_std=("realized_idx", "std"),
        realized_idx_p05=("realized_idx", lambda s: float(np.percentile(s, 5.0))),
        realized_idx_p25=("realized_idx", lambda s: float(np.percentile(s, 25.0))),
        realized_idx_p50=("realized_idx", lambda s: float(np.percentile(s, 50.0))),
        realized_idx_p75=("realized_idx", lambda s: float(np.percentile(s, 75.0))),
        realized_idx_p95=("realized_idx", lambda s: float(np.percentile(s, 95.0))),
        contextual_band_low_idx=("pred_band_low_idx", "mean"),
        contextual_band_expected_idx=("pred_expected_idx", "mean"),
        contextual_band_high_idx=("pred_band_high_idx", "mean"),
        below_band_orders_pct=("is_below_band", lambda s: float(np.mean(s) * 100.0)),
        price_leakage_brl=("line_leakage_brl", "sum"),
        total_net_price_rev=("net_price_rev", "sum"),
        total_tax=("tax_amount", "sum"),
        total_comm=("commission_amount", "sum"),
        total_cogs=("cogs", "sum"),
        total_freight=("freight_amount", "sum"),
    )

    net_pr = np.maximum(grouped["total_net_price_rev"].to_numpy(dtype=np.float64), 1.0)
    tax_r = np.clip(grouped["total_tax"].to_numpy(dtype=np.float64) / net_pr, 0.0, 0.40)
    comm_r = np.clip(grouped["total_comm"].to_numpy(dtype=np.float64) / net_pr, 0.0, 0.25)
    denom_r = np.maximum(1.0 - tax_r - comm_r, 0.25)
    units_arr = np.maximum(grouped["units_sold"].to_numpy(dtype=np.float64), 1.0)
    unit_cost_arr = grouped["total_cogs"].to_numpy(dtype=np.float64) / units_arr
    unit_freight_arr = grouped["total_freight"].to_numpy(dtype=np.float64) / units_arr
    base_p_arr = grouped["base_unit_price"].to_numpy(dtype=np.float64)

    min_healthy = (
        (unit_cost_arr + unit_freight_arr + TARGET_MIN_MC_RATIO * base_p_arr) / (base_p_arr * denom_r)
    ) * 100.0
    grouped["min_healthy_idx"] = np.round(np.clip(min_healthy, 50.0, 125.0), 2)

    mean_idx = np.maximum(grouped["realized_idx_mean"].to_numpy(dtype=np.float64), 1.0)
    std_idx = grouped["realized_idx_std"].fillna(0.0).to_numpy(dtype=np.float64)
    grouped["price_cv_pct"] = np.round((std_idx / mean_idx) * 100.0, 2)

    betas = grouped["family"].astype(str).map(elasticity_map).fillna(-1.2).to_numpy(dtype=np.float64)
    gap_to_expected = np.maximum(
        0.0,
        (grouped["contextual_band_expected_idx"] - grouped["realized_idx_mean"]).to_numpy(dtype=np.float64)
        / 100.0,
    )
    is_inelastic = betas > -1.0
    # Upside anualizado (dividido por ~2 anos da janela) mantendo volume ajustado por beta
    vol_factor = np.power(1.0 + gap_to_expected, betas)
    upside = np.where(is_inelastic, (gap_to_expected * base_p_arr * units_arr * vol_factor) / 2.0, 0.0)
    grouped["inelastic_upside_brl"] = np.round(np.maximum(upside, 0.0), 2)

    grouped["scenario_id"] = scenario_id
    grouped["primary_offender_rep"] = grouped["product_id"].astype(str).map(offender_map).fillna("Sem desvio")
    grouped["snapshot_date"] = snapshot_date

    round_2 = [
        "base_unit_price",
        "avg_list_price",
        "avg_net_price",
        "realized_idx_mean",
        "realized_idx_p05",
        "realized_idx_p25",
        "realized_idx_p50",
        "realized_idx_p75",
        "realized_idx_p95",
        "contextual_band_low_idx",
        "contextual_band_expected_idx",
        "contextual_band_high_idx",
        "below_band_orders_pct",
        "price_leakage_brl",
    ]
    for col in round_2:
        grouped[col] = grouped[col].round(2)

    ordered_cols = [
        "scenario_id",
        "product_id",
        "product_name",
        "family",
        "abc_class",
        "units_sold",
        "orders_count",
        "base_unit_price",
        "avg_list_price",
        "avg_net_price",
        "realized_idx_mean",
        "realized_idx_p05",
        "realized_idx_p25",
        "realized_idx_p50",
        "realized_idx_p75",
        "realized_idx_p95",
        "contextual_band_low_idx",
        "contextual_band_expected_idx",
        "contextual_band_high_idx",
        "min_healthy_idx",
        "price_cv_pct",
        "below_band_orders_pct",
        "price_leakage_brl",
        "inelastic_upside_brl",
        "primary_offender_rep",
        "snapshot_date",
    ]
    return grouped[ordered_cols].sort_values("price_leakage_brl", ascending=False).reset_index(drop=True)


def _persist_pricing_mart(
    con: duckdb.DuckDBPyConnection,
    df: pd.DataFrame,
    *,
    table_name: GoldTable,
    scenario_id: ScenarioId,
) -> None:
    """Registra tabela em `gold.<table_name>`, `<scenario_id>.<table_name>` e Parquet ZSTD."""
    temp_view = f"temp_{table_name}"
    con.execute("CREATE SCHEMA IF NOT EXISTS gold")
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {scenario_id}")
    con.register(temp_view, df)
    con.execute(f"CREATE OR REPLACE TABLE {scenario_id}.{table_name} AS SELECT * FROM {temp_view}")
    con.execute(f"CREATE OR REPLACE TABLE gold.{table_name} AS SELECT * FROM {temp_view}")
    con.unregister(temp_view)

    parquet_p = gold_snapshot_path(scenario_id, table_name)
    parquet_p.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY gold.{table_name} TO '{parquet_p.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)")


def build_pricing_marts(
    con: duckdb.DuckDBPyConnection,
    *,
    as_of_date: date | datetime | str | None = None,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Materializa e valida `mart_price_realization` e `mart_pricing_drivers`."""
    with timed_step("build_pricing_marts"):
        raw_df, snapshot_date = load_pricing_sales_frame(con, as_of_date=as_of_date, scenario_id=scenario_id)
        freight_cfg = load_freight_config()
        wc_cfg = load_working_capital_config(scenario_id)
        pmr_map = {
            str(k): float(v) for k, v in wc_cfg.get("pmr_days_by_size", {"P": 28, "M": 42, "G": 56}).items()
        }

        feat_df = prepare_pricing_features(
            raw_df,
            freight_by_region=freight_cfg.cost_per_box_by_region,
            default_freight_per_box=freight_cfg.default_cost_per_box,
            pmr_by_size=pmr_map,
        )
        freight_ref = float(
            freight_cfg.cost_per_box_by_region.get("Sudeste", freight_cfg.default_cost_per_box)
        )
        pmr_ref = float(pmr_map.get("P", 28.0))

        scored_parts: list[pd.DataFrame] = []
        driver_rows: list[dict[str, object]] = []
        for family_val, fam_df in feat_df.groupby("family", sort=True):
            family = str(family_val)
            scored_fam, _ = fit_family_pricing_models(fam_df, freight_ref=freight_ref, pmr_ref=pmr_ref)
            scored_parts.append(scored_fam)
            driver_rows.extend(
                build_driver_rows_for_scope(
                    scored_fam,
                    scenario_id=scenario_id,
                    scope_type="family",
                    scope_id=family,
                    scope_label=family,
                    family=family,
                    snapshot_date=snapshot_date,
                )
            )

        scored_all = pd.concat(scored_parts, ignore_index=True)
        elasticity_map = _load_elasticity_map(con, scenario_id)
        realization_raw = _build_sku_realization_df(
            scored_all,
            scenario_id=scenario_id,
            snapshot_date=snapshot_date,
            elasticity_map=elasticity_map,
        )

        top_leak_ids = realization_raw.head(30)["product_id"].astype(str).tolist()
        top_rev_ids = (
            scored_all.groupby("product_id")["gross_revenue"].sum().nlargest(10).index.astype(str).tolist()
        )
        sku_scope_ids = list(dict.fromkeys([*top_leak_ids, *top_rev_ids]))
        for pid in sku_scope_ids:
            sku_df = scored_all[scored_all["product_id"].astype(str) == pid]
            if sku_df.empty:
                continue
            first = sku_df.iloc[0]
            driver_rows.extend(
                build_driver_rows_for_scope(
                    sku_df,
                    scenario_id=scenario_id,
                    scope_type="sku",
                    scope_id=pid,
                    scope_label=str(first["product_name"]),
                    family=str(first["family"]),
                    snapshot_date=snapshot_date,
                )
            )

        realization_df = validate_contract(
            realization_raw,
            GoldPriceRealizationSchema,
            layer="Gold (mart_price_realization)",
        )
        drivers_df = validate_contract(
            pd.DataFrame(driver_rows),
            GoldPricingDriversSchema,
            layer="Gold (mart_pricing_drivers)",
        )

        _persist_pricing_mart(
            con, realization_df, table_name="mart_price_realization", scenario_id=scenario_id
        )
        _persist_pricing_mart(con, drivers_df, table_name="mart_pricing_drivers", scenario_id=scenario_id)
        logger.info(
            "Marts de Precificação materializados para '%s': %d SKUs, %d linhas de drivers SHAP.",
            scenario_id,
            len(realization_df),
            len(drivers_df),
        )
        return realization_df, drivers_df
