from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pandas as pd

from src.core.logging import get_logger
from src.core.types import ScenarioId
from src.db.repository import DataRepository

logger = get_logger(__name__)

__all__ = [
    "query_family_forecast_30d",
    "query_forecast_30d_rollup",
    "query_forecast_sku_options",
    "query_inventory_position",
    "query_sku_forecast_series",
]


def _build_family_clause(families: Sequence[str], alias: str = "") -> tuple[str, list[Any]]:
    """Constrói cláusula SQL segura de filtro por família de produtos."""
    if not families:
        return "", []
    prefix = f"{alias}." if alias else ""
    fam_list = list(families)
    placeholders = ", ".join(["?"] * len(fam_list))
    return f" AND {prefix}family IN ({placeholders})", fam_list


def query_inventory_position(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    families: Sequence[str] = (),
) -> pd.DataFrame:
    """Consulta a posição prescritiva de estoque em `gold.mart_inventory_position`."""
    fam_clause, fam_params = _build_family_clause(families)
    params: list[Any] = [scenario_id, *fam_params]
    sql = f"""
    SELECT
        scenario_id,
        branch_id,
        product_id,
        product_name,
        family,
        abc_class,
        xyz_class,
        abc_xyz_class,
        pack,
        unit_cost,
        unit_list_price,
        stock_units,
        stock_boxes,
        stock_value_brl,
        forecast_daily_demand,
        daily_demand_std,
        lead_time_days,
        safety_stock_units,
        reorder_point_units,
        coverage_days,
        days_to_stockout,
        stock_status,
        suggested_order_boxes,
        protected_revenue_brl,
        locked_capital_brl,
        action_prescription,
        snapshot_date
    FROM gold.mart_inventory_position
    WHERE scenario_id = ? {fam_clause}
    ORDER BY
        CASE stock_status
            WHEN 'Ruptura Iminente' THEN 1
            WHEN 'Capital Travado' THEN 2
            WHEN 'Atenção (Excesso Moderado)' THEN 3
            ELSE 4
        END,
        protected_revenue_brl DESC,
        locked_capital_brl DESC,
        product_name ASC
    """
    try:
        return repo.query(sql, params=params)
    except Exception as exc:
        logger.warning("mart_inventory_position indisponível para %s: %s", scenario_id, exc)
        return pd.DataFrame()


def query_forecast_sku_options(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    families: Sequence[str] = (),
) -> pd.DataFrame:
    """Lista os SKUs disponíveis para consulta no Forecast 30d ordenados por relevância."""
    fam_clause, fam_params = _build_family_clause(families, alias="fc")
    params: list[Any] = [scenario_id, *fam_params]
    sql = f"""
    SELECT DISTINCT
        fc.product_id,
        COALESCE(pos.product_name, p.product_name, fc.product_id) AS product_name,
        fc.family,
        COALESCE(pos.abc_xyz_class, 'CZ') AS abc_xyz_class,
        fc.selected_model,
        fc.family_wape_pct,
        fc.sku_mae
    FROM gold.mart_forecast_30d fc
    LEFT JOIN gold.mart_inventory_position pos
      ON fc.scenario_id = pos.scenario_id AND fc.product_id = pos.product_id
    LEFT JOIN gold.dim_product p
      ON fc.product_id = p.product_id
    WHERE fc.scenario_id = ? {fam_clause}
    ORDER BY
        CASE LEFT(COALESCE(pos.abc_xyz_class, 'CZ'), 1)
            WHEN 'A' THEN 1
            WHEN 'B' THEN 2
            ELSE 3
        END,
        product_name ASC
    """
    try:
        return repo.query(sql, params=params)
    except Exception as exc:
        logger.warning("mart_forecast_30d indisponível para %s: %s", scenario_id, exc)
        return pd.DataFrame()


def query_sku_forecast_series(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    product_id: str,
) -> pd.DataFrame:
    """Retorna a série diária (90d histórico + 30d forecast) para um SKU específico."""
    sql = """
    SELECT
        fc.product_id,
        COALESCE(pos.product_name, p.product_name, fc.product_id) AS product_name,
        fc.family,
        COALESCE(pos.abc_xyz_class, 'CZ') AS abc_xyz_class,
        fc.date,
        fc.record_type,
        fc.actual_units,
        fc.forecast_units,
        fc.lo_80,
        fc.hi_80,
        fc.lo_95,
        fc.hi_95,
        fc.selected_model,
        fc.family_wape_pct,
        fc.sku_mae
    FROM gold.mart_forecast_30d fc
    LEFT JOIN gold.mart_inventory_position pos
      ON fc.scenario_id = pos.scenario_id AND fc.product_id = pos.product_id
    LEFT JOIN gold.dim_product p
      ON fc.product_id = p.product_id
    WHERE fc.scenario_id = ? AND fc.product_id = ?
    ORDER BY fc.date ASC
    """
    try:
        return repo.query(sql, params=[scenario_id, product_id])
    except Exception as exc:
        logger.warning("Erro ao consultar série de forecast para %s (%s): %s", product_id, scenario_id, exc)
        return pd.DataFrame()


def query_forecast_30d_rollup(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    families: Sequence[str] = (),
) -> dict[str, float | int]:
    """Soma unidades, faturamento previsto (30d), WAPE ponderado e variação vs. últimos 30d reais."""
    fam_clause, fam_params = _build_family_clause(families, alias="fc")
    params: list[Any] = [scenario_id, scenario_id, *fam_params]
    sql = f"""
    WITH max_hist AS (
        SELECT COALESCE(MAX(date), DATE '2024-12-31') AS mx
        FROM gold.mart_forecast_30d
        WHERE scenario_id = ? AND record_type = 'historical'
    )
    SELECT
        COALESCE(SUM(CASE WHEN fc.record_type = 'forecast' THEN fc.forecast_units ELSE 0.0 END), 0.0)
            AS forecast_30d_units_total,
        COALESCE(
            SUM(
                CASE WHEN fc.record_type = 'forecast'
                THEN fc.forecast_units * COALESCE(pos.unit_list_price, p.base_unit_price, 0.0)
                ELSE 0.0 END
            ),
            0.0
        ) AS forecast_30d_revenue_brl,
        COALESCE(
            SUM(
                CASE WHEN fc.record_type = 'forecast'
                THEN fc.forecast_units * fc.family_wape_pct ELSE 0.0 END
            )
            / NULLIF(SUM(CASE WHEN fc.record_type = 'forecast' THEN fc.forecast_units ELSE 0.0 END), 0.0),
            0.0
        ) AS weighted_wape_pct,
        COALESCE(
            SUM(
                CASE WHEN fc.record_type = 'historical'
                     AND fc.date > (SELECT mx - INTERVAL 30 DAY FROM max_hist)
                THEN fc.actual_units ELSE 0.0 END
            ),
            0.0
        ) AS last_30d_actual_units
    FROM gold.mart_forecast_30d fc
    LEFT JOIN gold.mart_inventory_position pos
      ON fc.scenario_id = pos.scenario_id AND fc.product_id = pos.product_id
    LEFT JOIN gold.dim_product p
      ON fc.product_id = p.product_id
    WHERE fc.scenario_id = ? {fam_clause}
    """
    try:
        df = repo.query(sql, params=params)
        if not df.empty:
            r0 = df.iloc[0]
            fc_units = round(float(r0["forecast_30d_units_total"]))
            hist_units = round(float(r0["last_30d_actual_units"]))
            delta_pct = round(((fc_units - hist_units) / hist_units) * 100.0, 1) if hist_units > 0 else 0.0
            return {
                "forecast_30d_units_total": fc_units,
                "forecast_30d_revenue_brl": round(float(r0["forecast_30d_revenue_brl"]), 2),
                "weighted_wape_pct": round(float(r0["weighted_wape_pct"]), 1),
                "last_30d_actual_units": hist_units,
                "forecast_vs_30d_pct": delta_pct,
            }
    except Exception as exc:
        logger.warning("Rollup de forecast 30d indisponível para %s: %s", scenario_id, exc)
    return {
        "forecast_30d_units_total": 0,
        "forecast_30d_revenue_brl": 0.0,
        "weighted_wape_pct": 0.0,
        "last_30d_actual_units": 0,
        "forecast_vs_30d_pct": 0.0,
    }


def query_family_forecast_30d(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    families: Sequence[str] = (),
) -> pd.DataFrame:
    """Agrega demanda prevista 30d e WAPE médio por família."""
    fam_clause, fam_params = _build_family_clause(families)
    params: list[Any] = [scenario_id, *fam_params]
    sql = f"""
    SELECT
        family,
        ROUND(COALESCE(SUM(forecast_units), 0.0), 0)::INTEGER AS forecast_30d_units,
        ROUND(COALESCE(AVG(family_wape_pct), 0.0), 1) AS family_wape_pct
    FROM gold.mart_forecast_30d
    WHERE scenario_id = ? AND record_type = 'forecast' {fam_clause}
    GROUP BY family
    ORDER BY forecast_30d_units DESC
    """
    try:
        return repo.query(sql, params=params)
    except Exception as exc:
        logger.warning("Forecast por família indisponível para %s: %s", scenario_id, exc)
        return pd.DataFrame(columns=["family", "forecast_30d_units", "family_wape_pct"])
