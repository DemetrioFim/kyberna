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
    white_space_eligible_customers: int = 0
    white_space_total_offers: int = 0
    avg_families_per_customer: float = 0.0
    total_catalog_families: int = 7
    apriori_rules_count: int = 0
    apriori_max_lift: float = 0.0
    apriori_avg_confidence_pct: float = 0.0
    apriori_avg_support_pct: float = 0.0


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
    apriori_rules_df: pd.DataFrame = Field(default_factory=pd.DataFrame)
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


class FortitudeKpisDTO(BaseModel):
    """KPIs consolidados de solvência, liquidez, ciclo financeiro e concentração (Fortaleza)."""

    cash_reserve_brl: float
    cash_runway_months: float
    cash_reserve_target_months: float
    fixed_costs_monthly_brl: float
    monthly_gross_revenue_brl: float
    monthly_net_revenue_brl: float
    monthly_contribution_margin_brl: float
    free_cash_generation_brl: float
    margin_pct_of_gross: float
    margin_pct_of_net: float
    breakeven_revenue_brl: float
    breakeven_day_of_month: int
    pme_days: float
    pmr_days: float
    pmp_days: float
    cash_conversion_cycle_days: float
    ncg_brl: float
    top5_customers_share_pct: float
    top10_customers_share_pct: float
    top2_families_share_pct: float
    active_customers_count: int
    at_risk_portfolio_brl: float
    at_risk_portfolio_pct: float
    at_risk_customers_count: int


class FortitudePageDTO(BaseModel):
    """Payload completo e tipado consumido pela Página 2 — Fortaleza."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    scenario_id: ScenarioId
    kpis: FortitudeKpisDTO
    headline_title: str
    headline_text: str
    breakeven_curve_df: pd.DataFrame
    cycle_components_df: pd.DataFrame
    customer_concentration_df: pd.DataFrame
    family_concentration_df: pd.DataFrame
    aging_buckets_df: pd.DataFrame
    aging_customers_df: pd.DataFrame = Field(default_factory=pd.DataFrame)
    prescription_title: str
    prescription_html: str
    prescription_impact_brl: float | None = None
    as_of_date_label: str = "31/12/2024"


class SimulationBaseline(BaseModel):
    """Parâmetros financeiros de baseline para o Simulador What-If (M4-S4)."""

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
        """Constrói um `SimulationBaseline` consistente a partir de `ExecutiveKpisDTO`."""
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
    """Alavancas comerciais e operacionais do Simulador What-If (valores fracionários)."""

    model_config = ConfigDict(frozen=True)

    delta_price_pct: float = Field(0.0, ge=-0.50, le=0.50)
    delta_discount_pp: float = Field(0.0, ge=-0.50, le=0.50)
    delta_commission_pp: float = Field(0.0, ge=-0.25, le=0.25)
    delta_cogs_pct: float = Field(0.0, ge=-0.50, le=0.50)
    apply_elasticity: bool = True
    beta_override: float | None = None


class SimulationResult(BaseModel):
    """Resultado completo do Simulador What-If, Breakeven, Curva Lucro x Preço e Tornado."""

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
    profit_curve_df: pd.DataFrame
    tornado_df: pd.DataFrame
