from __future__ import annotations

import pandas as pd
import pandera.pandas as pa
from pandera.pandas import Field

from src.etl.gold_contracts import VALID_SCENARIO_IDS


class GoldPriceRealizationSchema(pa.DataFrameModel):
    """Contrato do mart Gold de realização de preço e banda contextual por SKU (`mart_price_realization`)."""

    scenario_id: str = Field(isin=VALID_SCENARIO_IDS, nullable=False)
    product_id: str = Field(nullable=False, str_length=13, description="Código de barras EAN-13")
    product_name: str = Field(nullable=False)
    family: str = Field(nullable=False)
    abc_class: str = Field(isin=["A", "B", "C"], nullable=False)
    units_sold: int = Field(ge=0, nullable=False)
    orders_count: int = Field(ge=0, nullable=False)
    base_unit_price: float = Field(gt=0.0, nullable=False)
    avg_list_price: float = Field(gt=0.0, nullable=False)
    avg_net_price: float = Field(gt=0.0, nullable=False)
    realized_idx_mean: float = Field(ge=0.0, nullable=False)
    realized_idx_p05: float = Field(ge=0.0, nullable=False)
    realized_idx_p25: float = Field(ge=0.0, nullable=False)
    realized_idx_p50: float = Field(ge=0.0, nullable=False)
    realized_idx_p75: float = Field(ge=0.0, nullable=False)
    realized_idx_p95: float = Field(ge=0.0, nullable=False)
    contextual_band_low_idx: float = Field(ge=0.0, nullable=False)
    contextual_band_expected_idx: float = Field(ge=0.0, nullable=False)
    contextual_band_high_idx: float = Field(ge=0.0, nullable=False)
    min_healthy_idx: float = Field(ge=0.0, nullable=False)
    price_cv_pct: float = Field(ge=0.0, nullable=False)
    below_band_orders_pct: float = Field(ge=0.0, le=100.0, nullable=False)
    price_leakage_brl: float = Field(ge=0.0, nullable=False)
    inelastic_upside_brl: float = Field(ge=0.0, nullable=False)
    primary_offender_rep: str = Field(nullable=False)
    snapshot_date: str = Field(nullable=False)

    @pa.dataframe_check
    @classmethod
    def check_quantile_band_and_leakage(cls, df: pd.DataFrame) -> pd.Series:
        """Garante ordenação dos quantis realizados, banda contextual [P25..P75] e vazamento >= 0."""
        tol = 1e-6
        return (
            (df["contextual_band_low_idx"] <= df["contextual_band_expected_idx"] + tol)
            & (df["contextual_band_expected_idx"] <= df["contextual_band_high_idx"] + tol)
            & (df["realized_idx_p05"] <= df["realized_idx_p25"] + tol)
            & (df["realized_idx_p25"] <= df["realized_idx_p50"] + tol)
            & (df["realized_idx_p50"] <= df["realized_idx_p75"] + tol)
            & (df["realized_idx_p75"] <= df["realized_idx_p95"] + tol)
            & (df["price_leakage_brl"] >= 0.0)
        )

    class Config:
        strict = False
        coerce = True


class GoldPricingDriversSchema(pa.DataFrameModel):
    """Contrato do mart Gold de drivers de preço Linear SHAP (`mart_pricing_drivers`)."""

    scenario_id: str = Field(isin=VALID_SCENARIO_IDS, nullable=False)
    scope_type: str = Field(isin=["family", "sku"], nullable=False)
    scope_id: str = Field(nullable=False)
    scope_label: str = Field(nullable=False)
    family: str = Field(nullable=False)
    base_idx: float = Field(gt=0.0, nullable=False)
    expected_idx: float = Field(gt=0.0, nullable=False)
    realized_idx: float = Field(gt=0.0, nullable=False)
    unjustified_gap_pp: float = Field(nullable=False)
    driver_order: int = Field(ge=1, le=5, nullable=False)
    driver_name: str = Field(
        isin=[
            "Porte do Cliente",
            "Volume do Pedido",
            "Campanha & Sazonalidade",
            "Frete CIF & Prazo Porte",
            "Posicionamento SKU",
        ],
        nullable=False,
    )
    shap_impact_pp: float = Field(nullable=False)
    snapshot_date: str = Field(nullable=False)

    class Config:
        strict = False
        coerce = True
