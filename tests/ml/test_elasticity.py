from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

from src.cli import app
from src.core.paths import get_duckdb_path
from src.ml.elasticity import (
    build_price_elasticity_mart,
    check_lgbm_monotonicity,
    fit_family_elasticity_models,
    load_elasticity_ground_truth,
    load_elasticity_sales_frame,
)
from src.ml.elasticity_models import compute_optimal_price_change_pct, predict_price_response_curve

runner = CliRunner()


def _make_synthetic_elastic_sales(
    *,
    beta_elastic: float = -1.65,
    beta_inelastic: float = -0.55,
    seed: int = 42,
) -> pd.DataFrame:
    """Gera base transacional sintética controlada com elasticidade exata conhecida."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=104, freq="7D")
    rows: list[dict[str, object]] = []

    families = [
        ("Linha Escolar", beta_elastic, "SKU-E1", 50.0, 22.0),
        ("Brinquedos de Madeira", beta_inelastic, "SKU-M1", 80.0, 32.0),
    ]
    for family, beta, sku, base_p, unit_cost in families:
        for cust_idx in range(5):
            cust_mult = 1.0 + 0.35 * cust_idx
            for d in dates:
                delta_p = float(rng.choice([0.0, 0.0, 0.0, -0.15, -0.10, 0.08]))
                p_list = round(base_p * (1.0 + delta_p), 2)
                noise = float(rng.normal(0.0, 0.02))
                units = max(1, round(20.0 * cust_mult * ((p_list / base_p) ** beta) * np.exp(noise)))
                net_rev = round(units * p_list * 0.85, 2)
                cogs = round(units * unit_cost, 2)
                rows.append(
                    {
                        "scenario_id": "c1_toys",
                        "product_id": sku,
                        "family": family,
                        "customer_id": f"CLI-{cust_idx}",
                        "full_date": d,
                        "units": units,
                        "unit_list_price": p_list,
                        "unit_net_price": p_list * 0.92,
                        "net_revenue": net_rev,
                        "cogs": cogs,
                        "contribution_margin": round(net_rev - cogs, 2),
                    }
                )
    return pd.DataFrame(rows)


def test_fit_family_elasticity_synthetic_recovery_and_monotonicity() -> None:
    """Valida recuperação de elasticidade conhecida, classificação e monotonicidade LGBM."""
    df_syn = _make_synthetic_elastic_sales(beta_elastic=-1.65, beta_inelastic=-0.55)
    gt_map = {"Linha Escolar": -1.65, "Brinquedos de Madeira": -0.55}

    out_df, lgbm_models = fit_family_elasticity_models(
        df_syn,
        snapshot_date="2024-12-31",
        scenario_id="c1_toys",
        ground_truth_map=gt_map,
        bootstrap_samples=80,
        seed=42,
    )

    by_fam = out_df.set_index("family")
    assert float(by_fam.loc["Linha Escolar", "abs_error"]) < 0.15
    assert float(by_fam.loc["Brinquedos de Madeira", "abs_error"]) < 0.15
    assert by_fam.loc["Linha Escolar", "elasticity_classification"] == "Elástica"
    assert by_fam.loc["Brinquedos de Madeira", "elasticity_classification"] == "Inelástica"

    mono = check_lgbm_monotonicity(lgbm_models)
    assert all(mono.values())
    for model in lgbm_models.values():
        curve = predict_price_response_curve(model)
        assert np.all(np.diff(curve) <= 1e-9)

    assert compute_optimal_price_change_pct(beta_hat=-3.0, avg_margin_ratio=0.50) < 0.0
    assert compute_optimal_price_change_pct(beta_hat=-0.5, avg_margin_ratio=0.50) > 0.0


def _clone_c1_elasticity_inputs(target_db: Path, source_db: Path) -> None:
    """Clona tabelas necessárias do C1 para DuckDB isolado sem disputar lock no arquivo principal."""
    src = duckdb.connect(str(source_db), read_only=True)
    try:
        fact_sales = src.execute("SELECT * FROM gold.fact_sales WHERE scenario_id = 'c1_toys'").df()
        dim_product = src.execute("SELECT * FROM gold.dim_product").df()
        dim_date = src.execute("SELECT * FROM gold.dim_date").df()
        gt_df = src.execute("SELECT * FROM silver.elasticity_ground_truth").df()
    finally:
        src.close()

    dst = duckdb.connect(str(target_db))
    try:
        dst.execute("CREATE SCHEMA IF NOT EXISTS gold")
        dst.execute("CREATE SCHEMA IF NOT EXISTS silver")
        dst.execute("CREATE SCHEMA IF NOT EXISTS c1_toys")
        for qualified, df in [
            ("gold.fact_sales", fact_sales),
            ("gold.dim_product", dim_product),
            ("gold.dim_date", dim_date),
            ("silver.elasticity_ground_truth", gt_df),
        ]:
            dst.register("_tmp_el_clone", df)
            dst.execute(f"CREATE TABLE {qualified} AS SELECT * FROM _tmp_el_clone")
            dst.unregister("_tmp_el_clone")
    finally:
        dst.close()


def test_build_price_elasticity_mart_c1_dod_and_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DoD M4-S3: |beta_hat - beta_true| < 0.30 em 100%, IC95 >= 80%, LGBM monotônico e CLI."""
    source_db = get_duckdb_path()
    test_db = tmp_path / "test_elasticity.duckdb"
    _clone_c1_elasticity_inputs(test_db, source_db)

    out_parquet = tmp_path / "mart_price_elasticity.parquet"
    monkeypatch.setattr("src.ml.elasticity.gold_snapshot_path", lambda s, t: out_parquet)
    monkeypatch.setattr("src.cli_ml.get_duckdb_path", lambda: test_db)

    con = duckdb.connect(str(test_db))
    try:
        df_mart = build_price_elasticity_mart(con, scenario_id="c1_toys", bootstrap_samples=200)
        sales_df, snapshot_date = load_elasticity_sales_frame(con, scenario_id="c1_toys")
        gt_map = load_elasticity_ground_truth(con)
        _, lgbm_models = fit_family_elasticity_models(
            sales_df,
            snapshot_date=snapshot_date,
            scenario_id="c1_toys",
            ground_truth_map=gt_map,
            bootstrap_samples=50,
        )
    finally:
        con.close()

    assert len(df_mart) == 7
    assert out_parquet.exists()
    assert df_mart["abs_error"].notna().all()
    assert (df_mart["abs_error"] < 0.30).all()

    covered = (
        (df_mart["ci_95_low"] <= df_mart["beta_true"]) & (df_mart["beta_true"] <= df_mart["ci_95_high"])
    ).mean()
    assert float(covered) >= 0.80

    mono = check_lgbm_monotonicity(lgbm_models)
    assert all(mono.values())

    cli_res = runner.invoke(app, ["ml", "elasticity", "--scenario", "c1_toys", "-b", "50"])
    assert cli_res.exit_code == 0, cli_res.output
    assert "Elasticidade-Preço estimada para 'c1_toys'" in cli_res.output
