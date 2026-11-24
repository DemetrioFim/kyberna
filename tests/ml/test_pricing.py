from __future__ import annotations

from pathlib import Path

import duckdb
import pytest
from typer.testing import CliRunner

from src.cli import app
from src.core.paths import get_duckdb_path, gold_snapshot_path
from src.ml.pricing import build_pricing_marts

runner = CliRunner()


def test_build_pricing_marts_shap_identity_and_leakage() -> None:
    """Valida identidade aditiva SHAP (< 1e-4), ordenação quantílica e captura de descontos sem lastro."""
    db_path = get_duckdb_path()
    if not db_path.exists():
        pytest.skip(f"Banco '{db_path}' não encontrado.")

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        # Copia para conexão em memória apenas para testar a leitura sem travar escrita no arquivo principal
        mem = duckdb.connect(":memory:")
        mem.execute("CREATE SCHEMA gold")
        for tbl in (
            "fact_sales",
            "dim_product",
            "dim_customer",
            "dim_date",
            "mart_abc_xyz",
            "mart_price_elasticity",
        ):
            df_tbl = con.execute(f"SELECT * FROM gold.{tbl}").df()
            mem.register(f"v_{tbl}", df_tbl)
            mem.execute(f"CREATE TABLE gold.{tbl} AS SELECT * FROM v_{tbl}")
    finally:
        con.close()

    try:
        realization_df, drivers_df = build_pricing_marts(mem, scenario_id="c1_toys")
    finally:
        mem.close()

    assert len(realization_df) == 397
    assert not drivers_df.empty

    # 1. Ordenação quantílica da banda contextual
    assert (
        realization_df["contextual_band_low_idx"] <= realization_df["contextual_band_expected_idx"] + 1e-6
    ).all()
    assert (
        realization_df["contextual_band_expected_idx"] <= realization_df["contextual_band_high_idx"] + 1e-6
    ).all()

    # 2. Identidade aditiva exata do Linear SHAP em 100% dos escopos
    grouped = drivers_df.groupby(["scope_type", "scope_id"], as_index=False).agg(
        base_idx=("base_idx", "first"),
        expected_idx=("expected_idx", "first"),
        sum_shap=("shap_impact_pp", "sum"),
        n_drivers=("driver_order", "count"),
    )
    assert (grouped["n_drivers"] == 5).all()
    diff = (grouped["base_idx"] + grouped["sum_shap"] - grouped["expected_idx"]).abs()
    assert (diff < 1e-4).all(), f"Erro máximo SHAP excedeu 1e-4: {diff.max()}"

    # 3. Captura de vazamento causado por high_discount_reps
    assert float(realization_df["price_leakage_brl"].sum()) > 10_000.0
    offenders = set(realization_df["primary_offender_rep"].astype(str))
    assert any(rep in offenders for rep in ("RCA-003", "RCA-007", "RCA-012", "RCA-015"))


def test_cli_ml_pricing_materializes_duckdb_and_parquet() -> None:
    """Valida comando `kyberna ml pricing --scenario c1_toys` gravando DuckDB e Parquet."""
    res = runner.invoke(app, ["ml", "pricing", "--scenario", "c1_toys"])
    assert res.exit_code == 0, f"CLI pricing falhou: {res.output}"
    assert "Precificação Contextual concluída" in res.output

    p_real: Path = gold_snapshot_path("c1_toys", "mart_price_realization")
    p_drv: Path = gold_snapshot_path("c1_toys", "mart_pricing_drivers")
    assert p_real.exists()
    assert p_drv.exists()

    con = duckdb.connect(str(get_duckdb_path()), read_only=True)
    try:
        cnt_real = con.execute(
            "SELECT COUNT(*) FROM gold.mart_price_realization WHERE scenario_id = 'c1_toys'"
        ).fetchone()
        cnt_drv = con.execute(
            "SELECT COUNT(*) FROM gold.mart_pricing_drivers WHERE scenario_id = 'c1_toys'"
        ).fetchone()
        assert cnt_real is not None and int(cnt_real[0]) == 397
        assert cnt_drv is not None and int(cnt_drv[0]) >= 35
    finally:
        con.close()
