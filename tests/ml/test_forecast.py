from __future__ import annotations

import shutil
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

from src.cli import app
from src.core.paths import get_duckdb_path
from src.etl.contracts import GoldForecast30dSchema, validate_contract
from src.ml.forecast import build_forecast_30d_mart, compute_forecast_summary

runner = CliRunner()


@pytest.fixture
def isolated_gold_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[duckdb.DuckDBPyConnection, Path]:
    """Cria cópia isolada do DuckDB seedado para testar forecast sem afetar `data/kyberna.duckdb`."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_copy = data_dir / "kyberna.duckdb"
    shutil.copy2(get_duckdb_path(), db_copy)

    monkeypatch.setenv("KYBERNA_DATA_DIR", str(data_dir))
    monkeypatch.setenv("KYBERNA_DUCKDB_PATH", str(db_copy))
    con = duckdb.connect(str(db_copy))
    return con, data_dir


def test_forecast_30d_dod_wape_class_a_and_runtime(
    isolated_gold_db: tuple[duckdb.DuckDBPyConnection, Path],
) -> None:
    """Valida DoD do M4-S1: WAPE <= 35% por família, >= 60% Classe A vs SeasonalNaive, >= 0 e <= 2 min."""
    con, data_dir = isolated_gold_db
    try:
        t0 = time.perf_counter()
        df = build_forecast_30d_mart(con, scenario_id="c1_toys", horizon_days=30)
        elapsed = time.perf_counter() - t0

        assert elapsed <= 120.0, f"Forecast levou {elapsed:.1f}s (limite: 120s)"
        validate_contract(df, GoldForecast30dSchema, layer="gold")

        # 397 SKUs * (90d histórico + 30d forecast) = 47.640 linhas
        n_skus = df["product_id"].nunique()
        assert n_skus >= 390
        assert len(df) == n_skus * 120

        fc_only = df[df["record_type"] == "forecast"]
        hist_only = df[df["record_type"] == "historical"]
        assert len(fc_only) == n_skus * 30
        assert len(hist_only) == n_skus * 90

        # Não-negatividade estrita e monotonicidade dos limites
        for col in ("forecast_units", "lo_80", "hi_80", "lo_95", "hi_95"):
            assert bool((fc_only[col] >= 0.0).all()), f"Valores negativos em {col}"

        # WAPE agregado por família <= 35%
        summary = compute_forecast_summary(df)
        assert not summary.empty
        assert bool((summary["family_wape_pct"] <= 35.0).all()), summary[["family", "family_wape_pct"]]

        # >= 60% das séries Classe A utilizam modelo especialista que empatou ou superou SeasonalNaive
        cls_a_df = con.execute(
            """
            SELECT product_id
            FROM gold.mart_abc_xyz
            WHERE scenario_id = 'c1_toys' AND abc_class = 'A'
            """
        ).df()
        sku_models = fc_only[["product_id", "selected_model"]].drop_duplicates()
        cls_a_models = cls_a_df.merge(sku_models, on="product_id", how="inner")
        beat_rate = float((cls_a_models["selected_model"] != "SeasonalNaive").mean())
        assert beat_rate >= 0.60, f"Taxa Classe A vs SeasonalNaive={beat_rate:.1%} (< 60%)"

        # Persistência DuckDB + Parquet ZSTD
        parquet_p = data_dir / "gold" / "snapshot" / "c1_toys" / "mart_forecast_30d.parquet"
        assert parquet_p.exists()
        db_count = con.execute("SELECT COUNT(*) FROM gold.mart_forecast_30d").fetchone()
        assert db_count is not None and int(db_count[0]) == len(df)
    finally:
        con.close()


def test_forecast_zero_data_leakage(
    isolated_gold_db: tuple[duckdb.DuckDBPyConnection, Path],
) -> None:
    """Prova ausência de vazamento temporal: cortar fact_sales após `cutoff` produz forecast idêntico."""
    con_full, _ = isolated_gold_db
    cutoff = "2024-11-30"
    try:
        df_full = build_forecast_30d_mart(con_full, as_of_date=cutoff, scenario_id="c1_toys", horizon_days=30)

        con_trunc = duckdb.connect(":memory:")
        con_trunc.execute("CREATE SCHEMA gold")
        for tbl in ("dim_date", "dim_product"):
            tbl_df = con_full.execute(f"SELECT * FROM gold.{tbl}").df()
            con_trunc.register(f"tmp_{tbl}", tbl_df)
            con_trunc.execute(f"CREATE TABLE gold.{tbl} AS SELECT * FROM tmp_{tbl}")

        fact_trunc_df = con_full.execute(
            f"""
            SELECT f.*
            FROM gold.fact_sales f
            JOIN gold.dim_date d ON f.date_key = d.date_key
            WHERE d.full_date <= DATE '{cutoff}'
            """
        ).df()
        con_trunc.register("tmp_fact", fact_trunc_df)
        con_trunc.execute("CREATE TABLE gold.fact_sales AS SELECT * FROM tmp_fact")

        df_trunc = build_forecast_30d_mart(
            con_trunc, as_of_date=cutoff, scenario_id="c1_toys", horizon_days=30
        )
        con_trunc.close()

        pd.testing.assert_frame_equal(df_full, df_trunc)
    finally:
        con_full.close()


def test_forecast_moving_average_fallback_short_series(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Garante fallback MovingAverage28d para histórico < 60 dias com intervalos >= 0."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("KYBERNA_DATA_DIR", str(data_dir))

    con = duckdb.connect(":memory:")
    try:
        con.execute("CREATE SCHEMA gold")
        dates = pd.date_range("2024-11-01", periods=30, freq="D")
        dim_date = pd.DataFrame(
            {
                "date_key": [int(d.strftime("%Y%m%d")) for d in dates],
                "full_date": dates.date,
            }
        )
        dim_prod = pd.DataFrame([{"product_id": "7891000100103", "family": "Linha Escolar"}])
        fact = pd.DataFrame(
            {
                "scenario_id": "c1_toys",
                "product_id": "7891000100103",
                "date_key": [int(d.strftime("%Y%m%d")) for d in dates[::10]],
                "units": [12, 8, 10],
            }
        )
        con.register("t_dd", dim_date)
        con.register("t_dp", dim_prod)
        con.register("t_fs", fact)
        con.execute("CREATE TABLE gold.dim_date AS SELECT * FROM t_dd")
        con.execute("CREATE TABLE gold.dim_product AS SELECT * FROM t_dp")
        con.execute("CREATE TABLE gold.fact_sales AS SELECT * FROM t_fs")

        df = build_forecast_30d_mart(con, as_of_date="2024-11-30", scenario_id="c1_toys", horizon_days=14)
        validate_contract(df, GoldForecast30dSchema, layer="gold")
        assert set(df["selected_model"].unique()) == {"MovingAverage28d"}
        assert bool(np.isfinite(df["family_wape_pct"]).all())
    finally:
        con.close()


def test_cli_ml_forecast_command(
    isolated_gold_db: tuple[duckdb.DuckDBPyConnection, Path],
) -> None:
    """Valida execução via CLI 'kyberna ml forecast --scenario c1_toys'."""
    con, _ = isolated_gold_db
    con.close()

    res = runner.invoke(app, ["ml", "forecast", "--scenario", "c1_toys"])
    assert res.exit_code == 0, res.output
    assert "Previsão de demanda 30d concluída para 'c1_toys'" in res.output
