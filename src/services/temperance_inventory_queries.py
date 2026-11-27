from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pandas as pd

from src.core.logging import get_logger
from src.core.types import ScenarioId
from src.db.repository import DataRepository
from src.services.executive_abc_queries import (
    build_filtered_abc_xyz_matrix,
    query_filtered_abc_xyz_skus,
)

logger = get_logger(__name__)

__all__ = [
    "query_temperance_inventory_details",
    "query_temperance_inventory_kpis",
]


def _family_filter(
    families: Sequence[str],
    *,
    alias: str,
) -> tuple[str, list[Any]]:
    """Constrói cláusula SQL segura para filtro opcional por família."""
    if not families:
        return "", []
    fam_list = list(families)
    ph = ", ".join(["?"] * len(fam_list))
    prefix = f"{alias}." if alias else ""
    return f" AND {prefix}family IN ({ph})", fam_list


def _has_inventory_position(repo: DataRepository, scenario_id: ScenarioId) -> bool:
    """Verifica se a tabela SSOT `gold.mart_inventory_position` possui dados para o cenário."""
    try:
        df = repo.query(
            "SELECT 1 FROM gold.mart_inventory_position WHERE scenario_id = ? LIMIT 1",
            params=[scenario_id],
        )
        return not df.empty
    except Exception:
        return False


def query_temperance_inventory_kpis(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    families: Sequence[str] = (),
) -> dict[str, float | int]:
    """Consulta métricas agregadas de estoque com SSOT em `gold.mart_inventory_position`."""
    use_ssot = _has_inventory_position(repo, scenario_id)
    alias = "pos" if use_ssot else "inv"
    inv_fam_clause, fam_params = _family_filter(families, alias=alias)
    inv_params: list[Any] = [scenario_id, *fam_params]

    if use_ssot:
        inv_sql = f"""
        SELECT
            COALESCE(SUM(pos.stock_value_brl), 0.0) AS total_stock_value_brl,
            COALESCE(SUM(CASE WHEN pos.locked_capital_brl > 0.0
                THEN pos.locked_capital_brl ELSE 0.0 END), 0.0) AS locked_capital_brl,
            COUNT(CASE WHEN pos.stock_status = 'Capital Travado' THEN 1 END)::INTEGER
                AS locked_skus_count,
            COUNT(CASE WHEN pos.abc_class = 'A' AND pos.stock_status = 'Ruptura Iminente'
                THEN 1 END)::INTEGER AS stockout_risk_skus_count,
            COALESCE(SUM(CASE WHEN pos.abc_class = 'A' AND pos.stock_status = 'Ruptura Iminente'
                THEN pos.protected_revenue_brl ELSE 0.0 END), 0.0) AS stockout_risk_revenue_brl
        FROM gold.mart_inventory_position pos
        WHERE pos.scenario_id = ? {inv_fam_clause}
        """
    else:
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
    regiao: str = "Todas",
    uf: str = "Todas",
    sales_reps: Sequence[str] = (),
    start_date_key: int | None = None,
    end_date_key: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Retorna tabelas detalhadas de capital imobilizado, risco de ruptura e matriz ABC/XYZ."""
    use_ssot = _has_inventory_position(repo, scenario_id)
    alias = "pos" if use_ssot else "inv"
    inv_fam_clause, fam_params = _family_filter(families, alias=alias)
    inv_params: list[Any] = [scenario_id, *fam_params]

    if use_ssot:
        locked_sql = f"""
        SELECT
            pos.product_id,
            pos.product_name,
            pos.family,
            pos.pack,
            pos.stock_units,
            pos.stock_boxes,
            pos.stock_value_brl,
            pos.locked_capital_brl,
            pos.coverage_days,
            pos.abc_xyz_class AS cell,
            pos.action_prescription
        FROM gold.mart_inventory_position pos
        WHERE pos.scenario_id = ? AND pos.stock_status = 'Capital Travado' {inv_fam_clause}
        ORDER BY pos.locked_capital_brl DESC, pos.product_name ASC
        """
        stockout_sql = f"""
        SELECT
            pos.product_id,
            pos.product_name,
            pos.family,
            pos.pack,
            pos.stock_units,
            pos.stock_boxes,
            pos.coverage_days,
            pos.lead_time_days,
            ROUND(pos.forecast_daily_demand, 2) AS avg_daily_demand_90d,
            pos.suggested_order_boxes,
            pos.protected_revenue_brl AS revenue_at_risk_brl,
            pos.abc_xyz_class AS cell
        FROM gold.mart_inventory_position pos
        WHERE pos.scenario_id = ?
          AND pos.abc_class IN ('A', 'B')
          AND pos.stock_status = 'Ruptura Iminente'
          AND pos.suggested_order_boxes >= 1 {inv_fam_clause}
        ORDER BY pos.protected_revenue_brl DESC, pos.suggested_order_boxes DESC
        """
    else:
        locked_sql = f"""
        SELECT
            inv.product_id,
            p.product_name,
            inv.family,
            inv.pack,
            inv.stock_units,
            inv.stock_boxes,
            inv.stock_value_brl,
            inv.stock_value_brl AS locked_capital_brl,
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

    df_locked = repo.query(locked_sql, params=inv_params)
    df_stockout = repo.query(stockout_sql, params=inv_params)

    # 3. Resumo ABC/XYZ 3x3 reativo aos 5 filtros globais
    skus_df = query_filtered_abc_xyz_skus(
        repo,
        scenario_id,
        regiao=regiao,
        uf=uf,
        families=families,
        sales_reps=sales_reps,
        start_date_key=start_date_key,
        end_date_key=end_date_key,
    )
    df_abc = build_filtered_abc_xyz_matrix(skus_df)

    return df_locked, df_stockout, df_abc
