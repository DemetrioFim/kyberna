from __future__ import annotations

import pytest

from src.services.dto import ExecutiveKpisDTO
from src.services.simulator import simulate_quick_what_if


def _make_sample_kpis(*, gross_revenue: float = 1_000_000.0) -> ExecutiveKpisDTO:
    """Constrói um DTO sintético consistente para testes determinísticos do simulador What-If."""
    if gross_revenue <= 0:
        return ExecutiveKpisDTO(
            gross_revenue=0.0,
            discount_amount=0.0,
            net_price_revenue=0.0,
            tax_amount=0.0,
            net_revenue=0.0,
            cogs=0.0,
            commission_amount=0.0,
            freight_amount=0.0,
            contribution_margin=0.0,
            contribution_margin_pct=0.0,
            total_orders=0,
            active_customers=0,
            avg_ticket=0.0,
            total_boxes=0.0,
            total_units=0,
        )

    discount_amount = gross_revenue * 0.08
    net_price_revenue = gross_revenue - discount_amount
    tax_amount = net_price_revenue * 0.174
    net_revenue = net_price_revenue - tax_amount
    cogs = gross_revenue * 0.43
    commission_amount = net_price_revenue * 0.05
    freight_amount = gross_revenue * 0.011
    contribution_margin = net_revenue - cogs - commission_amount - freight_amount
    margin_pct = round(contribution_margin / gross_revenue * 100.0, 2)

    return ExecutiveKpisDTO(
        gross_revenue=gross_revenue,
        discount_amount=discount_amount,
        net_price_revenue=net_price_revenue,
        tax_amount=tax_amount,
        net_revenue=net_revenue,
        cogs=cogs,
        commission_amount=commission_amount,
        freight_amount=freight_amount,
        contribution_margin=contribution_margin,
        contribution_margin_pct=margin_pct,
        total_orders=1000,
        active_customers=100,
        avg_ticket=gross_revenue / 1000,
        total_boxes=5000.0,
        total_units=50_000,
    )


def test_what_if_zero_levers_preserves_baseline() -> None:
    """Com todas as alavancas zeradas (0, 0, 0), não há alteração de receita nem de margem."""
    kpis = _make_sample_kpis()
    res = simulate_quick_what_if(
        kpis,
        price_change_pct=0.0,
        discount_change_pp=0.0,
        commission_or_cost_change_pct=0.0,
    )

    assert res["simulated_revenue_brl"] == pytest.approx(kpis.gross_revenue, abs=1e-2)
    assert res["simulated_margin_brl"] == pytest.approx(kpis.contribution_margin, abs=1e-2)
    assert res["simulated_margin_pct"] == pytest.approx(kpis.contribution_margin_pct, abs=1e-2)
    assert res["margin_delta_brl"] == 0.0
    assert res["breakeven_volume_pct"] == 0.0
    assert res["estimated_volume_pct"] == 0.0


def test_what_if_discount_increase_compresses_margin_and_raises_breakeven() -> None:
    """Aumento de desconto comprime margem unitária e exige expansão de volume (breakeven > 0)."""
    kpis = _make_sample_kpis()
    res = simulate_quick_what_if(kpis, discount_change_pp=5.0, elasticity=-1.2)

    assert res["breakeven_volume_pct"] > 0.0
    assert res["estimated_volume_pct"] > 0.0
    assert res["simulated_margin_pct"] < kpis.contribution_margin_pct
    assert res["margin_delta_brl"] < 0.0


def test_what_if_third_lever_cost_change_impacts_margin() -> None:
    """Variações na 3ª alavanca (custo/CMV) impactam diretamente margem e breakeven."""
    kpis = _make_sample_kpis()

    res_cost_down = simulate_quick_what_if(kpis, commission_or_cost_change_pct=-10.0)
    assert res_cost_down["simulated_margin_brl"] > kpis.contribution_margin
    assert res_cost_down["margin_delta_brl"] > 0.0
    assert res_cost_down["breakeven_volume_pct"] < 0.0

    res_cost_up = simulate_quick_what_if(kpis, commission_or_cost_change_pct=10.0)
    assert res_cost_up["simulated_margin_brl"] < kpis.contribution_margin
    assert res_cost_up["margin_delta_brl"] < 0.0
    assert res_cost_up["breakeven_volume_pct"] > 0.0


def test_what_if_margin_destruction_returns_unviable_breakeven() -> None:
    """Quando a margem unitária simulada torna-se <= 0, o breakeven retorna a sentinela 999.0."""
    kpis = _make_sample_kpis()
    res = simulate_quick_what_if(kpis, commission_or_cost_change_pct=150.0)

    assert res["simulated_margin_brl"] <= 0.0
    assert res["breakeven_volume_pct"] == 999.0


def test_what_if_zero_gross_revenue_returns_safe_zeros() -> None:
    """Receita bruta zerada não provoca divisão por zero e devolve zeros seguros."""
    kpis = _make_sample_kpis(gross_revenue=0.0)
    res = simulate_quick_what_if(kpis, price_change_pct=5.0, discount_change_pp=2.0)

    assert res["simulated_revenue_brl"] == 0.0
    assert res["simulated_margin_brl"] == 0.0
    assert res["simulated_margin_pct"] == 0.0
    assert res["margin_delta_brl"] == 0.0
    assert res["breakeven_volume_pct"] == 0.0
    assert res["estimated_volume_pct"] == 0.0

