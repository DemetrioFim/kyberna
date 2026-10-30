from __future__ import annotations

import pandas as pd
import pytest

from src.etl.contracts import (
    BronzeSalesSchema,
    DataContractError,
    GoldFactSalesSchema,
    SilverCustomerSchema,
    SilverSalesSchema,
    validate_contract,
)


@pytest.fixture
def valid_bronze_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "invoice_and_item_number": "INV-001",
                "date": "2024-01-15",
                "store_number": "2190",
                "store_name": "Test Store",
                "address": "123 Main St",
                "city": "Des Moines",
                "zip_code": "50314",
                "store_location": "POINT (-93.6 41.6)",
                "county_number": "77",
                "county": "Polk",
                "category": "1011100",
                "category_name": "Vodka",
                "vendor_number": "260",
                "vendor_name": "Diageo",
                "item_number": "35916",
                "item_description": "Smirnoff 80",
                "pack": "12",
                "bottle_volume_ml": "750",
                "state_bottle_cost": "8.25",
                "state_bottle_retail": "12.38",
                "bottles_sold": "24",
                "sale_dollars": "297.12",
                "volume_sold_liters": "18.0",
                "volume_sold_gallons": "4.75",
                "_ingested_at": "2024-01-16T10:00:00Z",
                "_batch_id": "batch-01",
                "_source": "socrata",
            }
        ]
    )


@pytest.fixture
def valid_silver_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "invoice_line_id": "INV-001",
                "date": pd.Timestamp("2024-01-15"),
                "store_number": "2190",
                "store_name": "Test Store",
                "city": "Des Moines",
                "county": "Polk",
                "zip_code": "50314",
                "category_name": "Vodka",
                "vendor_number": "260",
                "vendor_name": "Diageo",
                "item_number": "35916",
                "item_description": "Smirnoff 80",
                "pack": 12,
                "bottle_volume_ml": 750.0,
                "unit_cost": 8.25,
                "unit_price": 12.38,
                "units": 24,
                "sale_amount": 297.12,
            }
        ]
    )


@pytest.fixture
def valid_gold_fact_df() -> pd.DataFrame:
    units = 24
    list_price = 15.0
    gross = units * list_price  # 360.0
    discount = 36.0  # 10%
    net_price = gross - discount  # 324.0
    tax = 58.32  # 18%
    net_revenue = net_price - tax  # 265.68
    cogs = 192.0  # 8.0 * 24
    commission = 16.20  # 5% sobre net_price
    freight = 10.0
    margin = net_revenue - cogs - commission - freight  # 47.48

    return pd.DataFrame(
        [
            {
                "scenario_id": "c1_toys",
                "order_id": "ORD-100",
                "date_key": 20240115,
                "customer_id": "CUST-01",
                "product_id": "PROD-01",
                "sales_rep_id": "REP-01",
                "branch_id": "BR-01",
                "units": units,
                "boxes": 2.0,
                "unit_list_price": list_price,
                "unit_net_price": 13.5,
                "gross_revenue": gross,
                "discount_amount": discount,
                "tax_amount": tax,
                "net_revenue": net_revenue,
                "cogs": cogs,
                "commission_amount": commission,
                "freight_amount": freight,
                "contribution_margin": margin,
            }
        ]
    )


def test_bronze_contract_valid(valid_bronze_df: pd.DataFrame) -> None:
    """Verifica que dataset Bronze válido passa na validação."""
    validated = validate_contract(valid_bronze_df, BronzeSalesSchema, layer="Bronze")
    assert not validated.empty


def test_bronze_contract_missing_column(valid_bronze_df: pd.DataFrame) -> None:
    """Verifica que coluna obrigatória ausente na Bronze dispara DataContractError."""
    invalid_df = valid_bronze_df.drop(columns=["invoice_and_item_number"])
    with pytest.raises(DataContractError) as exc_info:
        validate_contract(invalid_df, BronzeSalesSchema, layer="Bronze")
    assert "inconformidades" in str(exc_info.value) or "violado" in str(exc_info.value)


def test_silver_contract_valid(valid_silver_df: pd.DataFrame) -> None:
    """Verifica que dataset Silver canônico válido passa na validação."""
    validated = validate_contract(valid_silver_df, SilverSalesSchema, layer="Silver")
    assert len(validated) == 1


def test_silver_contract_duplicate_key(valid_silver_df: pd.DataFrame) -> None:
    """Verifica que duplicidade de chave primária é rejeitada na Silver."""
    dup_df = pd.concat([valid_silver_df, valid_silver_df], ignore_index=True)
    with pytest.raises(DataContractError):
        validate_contract(dup_df, SilverSalesSchema, layer="Silver")


def test_silver_contract_invalid_pack(valid_silver_df: pd.DataFrame) -> None:
    """Verifica que pack fora do intervalo [1, 96] dispara erro."""
    bad_df = valid_silver_df.copy()
    bad_df.loc[0, "pack"] = 120
    with pytest.raises(DataContractError):
        validate_contract(bad_df, SilverSalesSchema, layer="Silver")


def test_silver_contract_unit_price_sanity(valid_silver_df: pd.DataFrame) -> None:
    """Verifica que preço de venda abaixo de 50% do custo dispara erro de sanidade."""
    bad_df = valid_silver_df.copy()
    bad_df.loc[0, "unit_cost"] = 100.0
    bad_df.loc[0, "unit_price"] = 20.0  # menor que 50.0 (50% do custo)
    with pytest.raises(DataContractError):
        validate_contract(bad_df, SilverSalesSchema, layer="Silver")


def test_silver_customer_contract() -> None:
    """Testa regras da dimensão sintética de clientes."""
    valid_customer = pd.DataFrame(
        [
            {
                "customer_id": "CUST-001",
                "store_number": "2190",
                "cnpj": "12345678000195",
                "company_name": "Brinquedos ABC Ltda",
                "trade_name": "Loja ABC",
                "segment": "Varejo",
                "size": "M",
                "city": "Campinas",
                "state": "SP",
                "region": "Sudeste",
                "sales_rep_id": "REP-01",
                "whatsapp": "+5519999998888",
                "email": "contato@abc.com.br",
            }
        ]
    )
    validated = validate_contract(valid_customer, SilverCustomerSchema, layer="SilverCustomer")
    assert len(validated) == 1

    # Porte inválido
    bad_customer = valid_customer.copy()
    bad_customer.loc[0, "size"] = "EXTRA_LARGE"
    with pytest.raises(DataContractError):
        validate_contract(bad_customer, SilverCustomerSchema, layer="SilverCustomer")


def test_gold_contract_valid(valid_gold_fact_df: pd.DataFrame) -> None:
    """Verifica que dataset Gold de fatos de vendas é válido."""
    validated = validate_contract(valid_gold_fact_df, GoldFactSalesSchema, layer="Gold")
    assert len(validated) == 1


def test_gold_contract_invalid_scenario(valid_gold_fact_df: pd.DataFrame) -> None:
    """Verifica que cenário não reconhecido é bloqueado."""
    bad_df = valid_gold_fact_df.copy()
    bad_df.loc[0, "scenario_id"] = "c9_invalid_scenario"
    with pytest.raises(DataContractError):
        validate_contract(bad_df, GoldFactSalesSchema, layer="Gold")


def test_gold_contract_margin_identity_violation(valid_gold_fact_df: pd.DataFrame) -> None:
    """Verifica que quebra da identidade contábil do waterfall dispara erro."""
    bad_df = valid_gold_fact_df.copy()
    bad_df.loc[0, "contribution_margin"] = 99999.0  # valor arbitrário incorreto
    with pytest.raises(DataContractError):
        validate_contract(bad_df, GoldFactSalesSchema, layer="Gold")

