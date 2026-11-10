from __future__ import annotations

from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

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

    # Termômetro de Metas (Pacing) e Projeção (Virtus - Prudência)
    revenue_target_brl: float = 0.0
    revenue_pacing_pct: float = 100.0
    margin_target_pct: float = 26.0
    projected_quarter_revenue_brl: float = 0.0


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
    top_family_generators_df: pd.DataFrame = Field(default_factory=pd.DataFrame)
    top_family_destroyers_df: pd.DataFrame = Field(default_factory=pd.DataFrame)
    top_rep_generators_df: pd.DataFrame = Field(default_factory=pd.DataFrame)
    top_rep_destroyers_df: pd.DataFrame = Field(default_factory=pd.DataFrame)
    anomalies_df: pd.DataFrame = Field(default_factory=pd.DataFrame)
    pacing_kpis: dict[str, float] = Field(default_factory=dict)
    prescription_title: str
    prescription_html: str
    prescription_impact_brl: float | None = None
    period_label: str = "01/01/2023 a 31/12/2024 (24 Meses)"
    comparison_label: str = "Histórico Global Consolidado"
    as_of_date_label: str = "31/12/2024"
    monthly_sales_table_df: pd.DataFrame | None = None


class CommercialKpisDTO(BaseModel):
    """Métricas comerciais consolidadas do radar comercial e risco de churn."""

    total_customers: int
    active_customers: int
    at_risk_customers: int
    at_risk_customers_pct: float
    annual_revenue_at_risk_brl: float
    annual_margin_at_risk_brl: float
    white_space_potential_revenue_brl: float
    white_space_potential_margin_brl: float
    avg_positivation_pct: float
    attention_customers: int = 0
    attention_customers_pct: float = 0.0
    attention_revenue_brl: float = 0.0
    avg_ltv_brl: float = 0.0
    vampire_customers_count: int = 0


class CommercialPageDTO(BaseModel):
    """Payload completo e tipado consumido pela Página 3 (Justiça Comercial, Margem e Carteira)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    scenario_id: ScenarioId
    kpis: CommercialKpisDTO
    headline_title: str
    headline_text: str
    priority_risk_df: pd.DataFrame
    rfm_summary_df: pd.DataFrame
    white_space_matrix_df: pd.DataFrame
    rep_performance_df: pd.DataFrame
    cycle_funnel_df: pd.DataFrame = Field(default_factory=pd.DataFrame)
    top_white_space_deals_df: pd.DataFrame = Field(default_factory=pd.DataFrame)
    champions_df: pd.DataFrame = Field(default_factory=pd.DataFrame)
    vampires_df: pd.DataFrame = Field(default_factory=pd.DataFrame)
    top_family_generators_df: pd.DataFrame = Field(default_factory=pd.DataFrame)
    top_family_destroyers_df: pd.DataFrame = Field(default_factory=pd.DataFrame)
    top_product_generators_df: pd.DataFrame = Field(default_factory=pd.DataFrame)
    top_product_destroyers_df: pd.DataFrame = Field(default_factory=pd.DataFrame)
    top_customer_generators_df: pd.DataFrame = Field(default_factory=pd.DataFrame)
    top_customer_destroyers_df: pd.DataFrame = Field(default_factory=pd.DataFrame)
    top_rep_generators_df: pd.DataFrame = Field(default_factory=pd.DataFrame)
    top_rep_destroyers_df: pd.DataFrame = Field(default_factory=pd.DataFrame)
    prescription_title: str
    prescription_html: str
    prescription_impact_brl: float | None = None
    as_of_date_label: str = "31/12/2024"


class TemperanceKpisDTO(BaseModel):
    """Métricas consolidadas de controle de excessos, desperdícios e estoques."""

    # 1. Erosão Comercial
    gross_revenue: float
    total_commercial_erosion_brl: float  # discount + commission + freight
    total_commercial_erosion_pct: float  # erosion / gross * 100
    discount_amount: float
    discount_pct_of_gross: float

    # 2. Disciplina de Descontos e Prazos
    excess_discount_brl: float  # concedido acima do teto de tabela por porte
    excess_discount_pct_of_discount: float
    financial_term_leak_brl: float  # custo de carregamento para prazos > 30d
    freight_erosion_brl: float
    commission_erosion_brl: float

    # 3. Temperança de Estoque
    total_stock_value_brl: float
    locked_capital_brl: float  # estoque em SKUs com cobertura > 120d
    locked_skus_count: int
    stockout_risk_skus_count: int  # SKUs Curva A com cobertura <= lead_time
    stockout_risk_revenue_brl: float  # receita estimada em risco de ruptura


class TemperancePageDTO(BaseModel):
    """Payload completo e tipado consumido pela Página 4 — Temperança."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    scenario_id: ScenarioId
    kpis: TemperanceKpisDTO
    headline_title: str
    headline_text: str
    waterfall_df: pd.DataFrame
    policy_violations_by_rep_df: pd.DataFrame
    policy_violations_by_family_df: pd.DataFrame
    term_leak_by_rep_df: pd.DataFrame
    locked_inventory_df: pd.DataFrame
    stockout_risk_df: pd.DataFrame
    abc_xyz_summary_df: pd.DataFrame
    prescription_title: str
    prescription_html: str
    prescription_impact_brl: float | None = None
    as_of_date_label: str = "31/12/2024"
