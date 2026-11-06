from __future__ import annotations

from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict

from src.core.types import ScenarioId


class ExecutiveKpisDTO(BaseModel):
    """Métricas executivas consolidadas do período e filtros selecionados."""

    gross_revenue: float
    discount_amount: float
    net_price_revenue: float
    tax_amount: float
    net_revenue: float
    cogs: float
    commission_amount: float
    freight_amount: float
    contribution_margin: float
    contribution_margin_pct: float
    total_orders: int
    active_customers: int
    avg_ticket: float
    total_boxes: float
    total_units: int

    # Deltas contra o período anterior
    gross_revenue_delta_pct: float | None = None
    net_revenue_delta_pct: float | None = None
    contribution_margin_delta_pct: float | None = None
    margin_pct_delta_pp: float | None = None
    active_customers_delta_pct: float | None = None


class WaterfallStepDTO(BaseModel):
    """Etapa individual do Waterfall contábil de decomposição da margem."""

    step_key: str
    label: str
    amount: float
    pct_of_gross: float
    measure: Literal["absolute", "relative", "total"]


class AbcXyzCellDTO(BaseModel):
    """Resumo de uma célula da Matriz 3x3 ABC/XYZ."""

    abc_class: str
    xyz_class: str
    abc_xyz_cell: str
    sku_count: int
    sku_share_pct: float
    gross_revenue: float
    contribution_margin: float
    margin_share_pct: float
    avg_margin_rate: float
    recommended_policy: str


class MarginDriverDTO(BaseModel):
    """Entidade (SKU ou Lojista) de destaque como gerador ou destruidor de margem."""

    entity_id: str
    name: str
    secondary_label: str
    gross_revenue: float
    discount_pct: float
    contribution_margin: float
    margin_pct: float


class ExecutivePageDTO(BaseModel):
    """Payload completo e tipado consumido pela Tela 1 (Visão Executiva & Margem Real)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    scenario_id: ScenarioId
    kpis: ExecutiveKpisDTO
    headline_title: str
    headline_text: str
    waterfall_df: pd.DataFrame
    monthly_trend_df: pd.DataFrame
    abc_xyz_matrix_df: pd.DataFrame
    abc_xyz_skus_df: pd.DataFrame
    top_generators_df: pd.DataFrame
    top_destroyers_df: pd.DataFrame
    top_customer_generators_df: pd.DataFrame
    top_customer_destroyers_df: pd.DataFrame
    prescription_title: str
    prescription_html: str
    prescription_impact_brl: float | None = None
    period_label: str = "01/01/2023 a 31/12/2024 (24 Meses)"
    comparison_label: str = "Histórico Global Consolidado"
    as_of_date_label: str = "31/12/2024"
    monthly_sales_table_df: pd.DataFrame | None = None
