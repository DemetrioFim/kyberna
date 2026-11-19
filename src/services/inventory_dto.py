from __future__ import annotations

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from src.core.types import ScenarioId


class InventoryKpisDTO(BaseModel):
    """Métricas consolidadas da Posição Prescritiva de Estoque (`mart_inventory_position`)."""

    total_stock_value_brl: float
    locked_capital_brl: float
    locked_skus_count: int
    stockout_risk_skus_count: int
    protected_revenue_brl: float
    suggested_order_boxes_total: int
    healthy_skus_count: int
    attention_skus_count: int
    stockout_curve_a_skus_count: int = 0
    stockout_curve_a_revenue_brl: float = 0.0
    forecast_30d_units_total: int = 0
    forecast_30d_revenue_brl: float = 0.0


class SkuForecastSeriesDTO(BaseModel):
    """Série temporal de demanda 90d + previsão 30d e métricas de erro para um SKU."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    product_id: str
    product_name: str
    family: str
    abc_xyz_class: str
    selected_model: str
    family_wape_pct: float
    sku_mae: float
    forecast_30d_total_units: float
    series_df: pd.DataFrame = Field(default_factory=pd.DataFrame)


class InventoryPageDTO(BaseModel):
    """Payload completo de Posição de Estoque e opções de Forecast por SKU."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    scenario_id: ScenarioId
    kpis: InventoryKpisDTO
    position_df: pd.DataFrame = Field(default_factory=pd.DataFrame)
    stockout_df: pd.DataFrame = Field(default_factory=pd.DataFrame)
    locked_df: pd.DataFrame = Field(default_factory=pd.DataFrame)
    treemap_df: pd.DataFrame = Field(default_factory=pd.DataFrame)
    sku_options_df: pd.DataFrame = Field(default_factory=pd.DataFrame)
