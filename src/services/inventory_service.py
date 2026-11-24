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
    query_family_forecast_30d,
    query_forecast_30d_rollup,
    query_forecast_sku_options,
    query_inventory_position,
    query_sku_forecast_series,
)


def _build_family_supply_df(
    position_df: pd.DataFrame,
    family_fc_df: pd.DataFrame,
) -> pd.DataFrame:
    """Agrega posição de estoque, risco de ruptura (Curva A vs B/C) e demanda 30d por família."""
    if position_df.empty:
        return pd.DataFrame()

    df = position_df.copy()
    is_rup = df["stock_status"] == "Ruptura Iminente"
    is_a = df["abc_class"] == "A"
    df["curve_a_revenue_brl"] = df["protected_revenue_brl"].where(is_rup & is_a, 0.0)
    df["other_curves_revenue_brl"] = df["protected_revenue_brl"].where(is_rup & (~is_a), 0.0)
    df["is_stockout"] = is_rup.astype(int)

    fam_df = df.groupby("family", as_index=False).agg(
        skus_count=("product_id", "count"),
        stock_units=("stock_units", "sum"),
        stockout_skus=("is_stockout", "sum"),
        curve_a_revenue_brl=("curve_a_revenue_brl", "sum"),
        other_curves_revenue_brl=("other_curves_revenue_brl", "sum"),
        protected_revenue_brl=("protected_revenue_brl", "sum"),
        suggested_order_boxes=("suggested_order_boxes", "sum"),
        locked_capital_brl=("locked_capital_brl", "sum"),
    )
    if not family_fc_df.empty:
        fam_df = fam_df.merge(family_fc_df, on="family", how="left")
    else:
        fam_df["forecast_30d_units"] = 0
        fam_df["family_wape_pct"] = 0.0
    fam_df["forecast_30d_units"] = fam_df["forecast_30d_units"].fillna(0).astype(int)
    fam_df["family_wape_pct"] = fam_df["family_wape_pct"].fillna(0.0).round(1)
    return fam_df.sort_values("protected_revenue_brl", ascending=False).reset_index(drop=True)


def _build_pcp_plan_df(position_df: pd.DataFrame) -> pd.DataFrame:
    """Monta o plano mestre de necessidade de compra/produção por SKU para PCP."""
    if position_df.empty:
        return pd.DataFrame()
    df = position_df.copy()
    df["forecast_30d_units"] = (df["forecast_daily_demand"] * 30.0).round().astype(int)
    mask = (df["suggested_order_boxes"] > 0) | (df["coverage_days"] < 30.0)
    cols = [
        "product_id",
        "product_name",
        "family",
        "abc_xyz_class",
        "stock_units",
        "forecast_30d_units",
        "reorder_point_units",
        "suggested_order_boxes",
        "protected_revenue_brl",
    ]
    return (
        df.loc[mask, cols]
        .sort_values(["suggested_order_boxes", "protected_revenue_brl"], ascending=[False, False])
        .reset_index(drop=True)
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
    family_fc_df = query_family_forecast_30d(repo, scenario_id, families=families)

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
                weighted_wape_pct=float(fc_rollup["weighted_wape_pct"]),
                last_30d_actual_units=int(fc_rollup["last_30d_actual_units"]),
                forecast_vs_30d_pct=float(fc_rollup["forecast_vs_30d_pct"]),
                seasonal_peak_skus_count=0,
            ),
            position_df=position_df,
            stockout_df=pd.DataFrame(),
            locked_df=pd.DataFrame(),
            treemap_df=pd.DataFrame(),
            sku_options_df=sku_options_df,
            family_supply_df=pd.DataFrame(),
            pcp_plan_df=pd.DataFrame(),
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
    seasonal_peak_cnt = int(
        ((position_df["xyz_class"] == "Y") & (position_df["suggested_order_boxes"] > 0)).sum()
    )
    family_supply_df = _build_family_supply_df(position_df, family_fc_df)
    pcp_plan_df = _build_pcp_plan_df(position_df)
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
        weighted_wape_pct=float(fc_rollup["weighted_wape_pct"]),
        last_30d_actual_units=int(fc_rollup["last_30d_actual_units"]),
        forecast_vs_30d_pct=float(fc_rollup["forecast_vs_30d_pct"]),
        seasonal_peak_skus_count=seasonal_peak_cnt,
    )

    return InventoryPageDTO(
        scenario_id=scenario_id,
        kpis=kpis,
        position_df=position_df,
        stockout_df=stockout_df,
        locked_df=locked_df,
        treemap_df=treemap_df,
        sku_options_df=sku_options_df,
        family_supply_df=family_supply_df,
        pcp_plan_df=pcp_plan_df,
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
