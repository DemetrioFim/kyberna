from __future__ import annotations

import math

import pytest

from src.core.paths import get_duckdb_path
from src.db.duckdb_repo import DuckDBRepository
from src.services.commercial_service import build_commercial_dashboard
from src.services.executive_service import build_executive_dashboard
from src.services.fortitude_service import build_fortitude_dashboard
from src.services.period_comparison import (
    abs_delta,
    int_delta,
    pct_delta,
    pp_delta,
    resolve_effective_comparison_window,
)
from src.services.pricing_service import build_pricing_dashboard
from src.services.temperance_service import build_temperance_dashboard


@pytest.fixture
def repo() -> DuckDBRepository:
    """Fornece o DuckDBRepository conectado ao banco principal data/kyberna.duckdb."""
    db_path = get_duckdb_path()
    if not db_path.exists():
        pytest.skip(f"Banco '{db_path}' nao encontrado para testes de comparacao temporal.")
    return DuckDBRepository(db_path=db_path)


def test_delta_math_helpers() -> None:
    """Valida helpers puros de variacao percentual, p.p. e absoluta."""
    assert pct_delta(120.0, 100.0) == 20.0
    assert pct_delta(80.0, 100.0) == -20.0
    assert pct_delta(50.0, 0.0) is None
    assert pct_delta(50.0, -10.0) is None
    assert pp_delta(26.5, 25.0) == 1.5
    assert abs_delta(3.8, 3.2) == 0.6
    assert int_delta(5, 7) == -2


def test_resolve_effective_comparison_window_rules(repo: DuckDBRepository) -> None:
    """Valida regra canonica: all+pop->None, all+yoy->2024 vs 2023 e janelas explicitas."""
    assert (
        resolve_effective_comparison_window(
            repo,
            "c1_toys",
            start_date_key=None,
            end_date_key=None,
            comparison_mode="pop",
        )
        is None
    )

    all_yoy = resolve_effective_comparison_window(
        repo,
        "c1_toys",
        start_date_key=None,
        end_date_key=None,
        comparison_mode="yoy",
    )
    assert all_yoy is not None
    assert all_yoy.cur_start == 20240101
    assert all_yoy.prev_start == 20230101

    explicit = resolve_effective_comparison_window(
        repo,
        "c1_toys",
        start_date_key=20241201,
        end_date_key=20241231,
        comp_start_date_key=20241101,
        comp_end_date_key=20241130,
        comparison_mode="pop",
    )
    assert explicit is not None
    assert (explicit.cur_start, explicit.cur_end) == (20241201, 20241231)
    assert (explicit.prev_start, explicit.prev_end) == (20241101, 20241130)


def test_all_pop_returns_none_deltas_across_five_services(repo: DuckDBRepository) -> None:
    """No modo Historico Global + PoP, nenhum delta comparativo deve ser preenchido."""
    sid = "c1_toys"
    ex = build_executive_dashboard(repo, sid, comparison_mode="pop").kpis
    co = build_commercial_dashboard(repo, sid, comparison_mode="pop").kpis
    fo = build_fortitude_dashboard(repo, sid, comparison_mode="pop").kpis
    te = build_temperance_dashboard(repo, sid, comparison_mode="pop").kpis
    pr = build_pricing_dashboard(repo, sid, comparison_mode="pop").kpis

    assert ex.deductions_pct_delta_pp is None
    assert ex.active_skus_delta_pct is None
    assert co.white_space_revenue_delta_pct is None
    assert co.rep_gross_revenue_delta_pct is None
    assert fo.runway_delta_months is None
    assert fo.ncg_delta_pct is None
    assert te.excess_discount_delta_pct is None
    assert pr.realization_idx_delta_pp is None


def test_all_yoy_and_explicit_month_deltas_across_five_services(repo: DuckDBRepository) -> None:
    """Valida deltas finitos nos 5 servicos em all+yoy (2024 vs 2023) e mes explicito (PoP)."""
    sid = "c1_toys"

    # 1. all + yoy (simetrico 2024 vs 2023)
    ex_yoy = build_executive_dashboard(repo, sid, comparison_mode="yoy").kpis
    co_yoy = build_commercial_dashboard(repo, sid, comparison_mode="yoy").kpis
    fo_yoy = build_fortitude_dashboard(repo, sid, comparison_mode="yoy").kpis
    te_yoy = build_temperance_dashboard(repo, sid, comparison_mode="yoy").kpis
    pr_yoy = build_pricing_dashboard(repo, sid, comparison_mode="yoy").kpis

    for val in (
        ex_yoy.deductions_pct_delta_pp,
        ex_yoy.active_skus_delta_pct,
        ex_yoy.curve_a_skus_delta_pct,
        co_yoy.avg_families_delta,
        co_yoy.active_customers_delta_pct,
        co_yoy.rep_gross_revenue_delta_pct,
        co_yoy.rep_margin_pct_delta_pp,
        fo_yoy.runway_delta_months,
        fo_yoy.breakeven_revenue_delta_pct,
        fo_yoy.ccc_delta_days,
        fo_yoy.ncg_delta_pct,
        fo_yoy.top10_share_delta_pp,
        te_yoy.excess_discount_delta_pct,
        te_yoy.financial_term_leak_delta_pct,
        te_yoy.total_erosion_delta_pct,
        pr_yoy.realization_idx_delta_pp,
        pr_yoy.price_cv_delta_pp,
        pr_yoy.below_band_delta_pp,
    ):
        assert val is not None
        assert math.isfinite(val)

    assert co_yoy.vampire_customers_delta is not None

    # 2. Janela explicita (Dez/2024 vs Nov/2024 - PoP)
    ex_m = build_executive_dashboard(
        repo,
        sid,
        start_date_key=20241201,
        end_date_key=20241231,
        comp_start_date_key=20241101,
        comp_end_date_key=20241130,
        comparison_mode="pop",
    ).kpis
    co_m = build_commercial_dashboard(
        repo,
        sid,
        start_date_key=20241201,
        end_date_key=20241231,
        comp_start_date_key=20241101,
        comp_end_date_key=20241130,
        comparison_mode="pop",
    ).kpis
    fo_m = build_fortitude_dashboard(
        repo,
        sid,
        start_date_key=20241201,
        end_date_key=20241231,
        comp_start_date_key=20241101,
        comp_end_date_key=20241130,
        comparison_mode="pop",
    ).kpis
    te_m = build_temperance_dashboard(
        repo,
        sid,
        start_date_key=20241201,
        end_date_key=20241231,
        comp_start_date_key=20241101,
        comp_end_date_key=20241130,
        comparison_mode="pop",
    ).kpis
    pr_m = build_pricing_dashboard(
        repo,
        sid,
        start_date_key=20241201,
        end_date_key=20241231,
        comp_start_date_key=20241101,
        comp_end_date_key=20241130,
        comparison_mode="pop",
    ).kpis

    assert ex_m.deductions_pct_delta_pp is not None
    assert co_m.rep_gross_revenue_delta_pct is not None
    assert fo_m.ncg_delta_pct is not None
    assert te_m.total_erosion_delta_pct is not None
    assert pr_m.realization_idx_delta_pp is not None
