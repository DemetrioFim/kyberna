from __future__ import annotations

import duckdb
import pandas as pd
from typer.testing import CliRunner

from src.cli import app
from src.core.paths import get_duckdb_path, gold_snapshot_path
from src.etl.contracts import GoldInventorySnapshotSchema, validate_contract
from src.etl.gold.inventory_snapshot import (
    build_inventory_snapshot,
    compute_inventory_snapshot,
    load_working_capital_config,
)

runner = CliRunner()


def test_load_working_capital_config() -> None:
    """Valida leitura e integridade dos parâmetros de capital de giro e estoque."""
    cfg = load_working_capital_config("c1_toys")
    assert "fixed_cost_pct_of_avg_net_revenue" in cfg
    assert cfg["fixed_cost_pct_of_avg_net_revenue"] == 0.14
    assert cfg["cash_reserve_months_target"] == 3.5
    assert cfg["pmp_supplier_days"] == 35
    assert "pmr_days_by_size" in cfg
    assert cfg["pmr_days_by_size"]["P"] == 28
    assert "lead_time_days_by_family" in cfg
    assert cfg["lead_time_days_by_family"]["Jogos de Tabuleiro"] == 7


def test_inventory_snapshot_contract_and_determinism() -> None:
    """Valida contrato Pandera, conservação de SKUs e determinismo byte a byte (seed=42)."""
    db_path = get_duckdb_path()
    assert db_path.exists(), f"Banco DuckDB não encontrado em {db_path}."

    con = duckdb.connect(str(db_path))
    try:
        df1 = build_inventory_snapshot(con, scenario_id="c1_toys", seed=42)
        df2 = compute_inventory_snapshot(con, scenario_id="c1_toys", seed=42)

        # Determinismo byte-a-byte
        pd.testing.assert_frame_equal(df1, df2)

        # Validação do Contrato Pandera
        validated_df = validate_contract(
            df1,
            GoldInventorySnapshotSchema,
            layer="Gold (inventory_snapshot)",
        )
        assert len(validated_df) == len(df1)

        # Conservação de SKUs com gold.dim_product
        product_count = con.execute("SELECT COUNT(*) FROM gold.dim_product").fetchone()[0]
        assert len(df1) == product_count
        assert df1["product_id"].is_unique
        assert df1["product_id"].notna().all()

        # Snapshot Parquet físico gerado
        parquet_p = gold_snapshot_path("c1_toys", "inventory_snapshot")
        assert parquet_p.exists(), f"Arquivo Parquet não encontrado em {parquet_p}"
        assert parquet_p.stat().st_size > 0
    finally:
        con.close()


def test_inventory_snapshot_proportions_dod() -> None:
    """DoD: Valida proporções das 4 faixas de cobertura logística dentro de ±3 p.p."""
    db_path = get_duckdb_path()
    con = duckdb.connect(str(db_path))
    try:
        df = compute_inventory_snapshot(con, scenario_id="c1_toys", seed=42)
        n = len(df)

        pct_rupture = (df["coverage_days"] <= 7.0).sum() / n
        pct_healthy = ((df["coverage_days"] > 7.0) & (df["coverage_days"] <= 60.0)).sum() / n
        pct_attention = ((df["coverage_days"] > 60.0) & (df["coverage_days"] <= 120.0)).sum() / n
        pct_locked = (df["coverage_days"] > 120.0).sum() / n

        # Metas: 10%, 60%, 15%, 15% com tolerância de ±3 p.p. (0.03)
        assert 0.07 <= pct_rupture <= 0.13, f"Ruptura fora da faixa esperada: {pct_rupture:.1%}"
        assert 0.57 <= pct_healthy <= 0.63, f"Saudável fora da faixa esperada: {pct_healthy:.1%}"
        assert 0.12 <= pct_attention <= 0.18, f"Atenção fora da faixa esperada: {pct_attention:.1%}"
        assert 0.12 <= pct_locked <= 0.18, f"Capital travado fora da faixa esperada: {pct_locked:.1%}"
    finally:
        con.close()


def test_inventory_snapshot_locked_capital_value_dod() -> None:
    """DoD: O capital travado (>120d) deve representar entre 10% e 25% do valor contábil total."""
    db_path = get_duckdb_path()
    con = duckdb.connect(str(db_path))
    try:
        df = compute_inventory_snapshot(con, scenario_id="c1_toys", seed=42)
        total_val = float(df["stock_value_brl"].sum())
        locked_val = float(df.loc[df["coverage_days"] > 120.0, "stock_value_brl"].sum())

        assert total_val > 0
        locked_pct = (locked_val / total_val) * 100.0

        assert 10.0 <= locked_pct <= 25.0, (
            f"Capital travado em R$ ({locked_pct:.1f}%) fora do limite de 10% a 25% do estoque total."
        )
    finally:
        con.close()


def test_inventory_snapshot_cli() -> None:
    """Valida execução do comando CLI `kyberna gold inventory-snapshot`."""
    result = runner.invoke(app, ["gold", "inventory-snapshot", "--scenario", "c1_toys"])
    assert result.exit_code == 0, f"Falha na CLI: {result.stdout}"
    assert "Snapshot de Estoque gerado com sucesso" in result.stdout
    assert "Capital Travado (>120d)" in result.stdout
    assert "Ruptura Iminente" in result.stdout
