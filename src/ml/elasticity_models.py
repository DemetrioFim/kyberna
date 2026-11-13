from __future__ import annotations

from typing import Final

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.linear_model import HuberRegressor, LinearRegression

DEFAULT_BOOTSTRAP_SAMPLES: Final[int] = 200
DEFAULT_SEED: Final[int] = 42
PRICE_CURVE_GRID: Final[np.ndarray] = np.round(np.linspace(0.75, 1.30, 23), 4)
OPTIMAL_PRICE_DELTA_GRID: Final[np.ndarray] = np.round(np.linspace(-0.25, 0.25, 51), 4)
HUBER_MAX_ITER: Final[int] = 500
MIN_ROWS_FOR_ROBUST_FIT: Final[int] = 15


def prepare_family_elasticity_features(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Prepara features normalizadas por SKU e cliente removendo viés de porte e sazonalidade."""
    if raw_df.empty:
        return pd.DataFrame()

    df = raw_df[
        (raw_df["unit_list_price"] > 0.0)
        & (raw_df["units"] > 0)
        & (raw_df["product_id"].notna())
        & (raw_df["customer_id"].notna())
    ].copy()
    if df.empty:
        return pd.DataFrame()

    med_sku_price = df.groupby("product_id")["unit_list_price"].transform("median")
    df = df[med_sku_price > 0.0].copy()
    med_sku_price = df.groupby("product_id")["unit_list_price"].transform("median")

    df["price_ratio"] = df["unit_list_price"].to_numpy(dtype=np.float64) / med_sku_price.to_numpy(
        dtype=np.float64
    )
    df["ln_p"] = np.log(df["price_ratio"].to_numpy(dtype=np.float64))

    ln_u = np.log(df["units"].to_numpy(dtype=np.float64))
    df["_ln_u"] = ln_u
    ln_u_sku = df["_ln_u"] - df.groupby("product_id")["_ln_u"].transform("mean")
    df["_ln_u_sku"] = ln_u_sku
    ln_u_adj = df["_ln_u_sku"] - df.groupby("customer_id")["_ln_u_sku"].transform("mean")

    df["ln_q"] = ln_u_adj.to_numpy(dtype=np.float64)
    df["q_rel"] = np.exp(df["ln_q"].to_numpy(dtype=np.float64))

    dates = pd.to_datetime(df["full_date"])
    iso_week = dates.dt.isocalendar().week.astype(np.float64)
    angle = 2.0 * np.pi * iso_week / 52.0
    df["sin_week"] = np.sin(angle)
    df["cos_week"] = np.cos(angle)

    return df.drop(columns=["_ln_u", "_ln_u_sku"]).reset_index(drop=True)


def fit_log_log_bootstrap(
    features: np.ndarray,
    target: np.ndarray,
    *,
    bootstrap_samples: int = DEFAULT_BOOTSTRAP_SAMPLES,
    seed: int = DEFAULT_SEED,
) -> dict[str, float]:
    """Ajusta regressão log-log robusta (Huber) com intervalo de confiança via bootstrap."""
    n_obs = len(target)
    if n_obs < 5 or float(np.std(features[:, 0])) < 1e-6:
        return {
            "beta_hat": 0.0,
            "ci_95_low": 0.0,
            "ci_95_high": 0.0,
            "r2_score": 0.0,
        }

    use_huber = n_obs >= MIN_ROWS_FOR_ROBUST_FIT
    if use_huber:
        model: HuberRegressor | LinearRegression = HuberRegressor(max_iter=HUBER_MAX_ITER).fit(
            features, target
        )
    else:
        model = LinearRegression().fit(features, target)

    beta_hat = float(model.coef_[0])
    y_pred = model.predict(features)
    var_target = float(np.var(target))
    r2_val = float(max(0.0, 1.0 - float(np.var(target - y_pred)) / var_target)) if var_target > 1e-12 else 0.0

    rng = np.random.default_rng(seed)
    n_boot = max(int(bootstrap_samples), 1)
    boot_betas = np.empty(n_boot, dtype=np.float64)

    for idx_b in range(n_boot):
        sample_idx = rng.integers(0, n_obs, size=n_obs)
        x_b = features[sample_idx]
        y_b = target[sample_idx]
        if float(np.std(x_b[:, 0])) < 1e-8:
            boot_betas[idx_b] = beta_hat
            continue
        boot_model: HuberRegressor | LinearRegression = (
            HuberRegressor(max_iter=HUBER_MAX_ITER).fit(x_b, y_b)
            if use_huber
            else LinearRegression().fit(x_b, y_b)
        )
        boot_betas[idx_b] = float(boot_model.coef_[0])

    ci_low = float(np.percentile(boot_betas, 2.5))
    ci_high = float(np.percentile(boot_betas, 97.5))
    return {
        "beta_hat": round(beta_hat, 4),
        "ci_95_low": round(min(ci_low, ci_high), 4),
        "ci_95_high": round(max(ci_low, ci_high), 4),
        "r2_score": round(r2_val, 4),
    }


def fit_monotonic_lgbm(
    features_lgbm: np.ndarray,
    q_rel: np.ndarray,
    *,
    seed: int = DEFAULT_SEED,
) -> LGBMRegressor:
    """Treina LGBMRegressor com restrição monotônica estritamente não-crescente no preço."""
    model = LGBMRegressor(
        monotone_constraints=[-1, 0, 0],
        n_estimators=80,
        learning_rate=0.05,
        random_state=seed,
        verbose=-1,
        n_jobs=1,
    )
    model.fit(features_lgbm, q_rel)
    return model


def predict_price_response_curve(
    model: LGBMRegressor,
    price_ratios: np.ndarray | None = None,
) -> np.ndarray:
    """Avalia curva de resposta de quantidade relativa sobre uma grade crescente de preços."""
    ratios = PRICE_CURVE_GRID if price_ratios is None else np.asarray(price_ratios, dtype=np.float64)
    grid = np.column_stack([ratios, np.zeros(len(ratios)), np.ones(len(ratios))])
    return np.asarray(model.predict(grid), dtype=np.float64)


def compute_optimal_price_change_pct(beta_hat: float, avg_margin_ratio: float) -> float:
    """Encontra variação de preço em [-25%, +25%] que maximiza a margem de contribuição esperada."""
    cost_ratio = float(np.clip(1.0 - avg_margin_ratio, 0.15, 0.85))
    price_mult = 1.0 + OPTIMAL_PRICE_DELTA_GRID
    unit_margin = price_mult - cost_ratio
    expected_profit = np.where(
        unit_margin > 0.0,
        unit_margin * np.power(price_mult, beta_hat),
        -1e9,
    )
    best_idx = int(np.argmax(expected_profit))
    return float(OPTIMAL_PRICE_DELTA_GRID[best_idx])


def build_elasticity_prescription(family: str, beta_hat: float, optimal_dp: float) -> str:
    """Gera texto prescritivo B2B objetivo conforme elasticidade estimada e ponto ótimo."""
    classification = "Elástica" if beta_hat < -1.0 else "Inelástica"
    opt_pct = optimal_dp * 100.0
    if classification == "Elástica" and optimal_dp <= -0.02:
        return (
            f"{family}: demanda {classification} (beta={beta_hat:.2f}); ações promocionais seletivas "
            f"próximas de {opt_pct:+.0f}% tendem a ampliar giro e massa de margem."
        )
    if classification == "Inelástica" and optimal_dp >= 0.02:
        return (
            f"{family}: demanda {classification} (beta={beta_hat:.2f}); há espaço para recomposição "
            f"gradual de tabela (ótimo até {opt_pct:+.0f}%) preservando volume."
        )
    return (
        f"{family}: demanda {classification} (beta={beta_hat:.2f}); preço atual próximo ao ótimo "
        f"({opt_pct:+.0f}%), priorizar disciplina de descontos e mix."
    )
