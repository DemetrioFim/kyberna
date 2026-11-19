from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from src.core.types import ScenarioId
from src.db.repository import DataRepository
from src.services.inventory_dto import (
    InventoryKpisDTO,
    InventoryPageDTO,
    SkuForecastSeriesDTO,
)
from src.services.inventory_queries import (
    query_forecast_30d_rollup,
    query_forecast_sku_options,
    query_inventory_position,
    query_sku_forecast_series,
)


def build_inventory_dashboard(
    repo: DataRepository,
    scenario_id: ScenarioId = "c1_toys",
    *,
    families: Sequence[str] = (),
) -> InventoryPageDTO:
    """Agrega posição prescritiva de estoque, treemap de capital travado e opções de forecast."""
    position_df = query_inventory_position(repo, scenario_id, families=families)
    sku_options_df = query_forecast_sku_options(repo, scenario_id, families=families)
    fc_rollup = query_forecast_30d_rollup(repo, scenario_id, families=families)

    if position_df.empty:
        return InventoryPageDTO(
            scenario_id=scenario_id,
            kpis=InventoryKpisDTO(
                total_stock_value_brl=0.0,
                locked_capital_brl=0.0,
                locked_skus_count=0,
                stockout_risk_skus_count=0,
                protected_revenue_brl=0.0,
                suggested_order_boxes_total=0,
                healthy_skus_count=0,
                attention_skus_count=0,
                stockout_curve_a_skus_count=0,
                stockout_curve_a_revenue_brl=0.0,
                forecast_30d_units_total=int(fc_rollup["forecast_30d_units_total"]),
                forecast_30d_revenue_brl=float(fc_rollup["forecast_30d_revenue_brl"]),
            ),
            position_df=position_df,
            stockout_df=pd.DataFrame(),
            locked_df=pd.DataFrame(),
            treemap_df=pd.DataFrame(),
            sku_options_df=sku_options_df,
        )

    stockout_mask = (position_df["stock_status"] == "Ruptura Iminente") | (
        position_df["suggested_order_boxes"] > 0
    )
    stockout_df = (
        position_df.loc[stockout_mask]
        .sort_values(["protected_revenue_brl", "suggested_order_boxes"], ascending=[False, False])
        .reset_index(drop=True)
    )

    locked_df = (
        position_df.loc[position_df["locked_capital_brl"] > 0.0]
        .sort_values("locked_capital_brl", ascending=False)
        .reset_index(drop=True)
    )

    treemap_df = (
        locked_df[
            ["product_id", "product_name", "family", "abc_xyz_class", "coverage_days", "locked_capital_brl"]
        ]
        .copy()
        .reset_index(drop=True)
    )

    locked_capital_total = float(treemap_df["locked_capital_brl"].sum()) if not treemap_df.empty else 0.0
    curve_a_rup_mask = (position_df["stock_status"] == "Ruptura Iminente") & (position_df["abc_class"] == "A")
    curve_a_rup_df = position_df.loc[curve_a_rup_mask]
    kpis = InventoryKpisDTO(
        total_stock_value_brl=float(position_df["stock_value_brl"].sum()),
        locked_capital_brl=locked_capital_total,
        locked_skus_count=int((position_df["stock_status"] == "Capital Travado").sum()),
        stockout_risk_skus_count=int((position_df["stock_status"] == "Ruptura Iminente").sum()),
        protected_revenue_brl=float(stockout_df["protected_revenue_brl"].sum())
        if not stockout_df.empty
        else 0.0,
        suggested_order_boxes_total=int(stockout_df["suggested_order_boxes"].sum())
        if not stockout_df.empty
        else 0,
        healthy_skus_count=int((position_df["stock_status"] == "Saudável").sum()),
        attention_skus_count=int((position_df["stock_status"] == "Atenção (Excesso Moderado)").sum()),
        stockout_curve_a_skus_count=len(curve_a_rup_df),
        stockout_curve_a_revenue_brl=round(float(curve_a_rup_df["protected_revenue_brl"].sum()), 2)
        if not curve_a_rup_df.empty
        else 0.0,
        forecast_30d_units_total=int(fc_rollup["forecast_30d_units_total"]),
        forecast_30d_revenue_brl=float(fc_rollup["forecast_30d_revenue_brl"]),
    )

    return InventoryPageDTO(
        scenario_id=scenario_id,
        kpis=kpis,
        position_df=position_df,
        stockout_df=stockout_df,
        locked_df=locked_df,
        treemap_df=treemap_df,
        sku_options_df=sku_options_df,
    )


def get_sku_forecast_series(
    repo: DataRepository,
    scenario_id: ScenarioId = "c1_toys",
    *,
    product_id: str,
) -> SkuForecastSeriesDTO:
    """Retorna a série temporal de histórico 90d + previsão 30d de um SKU."""
    series_df = query_sku_forecast_series(repo, scenario_id, product_id=product_id)
    if series_df.empty:
        return SkuForecastSeriesDTO(
            product_id=product_id,
            product_name=product_id,
            family="—",
            abc_xyz_class="—",
            selected_model="—",
            family_wape_pct=0.0,
            sku_mae=0.0,
            forecast_30d_total_units=0.0,
            series_df=series_df,
        )

    series_df = series_df.copy()
    series_df["date"] = pd.to_datetime(series_df["date"])
    first = series_df.iloc[0]
    fc_mask = series_df["record_type"] == "forecast"
    fc_total = float(series_df.loc[fc_mask, "forecast_units"].fillna(0.0).sum())

    return SkuForecastSeriesDTO(
        product_id=str(first["product_id"]),
        product_name=str(first["product_name"]),
        family=str(first["family"]),
        abc_xyz_class=str(first["abc_xyz_class"]),
        selected_model=str(first["selected_model"]),
        family_wape_pct=float(first["family_wape_pct"]),
        sku_mae=float(first["sku_mae"]),
        forecast_30d_total_units=round(fc_total, 1),
        series_df=series_df,
    )
