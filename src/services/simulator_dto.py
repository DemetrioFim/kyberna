from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from src.services.dto import ExecutiveKpisDTO

__all__ = [
    "SimulationBaseline",
    "SimulationLevers",
    "SimulationResult",
]


class SimulationBaseline(BaseModel):
    """Parametros financeiros de baseline para o Simulador What-If (M4-S4)."""

    model_config = ConfigDict(frozen=True)

    units_0: float = Field(gt=0.0)
    gross_revenue_0: float = Field(ge=0.0)
    discount_rate_0: float = Field(ge=0.0, le=0.50)
    tax_rate_eff: float = Field(ge=0.0, le=0.60)
    cogs_0: float = Field(ge=0.0)
    commission_rate_0: float = Field(ge=0.0, le=0.25)
    freight_0: float = Field(ge=0.0)
    beta_elasticity: float = -1.2

    @classmethod
    def from_executive_kpis(
        cls,
        kpis: ExecutiveKpisDTO,
        *,
        beta_elasticity: float = -1.2,
    ) -> SimulationBaseline:
        """Constroi um `SimulationBaseline` consistente a partir de `ExecutiveKpisDTO`."""
        gross_0 = max(float(kpis.gross_revenue), 0.0)
        net_price_0 = max(float(kpis.net_price_revenue), 0.0)
        disc_rate = min(max(kpis.discount_amount / gross_0, 0.0), 0.50) if gross_0 > 0.0 else 0.0
        tax_rate = min(max(kpis.tax_amount / net_price_0, 0.0), 0.60) if net_price_0 > 0.0 else 0.174
        comm_rate = min(max(kpis.commission_amount / net_price_0, 0.0), 0.25) if net_price_0 > 0.0 else 0.05
        return cls(
            units_0=float(max(kpis.total_units, 1)),
            gross_revenue_0=gross_0,
            discount_rate_0=disc_rate,
            tax_rate_eff=tax_rate,
            cogs_0=max(float(kpis.cogs), 0.0),
            commission_rate_0=comm_rate,
            freight_0=max(float(kpis.freight_amount), 0.0),
            beta_elasticity=float(beta_elasticity),
        )


class SimulationLevers(BaseModel):
    """Alavancas comerciais e operacionais do Simulador What-If (valores fracionarios)."""

    model_config = ConfigDict(frozen=True)

    delta_price_pct: float = Field(0.0, ge=-0.50, le=0.50)
    delta_discount_pp: float = Field(0.0, ge=-0.50, le=0.50)
    delta_commission_pp: float = Field(0.0, ge=-0.25, le=0.25)
    delta_cogs_pct: float = Field(0.0, ge=-0.50, le=0.50)
    apply_elasticity: bool = True
    beta_override: float | None = None
    band_low_change_pct: float = -0.12
    band_high_change_pct: float = 0.08


class SimulationResult(BaseModel):
    """Resultado completo do Simulador What-If, Breakeven, Curva Lucro x Preco e Tornado."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    units_0: float
    units_1: float
    volume_ratio: float
    projected_volume_change_pct: float
    net_price_ratio: float
    effective_discount_rate: float
    effective_commission_rate: float
    gross_revenue_0: float
    gross_revenue_1: float
    discount_amount_0: float
    discount_amount_1: float
    net_price_revenue_0: float
    net_price_revenue_1: float
    tax_amount_0: float
    tax_amount_1: float
    net_revenue_0: float
    net_revenue_1: float
    cogs_0: float
    cogs_1: float
    commission_amount_0: float
    commission_amount_1: float
    freight_0: float
    freight_1: float
    contribution_margin_0: float
    contribution_margin_1: float
    margin_pct_0: float
    margin_pct_1: float
    margin_delta_brl: float
    revenue_delta_brl: float
    unit_margin_1: float
    breakeven_volume_change_pct: float | None = None
    verdict: str
    optimal_price_change_pct: float
    optimal_margin_brl: float
    band_constrained_optimal_pct: float = 0.0
    is_outside_band: bool = False
    profit_curve_df: pd.DataFrame
    tornado_df: pd.DataFrame
