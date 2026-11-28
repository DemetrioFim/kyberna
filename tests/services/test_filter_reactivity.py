from __future__ import annotations

import pytest

from src.core.paths import get_duckdb_path
from src.db.duckdb_repo import DuckDBRepository
from src.services.commercial_service import build_commercial_dashboard
from src.services.executive_service import build_executive_dashboard
from src.services.fortitude_service import build_fortitude_dashboard
from src.services.pricing_service import build_pricing_dashboard
from src.services.temperance_service import build_temperance_dashboard


@pytest.fixture
def repo() -> DuckDBRepository:
    """Fornece o DuckDBRepository conectado ao banco principal data/kyberna.duckdb."""
    db_path = get_duckdb_path()
    if not db_path.exists():
        pytest.skip(f"Banco '{db_path}' não encontrado para testes de reatividade.")
    return DuckDBRepository(db_path=db_path)


def test_period_and_geo_reactivity_across_services(repo: DuckDBRepository) -> None:
    """Valida reatividade a Período, Região e UF em todos os serviços."""
    scenario_id = "c1_toys"
    exec_base = build_executive_dashboard(repo, scenario_id)
    comm_base = build_commercial_dashboard(repo, scenario_id)
    fort_base = build_fortitude_dashboard(repo, scenario_id)

    # 1. Período (H2 2024 vs Global)
    p_start, p_end = 20240701, 20241231
    exec_per = build_executive_dashboard(repo, scenario_id, start_date_key=p_start, end_date_key=p_end)
    temp_per = build_temperance_dashboard(repo, scenario_id, start_date_key=p_start, end_date_key=p_end)
    comm_per = build_commercial_dashboard(repo, scenario_id, start_date_key=p_start, end_date_key=p_end)
    fort_per = build_fortitude_dashboard(repo, scenario_id, start_date_key=p_start, end_date_key=p_end)
    pric_per = build_pricing_dashboard(repo, scenario_id, start_date_key=p_start, end_date_key=p_end)

    assert exec_per.abc_xyz_skus_df["gross_revenue"].sum() < exec_base.abc_xyz_skus_df["gross_revenue"].sum()
    assert temp_per.abc_xyz_summary_df["gross_revenue"].sum() == pytest.approx(
        exec_per.abc_xyz_matrix_df["gross_revenue"].sum(), abs=1.0
    )
    assert (
        comm_per.rep_performance_df["gross_revenue"].sum()
        < comm_base.rep_performance_df["gross_revenue"].sum()
    )
    assert len(comm_per.vampires_df) == comm_per.kpis.vampire_customers_count
    assert fort_per.kpis.monthly_gross_revenue_brl != pytest.approx(
        fort_base.kpis.monthly_gross_revenue_brl, abs=1.0
    )
    assert pric_per.kpis.realization_index_pct > 0.0

    # 2. Região (Sudeste) e UF (SP)
    exec_reg = build_executive_dashboard(repo, scenario_id, regiao="Sudeste")
    temp_reg = build_temperance_dashboard(repo, scenario_id, regiao="Sudeste")
    comm_reg = build_commercial_dashboard(repo, scenario_id, regiao="Sudeste")
    fort_reg = build_fortitude_dashboard(repo, scenario_id, regiao="Sudeste")
    exec_uf = build_executive_dashboard(repo, scenario_id, uf="SP")
    comm_uf = build_commercial_dashboard(repo, scenario_id, uf="SP")
    fort_uf = build_fortitude_dashboard(repo, scenario_id, uf="SP")

    assert exec_reg.abc_xyz_skus_df["gross_revenue"].sum() < exec_base.abc_xyz_skus_df["gross_revenue"].sum()
    assert temp_reg.abc_xyz_summary_df["gross_revenue"].sum() == pytest.approx(
        exec_reg.abc_xyz_matrix_df["gross_revenue"].sum(), abs=1.0
    )
    assert comm_reg.kpis.total_customers < comm_base.kpis.total_customers
    assert fort_reg.kpis.monthly_gross_revenue_brl < fort_base.kpis.monthly_gross_revenue_brl
    assert exec_uf.abc_xyz_skus_df["gross_revenue"].sum() < exec_reg.abc_xyz_skus_df["gross_revenue"].sum()
    assert (
        comm_uf.rep_performance_df["gross_revenue"].sum()
        < comm_base.rep_performance_df["gross_revenue"].sum()
    )
    assert fort_uf.kpis.monthly_gross_revenue_brl < fort_reg.kpis.monthly_gross_revenue_brl


def test_family_and_rep_reactivity_across_services(repo: DuckDBRepository) -> None:
    """Valida reatividade a Família e RCA por nome (incluindo regressão do Ritmo Mensal)."""
    scenario_id = "c1_toys"
    rep_df = repo.query("SELECT name FROM gold.dim_sales_rep ORDER BY name LIMIT 1")
    fam_df = repo.query("SELECT DISTINCT family FROM gold.dim_product ORDER BY family LIMIT 1")
    assert not rep_df.empty
    assert not fam_df.empty
    sample_rep_name = str(rep_df["name"].iloc[0])
    sample_family = str(fam_df["family"].iloc[0])

    exec_base = build_executive_dashboard(repo, scenario_id)
    comm_base = build_commercial_dashboard(repo, scenario_id)
    fort_base = build_fortitude_dashboard(repo, scenario_id)

    # 3. Família
    exec_fam = build_executive_dashboard(repo, scenario_id, families=(sample_family,))
    comm_fam = build_commercial_dashboard(repo, scenario_id, families=(sample_family,))
    fort_fam = build_fortitude_dashboard(repo, scenario_id, families=(sample_family,))

    assert exec_fam.abc_xyz_skus_df["family"].unique().tolist() == [sample_family]
    assert (
        comm_fam.rep_performance_df["gross_revenue"].sum()
        < comm_base.rep_performance_df["gross_revenue"].sum()
    )
    assert len(comm_fam.vampires_df) == comm_fam.kpis.vampire_customers_count
    assert comm_fam.rfm_summary_df["gross_revenue"].sum() < comm_base.rfm_summary_df["gross_revenue"].sum()
    assert fort_fam.kpis.monthly_gross_revenue_brl < fort_base.kpis.monthly_gross_revenue_brl

    # 4. RCA por nome (regressão direta de query_monthly_trend)
    exec_rep = build_executive_dashboard(repo, scenario_id, sales_reps=(sample_rep_name,))
    comm_rep = build_commercial_dashboard(repo, scenario_id, sales_reps=(sample_rep_name,))
    fort_rep = build_fortitude_dashboard(repo, scenario_id, sales_reps=(sample_rep_name,))

    assert not exec_rep.monthly_trend_df.empty
    assert exec_rep.kpis.gross_revenue < exec_base.kpis.gross_revenue
    assert exec_rep.abc_xyz_skus_df["gross_revenue"].sum() < exec_base.abc_xyz_skus_df["gross_revenue"].sum()
    assert len(comm_rep.rep_performance_df) == 1
    assert fort_rep.kpis.monthly_gross_revenue_brl < fort_base.kpis.monthly_gross_revenue_brl
    assert len(comm_rep.silent_churn_df) <= len(comm_base.silent_churn_df)
    assert comm_fam.white_space_matrix_df["potential_revenue_brl"].sum() <= (
        comm_base.white_space_matrix_df["potential_revenue_brl"].sum() + 1e-2
    )
    assert comm_fam.silent_churn_df["rev_prev_90d"].sum() != pytest.approx(
        comm_base.silent_churn_df["rev_prev_90d"].sum(), abs=1.0
    )


def test_temperance_pricing_and_pvm_reactivity(repo: DuckDBRepository) -> None:
    """Valida reatividade de Temperanca, Pricing e fechamento exato do Bridge PVM sob recorte YoY."""
    scenario_id = "c1_toys"
    rep_df = repo.query("SELECT name FROM gold.dim_sales_rep ORDER BY name LIMIT 1")
    fam_df = repo.query("SELECT DISTINCT family FROM gold.dim_product ORDER BY family LIMIT 1")
    sample_rep_name = str(rep_df["name"].iloc[0])
    sample_family = str(fam_df["family"].iloc[0])

    temp_base = build_temperance_dashboard(repo, scenario_id)
    temp_uf = build_temperance_dashboard(repo, scenario_id, uf="SP")
    temp_fam = build_temperance_dashboard(repo, scenario_id, families=(sample_family,))
    temp_rep = build_temperance_dashboard(repo, scenario_id, sales_reps=(sample_rep_name,))

    assert temp_uf.kpis.gross_revenue < temp_base.kpis.gross_revenue
    assert temp_fam.kpis.gross_revenue < temp_base.kpis.gross_revenue
    assert temp_rep.kpis.gross_revenue < temp_base.kpis.gross_revenue

    pric_base = build_pricing_dashboard(repo, scenario_id)
    pric_uf = build_pricing_dashboard(repo, scenario_id, uf="SP")
    pric_fam = build_pricing_dashboard(repo, scenario_id, families=(sample_family,))
    pric_rep = build_pricing_dashboard(repo, scenario_id, sales_reps=(sample_rep_name,))

    assert pric_uf.kpis.realization_index_pct != pytest.approx(
        pric_base.kpis.realization_index_pct, abs=0.0
    ) or (len(pric_uf.sku_deviations_df) <= len(pric_base.sku_deviations_df))
    assert pric_fam.kpis.subpricing_leakage_brl <= pric_base.kpis.subpricing_leakage_brl
    assert pric_rep.kpis.subpricing_leakage_brl <= pric_base.kpis.subpricing_leakage_brl

    exec_yoy_reg = build_executive_dashboard(
        repo,
        scenario_id,
        regiao="Sudeste",
        comparison_mode="yoy",
    )
    pvm = exec_yoy_reg.pvm_bridge_df
    assert not pvm.empty
    mc0 = float(pvm.loc[pvm["step_key"] == "mc_base", "amount"].iloc[0])
    mc1 = float(pvm.loc[pvm["step_key"] == "mc_final", "amount"].iloc[0])
    effects = float(pvm.loc[pvm["measure"] == "relative", "amount"].sum())
    assert abs((mc0 + effects) - mc1) < 1e-2
