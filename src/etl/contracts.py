from __future__ import annotations

import pandas as pd
import pandera.pandas as pa
from pandera.errors import SchemaErrors
from pandera.pandas import Field

from src.core.logging import logger

VALID_SCENARIO_IDS = [
    "c1_toys",
    "c2_beverages",
    "c3_retail_chain",
    "c4_single_store",
]


class DataContractError(Exception):
    """Exceção levantada quando um dataset viola o contrato de dados de sua camada."""

    def __init__(self, message: str, failures: pd.DataFrame | None = None) -> None:
        super().__init__(message)
        self.failures = failures


# ==============================================================================
# Camada Bronze: Dado Bruto como String + Metadados de Ingestão
# ==============================================================================
class BronzeSalesSchema(pa.DataFrameModel):
    """Contrato da camada Bronze (dados da API Socrata armazenados como string)."""

    invoice_and_item_number: str = Field(nullable=False, description="Chave natural da linha")
    date: str = Field(nullable=False)
    store_number: str = Field(nullable=False)
    store_name: str = Field(nullable=False)
    address: str = Field(nullable=True)
    city: str = Field(nullable=True)
    zip_code: str = Field(nullable=True)
    store_location: str = Field(nullable=True)
    county_number: str = Field(nullable=True)
    county: str = Field(nullable=True)
    category: str = Field(nullable=True)
    category_name: str = Field(nullable=True)
    vendor_number: str = Field(nullable=True)
    vendor_name: str = Field(nullable=True)
    item_number: str = Field(nullable=False)
    item_description: str = Field(nullable=False)
    pack: str = Field(nullable=False)
    bottle_volume_ml: str = Field(nullable=False)
    state_bottle_cost: str = Field(nullable=False)
    state_bottle_retail: str = Field(nullable=False)
    bottles_sold: str = Field(nullable=False)
    sale_dollars: str = Field(nullable=False)
    volume_sold_liters: str = Field(nullable=True)
    volume_sold_gallons: str = Field(nullable=True)

    # Metadados de Ingestão
    _ingested_at: str = Field(nullable=False)
    _batch_id: str = Field(nullable=False)
    _source: str = Field(nullable=False)

    class Config:
        strict = False  # Permite colunas extras se houver
        coerce = False


# ==============================================================================
# Camada Silver: Modelo Canônico Limpo, Tipado e Validado
# ==============================================================================
class SilverSalesSchema(pa.DataFrameModel):
    """Contrato da tabela fato canônica Silver no DuckDB/Parquet."""

    invoice_line_id: str = Field(unique=True, nullable=False, description="Identificador único da linha")
    date: pd.Timestamp = Field(nullable=False)
    original_date: pd.Timestamp | None = Field(
        default=None, nullable=True, required=False, description="Data original antes do time-shift"
    )
    time_shift_days: int | None = Field(
        default=None, nullable=True, required=False, description="Offset de dias aplicado pelo time-shift"
    )
    store_number: str = Field(nullable=False)
    store_name: str = Field(nullable=False)
    city: str = Field(nullable=False)
    county: str = Field(nullable=False)
    zip_code: str | None = Field(default=None, nullable=True)
    chain_name: str | None = Field(default=None, nullable=True, description="Rede varejista derivada da loja")
    category_name: str = Field(nullable=False)
    vendor_number: str | None = Field(default=None, nullable=True)
    vendor_name: str = Field(nullable=False)
    item_number: str = Field(nullable=False)
    item_description: str = Field(nullable=False)
    pack: int = Field(ge=1, le=96, nullable=False, description="Unidades por caixa")
    bottle_volume_ml: float = Field(gt=0, nullable=False)
    unit_cost: float = Field(gt=0, nullable=False)
    unit_price: float = Field(gt=0, nullable=False)
    units: int = Field(gt=0, nullable=False, description="Quantidade de unidades vendidas")
    sale_amount: float = Field(gt=0, nullable=False, description="Valor monetário da venda")

    @pa.dataframe_check
    @classmethod
    def check_unit_price_sanity(cls, df: pd.DataFrame) -> pd.Series:
        """Regra de negócio: Preço de venda unitário não pode ser inferior a 50% do custo."""
        return df["unit_price"] >= (df["unit_cost"] * 0.5)

    class Config:
        strict = True
        coerce = True


class SilverCustomerSchema(pa.DataFrameModel):
    """Contrato da dimensão sintética de clientes (lojistas / CNPJs)."""

    customer_id: str = Field(unique=True, nullable=False)
    store_number: str = Field(unique=True, nullable=False)
    cnpj: str = Field(nullable=False, str_length={"min_value": 14, "max_value": 18})
    company_name: str = Field(nullable=False)
    trade_name: str = Field(nullable=False)
    segment: str = Field(nullable=False)
    size: str = Field(isin=["P", "M", "G"], nullable=False)
    city: str = Field(nullable=False)
    state: str = Field(str_length=2, nullable=False)
    region: str = Field(isin=["Sudeste", "Sul", "Nordeste", "Centro-Oeste", "Norte"], nullable=False)
    sales_rep_id: str = Field(nullable=False)
    whatsapp: str = Field(nullable=False)
    email: str = Field(nullable=False)

    class Config:
        strict = True
        coerce = True


class SilverSalesRepSchema(pa.DataFrameModel):
    """Contrato da dimensão sintética de Representantes Comerciais (RCAs)."""

    sales_rep_id: str = Field(unique=True, nullable=False)
    name: str = Field(nullable=False)
    region: str = Field(isin=["Sudeste", "Sul", "Nordeste", "Centro-Oeste", "Norte"], nullable=False)
    commission_rate: float = Field(ge=0.01, le=0.15, nullable=False)

    class Config:
        strict = True
        coerce = True


# ==============================================================================
# Camada Gold: Fato de Vendas e Waterfall Financeiro
# ==============================================================================
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


# ==============================================================================
# Helper Unificado de Validação
# ==============================================================================
def validate_contract(
    df: pd.DataFrame,
    schema: type[pa.DataFrameModel] | pa.DataFrameSchema,
    layer: str = "dados",
    lazy: bool = True,
) -> pd.DataFrame:
    """Valida um DataFrame contra um contrato Pandera e resume eventuais falhas.

    Args:
        df: DataFrame a ser validado.
        schema: Classe DataFrameModel ou instância DataFrameSchema.
        layer: Nome identificador da camada ('Bronze', 'Silver', 'Gold').
        lazy: Se True, acumula todos os erros de validação antes de falhar.

    Returns:
        pd.DataFrame validado (e com tipos coagidos, se aplicável).

    Raises:
        DataContractError: Se qualquer checagem ou tipo for violado.
    """
    try:
        return schema.validate(df, lazy=lazy)
    except SchemaErrors as err:
        failure_cases: pd.DataFrame = err.failure_cases
        n_failures = len(failure_cases)
        logger.error(
            "Violação de contrato de dados na camada '%s' com %d inconformidades.",
            layer,
            n_failures,
            extra={
                "layer": layer,
                "failures_count": n_failures,
                "top_failures": failure_cases.head(5).to_dict(orient="records"),
            },
        )
        msg = (
            f"Contrato de dados da camada '{layer}' violado com {n_failures} falhas. "
            f"Exemplos de regras violadas: {list(failure_cases['check'].unique()[:3])}"
        )
        raise DataContractError(msg, failures=failure_cases) from err
