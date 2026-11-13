from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import cast

import duckdb
import numpy as np
import pandas as pd
import yaml
from pydantic import BaseModel, ConfigDict, Field

from src.core.paths import config_path
from src.core.types import ScenarioId

Z_80 = 1.28155
Z_95 = 1.95996


class ForecastConfig(BaseModel):
    """Configuração tipada do motor de previsão de demanda 30d."""

    model_config = ConfigDict(frozen=True)

    lookback_days: int = Field(180, ge=30, le=730)
    history_output_days: int = Field(90, ge=7, le=365)
    holdout_days: int = Field(28, ge=7, le=90)
    adi_threshold: float = Field(1.32, ge=1.0, le=5.0)
    min_nonzero_days: int = Field(5, ge=1, le=30)
    min_history_days: int = Field(60, ge=14, le=180)


def load_forecast_config(pipeline_yaml: Path | None = None) -> ForecastConfig:
    """Carrega parâmetros de previsão de demanda a partir de `config/pipeline.yaml`."""
    yaml_path = pipeline_yaml or config_path("pipeline.yaml")
    if not yaml_path.exists():
        return ForecastConfig()
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    fc_raw = raw.get("thresholds", {}).get("forecast", {})
    return ForecastConfig.model_validate(fc_raw)


def load_dense_daily_sku_series(
    con: duckdb.DuckDBPyConnection,
    *,
    scenario_id: ScenarioId,
    cutoff: date,
    lookback_days: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Carrega série diária completa (com zeros preenchidos) por SKU e catálogo de produtos até `cutoff`."""
    start_date = cutoff - timedelta(days=lookback_days - 1)
    start_str = start_date.isoformat()
    cutoff_str = cutoff.isoformat()

    products_df = con.execute(
        """
        SELECT DISTINCT product_id, family
        FROM gold.dim_product
        ORDER BY product_id
        """
    ).df()
    if products_df.empty:
        return pd.DataFrame(columns=["unique_id", "ds", "y"]), products_df

    sales_df = con.execute(
        f"""
        SELECT
            f.product_id AS unique_id,
            d.full_date::DATE AS ds,
            SUM(f.units)::DOUBLE AS y
        FROM gold.fact_sales f
        JOIN gold.dim_date d ON f.date_key = d.date_key
        WHERE f.scenario_id = '{scenario_id}'
          AND d.full_date >= DATE '{start_str}'
          AND d.full_date <= DATE '{cutoff_str}'
        GROUP BY f.product_id, d.full_date::DATE
        """
    ).df()

    all_dates = pd.date_range(start=start_str, end=cutoff_str, freq="D")
    idx = pd.MultiIndex.from_product(
        [products_df["product_id"].astype(str).tolist(), all_dates],
        names=["unique_id", "ds"],
    )
    dense_df = pd.DataFrame(index=idx).reset_index()

    if not sales_df.empty:
        sales_df["unique_id"] = sales_df["unique_id"].astype(str)
        sales_df["ds"] = pd.to_datetime(sales_df["ds"])
        dense_df = dense_df.merge(sales_df, on=["unique_id", "ds"], how="left")
        dense_df["y"] = dense_df["y"].fillna(0.0).astype(np.float64)
    else:
        dense_df["y"] = 0.0

    return dense_df.sort_values(["unique_id", "ds"]).reset_index(drop=True), products_df


def classify_sku_routing(
    train_df: pd.DataFrame,
    cfg: ForecastConfig,
) -> pd.DataFrame:
    """Classifica cada SKU em grupo de modelagem (`fallback`, `intermittent`, `regular`) pelo ADI."""
    stats = (
        train_df.assign(is_nz=train_df["y"] > 0.0)
        .groupby("unique_id", as_index=False)
        .agg(
            n_days=("ds", "count"),
            n_nonzero=("is_nz", "sum"),
            daily_mean=("y", "mean"),
            daily_std=("y", "std"),
        )
    )
    stats["daily_std"] = stats["daily_std"].fillna(0.0)
    stats["adi"] = np.where(
        stats["n_nonzero"] > 0,
        stats["n_days"] / np.maximum(stats["n_nonzero"], 1),
        float(cfg.lookback_days),
    )

    is_fallback = (stats["n_days"] < cfg.min_history_days) | (stats["n_nonzero"] < cfg.min_nonzero_days)
    is_regular = (~is_fallback) & (stats["adi"] <= cfg.adi_threshold)
    stats["route_group"] = np.where(
        is_fallback,
        "fallback",
        np.where(is_regular, "regular", "intermittent"),
    )
    return stats


def moving_average_forecast(
    train_df: pd.DataFrame,
    sku_ids: list[str],
    *,
    last_train_date: pd.Timestamp,
    horizon_days: int,
    window_days: int = 28,
) -> pd.DataFrame:
    """Fallback determinístico por média móvel dos últimos 28 dias com bandas não-negativas."""
    if not sku_ids:
        return pd.DataFrame(
            columns=[
                "unique_id",
                "ds",
                "MovingAverage28d",
                "MovingAverage28d-lo-80",
                "MovingAverage28d-hi-80",
                "MovingAverage28d-lo-95",
                "MovingAverage28d-hi-95",
            ]
        )

    sub = train_df[train_df["unique_id"].isin(sku_ids)]
    win_start = last_train_date - pd.Timedelta(days=window_days - 1)
    recent = sub[sub["ds"] >= win_start]

    agg = (
        recent.groupby("unique_id", as_index=False)["y"]
        .agg(mean_val="mean", std_val="std")
        .set_index("unique_id")
        .reindex(sku_ids)
        .fillna(0.0)
        .reset_index()
    )
    future_dates = pd.date_range(last_train_date + pd.Timedelta(days=1), periods=horizon_days, freq="D")

    grid = (
        agg.assign(_key=1)
        .merge(pd.DataFrame({"ds": future_dates, "_key": 1}), on="_key", how="inner")
        .drop(columns=["_key"])
    )
    mean_v = np.clip(grid["mean_val"].to_numpy(dtype=np.float64), 0.0, None)
    std_v = np.maximum(grid["std_val"].to_numpy(dtype=np.float64), mean_v * 0.35)

    grid["MovingAverage28d"] = mean_v
    grid["MovingAverage28d-lo-80"] = np.clip(mean_v - Z_80 * std_v, 0.0, None)
    grid["MovingAverage28d-hi-80"] = np.clip(mean_v + Z_80 * std_v, 0.0, None)
    grid["MovingAverage28d-lo-95"] = np.clip(mean_v - Z_95 * std_v, 0.0, None)
    grid["MovingAverage28d-hi-95"] = np.clip(mean_v + Z_95 * std_v, 0.0, None)
    return cast(pd.DataFrame, grid.drop(columns=["mean_val", "std_val"]))


def enforce_non_negative_quantiles(df: pd.DataFrame) -> pd.DataFrame:
    """Garante previsão >= 0 e ordenação estrita lo_95 <= lo_80 <= forecast_units <= hi_80 <= hi_95."""
    out = df.copy()
    fc = np.clip(np.nan_to_num(out["forecast_units"].to_numpy(dtype=np.float64), nan=0.0), 0.0, None)
    lo80 = np.clip(np.nan_to_num(out["lo_80"].to_numpy(dtype=np.float64), nan=0.0), 0.0, None)
    hi80 = np.clip(np.nan_to_num(out["hi_80"].to_numpy(dtype=np.float64), nan=0.0), 0.0, None)
    lo95 = np.clip(np.nan_to_num(out["lo_95"].to_numpy(dtype=np.float64), nan=0.0), 0.0, None)
    hi95 = np.clip(np.nan_to_num(out["hi_95"].to_numpy(dtype=np.float64), nan=0.0), 0.0, None)

    lo80 = np.minimum(lo80, fc)
    lo95 = np.minimum(lo95, lo80)
    hi80 = np.maximum(hi80, fc)
    hi95 = np.maximum(hi95, hi80)

    out["forecast_units"] = np.round(fc, 2)
    out["lo_80"] = np.round(lo80, 2)
    out["hi_80"] = np.round(hi80, 2)
    out["lo_95"] = np.round(lo95, 2)
    out["hi_95"] = np.round(hi95, 2)
    return out
