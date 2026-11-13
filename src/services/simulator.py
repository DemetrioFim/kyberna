from __future__ import annotations

from src.services.dto import ExecutiveKpisDTO


def simulate_quick_what_if(
    kpis: ExecutiveKpisDTO,
    *,
    price_change_pct: float = 0.0,
    discount_change_pp: float = 0.0,
    commission_or_cost_change_pct: float = 0.0,
    elasticity: float = -1.2,
) -> dict[str, float]:
    """Simula rapidamente o impacto de 3 alavancas no lucro líquido e calcula breakeven.

    Alavancas:
      - price_change_pct: variação percentual na tabela de preços (% delta).
      - discount_change_pp: variação em pontos percentuais no desconto médio.
      - commission_or_cost_change_pct: variação percentual no custo da mercadoria (COGS).
    """
    gross_0 = kpis.gross_revenue
    if gross_0 <= 0 or (
        price_change_pct == 0.0 and discount_change_pp == 0.0 and commission_or_cost_change_pct == 0.0
    ):
        return {
            "simulated_revenue_brl": gross_0,
            "simulated_margin_brl": kpis.contribution_margin,
            "simulated_margin_pct": kpis.contribution_margin_pct,
            "margin_delta_brl": 0.0,
            "breakeven_volume_pct": 0.0,
            "estimated_volume_pct": 0.0,
        }

    if price_change_pct == 0.0 and discount_change_pp == 0.0 and commission_or_cost_change_pct == 0.0:
        return {
            "simulated_revenue_brl": round(gross_0, 2),
            "simulated_margin_brl": round(kpis.contribution_margin, 2),
            "simulated_margin_pct": round(kpis.contribution_margin / gross_0 * 100.0, 2),
            "margin_delta_brl": 0.0,
            "breakeven_volume_pct": 0.0,
            "estimated_volume_pct": 0.0,
        }

    disc_0 = kpis.discount_amount / gross_0 if gross_0 > 0 else 0.0
    disc_1 = min(max(disc_0 + discount_change_pp / 100.0, 0.0), 0.50)
    price_factor = 1.0 + price_change_pct / 100.0
    net_price_ratio = max(price_factor * (1.0 - disc_1) / max(1.0 - disc_0, 0.01), 0.05)

    vol_factor = max(net_price_ratio**elasticity, 0.05)
    estimated_vol_pct = round((vol_factor - 1.0) * 100.0, 1)

    gross_1 = gross_0 * vol_factor * price_factor
    net_price_rev_1 = gross_1 * (1.0 - disc_1)
    tax_rate = kpis.tax_amount / kpis.net_price_revenue if kpis.net_price_revenue > 0 else 0.174
    net_rev_1 = net_price_rev_1 * (1.0 - tax_rate)

    cogs_factor = 1.0 + commission_or_cost_change_pct / 100.0
    cogs_1 = kpis.cogs * vol_factor * cogs_factor
    comm_rate = kpis.commission_amount / kpis.net_price_revenue if kpis.net_price_revenue > 0 else 0.05
    comm_1 = net_price_rev_1 * comm_rate
    freight_1 = kpis.freight_amount * vol_factor

    margin_1 = net_rev_1 - cogs_1 - comm_1 - freight_1
    margin_pct_1 = round(margin_1 / gross_1 * 100.0, 2) if gross_1 > 0 else 0.0
    margin_delta = round(margin_1 - kpis.contribution_margin, 2)

    margin_at_base_vol = margin_1 / vol_factor
    breakeven_vol = (
        round(((kpis.contribution_margin / margin_at_base_vol) - 1.0) * 100.0, 1)
        if (margin_at_base_vol > 0 and kpis.contribution_margin > 0)
        else 999.0
    )

    return {
        "simulated_revenue_brl": round(gross_1, 2),
        "simulated_margin_brl": round(margin_1, 2),
        "simulated_margin_pct": margin_pct_1,
        "margin_delta_brl": margin_delta,
        "breakeven_volume_pct": breakeven_vol,
        "estimated_volume_pct": estimated_vol_pct,
    }
