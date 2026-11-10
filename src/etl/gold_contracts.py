from __future__ import annotations

import pandas as pd
import pandera.pandas as pa
from pandera.pandas import Field

VALID_SCENARIO_IDS = [
    "c1_toys",
    "c2_beverages",
    "c3_retail_chain",
    "c4_single_store",
]


class GoldFactSalesSchema(pa.DataFrameModel):
    """Contrato da tabela Gold fact_sales por cenário com decomposição do waterfall."""

    scenario_id: str = Field(isin=VALID_SCENARIO_IDS, nullable=False)
    order_id: str = Field(nullable=False)
    date_key: int = Field(ge=20200101, le=20301231, nullable=False)
    customer_id: str = Field(nullable=False)
    product_id: str = Field(nullable=False)
    sales_rep_id: str = Field(nullable=False)
    branch_id: str = Field(nullable=False)
    units: int = Field(gt=0, nullable=False)
    boxes: float = Field(gt=0, nullable=False)
    unit_list_price: float = Field(gt=0, nullable=False)
    unit_net_price: float = Field(gt=0, nullable=False)
    gross_revenue: float = Field(ge=0, nullable=False)
    discount_amount: float = Field(ge=0, nullable=False)
    tax_amount: float = Field(ge=0, nullable=False)
    net_revenue: float = Field(nullable=False)
    cogs: float = Field(ge=0, nullable=False)
    commission_amount: float = Field(ge=0, nullable=False)
    freight_amount: float = Field(ge=0, nullable=False)
    contribution_margin: float = Field(nullable=False)

    @pa.dataframe_check
    @classmethod
    def check_contribution_margin_identity(cls, df: pd.DataFrame) -> pd.Series:
        """Validação contábil: Margem de contribuição deve fechar com tolerância de centavos."""
        expected_margin = df["net_revenue"] - df["cogs"] - df["commission_amount"] - df["freight_amount"]
        return (df["contribution_margin"] - expected_margin).abs() < 0.05

    class Config:
        strict = False
        coerce = True


class GoldAbcXyzSchema(pa.DataFrameModel):
    """Contrato do mart analítico da Matriz ABC/XYZ e políticas prescritivas por SKU."""

    scenario_id: str = Field(isin=VALID_SCENARIO_IDS, nullable=False)
    as_of_date: str = Field(nullable=False)
    product_id: str = Field(nullable=False, str_length=13, description="EAN-13")
    item_number: str = Field(nullable=False)
    product_name: str = Field(nullable=False)
    family: str = Field(nullable=False)
    pack: int = Field(ge=1, nullable=False)
    units_sold: int = Field(ge=0, nullable=False)
    boxes_sold: float = Field(ge=0.0, nullable=False)
    gross_revenue: float = Field(ge=0.0, nullable=False)
    contribution_margin: float = Field(nullable=False)
    margin_pct: float | None = Field(nullable=True)
    weekly_demand_mean: float = Field(ge=0.0, nullable=False)
    weekly_demand_std: float = Field(ge=0.0, nullable=False)
    weekly_cv: float = Field(ge=0.0, nullable=False)
    revenue_share: float = Field(ge=0.0, le=1.0001, nullable=False)
    cum_revenue_share: float = Field(ge=0.0, le=1.0001, nullable=False)
    margin_share: float = Field(nullable=False)
    cum_margin_share: float = Field(nullable=False)
    abc_class: str = Field(isin=["A", "B", "C"], nullable=False)
    xyz_class: str = Field(isin=["X", "Y", "Z"], nullable=False)
    abc_xyz_class: str = Field(isin=["AX", "AY", "AZ", "BX", "BY", "BZ", "CX", "CY", "CZ"], nullable=False)
    policy: str = Field(nullable=False)
    snapshot_date: str = Field(nullable=False)

    class Config:
        strict = False
        coerce = True


class GoldRfmSchema(pa.DataFrameModel):
    """Contrato do mart analítico da Segmentação RFM baseada em Margem de Contribuição."""

    scenario_id: str = Field(isin=VALID_SCENARIO_IDS, nullable=False)
    as_of_date: str = Field(nullable=False)
    customer_id: str = Field(nullable=False)
    recency_days: int = Field(ge=0, nullable=False)
    frequency: int = Field(ge=1, nullable=False)
    gross_revenue: float = Field(ge=0.0, nullable=False)
    net_revenue: float = Field(nullable=False)
    contribution_margin: float = Field(nullable=False)
    margin_pct: float | None = Field(nullable=True)
    r_score: int = Field(isin=[1, 2, 3, 4, 5], nullable=False)
    f_score: int = Field(isin=[1, 2, 3, 4, 5], nullable=False)
    m_score: int = Field(isin=[1, 2, 3, 4, 5], nullable=False)
    rfm_cell: str = Field(nullable=False)
    rfm_score: float = Field(ge=1.0, le=5.0, nullable=False)
    rfm_segment: str = Field(
        isin=[
            "Campeões",
            "Não Pode Perder",
            "Fiéis",
            "Promissores",
            "Novos Clientes",
            "Em Risco",
            "Precisam de Atenção",
            "Hibernando",
            "Perdidos",
        ],
        nullable=False,
    )
    rfm_segment_description: str = Field(nullable=False)
    action_prescription: str = Field(nullable=False)
    snapshot_date: str = Field(nullable=False)

    class Config:
        strict = False
        coerce = True


class GoldCustomerRiskSchema(pa.DataFrameModel):
    """Contrato do mart analítico de ciclo individual de recompra e risco heurístico de Churn."""

    scenario_id: str = Field(isin=VALID_SCENARIO_IDS, nullable=False)
    as_of_date: str = Field(nullable=False)
    customer_id: str = Field(nullable=False)
    recency_days: int = Field(ge=0, nullable=False)
    frequency: int = Field(ge=1, nullable=False)
    expected_cycle_days: float = Field(gt=0.0, nullable=False)
    cycle_std_days: float = Field(ge=0.0, nullable=False)
    delay_ratio: float = Field(ge=0.0, nullable=False)
    churn_probability: float = Field(ge=0.0, le=1.0001, nullable=False)
    risk_status: str = Field(
        isin=["No Ciclo", "Atenção", "Em Risco Imediato", "Adormecido / Perdido"],
        nullable=False,
    )
    annual_revenue_at_risk: float = Field(ge=0.0, nullable=False)
    annual_margin_at_risk: float = Field(nullable=False)
    snapshot_date: str = Field(nullable=False)

    class Config:
        strict = False
        coerce = True


class GoldWhiteSpaceSchema(pa.DataFrameModel):
    """Contrato do mart analítico da Matriz White Space e Recomendações de Cross-Sell B2B."""

    scenario_id: str = Field(isin=VALID_SCENARIO_IDS, nullable=False)
    as_of_date: str = Field(nullable=False)
    customer_id: str = Field(nullable=False)
    recommended_family: str = Field(nullable=False)
    rank_order: int = Field(isin=[1, 2, 3], nullable=False)
    opportunity_score: float = Field(ge=0.0, le=1.0001, nullable=False)
    item_affinity_score: float = Field(ge=0.0, le=1.0001, nullable=False)
    lookalike_score: float = Field(ge=0.0, le=1.0001, nullable=False)
    peer_penetration_pct: float = Field(ge=0.0, le=100.0, nullable=False)
    peer_median_annual_revenue: float = Field(ge=0.0, nullable=False)
    churn_probability: float = Field(ge=0.0, le=1.0001, nullable=False)
    potential_revenue_brl: float = Field(ge=0.0, nullable=False)
    potential_margin_brl: float = Field(nullable=False)
    explanation_text: str = Field(nullable=False)
    action_pitch: str = Field(nullable=False)
    snapshot_date: str = Field(nullable=False)

    class Config:
        strict = False
        coerce = True


class GoldRepPerformanceSchema(pa.DataFrameModel):
    """Contrato do mart analítico de Eficiência Comercial de Representantes (Quadrante de RCAs)."""

    scenario_id: str = Field(isin=VALID_SCENARIO_IDS, nullable=False)
    as_of_date: str = Field(nullable=False)
    sales_rep_id: str = Field(nullable=False)
    sales_rep_name: str = Field(nullable=False)
    region: str = Field(nullable=False)
    commission_rate: float = Field(ge=0.0, le=0.20, nullable=False)
    portfolio_customers: int = Field(ge=0, nullable=False)
    active_customers: int = Field(ge=0, nullable=False)
    positivation_pct: float = Field(ge=0.0, le=100.0, nullable=False)
    avg_families_per_customer: float = Field(ge=0.0, nullable=False)
    orders_count: int = Field(ge=0, nullable=False)
    gross_revenue: float = Field(ge=0.0, nullable=False)
    discount_amount: float = Field(ge=0.0, nullable=False)
    avg_discount_pct: float = Field(ge=0.0, le=100.0, nullable=False)
    net_revenue: float = Field(nullable=False)
    commission_amount: float = Field(ge=0.0, nullable=False)
    contribution_margin: float = Field(nullable=False)
    margin_pct: float = Field(nullable=False)
    at_risk_customers_count: int = Field(ge=0, nullable=False)
    at_risk_customers_pct: float = Field(ge=0.0, le=100.0, nullable=False)
    revenue_at_risk_brl: float = Field(ge=0.0, nullable=False)
    margin_at_risk_brl: float = Field(nullable=False)
    white_space_potential_brl: float = Field(ge=0.0, nullable=False)
    white_space_margin_brl: float = Field(nullable=False)
    quadrant: str = Field(
        isin=["Estrela", "Volume sem margem", "Margem sem volume", "Atenção"],
        nullable=False,
    )
    action_prescription: str = Field(nullable=False)
    snapshot_date: str = Field(nullable=False)

    class Config:
        strict = False
        coerce = True


class GoldInventorySnapshotSchema(pa.DataFrameModel):
    """Contrato da tabela Gold de snapshot diário de posição de estoque."""

    scenario_id: str = Field(isin=VALID_SCENARIO_IDS, nullable=False)
    snapshot_date: str = Field(nullable=False)
    branch_id: str = Field(nullable=False)
    product_id: str = Field(nullable=False)
    family: str = Field(nullable=False)
    pack: int = Field(ge=1, nullable=False, description="Unidades por caixa master")
    unit_cost: float = Field(gt=0.0, nullable=False, description="Custo unitário de aquisição (R$)")
    avg_daily_demand_90d: float = Field(ge=0.0, nullable=False, description="Demanda diária (unidades)")
    stock_units: int = Field(ge=0, nullable=False, description="Unidades físicas em estoque")
    stock_boxes: float = Field(ge=0.0, nullable=False, description="Caixas master equivalentes")
    stock_value_brl: float = Field(ge=0.0, nullable=False, description="Valor contábil em estoque (R$)")
    coverage_days: float = Field(ge=0.0, nullable=False, description="Dias de cobertura (ritmo 90d)")
    lead_time_days: int = Field(ge=1, nullable=False, description="Tempo de reposição do fornecedor em dias")
    last_receipt_date: str = Field(nullable=False, description="Data estimada do último recebimento")

    class Config:
        strict = False
        coerce = True
