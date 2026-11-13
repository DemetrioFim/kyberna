from __future__ import annotations

from datetime import date, datetime
from typing import Final

import duckdb
import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor

from src.core.logging import get_logger, timed_step
from src.core.paths import gold_snapshot_path
from src.core.types import ScenarioId
from src.etl.contracts import GoldPriceElasticitySchema, validate_contract
from src.ml.elasticity_models import (
    DEFAULT_BOOTSTRAP_SAMPLES,
    DEFAULT_SEED,
    build_elasticity_prescription,
    compute_optimal_price_change_pct,
    fit_log_log_bootstrap,
    fit_monotonic_lgbm,
    predict_price_response_curve,
    prepare_family_elasticity_features,
)
from src.ml.features import resolve_as_of_date

logger = get_logger(__name__)

DEFAULT_SCENARIO: Final[ScenarioId] = "c1_toys"
OUTPUT_COLUMNS: Final[list[str]] = [
    "scenario_id",
    "family",
    "beta_hat",
    "beta_true",
    "abs_error",
    "ci_95_low",
    "ci_95_high",
    "r2_score",
    "optimal_price_change_pct",
    "elasticity_classification",
    "prescription_text",
    "snapshot_date",
]


def load_elasticity_ground_truth(con: duckdb.DuckDBPyConnection) -> dict[str, float]:
    """Lê parâmetros-verdade de elasticidade (`silver.elasticity_ground_truth`) se existirem."""
    exists = con.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_schema = 'silver' AND table_name = 'elasticity_ground_truth'
        """
    ).fetchone()
    if not exists or int(exists[0]) == 0:
        return {}

    gt_df = con.execute("SELECT family, beta_true FROM silver.elasticity_ground_truth").df()
    if gt_df.empty:
        return {}
    return {str(row["family"]): float(row["beta_true"]) for _, row in gt_df.iterrows()}


def load_elasticity_sales_frame(
    con: duckdb.DuckDBPyConnection,
    *,
    as_of_date: date | datetime | str | None = None,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
) -> tuple[pd.DataFrame, str]:
    """Carrega transações da camada Gold até `as_of_date` para estimação de elasticidade."""
    resolved_date = resolve_as_of_date(con, as_of_date=as_of_date, scenario_id=scenario_id)
    as_of_key = int(resolved_date.strftime("%Y%m%d"))

    sql = """
    SELECT
        f.scenario_id,
        f.product_id,
        p.family,
        f.customer_id,
        d.full_date,
        f.units,
        f.unit_list_price,
        f.unit_net_price,
        f.net_revenue,
        f.cogs,
        f.contribution_margin
    FROM gold.fact_sales f
    JOIN gold.dim_product p
      ON f.product_id = p.product_id
    JOIN gold.dim_date d
      ON f.date_key = d.date_key
    WHERE f.scenario_id = ?
      AND f.date_key <= ?
      AND f.units > 0
      AND f.unit_list_price > 0
    ORDER BY d.full_date, f.product_id, f.customer_id
    """
    df = con.execute(sql, [scenario_id, as_of_key]).df()
    if df.empty:
        msg = f"Nenhuma transação encontrada em `gold.fact_sales` para o cenário '{scenario_id}'."
        raise ValueError(msg)

    return df, resolved_date.strftime("%Y-%m-%d")


def fit_family_elasticity_models(
    sales_df: pd.DataFrame,
    *,
    snapshot_date: str,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
    ground_truth_map: dict[str, float] | None = None,
    bootstrap_samples: int = DEFAULT_BOOTSTRAP_SAMPLES,
    seed: int = DEFAULT_SEED,
) -> tuple[pd.DataFrame, dict[str, LGBMRegressor]]:
    """Estima elasticidade Log-Log + Bootstrap e curva monotônica LGBM por família."""
    prep_df = prepare_family_elasticity_features(sales_df)
    if prep_df.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS), {}

    gt_map = ground_truth_map or {}
    rows: list[dict[str, object]] = []
    lgbm_models: dict[str, LGBMRegressor] = {}

    for fam_idx, (family_val, fam_df) in enumerate(prep_df.groupby("family", sort=True)):
        family = str(family_val)
        x_lin = fam_df[["ln_p", "sin_week", "cos_week"]].to_numpy(dtype=np.float64)
        y_lin = fam_df["ln_q"].to_numpy(dtype=np.float64)

        stats = fit_log_log_bootstrap(
            x_lin,
            y_lin,
            bootstrap_samples=bootstrap_samples,
            seed=seed + fam_idx,
        )

        x_lgbm = fam_df[["price_ratio", "sin_week", "cos_week"]].to_numpy(dtype=np.float64)
        q_rel = fam_df["q_rel"].to_numpy(dtype=np.float64)
        lgbm_model = fit_monotonic_lgbm(x_lgbm, q_rel, seed=seed + fam_idx)
        lgbm_models[family] = lgbm_model

        total_net = float(fam_df["net_revenue"].sum())
        total_cogs = float(fam_df["cogs"].sum())
        avg_margin_ratio = ((total_net - total_cogs) / total_net) if total_net > 0.0 else 0.45

        beta_hat = float(stats["beta_hat"])
        beta_true = gt_map.get(family)
        abs_error = round(abs(beta_hat - beta_true), 4) if beta_true is not None else None
        classification = "Elástica" if beta_hat < -1.0 else "Inelástica"
        optimal_dp = compute_optimal_price_change_pct(beta_hat, avg_margin_ratio)

        rows.append(
            {
                "scenario_id": scenario_id,
                "family": family,
                "beta_hat": beta_hat,
                "beta_true": round(beta_true, 4) if beta_true is not None else None,
                "abs_error": abs_error,
                "ci_95_low": float(stats["ci_95_low"]),
                "ci_95_high": float(stats["ci_95_high"]),
                "r2_score": float(stats["r2_score"]),
                "optimal_price_change_pct": optimal_dp,
                "elasticity_classification": classification,
                "prescription_text": build_elasticity_prescription(family, beta_hat, optimal_dp),
                "snapshot_date": snapshot_date,
            }
        )

    out_df = pd.DataFrame(rows, columns=OUTPUT_COLUMNS).sort_values("beta_hat").reset_index(drop=True)
    return out_df, lgbm_models


def check_lgbm_monotonicity(lgbm_models: dict[str, LGBMRegressor]) -> dict[str, bool]:
    """Verifica se a curva prevista por cada LGBMRegressor é estritamente não-crescente no preço."""
    results: dict[str, bool] = {}
    for family, model in lgbm_models.items():
        curve = predict_price_response_curve(model)
        results[family] = bool(np.all(np.diff(curve) <= 1e-9))
    return results


def build_price_elasticity_mart(
    con: duckdb.DuckDBPyConnection,
    *,
    as_of_date: date | datetime | str | None = None,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
    bootstrap_samples: int = DEFAULT_BOOTSTRAP_SAMPLES,
    seed: int = DEFAULT_SEED,
) -> pd.DataFrame:
    """Materializa e valida o mart `gold.mart_price_elasticity` no DuckDB e Parquet."""
    with timed_step("build_price_elasticity_mart"):
        sales_df, snapshot_date = load_elasticity_sales_frame(
            con,
            as_of_date=as_of_date,
            scenario_id=scenario_id,
        )
        gt_map = load_elasticity_ground_truth(con)

        raw_df, lgbm_models = fit_family_elasticity_models(
            sales_df,
            snapshot_date=snapshot_date,
            scenario_id=scenario_id,
            ground_truth_map=gt_map,
            bootstrap_samples=bootstrap_samples,
            seed=seed,
        )
        mono_checks = check_lgbm_monotonicity(lgbm_models)
        if not all(mono_checks.values()):
            failed = [fam for fam, ok in mono_checks.items() if not ok]
            msg = f"Curva LGBM violou monotonicidade nas famílias: {failed}"
            raise ValueError(msg)

        validated_df = validate_contract(
            raw_df,
            GoldPriceElasticitySchema,
            layer="Gold (mart_price_elasticity)",
        )

        con.execute("CREATE SCHEMA IF NOT EXISTS gold")
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {scenario_id}")
        con.register("temp_mart_price_elasticity", validated_df)
        con.execute(
            f"CREATE OR REPLACE TABLE {scenario_id}.mart_price_elasticity "
            "AS SELECT * FROM temp_mart_price_elasticity"
        )
        con.execute(
            "CREATE OR REPLACE TABLE gold.mart_price_elasticity AS SELECT * FROM temp_mart_price_elasticity"
        )
        con.unregister("temp_mart_price_elasticity")

        parquet_p = gold_snapshot_path(scenario_id, "mart_price_elasticity")
        parquet_p.parent.mkdir(parents=True, exist_ok=True)
        con.execute(
            f"COPY gold.mart_price_elasticity TO '{parquet_p.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)"
        )

        max_err = (
            float(validated_df["abs_error"].dropna().max())
            if validated_df["abs_error"].notna().any()
            else 0.0
        )
        logger.info(
            "Mart `mart_price_elasticity` materializado para '%s': %d famílias "
            "(erro abs máx=%.4f | monotonicidade LGBM=100%%) em %s.",
            scenario_id,
            len(validated_df),
            max_err,
            parquet_p,
        )
        return validated_df
