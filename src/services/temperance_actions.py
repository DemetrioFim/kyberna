from __future__ import annotations

import pandas as pd

from src.services.dto import (
    CommercialPageDTO,
    FortitudePageDTO,
    TemperancePageDTO,
)
from src.services.inventory_dto import InventoryPageDTO
from src.services.pricing_dto import PricingPageDTO


def build_priority_actions_360(
    *,
    fort_dto: FortitudePageDTO,
    comm_dto: CommercialPageDTO,
    temp_dto: TemperancePageDTO,
    inv_dto: InventoryPageDTO,
    pricing_dto: PricingPageDTO,
) -> pd.DataFrame:
    """Consolida e ranqueia por impacto em R$ as 5 alavancas entre as Virtudes para Temperança."""
    ik = inv_dto.kpis
    ck = comm_dto.kpis
    tk = temp_dto.kpis
    fk = fort_dto.kpis
    pk = pricing_dto.kpis

    daily_net = fk.monthly_net_revenue_brl / 30.0 if fk.monthly_net_revenue_brl > 0.0 else 0.0
    ncg_10d_cash = daily_net * 10.0

    actions = [
        {
            "owner_pillar": "1. Prudência · Estoque",
            "initiative": (
                f"Reposição imediata de {ik.stockout_curve_a_skus_count} SKUs Curva A abaixo do ROP"
            ),
            "scope_detail": "Proteção de margem (26% sobre receita em risco 30d)",
            "recoverable_brl": round(ik.stockout_curve_a_revenue_brl * 0.26, 2),
        },
        {
            "owner_pillar": "2. Fortaleza · Retenção",
            "initiative": f"Reativação de {ck.at_risk_customers} lojistas em atraso crítico (>1,5x)",
            "scope_detail": "Captura estimada de 30% da margem anual em risco",
            "recoverable_brl": round(ck.annual_margin_at_risk_brl * 0.30, 2),
        },
        {
            "owner_pillar": "3. Justiça · Precificação",
            "initiative": "Contenção de vendas abaixo da banda P25 e reajuste inelásticos",
            "scope_detail": "70% do vazamento subprecificado + upside inelástico",
            "recoverable_brl": round(pk.subpricing_leakage_brl * 0.70 + pk.inelastic_reprice_upside_brl, 2),
        },
        {
            "owner_pillar": "2. Fortaleza · Alçadas",
            "initiative": "Trava sistêmica em descontos acima do teto por porte (RCAs)",
            "scope_detail": "Estancamento de 70% do excesso fora da política",
            "recoverable_brl": round(tk.excess_discount_brl * 0.70, 2),
        },
        {
            "owner_pillar": "1. Prudência / 3. Justiça",
            "initiative": f"Liquidação de {ik.locked_skus_count} SKUs >120d + redução de 10d no ciclo NCG",
            "scope_detail": "25% do estoque imobilizado + 10d de faturamento líquido no caixa",
            "recoverable_brl": round(ik.locked_capital_brl * 0.25 + ncg_10d_cash, 2),
        },
    ]
    df = pd.DataFrame(actions).sort_values("recoverable_brl", ascending=False).reset_index(drop=True)
    df.insert(0, "priority_rank", range(1, len(df) + 1))
    return df
