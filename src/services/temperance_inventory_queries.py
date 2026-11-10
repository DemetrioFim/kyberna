from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pandas as pd

from src.core.logging import get_logger
from src.core.types import ScenarioId
from src.db.repository import DataRepository

logger = get_logger(__name__)

__all__ = [
    "query_temperance_inventory_details",
    "query_temperance_inventory_kpis",
]


def query_temperance_inventory_kpis(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    families: Sequence[str] = (),
) -> dict[str, float | int]:
    """Consulta métricas agregadas de estoque, capital imobilizado e risco de ruptura."""
    inv_params: list[Any] = [scenario_id]
    inv_fam_clause = ""
    if families:
        fam_list = list(families)
        ph = ", ".join(["?"] * len(fam_list))
        inv_fam_clause = f" AND inv.family IN ({ph})"
        inv_params.extend(fam_list)

    inv_sql = f"""
    SELECT
        COALESCE(SUM(inv.stock_value_brl), 0.0) AS total_stock_value_brl,
        COALESCE(SUM(CASE WHEN inv.coverage_days > 120.0
            THEN inv.stock_value_brl ELSE 0.0 END), 0.0) AS locked_capital_brl,
        COUNT(CASE WHEN inv.coverage_days > 120.0 THEN 1 END) AS locked_skus_count,
        COUNT(CASE WHEN abc.abc_class = 'A' AND inv.coverage_days <= inv.lead_time_days
            THEN 1 END) AS stockout_risk_skus_count,
        COALESCE(SUM(CASE WHEN abc.abc_class = 'A' AND inv.coverage_days <= inv.lead_time_days
            THEN inv.avg_daily_demand_90d * 90.0 * p.base_unit_price ELSE 0.0 END), 0.0)
            AS stockout_risk_revenue_brl
    FROM gold.inventory_snapshot inv
    JOIN gold.dim_product p ON inv.product_id = p.product_id
    LEFT JOIN gold.mart_abc_xyz abc
      ON inv.product_id = abc.product_id AND inv.scenario_id = abc.scenario_id
    WHERE inv.scenario_id = ? {inv_fam_clause}
    """
    df_inv = repo.query(inv_sql, params=inv_params)
    if not df_inv.empty:
        r0 = df_inv.iloc[0]
        return {
            "total_stock_value_brl": float(r0["total_stock_value_brl"]),
            "locked_capital_brl": float(r0["locked_capital_brl"]),
            "locked_skus_count": int(r0["locked_skus_count"]),
            "stockout_risk_skus_count": int(r0["stockout_risk_skus_count"]),
            "stockout_risk_revenue_brl": float(r0["stockout_risk_revenue_brl"]),
        }

    return {
        "total_stock_value_brl": 0.0,
        "locked_capital_brl": 0.0,
        "locked_skus_count": 0,
        "stockout_risk_skus_count": 0,
        "stockout_risk_revenue_brl": 0.0,
    }


def query_temperance_inventory_details(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    families: Sequence[str] = (),
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Retorna tabelas detalhadas de capital imobilizado, risco de ruptura e matriz ABC/XYZ."""
    inv_params: list[Any] = [scenario_id]
    inv_fam_clause = ""
    if families:
        fam_list = list(families)
        ph = ", ".join(["?"] * len(fam_list))
        inv_fam_clause = f" AND inv.family IN ({ph})"
        inv_params.extend(fam_list)

    # 1. Capital Travado (> 120 dias)
    locked_sql = f"""
    SELECT
        inv.product_id,
        p.product_name,
        inv.family,
        inv.pack,
        inv.stock_units,
        inv.stock_boxes,
        inv.stock_value_brl,
        inv.coverage_days,
        COALESCE(abc.abc_xyz_class, 'CZ') AS cell,
        COALESCE(abc.policy, 'Liquidação de lote / Fechamento de estoque') AS action_prescription
    FROM gold.inventory_snapshot inv
    JOIN gold.dim_product p ON inv.product_id = p.product_id
    LEFT JOIN gold.mart_abc_xyz abc
      ON inv.product_id = abc.product_id AND inv.scenario_id = abc.scenario_id
    WHERE inv.scenario_id = ? AND inv.coverage_days > 120.0 {inv_fam_clause}
    ORDER BY inv.stock_value_brl DESC
    """
    df_locked = repo.query(locked_sql, params=inv_params)

    # 2. Ruptura Iminente (Curva A/B com cobertura <= lead time)
    stockout_sql = f"""
    SELECT
        inv.product_id,
        p.product_name,
        inv.family,
        inv.pack,
        inv.stock_units,
        inv.stock_boxes,
        inv.coverage_days,
        inv.lead_time_days,
        ROUND(inv.avg_daily_demand_90d, 2) AS avg_daily_demand_90d,
        GREATEST(1, ROUND(((45.0 - inv.coverage_days) * inv.avg_daily_demand_90d) / inv.pack))::INTEGER
            AS suggested_order_boxes,
        ROUND(inv.avg_daily_demand_90d * 90.0 * p.base_unit_price, 2) AS revenue_at_risk_brl,
        abc.abc_xyz_class AS cell
    FROM gold.inventory_snapshot inv
    JOIN gold.dim_product p ON inv.product_id = p.product_id
    JOIN gold.mart_abc_xyz abc
      ON inv.product_id = abc.product_id AND inv.scenario_id = abc.scenario_id
    WHERE inv.scenario_id = ?
      AND abc.abc_class IN ('A', 'B')
      AND inv.coverage_days <= inv.lead_time_days {inv_fam_clause}
    ORDER BY revenue_at_risk_brl DESC
    """
    df_stockout = repo.query(stockout_sql, params=inv_params)

    # 3. Resumo ABC/XYZ 3x3
    abc_params: list[Any] = [scenario_id]
    abc_fam_clause = ""
    if families:
        fam_list = list(families)
        ph = ", ".join(["?"] * len(fam_list))
        abc_fam_clause = f" AND family IN ({ph})"
        abc_params.extend(fam_list)

    abc_sql = f"""
    SELECT
        abc_xyz_class AS cell,
        abc_class,
        xyz_class,
        COUNT(*)::INTEGER AS sku_count,
        ROUND(SUM(gross_revenue), 2) AS gross_revenue,
        ROUND(SUM(contribution_margin), 2) AS contribution_margin,
        ROUND(COUNT(*) * 100.0 / (
            SELECT COUNT(*) FROM gold.mart_abc_xyz WHERE scenario_id = ? {abc_fam_clause}
        ), 2) AS sku_share_pct,
        ROUND(SUM(contribution_margin) * 100.0 / (
            SELECT SUM(contribution_margin) FROM gold.mart_abc_xyz WHERE scenario_id = ? {abc_fam_clause}
        ), 2) AS margin_share_pct,
        MAX(policy) AS policy
    FROM gold.mart_abc_xyz
    WHERE scenario_id = ? {abc_fam_clause}
    GROUP BY abc_xyz_class, abc_class, xyz_class
    ORDER BY abc_class, xyz_class
    """
    if families:
        f_list = list(families)
        abc_full_params = [scenario_id, *f_list, scenario_id, *f_list, scenario_id, *f_list]
    else:
        abc_full_params = [scenario_id, scenario_id, scenario_id]

    df_abc = repo.query(abc_sql, params=abc_full_params)

    return df_locked, df_stockout, df_abc
