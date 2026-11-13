from __future__ import annotations

from datetime import date, datetime
from typing import Any, Final, cast

import duckdb
import numpy as np
import pandas as pd
from statsforecast import StatsForecast
from statsforecast.models import AutoETS, CrostonOptimized, SeasonalNaive
from statsforecast.utils import ConformalIntervals

from src.core.logging import get_logger, timed_step
from src.core.paths import gold_snapshot_path
from src.core.types import ScenarioId
from src.etl.contracts import GoldForecast30dSchema, validate_contract
from src.ml.features import resolve_as_of_date
from src.ml.forecast_helpers import (
    Z_80,
    Z_95,
    ForecastConfig,
    classify_sku_routing,
    enforce_non_negative_quantiles,
    load_dense_daily_sku_series,
    load_forecast_config,
    moving_average_forecast,
)

logger = get_logger(__name__)

DEFAULT_SCENARIO: Final[ScenarioId] = "c1_toys"


def _fit_group_forecast(
    df_group: pd.DataFrame,
    models: list[Any],
    *,
    horizon_days: int,
    with_intervals: bool,
) -> pd.DataFrame:
    """Executa StatsForecast (n_jobs=1) para um subgrupo homogêneo de SKUs."""
    if df_group.empty:
        return pd.DataFrame(columns=["unique_id", "ds"])

    n_per_sku = int(df_group.groupby("unique_id")["ds"].count().min())
    max_windows = max(0, (n_per_sku - 14) // horizon_days)

    if with_intervals and max_windows >= 2:
        ci = ConformalIntervals(h=horizon_days, n_windows=min(2, max_windows))
        sf = StatsForecast(models=models, freq="D", n_jobs=1)
        return cast(
            pd.DataFrame,
            sf.forecast(
                h=horizon_days,
                df=df_group,
                level=[80, 95],
                prediction_intervals=ci,
            ),
        )

    sf = StatsForecast(models=models, freq="D", n_jobs=1)
    return cast(pd.DataFrame, sf.forecast(h=horizon_days, df=df_group))


def _evaluate_holdout_and_select(
    dense_df: pd.DataFrame,
    products_df: pd.DataFrame,
    cfg: ForecastConfig,
    *,
    cutoff: date,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Executa holdout temporal de `holdout_days`, seleciona modelo por SKU e calcula WAPE por família."""
    val_start = pd.Timestamp(cutoff) - pd.Timedelta(days=cfg.holdout_days - 1)
    train_df = dense_df[dense_df["ds"] < val_start].copy()
    val_df = dense_df[dense_df["ds"] >= val_start].copy()

    routing_df = classify_sku_routing(train_df, cfg=cfg)
    last_train_date = pd.Timestamp(train_df["ds"].max())

    fb_ids = routing_df.loc[routing_df["route_group"] == "fallback", "unique_id"].tolist()
    interm_ids = routing_df.loc[routing_df["route_group"] == "intermittent", "unique_id"].tolist()
    reg_ids = routing_df.loc[routing_df["route_group"] == "regular", "unique_id"].tolist()

    fb_val = moving_average_forecast(
        train_df,
        fb_ids,
        last_train_date=last_train_date,
        horizon_days=cfg.holdout_days,
    )
    interm_val = _fit_group_forecast(
        train_df[train_df["unique_id"].isin(interm_ids)],
        [CrostonOptimized(), SeasonalNaive(season_length=7)],
        horizon_days=cfg.holdout_days,
        with_intervals=False,
    )
    reg_val = _fit_group_forecast(
        train_df[train_df["unique_id"].isin(reg_ids)],
        [AutoETS(season_length=7), SeasonalNaive(season_length=7)],
        horizon_days=cfg.holdout_days,
        with_intervals=False,
    )

    preds_val = val_df[["unique_id", "ds", "y"]].merge(
        routing_df[["unique_id", "route_group"]], on="unique_id", how="left"
    )
    preds_val = preds_val.merge(
        fb_val[["unique_id", "ds", "MovingAverage28d"]], on=["unique_id", "ds"], how="left"
    )

    if not interm_val.empty:
        preds_val = preds_val.merge(
            interm_val[["unique_id", "ds", "CrostonOptimized", "SeasonalNaive"]].rename(
                columns={"SeasonalNaive": "SeasonalNaive_i"}
            ),
            on=["unique_id", "ds"],
            how="left",
        )
    else:
        preds_val["CrostonOptimized"] = np.nan
        preds_val["SeasonalNaive_i"] = np.nan

    if not reg_val.empty:
        preds_val = preds_val.merge(
            reg_val[["unique_id", "ds", "AutoETS", "SeasonalNaive"]].rename(
                columns={"SeasonalNaive": "SeasonalNaive_r"}
            ),
            on=["unique_id", "ds"],
            how="left",
        )
    else:
        preds_val["AutoETS"] = np.nan
        preds_val["SeasonalNaive_r"] = np.nan

    preds_val["SeasonalNaive"] = preds_val["SeasonalNaive_i"].combine_first(preds_val["SeasonalNaive_r"])
    preds_val["specialist_model"] = np.where(
        preds_val["route_group"] == "fallback",
        "MovingAverage28d",
        np.where(preds_val["route_group"] == "regular", "AutoETS", "CrostonOptimized"),
    )
    preds_val["specialist_pred"] = np.clip(
        preds_val["MovingAverage28d"]
        .combine_first(preds_val["CrostonOptimized"])
        .combine_first(preds_val["AutoETS"])
        .fillna(0.0),
        0.0,
        None,
    )
    preds_val["snaive_pred"] = np.clip(preds_val["SeasonalNaive"].fillna(0.0), 0.0, None)
    preds_val["err_spec"] = np.abs(preds_val["y"] - preds_val["specialist_pred"])
    preds_val["err_snaive"] = np.abs(preds_val["y"] - preds_val["snaive_pred"])

    sku_eval = (
        preds_val.groupby(["unique_id", "route_group", "specialist_model"], as_index=False)
        .agg(
            mae_spec=("err_spec", "mean"),
            mae_snaive=("err_snaive", "mean"),
            val_actual_sum=("y", "sum"),
            val_spec_sum=("specialist_pred", "sum"),
            val_snaive_sum=("snaive_pred", "sum"),
        )
        .merge(products_df, left_on="unique_id", right_on="product_id", how="left")
    )

    sku_eval["horizon_mae_spec"] = np.abs(sku_eval["val_actual_sum"] - sku_eval["val_spec_sum"]) / float(
        cfg.holdout_days
    )
    sku_eval["horizon_mae_snaive"] = np.abs(sku_eval["val_actual_sum"] - sku_eval["val_snaive_sum"]) / float(
        cfg.holdout_days
    )

    use_specialist = (sku_eval["route_group"] == "fallback") | (
        sku_eval["horizon_mae_spec"] <= sku_eval["horizon_mae_snaive"]
    )
    sku_eval["selected_model"] = np.where(use_specialist, sku_eval["specialist_model"], "SeasonalNaive")
    sku_eval["sku_mae"] = np.round(
        np.where(use_specialist, sku_eval["horizon_mae_spec"], sku_eval["horizon_mae_snaive"]), 4
    )
    sku_eval["val_selected_sum"] = np.where(
        use_specialist, sku_eval["val_spec_sum"], sku_eval["val_snaive_sum"]
    )
    sku_eval["beats_snaive"] = sku_eval["horizon_mae_spec"] <= sku_eval["horizon_mae_snaive"]

    fam_wape = sku_eval.groupby("family", as_index=False).agg(
        fam_actual=("val_actual_sum", "sum"),
        fam_pred=("val_selected_sum", "sum"),
    )
    fam_wape["family_wape_pct"] = np.round(
        np.where(
            fam_wape["fam_actual"] > 0.0,
            np.abs(fam_wape["fam_pred"] - fam_wape["fam_actual"]) / fam_wape["fam_actual"] * 100.0,
            0.0,
        ),
        2,
    )
    sku_eval = sku_eval.merge(fam_wape[["family", "family_wape_pct"]], on="family", how="left")
    return sku_eval, fam_wape


def _extract_selected_forecast(
    raw_fc: pd.DataFrame,
    sku_eval: pd.DataFrame,
    routing_df: pd.DataFrame,
) -> pd.DataFrame:
    """Seleciona ponto e intervalos do modelo vencedor por SKU com fallback analítico para NaNs."""
    out = (
        raw_fc[["unique_id", "ds"]]
        .merge(
            sku_eval[["unique_id", "selected_model", "family", "family_wape_pct", "sku_mae"]],
            on="unique_id",
            how="left",
        )
        .merge(routing_df[["unique_id", "daily_std"]], on="unique_id", how="left")
    )

    fc_vals = np.zeros(len(out), dtype=np.float64)
    lo80_vals = np.full(len(out), np.nan, dtype=np.float64)
    hi80_vals = np.full(len(out), np.nan, dtype=np.float64)
    lo95_vals = np.full(len(out), np.nan, dtype=np.float64)
    hi95_vals = np.full(len(out), np.nan, dtype=np.float64)

    for model_name in ("AutoETS", "CrostonOptimized", "SeasonalNaive", "MovingAverage28d"):
        mask = out["selected_model"].to_numpy() == model_name
        if not np.any(mask) or model_name not in raw_fc.columns:
            continue
        fc_vals[mask] = raw_fc.loc[mask, model_name].to_numpy(dtype=np.float64)
        for col, target in (
            (f"{model_name}-lo-80", lo80_vals),
            (f"{model_name}-hi-80", hi80_vals),
            (f"{model_name}-lo-95", lo95_vals),
            (f"{model_name}-hi-95", hi95_vals),
        ):
            if col in raw_fc.columns:
                target[mask] = raw_fc.loc[mask, col].to_numpy(dtype=np.float64)

    std_fallback = np.maximum(out["daily_std"].fillna(0.0).to_numpy(dtype=np.float64), fc_vals * 0.35)
    lo80_vals = np.where(np.isnan(lo80_vals), fc_vals - Z_80 * std_fallback, lo80_vals)
    hi80_vals = np.where(np.isnan(hi80_vals), fc_vals + Z_80 * std_fallback, hi80_vals)
    lo95_vals = np.where(np.isnan(lo95_vals), fc_vals - Z_95 * std_fallback, lo95_vals)
    hi95_vals = np.where(np.isnan(hi95_vals), fc_vals + Z_95 * std_fallback, hi95_vals)

    out["forecast_units"] = fc_vals
    out["lo_80"] = lo80_vals
    out["hi_80"] = hi80_vals
    out["lo_95"] = lo95_vals
    out["hi_95"] = hi95_vals
    return enforce_non_negative_quantiles(out.drop(columns=["daily_std"]))


def build_forecast_30d_mart(
    con: duckdb.DuckDBPyConnection,
    *,
    as_of_date: date | datetime | str | None = None,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
    horizon_days: int = 30,
) -> pd.DataFrame:
    """Gera previsão de demanda 30d por SKU via StatsForecast e materializa `gold.mart_forecast_30d`."""
    with timed_step(f"ml_forecast_30d_{scenario_id}"):
        cfg = load_forecast_config()
        cutoff = resolve_as_of_date(con, as_of_date, scenario_id=scenario_id)

        dense_df, products_df = load_dense_daily_sku_series(
            con,
            scenario_id=scenario_id,
            cutoff=cutoff,
            lookback_days=cfg.lookback_days,
        )
        if dense_df.empty:
            raise ValueError(f"Sem dados de vendas ou produtos para gerar forecast em '{scenario_id}'.")

        sku_eval, _ = _evaluate_holdout_and_select(dense_df, products_df, cfg, cutoff=cutoff)
        routing_full = classify_sku_routing(dense_df, cfg=cfg)
        last_date = pd.Timestamp(dense_df["ds"].max())

        fb_ids = routing_full.loc[routing_full["route_group"] == "fallback", "unique_id"].tolist()
        interm_ids = routing_full.loc[routing_full["route_group"] == "intermittent", "unique_id"].tolist()
        reg_ids = routing_full.loc[routing_full["route_group"] == "regular", "unique_id"].tolist()

        fb_fc = moving_average_forecast(
            dense_df, fb_ids, last_train_date=last_date, horizon_days=horizon_days
        )
        interm_fc = _fit_group_forecast(
            dense_df[dense_df["unique_id"].isin(interm_ids)],
            [CrostonOptimized(), SeasonalNaive(season_length=7)],
            horizon_days=horizon_days,
            with_intervals=True,
        )
        reg_fc = _fit_group_forecast(
            dense_df[dense_df["unique_id"].isin(reg_ids)],
            [AutoETS(season_length=7), SeasonalNaive(season_length=7)],
            horizon_days=horizon_days,
            with_intervals=True,
        )

        raw_fc = pd.concat([df_p for df_p in (fb_fc, interm_fc, reg_fc) if not df_p.empty], ignore_index=True)
        fc_clean = _extract_selected_forecast(raw_fc, sku_eval, routing_full)

        cutoff_str = cutoff.isoformat()
        hist_start = pd.Timestamp(cutoff) - pd.Timedelta(days=cfg.history_output_days - 1)
        hist_df = (
            dense_df[dense_df["ds"] >= hist_start]
            .merge(
                sku_eval[["unique_id", "selected_model", "family", "family_wape_pct", "sku_mae"]],
                on="unique_id",
                how="left",
            )
            .rename(columns={"unique_id": "product_id", "ds": "date", "y": "actual_units"})
        )
        hist_df["scenario_id"] = scenario_id
        hist_df["record_type"] = "historical"
        hist_df["actual_units"] = np.round(hist_df["actual_units"], 2)
        for col in ("forecast_units", "lo_80", "hi_80", "lo_95", "hi_95"):
            hist_df[col] = np.nan
        hist_df["snapshot_date"] = cutoff_str

        fc_out = fc_clean.rename(columns={"unique_id": "product_id", "ds": "date"})
        fc_out["scenario_id"] = scenario_id
        fc_out["record_type"] = "forecast"
        fc_out["actual_units"] = np.nan
        fc_out["snapshot_date"] = cutoff_str

        cols_order = [
            "scenario_id",
            "product_id",
            "family",
            "date",
            "record_type",
            "actual_units",
            "forecast_units",
            "lo_80",
            "hi_80",
            "lo_95",
            "hi_95",
            "selected_model",
            "family_wape_pct",
            "sku_mae",
            "snapshot_date",
        ]
        result_df = (
            pd.concat([hist_df[cols_order], fc_out[cols_order]], ignore_index=True)
            .sort_values(["product_id", "date"])
            .reset_index(drop=True)
        )
        validated_df = validate_contract(result_df, GoldForecast30dSchema, layer="gold")

        con.execute("CREATE SCHEMA IF NOT EXISTS gold")
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {scenario_id}")
        con.register("temp_mart_forecast_30d", validated_df)
        con.execute(
            f"CREATE OR REPLACE TABLE {scenario_id}.mart_forecast_30d AS SELECT * FROM temp_mart_forecast_30d"
        )
        con.execute("CREATE OR REPLACE TABLE gold.mart_forecast_30d AS SELECT * FROM temp_mart_forecast_30d")
        con.unregister("temp_mart_forecast_30d")

        parquet_p = gold_snapshot_path(scenario_id, "mart_forecast_30d")
        parquet_p.parent.mkdir(parents=True, exist_ok=True)
        con.execute(
            f"COPY gold.mart_forecast_30d TO '{parquet_p.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)"
        )

        logger.info(
            "Mart `mart_forecast_30d` materializado para '%s': %d registros (%d SKUs) salvo em %s.",
            scenario_id,
            len(validated_df),
            validated_df["product_id"].nunique(),
            parquet_p,
        )
        return validated_df


def compute_forecast_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Consolida métricas de previsão e WAPE por família para inspeção na CLI e auditoria."""
    fc_only = df[df["record_type"] == "forecast"].copy()
    if fc_only.empty:
        return pd.DataFrame()
    return (
        fc_only.groupby("family", as_index=False)
        .agg(
            skus_count=("product_id", "nunique"),
            total_forecast_30d=("forecast_units", "sum"),
            avg_daily_forecast=("forecast_units", "mean"),
            family_wape_pct=("family_wape_pct", "first"),
            avg_sku_mae=("sku_mae", "mean"),
            dominant_model=(
                "selected_model",
                lambda s: s.mode().iloc[0] if not s.empty else "MovingAverage28d",
            ),
        )
        .sort_values("total_forecast_30d", ascending=False)
        .reset_index(drop=True)
    )
