from __future__ import annotations

import pytest

from src.core.paths import get_duckdb_path
from src.db.duckdb_repo import DuckDBRepository
from src.services.inventory_dto import InventoryPageDTO, SkuForecastSeriesDTO
from src.services.inventory_service import (
    build_inventory_dashboard,
    get_sku_forecast_series,
)


@pytest.fixture
def repo() -> DuckDBRepository:
    """Fixture fornecendo DuckDBRepository conectado ao banco principal data/kyberna.duckdb."""
    db_path = get_duckdb_path()
    if not db_path.exists():
        pytest.skip(f"Banco '{db_path}' não encontrado para teste de inventory_service.")
    return DuckDBRepository(db_path=db_path)


def test_build_inventory_dashboard_reconciliation(repo: DuckDBRepository) -> None:
    """Valida KPIs, tabelas prescritivas e reconciliação estrita Treemap == Capital Travado."""
    dto = build_inventory_dashboard(repo, scenario_id="c1_toys")
    assert isinstance(dto, InventoryPageDTO)
    assert not dto.position_df.empty
    assert not dto.stockout_df.empty
    assert not dto.locked_df.empty
    assert not dto.treemap_df.empty
    assert not dto.sku_options_df.empty

    assert dto.kpis.total_stock_value_brl > 0.0
    assert dto.kpis.locked_capital_brl > 0.0
    assert dto.kpis.locked_skus_count > 0
    assert dto.kpis.stockout_risk_skus_count > 0
    assert 0 < dto.kpis.stockout_curve_a_skus_count < dto.kpis.stockout_risk_skus_count
    assert 0.0 < dto.kpis.stockout_curve_a_revenue_brl <= dto.kpis.protected_revenue_brl
    assert dto.kpis.forecast_30d_units_total > 0
    assert 500_000.0 < dto.kpis.forecast_30d_revenue_brl < 2_500_000.0
    assert dto.kpis.protected_revenue_brl > 0.0
    assert dto.kpis.suggested_order_boxes_total > 0

    # Reconciliação estrita exigida pelo DoD de M4-V1
    treemap_sum = float(dto.treemap_df["locked_capital_brl"].sum())
    assert treemap_sum == pytest.approx(dto.kpis.locked_capital_brl, abs=1e-6)

    # V8-S3 (ID-I01): Combos Destrava-Caixa para SKUs imobilizados
    assert len(dto.unlock_combos_df) == len(dto.locked_df)
    assert {"anchor_product_name", "anchor_cell", "combo_ratio", "combo_suggestion"}.issubset(
        set(dto.unlock_combos_df.columns)
    )
    assert (dto.unlock_combos_df["combo_suggestion"].str.startswith("Combo c/ ")).all()


def test_forecast_30d_rollup_and_family_filter(repo: DuckDBRepository) -> None:
    """Valida rollup de 30 dias do StatsForecast e redução proporcional ao filtrar por família."""
    full_dto = build_inventory_dashboard(repo, scenario_id="c1_toys")
    first_family = str(full_dto.position_df["family"].iloc[0])
    filtered = build_inventory_dashboard(repo, scenario_id="c1_toys", families=[first_family])

    assert 0 < filtered.kpis.forecast_30d_units_total < full_dto.kpis.forecast_30d_units_total
    assert 0.0 < filtered.kpis.forecast_30d_revenue_brl < full_dto.kpis.forecast_30d_revenue_brl


def test_build_inventory_dashboard_family_filter(repo: DuckDBRepository) -> None:
    """Valida filtro por família mantendo consistência entre posição e Treemap."""
    full_dto = build_inventory_dashboard(repo, scenario_id="c1_toys")
    first_family = str(full_dto.position_df["family"].iloc[0])

    filtered = build_inventory_dashboard(repo, scenario_id="c1_toys", families=[first_family])
    assert not filtered.position_df.empty
    assert set(filtered.position_df["family"].unique()) == {first_family}
    treemap_sum = (
        float(filtered.treemap_df["locked_capital_brl"].sum()) if not filtered.treemap_df.empty else 0.0
    )
    assert treemap_sum == pytest.approx(filtered.kpis.locked_capital_brl, abs=1e-6)


def test_get_sku_forecast_series_intervals(repo: DuckDBRepository) -> None:
    """Valida série 90d+30d e monotonicidade dos intervalos conformais de 80% e 95%."""
    dto = build_inventory_dashboard(repo, scenario_id="c1_toys")
    first_sku = str(dto.sku_options_df["product_id"].iloc[0])

    fc = get_sku_forecast_series(repo, scenario_id="c1_toys", product_id=first_sku)
    assert isinstance(fc, SkuForecastSeriesDTO)
    assert fc.product_id == first_sku
    assert not fc.series_df.empty
    assert fc.forecast_30d_total_units >= 0.0

    fc_rows = fc.series_df[fc.series_df["record_type"] == "forecast"]
    assert len(fc_rows) == 30
    assert (fc_rows["lo_95"] >= 0.0).all()
    assert (fc_rows["lo_95"] <= fc_rows["lo_80"] + 1e-5).all()
    assert (fc_rows["lo_80"] <= fc_rows["forecast_units"] + 1e-5).all()
    assert (fc_rows["forecast_units"] <= fc_rows["hi_80"] + 1e-5).all()
    assert (fc_rows["hi_80"] <= fc_rows["hi_95"] + 1e-5).all()
