from __future__ import annotations

import pytest

from src.core.paths import get_duckdb_path
from src.db.duckdb_repo import DuckDBRepository
from src.services.commercial_service import build_commercial_dashboard
from src.services.dto import SimulationBaseline, SimulationLevers
from src.services.executive_service import build_executive_dashboard
from src.services.fortitude_service import build_fortitude_dashboard
from src.services.inventory_service import build_inventory_dashboard
from src.services.pricing_service import build_pricing_dashboard, get_pricing_shap_waterfall
from src.services.simulator import simulate
from src.services.temperance_actions import build_priority_actions_360
from src.services.temperance_service import build_temperance_dashboard


@pytest.fixture
def repo() -> DuckDBRepository:
    """Fixture conectada ao banco principal data/kyberna.duckdb."""
    db_path = get_duckdb_path()
    if not db_path.exists():
        pytest.skip(f"Banco '{db_path}' não encontrado.")
    return DuckDBRepository(db_path=db_path)


def test_pricing_dashboard_and_shap_service(repo: DuckDBRepository) -> None:
    """Valida KPIs de precificação, boxplot por família/SKU e SHAP Waterfall."""
    dto_all = build_pricing_dashboard(repo, scenario_id="c1_toys")
    assert 80.0 <= dto_all.kpis.realization_index_pct <= 105.0
    assert dto_all.kpis.subpricing_leakage_brl > 0.0
    assert dto_all.kpis.below_band_sales_pct > 0.0
    assert len(dto_all.boxplot_df) == 7
    assert not dto_all.deviations_df.empty
    assert not dto_all.shap_options_df.empty
    assert len(dto_all.family_bands_df) == 7

    # Filtro de 1 família abre boxplot em Top SKUs
    dto_fam = build_pricing_dashboard(repo, scenario_id="c1_toys", families=["Quebra-Cabeças"])
    assert len(dto_fam.boxplot_df) <= 10
    assert (dto_fam.boxplot_df["family"] == "Quebra-Cabeças").all()

    # SHAP Waterfall fecha exatamente
    shap_dto = get_pricing_shap_waterfall(
        repo,
        scenario_id="c1_toys",
        scope_type="family",
        scope_id="Quebra-Cabeças",
    )
    assert len(shap_dto.drivers_df) == 5
    sum_shap = float(shap_dto.drivers_df["shap_impact_pp"].sum())
    assert shap_dto.base_idx + sum_shap == pytest.approx(shap_dto.expected_idx, abs=1e-3)


def test_v7_boundaries_supply_vampires_high_lift_and_actions_360(repo: DuckDBRepository) -> None:
    """Valida fronteiras V7: Radar Supply, Vampiros 4==4, Alto Lift, Fila 360 e Banda Sim."""
    exec_dto = build_executive_dashboard(repo, scenario_id="c1_toys")
    comm_dto = build_commercial_dashboard(repo, scenario_id="c1_toys")
    inv_dto = build_inventory_dashboard(repo, scenario_id="c1_toys")
    fort_dto = build_fortitude_dashboard(repo, scenario_id="c1_toys")
    temp_dto = build_temperance_dashboard(repo, scenario_id="c1_toys")
    pricing_dto = build_pricing_dashboard(repo, scenario_id="c1_toys")

    # 1. Radar de Prudência 100% Supply (sem Churn/WhatsApp/RCA)
    assert len(exec_dto.anomalies_df) == 3
    assert exec_dto.anomalies_df.iloc[0]["severity"] == "Crítica"
    all_radar = " ".join(
        exec_dto.anomalies_df["title"].astype(str) + " " + exec_dto.anomalies_df["recommendation"].astype(str)
    )
    assert "WhatsApp" not in all_radar
    assert "RCA" not in all_radar

    # 2. Métricas PCP em InventoryPageDTO
    assert inv_dto.kpis.weighted_wape_pct > 0.0
    assert inv_dto.kpis.last_30d_actual_units > 0
    assert len(inv_dto.family_supply_df) == 7
    assert not inv_dto.pcp_plan_df.empty

    # 3. Fortaleza: Alto Lift (>1,2x) e conciliação exata de Vampiros
    assert comm_dto.kpis.high_lift_customers_count > 0
    assert 0.0 < comm_dto.kpis.high_lift_coverage_pct < 100.0
    assert len(comm_dto.vampires_df) == comm_dto.kpis.vampire_customers_count

    # 4. Fila Priorizada 360°
    actions_df = build_priority_actions_360(
        fort_dto=fort_dto,
        comm_dto=comm_dto,
        temp_dto=temp_dto,
        inv_dto=inv_dto,
        pricing_dto=pricing_dto,
    )
    assert len(actions_df) == 5
    assert actions_df["recoverable_brl"].is_monotonic_decreasing

    # 5. Simulador respeitando banda competitiva
    baseline = SimulationBaseline.from_executive_kpis(exec_dto.kpis, beta_elasticity=-0.56)
    res = simulate(
        baseline,
        SimulationLevers(delta_price_pct=0.20, band_low_change_pct=-0.05, band_high_change_pct=0.05),
    )
    assert res.is_outside_band is True
    assert -0.05 <= res.band_constrained_optimal_pct <= 0.05
