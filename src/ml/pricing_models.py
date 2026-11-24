from __future__ import annotations

from typing import Final

import numpy as np
import pandas as pd
from sklearn.linear_model import QuantileRegressor, Ridge

DRIVER_ORDER_NAMES: Final[tuple[tuple[int, str], ...]] = (
    (1, "Porte do Cliente"),
    (2, "Volume do Pedido"),
    (3, "Campanha & Sazonalidade"),
    (4, "Frete CIF & Prazo Porte"),
    (5, "Posicionamento SKU"),
)

FEATURE_COLS: Final[tuple[str, ...]] = (
    "is_size_m",
    "is_size_g",
    "ln_boxes",
    "promo_flag_num",
    "sin_week",
    "cos_week",
    "freight_per_box",
    "pmr_porte",
    "sku_offset",
)

GROUP_INDICES: Final[dict[int, tuple[int, ...]]] = {
    1: (0, 1),
    2: (2,),
    3: (3, 4, 5),
    4: (6, 7),
    5: (8,),
}

MIN_ROWS_FOR_QUANTILE_FIT: Final[int] = 20


def prepare_pricing_features(
    raw_df: pd.DataFrame,
    *,
    freight_by_region: dict[str, float],
    default_freight_per_box: float,
    pmr_by_size: dict[str, float],
) -> pd.DataFrame:
    """Prepara features normativas legítimas por linha sem incluir `sales_rep_id`."""
    if raw_df.empty:
        return pd.DataFrame()

    df = raw_df[
        (raw_df["base_unit_price"] > 0.0) & (raw_df["unit_net_price"] > 0.0) & (raw_df["units"] > 0)
    ].copy()
    if df.empty:
        return pd.DataFrame()

    df["realized_idx"] = (
        df["unit_net_price"].to_numpy(dtype=np.float64) / df["base_unit_price"].to_numpy(dtype=np.float64)
    ) * 100.0

    size_series = df["customer_size"].astype(str)
    df["is_size_m"] = (size_series == "M").astype(np.float64)
    df["is_size_g"] = (size_series == "G").astype(np.float64)
    df["ln_boxes"] = np.log1p(np.maximum(df["boxes"].to_numpy(dtype=np.float64), 0.0))

    promo_raw = df["promo_flag"] if "promo_flag" in df.columns else False
    df["promo_flag_num"] = pd.Series(promo_raw, index=df.index).fillna(False).astype(np.float64)

    dates = pd.to_datetime(df["full_date"])
    iso_week = dates.dt.isocalendar().week.astype(np.float64)
    angle = 2.0 * np.pi * iso_week / 52.0
    df["sin_week"] = np.sin(angle)
    df["cos_week"] = np.cos(angle)

    df["freight_per_box"] = (
        df["region"].astype(str).map(freight_by_region).fillna(default_freight_per_box).astype(np.float64)
    )
    default_pmr = float(pmr_by_size.get("M", 42.0))
    df["pmr_porte"] = size_series.map(pmr_by_size).fillna(default_pmr).astype(np.float64)

    fam_mean = df.groupby("family")["realized_idx"].transform("mean")
    sku_mean = df.groupby("product_id")["realized_idx"].transform("mean")
    df["sku_offset"] = np.clip((sku_mean - fam_mean).to_numpy(dtype=np.float64), -15.0, 15.0)
    return df.reset_index(drop=True)


def fit_family_pricing_models(
    fam_df: pd.DataFrame,
    *,
    freight_ref: float,
    pmr_ref: float,
) -> tuple[pd.DataFrame, Ridge]:
    """Ajusta banda quantílica [P25, P50, P75] e Ridge para Linear SHAP exato."""
    x_mat = fam_df[list(FEATURE_COLS)].to_numpy(dtype=np.float64)
    y_vec = fam_df["realized_idx"].to_numpy(dtype=np.float64)

    ridge = Ridge(alpha=1.0).fit(x_mat, y_vec)
    expected = np.asarray(ridge.predict(x_mat), dtype=np.float64)

    if len(fam_df) >= MIN_ROWS_FOR_QUANTILE_FIT and float(np.std(y_vec)) > 1e-6:
        q25_m = QuantileRegressor(quantile=0.25, alpha=0.01, solver="highs").fit(x_mat, y_vec)
        q50_m = QuantileRegressor(quantile=0.50, alpha=0.01, solver="highs").fit(x_mat, y_vec)
        q75_m = QuantileRegressor(quantile=0.75, alpha=0.01, solver="highs").fit(x_mat, y_vec)
        p25 = np.asarray(q25_m.predict(x_mat), dtype=np.float64)
        p50 = np.asarray(q50_m.predict(x_mat), dtype=np.float64)
        p75 = np.asarray(q75_m.predict(x_mat), dtype=np.float64)
    else:
        q25_c, q50_c, q75_c = np.percentile(y_vec, [25.0, 50.0, 75.0])
        p25 = np.full(len(fam_df), q25_c, dtype=np.float64)
        p50 = np.full(len(fam_df), q50_c, dtype=np.float64)
        p75 = np.full(len(fam_df), q75_c, dtype=np.float64)

    # Garante ordenação monotônica contextual: P25 <= expected <= P75
    band_low = np.minimum(p25, np.minimum(expected, p50))
    band_high = np.maximum(p75, np.maximum(expected, p50))
    band_low = np.clip(band_low, 40.0, 140.0)
    band_expected = np.clip(expected, band_low, band_high)
    band_high = np.clip(band_high, band_expected, 150.0)

    out = fam_df.copy()
    out["pred_band_low_idx"] = band_low
    out["pred_expected_idx"] = band_expected
    out["pred_band_high_idx"] = band_high

    ref_vec = np.array([0.0, 0.0, np.log1p(1.0), 0.0, 0.0, 0.0, freight_ref, pmr_ref, 0.0], dtype=np.float64)
    y_ref = float(ridge.predict(ref_vec.reshape(1, -1))[0])
    coefs = np.asarray(ridge.coef_, dtype=np.float64)
    diffs = x_mat - ref_vec

    for grp_id, col_idxs in GROUP_INDICES.items():
        contrib = np.sum(diffs[:, list(col_idxs)] * coefs[list(col_idxs)], axis=1)
        if grp_id == 1:
            contrib = contrib + (y_ref - 100.0)
        out[f"shap_g{grp_id}"] = contrib

    return out, ridge


def build_driver_rows_for_scope(
    scope_df: pd.DataFrame,
    *,
    scenario_id: str,
    scope_type: str,
    scope_id: str,
    scope_label: str,
    family: str,
    snapshot_date: str,
) -> list[dict[str, object]]:
    """Agrega os 5 drivers Linear SHAP mantendo fechamento exato a partir de base_idx=100."""
    expected_idx = float(scope_df["pred_expected_idx"].mean())
    realized_idx = float(scope_df["realized_idx"].mean())

    shaps = [float(scope_df[f"shap_g{idx}"].mean()) for idx, _ in DRIVER_ORDER_NAMES]
    residual = (expected_idx - 100.0) - sum(shaps)
    shaps[0] += residual

    unjustified_gap = round(realized_idx - expected_idx, 4)
    rows: list[dict[str, object]] = []
    for (order, name), val in zip(DRIVER_ORDER_NAMES, shaps, strict=True):
        rows.append(
            {
                "scenario_id": scenario_id,
                "scope_type": scope_type,
                "scope_id": scope_id,
                "scope_label": scope_label,
                "family": family,
                "base_idx": 100.0,
                "expected_idx": round(expected_idx, 4),
                "realized_idx": round(realized_idx, 4),
                "unjustified_gap_pp": unjustified_gap,
                "driver_order": order,
                "driver_name": name,
                "shap_impact_pp": round(val, 6),
                "snapshot_date": snapshot_date,
            }
        )
    return rows
