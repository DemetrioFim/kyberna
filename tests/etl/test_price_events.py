from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

from src.cli import app
from src.etl.contracts import (
    SilverElasticityGroundTruthSchema,
    SilverSalesSchema,
    validate_contract,
)
from src.etl.lake import get_duckdb_connection, read_parquet
from src.etl.silver.clean import build_silver_sales
from src.etl.silver.price_events import (
    apply_price_events,
    load_price_events_config,
    map_categories_to_families,
)

runner = CliRunner()

EXPECTED_C1_FAMILIES = {
    "Linha Escolar",
    "Jogos Educativos",
    "Quebra-Cabeças",
    "Primeira Infância",
    "Jogos de Tabuleiro",
    "Pelúcias",
    "Brinquedos de Madeira",
    "Outros",
}


def test_load_elasticity_ground_truth_config() -> None:
    """Valida leitura da seção thresholds.elasticity_ground_truth de config/pipeline.yaml."""
    cfg = load_price_events_config()
    assert set(cfg.elasticity_ground_truth.keys()) == EXPECTED_C1_FAMILIES
    assert cfg.elasticity_ground_truth["Linha Escolar"] == pytest.approx(-1.8)
    assert cfg.elasticity_ground_truth["Jogos Educativos"] == pytest.approx(-1.2)
    assert cfg.elasticity_ground_truth["Brinquedos de Madeira"] == pytest.approx(-0.6)
    assert cfg.promo_fraction_target == pytest.approx(0.12)
    assert cfg.markup_fraction_target == pytest.approx(0.06)


def test_price_events_injection_dod_and_ols_recovery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Valida DoD do M4-D1: fração afetada, variação de volume, trava de custo e OLS por família."""
    monkeypatch.setenv("KYBERNA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("KYBERNA_DUCKDB_PATH", str(tmp_path / "data" / "kyberna.duckdb"))

    db_path = tmp_path / "data" / "kyberna.duckdb"
    con = get_duckdb_connection(db_path=db_path)
    try:
        build_silver_sales(db_con=con, base_dir=tmp_path, sample=True)
        sales_parquet, meta = apply_price_events(db_con=con, seed=42, base_dir=tmp_path)

        assert sales_parquet.exists()
        assert meta["total_rows"] >= 19500
        assert 0.10 <= float(meta["affected_fraction"]) <= 0.25
        assert abs(float(meta["volume_change_pct"])) < 5.0

        df_sales = read_parquet(sales_parquet)
        validate_contract(df_sales, SilverSalesSchema, layer="silver")

        assert {"promo_flag", "price_event_id", "original_unit_price", "original_units"}.issubset(
            df_sales.columns
        )

        # Trava de preço >= unit_cost * 0.55 nos eventos injetados
        affected = df_sales[df_sales["price_event_id"].notna()].copy()
        assert not affected.empty
        assert bool((affected["unit_price"] >= np.round(affected["unit_cost"] * 0.55, 2) - 1e-6).all())

        # Valida ground truth persistido no DuckDB e em Parquet
        df_gt_db = con.execute("SELECT * FROM silver.elasticity_ground_truth").df()
        validate_contract(df_gt_db, SilverElasticityGroundTruthSchema, layer="silver")
        assert set(df_gt_db["family"]) == EXPECTED_C1_FAMILIES

        gt_parquet = tmp_path / "data" / "silver" / "elasticity_ground_truth.parquet"
        assert gt_parquet.exists()

        # Recuperação OLS simples por família: |beta_hat - beta_true| < 0.25
        cfg = load_price_events_config()
        affected["family"] = map_categories_to_families(affected["category_name"])
        affected["p_ratio"] = affected["unit_price"] / affected["original_unit_price"]
        affected["q_ratio"] = affected["units"] / affected["original_units"]

        families_checked = 0
        for family, grp in affected.groupby("family"):
            if len(grp) < 10:
                continue
            p_ratio = grp["p_ratio"].to_numpy(dtype=np.float64)
            q_ratio = grp["q_ratio"].to_numpy(dtype=np.float64)
            beta_ols = float(np.polyfit(np.log(p_ratio), np.log(q_ratio), 1)[0])
            beta_true = cfg.elasticity_ground_truth[str(family)]
            assert abs(beta_ols - beta_true) < 0.25, (
                f"Família '{family}': beta_ols={beta_ols:.3f} vs beta_true={beta_true:.3f}"
            )
            families_checked += 1

        present_families = set(map_categories_to_families(df_sales["category_name"]).unique())
        assert len(present_families) >= 7
        assert families_checked == len(present_families)
    finally:
        con.close()


def test_price_events_idempotency_and_determinism(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Garante idempotência (reexecução não acumula descontos) e determinismo estrito por seed."""
    root_a = tmp_path / "run_a"
    root_b = tmp_path / "run_b"
    monkeypatch.setenv("KYBERNA_DATA_DIR", str(root_a / "data"))
    monkeypatch.setenv("KYBERNA_DUCKDB_PATH", str(root_a / "data" / "kyberna.duckdb"))

    con_a = get_duckdb_connection(db_path=root_a / "data" / "kyberna.duckdb")
    con_b = get_duckdb_connection(db_path=root_b / "data" / "kyberna.duckdb")
    try:
        silver_base_parquet, _ = build_silver_sales(db_con=con_a, base_dir=root_a, sample=True)
        df_base = read_parquet(silver_base_parquet)

        parquet_a1, meta_a1 = apply_price_events(db_con=con_a, seed=42, base_dir=root_a)
        df_a1 = read_parquet(parquet_a1)

        # Segunda execução sobre o mesmo banco (idempotência)
        parquet_a2, meta_a2 = apply_price_events(db_con=con_a, seed=42, base_dir=root_a)
        df_a2 = read_parquet(parquet_a2)

        assert meta_a1["affected_rows"] == meta_a2["affected_rows"]
        assert meta_a1["adjusted_volume"] == meta_a2["adjusted_volume"]
        pd.testing.assert_frame_equal(df_a1, df_a2)

        # Execução independente em outro banco com a mesma entrada base e seed (determinismo)
        con_b.execute("CREATE SCHEMA IF NOT EXISTS silver")
        con_b.register("temp_silver_base", df_base)
        con_b.execute("CREATE OR REPLACE TABLE silver.sales AS SELECT * FROM temp_silver_base")
        con_b.unregister("temp_silver_base")

        parquet_b, _ = apply_price_events(db_con=con_b, seed=42, base_dir=root_b)
        df_b = read_parquet(parquet_b)

        pd.testing.assert_frame_equal(df_a1, df_b)
    finally:
        con_a.close()
        con_b.close()


def test_cli_silver_price_events_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Valida comando CLI 'kyberna silver price-events --seed 42' em banco isolado."""
    monkeypatch.setenv("KYBERNA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("KYBERNA_DUCKDB_PATH", str(tmp_path / "data" / "kyberna.duckdb"))

    build_res = runner.invoke(app, ["silver", "build", "--sample"])
    assert build_res.exit_code == 0, build_res.output
    assert "Eventos de preço aplicados:" in build_res.output

    pe_res = runner.invoke(app, ["silver", "price-events", "--seed", "42"])
    assert pe_res.exit_code == 0, pe_res.output
    assert "Eventos de preço aplicados em" in pe_res.output
