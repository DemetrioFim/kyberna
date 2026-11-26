from __future__ import annotations

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from src.core.types import ScenarioId


class PricingKpisDTO(BaseModel):
    """KPIs consolidados de Precificação Contextual & Realização vs. Tabela."""

    realization_index_pct: float
    price_cv_pct: float
    below_band_sales_pct: float
    subpricing_leakage_brl: float
    inelastic_reprice_upside_brl: float
    orders_count: int = 0
    skus_count: int = 0


class PricingShapDTO(BaseModel):
    """Decomposição Linear SHAP de um escopo (Família ou SKU) para Waterfall."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    scope_type: str
    scope_id: str
    scope_label: str
    family: str
    base_idx: float
    expected_idx: float
    realized_idx: float
    unjustified_gap_pp: float
    table_gross_brl: float = 0.0
    expected_net_brl: float = 0.0
    realized_net_brl: float = 0.0
    unjustified_gap_brl: float = 0.0
    avg_base_unit_brl: float = 0.0
    units_sold: int = 0
    drivers_df: pd.DataFrame = Field(default_factory=pd.DataFrame)


class PricingPageDTO(BaseModel):
    """Payload completo de Precificação Contextual para 3. Justiça (Aba 3) e Simulador."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    scenario_id: ScenarioId
    kpis: PricingKpisDTO
    boxplot_df: pd.DataFrame = Field(default_factory=pd.DataFrame)
    deviations_df: pd.DataFrame = Field(default_factory=pd.DataFrame)
    shap_options_df: pd.DataFrame = Field(default_factory=pd.DataFrame)
    family_bands_df: pd.DataFrame = Field(default_factory=pd.DataFrame)
    prescription_title: str = ""
    prescription_html: str = ""
    prescription_impact_brl: float | None = None
