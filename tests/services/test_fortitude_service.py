from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.core.paths import get_duckdb_path
from src.db.duckdb_repo import DuckDBRepository
from src.services.dto import FortitudePageDTO
from src.services.fortitude_service import (
    build_breakeven_curve_df,
    build_fortitude_dashboard,
)


@pytest.fixture
def repo() -> DuckDBRepository:
    """Fixture fornecendo o DuckDBRepository conectado ao banco principal data/kyberna.duckdb."""
    db_path = get_duckdb_path()
    if not db_path.exists():
        pytest.skip(f"Banco '{db_path}' não encontrado para teste de serviços de fortaleza.")
    return DuckDBRepository(db_path=db_path)


def test_fortitude_dashboard_kpis_and_invariants(repo: DuckDBRepository) -> None:
    """Valida métricas financeiras, ciclo de caixa, break-even e concentração no Cenário 1."""
    dto = build_fortitude_dashboard(repo, scenario_id="c1_toys")
    assert isinstance(dto, FortitudePageDTO)

    k = dto.kpis
    assert k.monthly_gross_revenue_brl > 0.0
    assert k.monthly_net_revenue_brl > 0.0
    assert k.monthly_contribution_margin_brl > 0.0
    assert k.fixed_costs_monthly_brl > 0.0
    assert k.cash_reserve_brl > 0.0
    assert k.cash_runway_months > 0.0

    # Break-even no mês (entre dia 1 e dia 30)
    assert 1 <= k.breakeven_day_of_month <= 30
    assert k.breakeven_revenue_brl > 0.0

    # Ciclo Financeiro: CCC = PME + PMR - PMP
    expected_ccc = round(k.pme_days + k.pmr_days - k.pmp_days, 1)
    assert k.cash_conversion_cycle_days == pytest.approx(expected_ccc, abs=0.2)

    expected_ncg = (k.monthly_net_revenue_brl / 30.0) * k.cash_conversion_cycle_days
    assert k.ncg_brl == pytest.approx(expected_ncg, abs=5.0)

    # Limites de concentração
    assert 0.0 <= k.top5_customers_share_pct <= k.top10_customers_share_pct <= 100.0
    assert 0.0 <= k.top2_families_share_pct <= 100.0
    assert k.active_customers_count > 0
    assert 0.0 <= k.at_risk_portfolio_pct <= 100.0

    # DataFrames estruturais
    assert len(dto.breakeven_curve_df) == 30
    assert len(dto.cycle_components_df) == 4
    assert len(dto.aging_buckets_df) == 4
    assert dto.aging_buckets_df["revenue_share_pct"].sum() == pytest.approx(100.0, abs=0.5)
    assert not dto.customer_concentration_df.empty
    assert not dto.family_concentration_df.empty
    assert not dto.aging_customers_df.empty
    assert dto.prescription_impact_brl is not None and dto.prescription_impact_brl > 0.0


def test_fortitude_breakeven_curve_monotonic_transition() -> None:
    """Garante que a curva diária de break-even atinge o equilíbrio no dia esperado."""
    curve = build_breakeven_curve_df(
        monthly_gross_revenue_brl=600_000.0,
        monthly_contribution_margin_brl=180_000.0,
        fixed_costs_monthly_brl=90_000.0,
    )
    assert len(curve) == 30
    # Meta 90k com CM diária = 6k -> atinge exatamente no dia 15
    reached_days = curve[curve["is_breakeven_reached"]]["day_of_month"]
    assert int(reached_days.min()) == 15


def test_fortitude_filters_propagate_consistently(repo: DuckDBRepository) -> None:
    """Valida que filtros regionais e de família reduzem o escopo mantendo invariantes."""
    full_dto = build_fortitude_dashboard(repo, scenario_id="c1_toys")
    filtered_dto = build_fortitude_dashboard(
        repo,
        scenario_id="c1_toys",
        regiao="Sudeste",
    )
    assert filtered_dto.kpis.monthly_gross_revenue_brl > 0.0
    assert filtered_dto.kpis.monthly_gross_revenue_brl < full_dto.kpis.monthly_gross_revenue_brl
    assert filtered_dto.aging_buckets_df["revenue_share_pct"].sum() == pytest.approx(100.0, abs=0.5)

    # Filtro inexistente retorna estado vazio sem quebrar
    empty_dto = build_fortitude_dashboard(
        repo,
        scenario_id="c1_toys",
        uf="XX",
    )
    assert empty_dto.kpis.monthly_gross_revenue_brl == 0.0
    assert len(empty_dto.aging_buckets_df) == 4
    assert empty_dto.prescription_impact_brl is None


def test_fortitude_services_have_no_streamlit_import() -> None:
    """Garante isolamento arquitetural: src/services não importa streamlit."""
    for rel in (
        "src/services/fortitude_queries.py",
        "src/services/fortitude_risk_queries.py",
        "src/services/fortitude_service.py",
    ):
        tree = ast.parse(Path(rel).read_text(encoding="utf-8"))
        imported_modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.add(node.module.split(".")[0])
        assert "streamlit" not in imported_modules
