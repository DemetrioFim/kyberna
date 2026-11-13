from __future__ import annotations

import math
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

from src.cli import app
from src.etl.contracts import GoldInventoryPositionSchema, validate_contract
from src.ml.inventory import (
    SERVICE_LEVEL_Z,
    build_inventory_position_mart,
    compute_inventory_position,
    compute_inventory_position_summary,
)

runner = CliRunner()


def _make_inputs_row(
    *,
    product_id: str,
    abc_class: str = "A",
    xyz_class: str = "X",
    pack: int = 12,
    unit_cost: float = 10.0,
    unit_list_price: float = 25.0,
    stock_units: int = 100,
    avg_daily_demand_90d: float = 10.0,
    fc_daily_demand: float = 10.0,
    weekly_demand_std: float = 7.0,
    lead_time_days: int = 14,
) -> dict[str, object]:
    """Cria registro sintético padronizado de entrada para `compute_inventory_position`."""
    return {
        "scenario_id": "c1_toys",
        "branch_id": "FAB-SP01",
        "product_id": product_id,
        "product_name": f"Produto {product_id}",
        "family": "Jogos Educativos",
        "abc_class": abc_class,
        "xyz_class": xyz_class,
        "abc_xyz_class": f"{abc_class}{xyz_class}",
        "pack": pack,
        "unit_cost": unit_cost,
        "unit_list_price": unit_list_price,
        "stock_units": stock_units,
        "stock_boxes": round(stock_units / pack, 2),
        "stock_value_brl": round(stock_units * unit_cost, 2),
        "avg_daily_demand_90d": avg_daily_demand_90d,
        "fc_daily_demand": fc_daily_demand,
        "weekly_demand_std": weekly_demand_std,
        "lead_time_days": lead_time_days,
    }


def test_compute_inventory_position_safety_stock_and_rop() -> None:
    """Valida fatores z por classe ABC e fórmulas exatas de SS e ROP."""
    df_in = pd.DataFrame(
        [
            _make_inputs_row(product_id="7890000000001", abc_class="A", stock_units=300),
            _make_inputs_row(product_id="7890000000002", abc_class="B", stock_units=300),
            _make_inputs_row(product_id="7890000000003", abc_class="C", stock_units=300),
        ]
    )

    out = compute_inventory_position(df_in, snapshot_date="2025-12-31", scenario_id="c1_toys")
    validated = validate_contract(out, GoldInventoryPositionSchema, layer="test")

    daily_std = 7.0 / math.sqrt(7.0)
    expected_ss = {
        cls: math.ceil(SERVICE_LEVEL_Z[cls] * daily_std * math.sqrt(14)) for cls in ("A", "B", "C")
    }

    by_abc = validated.set_index("abc_class")
    for cls in ("A", "B", "C"):
        assert int(by_abc.loc[cls, "safety_stock_units"]) == expected_ss[cls]
        assert int(by_abc.loc[cls, "reorder_point_units"]) == 140 + expected_ss[cls]

    assert by_abc.loc["A", "safety_stock_units"] > by_abc.loc["B", "safety_stock_units"]
    assert by_abc.loc["B", "safety_stock_units"] > by_abc.loc["C", "safety_stock_units"]


def test_compute_inventory_position_statuses_orders_and_locked_capital() -> None:
    """Valida as 4 faixas de stock_status, caixas sugeridas, receita protegida e capital travado."""
    df_in = pd.DataFrame(
        [
            # 1) Ruptura Iminente: stock=50 < ROP -> target=30*10=300 -> needed=250 -> 21 cx (pack 12)
            _make_inputs_row(
                product_id="7890000000011",
                abc_class="A",
                stock_units=50,
                pack=12,
                unit_cost=10.0,
                unit_list_price=25.0,
                fc_daily_demand=10.0,
                weekly_demand_std=7.0,
                lead_time_days=14,
            ),
            # 2) Capital Travado: stock=1500 -> 150d > 120d -> excess=300 -> locked=300*20=6000
            _make_inputs_row(
                product_id="7890000000012",
                abc_class="B",
                xyz_class="Z",
                stock_units=1500,
                pack=10,
                unit_cost=20.0,
                unit_list_price=40.0,
                fc_daily_demand=10.0,
                weekly_demand_std=7.0,
                lead_time_days=14,
            ),
            # 3) Atenção (Excesso Moderado): stock=900 -> 90d in (60, 120]
            _make_inputs_row(
                product_id="7890000000013",
                abc_class="B",
                stock_units=900,
                fc_daily_demand=10.0,
                weekly_demand_std=7.0,
                lead_time_days=14,
            ),
            # 4) Saudável: stock=300 -> 30d (> lead_time=14 e > ROP=153)
            _make_inputs_row(
                product_id="7890000000014",
                abc_class="B",
                stock_units=300,
                fc_daily_demand=10.0,
                weekly_demand_std=7.0,
                lead_time_days=14,
            ),
        ]
    )

    out = compute_inventory_position(df_in, snapshot_date="2025-12-31", scenario_id="c1_toys")
    validated = validate_contract(out, GoldInventoryPositionSchema, layer="test").set_index("product_id")

    r_rup = validated.loc["7890000000011"]
    assert r_rup["stock_status"] == "Ruptura Iminente"
    assert int(r_rup["suggested_order_boxes"]) == 21
    assert float(r_rup["protected_revenue_brl"]) == pytest.approx(6300.0)
    assert float(r_rup["locked_capital_brl"]) == 0.0

    r_lock = validated.loc["7890000000012"]
    assert r_lock["stock_status"] == "Capital Travado"
    assert int(r_lock["suggested_order_boxes"]) == 0
    assert float(r_lock["locked_capital_brl"]) == pytest.approx(6000.0)

    r_att = validated.loc["7890000000013"]
    assert r_att["stock_status"] == "Atenção (Excesso Moderado)"
    assert float(r_att["locked_capital_brl"]) == 0.0
    assert int(r_att["suggested_order_boxes"]) == 0

    r_ok = validated.loc["7890000000014"]
    assert r_ok["stock_status"] == "Saudável"
    assert float(r_ok["locked_capital_brl"]) == 0.0
    assert int(r_ok["suggested_order_boxes"]) == 0


def test_compute_inventory_position_zero_demand_fallback() -> None:
    """Garante fallback seguro para demanda 90d ou piso 0.01 sem NaN ou divisão por zero."""
    df_in = pd.DataFrame(
        [
            _make_inputs_row(
                product_id="7890000000021",
                abc_class="C",
                stock_units=40,
                avg_daily_demand_90d=0.25,
                fc_daily_demand=0.0,
                weekly_demand_std=0.0,
            ),
            _make_inputs_row(
                product_id="7890000000022",
                abc_class="C",
                stock_units=5,
                avg_daily_demand_90d=0.0,
                fc_daily_demand=0.0,
                weekly_demand_std=0.0,
            ),
        ]
    )

    out = compute_inventory_position(df_in, snapshot_date="2025-12-31", scenario_id="c1_toys")
    validated = validate_contract(out, GoldInventoryPositionSchema, layer="test").set_index("product_id")

    assert np.all(np.isfinite(validated["coverage_days"].to_numpy(dtype=float)))
    assert np.all(np.isfinite(validated["locked_capital_brl"].to_numpy(dtype=float)))
    assert float(validated.loc["7890000000021", "forecast_daily_demand"]) == pytest.approx(0.25)
    assert float(validated.loc["7890000000021", "coverage_days"]) == pytest.approx(160.0)
    assert float(validated.loc["7890000000022", "coverage_days"]) == pytest.approx(500.0)


def _clone_c1_inventory_inputs(target_db: Path, source_db: Path) -> None:
    """Copia tabelas Gold necessárias do `c1_toys` para um DuckDB isolado de teste."""
    src = duckdb.connect(str(source_db), read_only=True)
    try:
        dim_date = src.execute("SELECT * FROM gold.dim_date").df()
        dim_product = src.execute("SELECT * FROM gold.dim_product").df()
        fact_dates = src.execute(
            "SELECT MAX(date_key) AS max_dk FROM gold.fact_sales WHERE scenario_id = 'c1_toys'"
        ).df()
        inv_snap = src.execute("SELECT * FROM gold.inventory_snapshot WHERE scenario_id = 'c1_toys'").df()
        abc_xyz = src.execute("SELECT * FROM gold.mart_abc_xyz WHERE scenario_id = 'c1_toys'").df()
        forecast = src.execute("SELECT * FROM gold.mart_forecast_30d WHERE scenario_id = 'c1_toys'").df()
    finally:
        src.close()

    max_dk = int(fact_dates["max_dk"].iloc[0])
    dst = duckdb.connect(str(target_db))
    try:
        dst.execute("CREATE SCHEMA IF NOT EXISTS gold")
        dst.execute("CREATE SCHEMA IF NOT EXISTS c1_toys")
        dst.execute(f"CREATE TABLE gold.fact_sales AS SELECT 'c1_toys' AS scenario_id, {max_dk} AS date_key")
        for tbl_name, df in [
            ("dim_date", dim_date),
            ("dim_product", dim_product),
            ("inventory_snapshot", inv_snap),
            ("mart_abc_xyz", abc_xyz),
            ("mart_forecast_30d", forecast),
        ]:
            dst.register("_tmp_clone_df", df)
            dst.execute(f"CREATE TABLE gold.{tbl_name} AS SELECT * FROM _tmp_clone_df")
            dst.unregister("_tmp_clone_df")
    finally:
        dst.close()


def test_build_inventory_position_mart_duckdb_and_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DoD: Valida materialização Gold, alinhamento >120d com M4-D2 e comando CLI `ml inventory`."""
    from src.core.paths import get_duckdb_path

    source_db = get_duckdb_path()
    test_db = tmp_path / "test_inventory.duckdb"
    _clone_c1_inventory_inputs(test_db, source_db)

    out_parquet = tmp_path / "mart_inventory_position.parquet"
    monkeypatch.setattr("src.ml.inventory.gold_snapshot_path", lambda s, t: out_parquet)
    monkeypatch.setattr("src.cli_ml.get_duckdb_path", lambda: test_db)

    con = duckdb.connect(str(test_db))
    try:
        pos_df = build_inventory_position_mart(con, scenario_id="c1_toys")
        snap_locked = set(
            con.execute(
                "SELECT product_id FROM gold.inventory_snapshot "
                "WHERE scenario_id = 'c1_toys' AND coverage_days > 120.0"
            )
            .df()["product_id"]
            .tolist()
        )
        summary = compute_inventory_position_summary(pos_df)
    finally:
        con.close()

    assert len(pos_df) == 397
    assert out_parquet.exists()
    assert not summary.empty

    pos_locked = set(pos_df.loc[pos_df["coverage_days"] > 120.0, "product_id"].tolist())
    assert len(pos_locked) >= 40
    # Maioria expressiva (>= 70%) da faixa >120d do M4-D2 permanece na faixa >120d no M4-S2
    assert len(snap_locked & pos_locked) / max(len(snap_locked), 1) >= 0.70
    assert float(pos_df["locked_capital_brl"].sum()) > 0.0
    assert float(pos_df["protected_revenue_brl"].sum()) > 0.0

    cli_res = runner.invoke(app, ["ml", "inventory", "--scenario", "c1_toys"])
    assert cli_res.exit_code == 0, cli_res.output
    assert "Posição Prescritiva de Estoque gerada para 'c1_toys'" in cli_res.output
