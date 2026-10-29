from __future__ import annotations

from typing import Literal

Environment = Literal["dev", "ci", "prod"]
DataBackend = Literal["auto", "azure_sql", "duckdb"]
AzureSqlAuth = Literal["token", "sql"]

ScenarioId = Literal[
    "c1_toys",
    "c2_beverages",
    "c3_retail_chain",
    "c4_single_store",
]

GoldTable = Literal[
    "dim_date",
    "dim_product",
    "dim_customer",
    "dim_sales_rep",
    "dim_branch",
    "dim_geography",
    "fact_sales",
    "mart_margin_monthly",
    "mart_abc_xyz",
    "mart_customer_risk",
    "mart_white_space",
    "mart_rep_performance",
    "mart_forecast_30d",
    "mart_inventory_position",
    "mart_price_elasticity",
    "mart_branch_transfers",
]
