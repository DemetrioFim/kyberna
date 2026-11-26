from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pandas as pd

from src.core.logging import get_logger
from src.core.types import ScenarioId
from src.db.repository import DataRepository
from src.services.pricing_queries import build_pricing_fact_clauses

logger = get_logger(__name__)


def query_pricing_shap_options(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    families: Sequence[str] = (),
) -> pd.DataFrame:
    """Lista escopos (Famílias e Top SKUs) disponíveis em `gold.mart_pricing_drivers`."""
    fam_clause = ""
    params: list[Any] = [scenario_id]
    if families:
        fam_list = list(families)
        placeholders = ", ".join(["?"] * len(fam_list))
        fam_clause = f" AND family IN ({placeholders})"
        params.extend(fam_list)

    sql = f"""
    SELECT DISTINCT
        scope_type,
        scope_id,
        scope_label,
        family,
        unjustified_gap_pp
    FROM gold.mart_pricing_drivers
    WHERE scenario_id = ?{fam_clause}
    ORDER BY
        CASE scope_type WHEN 'family' THEN 1 ELSE 2 END,
        unjustified_gap_pp ASC,
        scope_label ASC
    """
    try:
        return repo.query(sql, params=params)
    except Exception as exc:
        logger.warning("mart_pricing_drivers indisponível para %s: %s", scenario_id, exc)
        return pd.DataFrame()


def query_pricing_shap_drivers(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    scope_type: str,
    scope_id: str,
    regiao: str = "Todas",
    uf: str = "Todas",
    families: Sequence[str] = (),
    sales_reps: Sequence[str] = (),
    start_date_key: int | None = None,
    end_date_key: int | None = None,
) -> tuple[pd.DataFrame, dict[str, float | int]]:
    """Retorna os 5 drivers SHAP e os totais financeiros reais (R$) do escopo filtrado."""
    sql = """
    SELECT
        scope_type,
        scope_id,
        scope_label,
        family,
        base_idx,
        expected_idx,
        realized_idx,
        unjustified_gap_pp,
        driver_order,
        driver_name,
        shap_impact_pp
    FROM gold.mart_pricing_drivers
    WHERE scenario_id = ? AND scope_type = ? AND scope_id = ?
    ORDER BY driver_order ASC
    """
    try:
        drivers_df = repo.query(sql, params=[scenario_id, scope_type, scope_id])
    except Exception as exc:
        logger.warning("Falha ao consultar drivers SHAP (%s/%s): %s", scope_type, scope_id, exc)
        return pd.DataFrame(), {}

    if drivers_df.empty:
        return drivers_df, {}

    where_sql, params = build_pricing_fact_clauses(
        scenario_id,
        regiao=regiao,
        uf=uf,
        families=families,
        sales_reps=sales_reps,
        start_date_key=start_date_key,
        end_date_key=end_date_key,
    )
    scope_col = "p.family" if scope_type == "family" else "f.product_id"
    fin_sql = f"""
    SELECT
        COALESCE(SUM(f.units * p.base_unit_price), 0.0) AS table_gross_brl,
        COALESCE(SUM(f.units * f.unit_net_price), 0.0) AS realized_net_brl,
        COALESCE(SUM(f.units), 0)::INTEGER AS units_sold,
        COALESCE(AVG(p.base_unit_price), 0.0) AS avg_base_unit_brl
    FROM gold.fact_sales f
    JOIN gold.dim_product p ON f.product_id = p.product_id
    JOIN gold.dim_customer c ON f.customer_id = c.customer_id
    JOIN gold.dim_sales_rep r ON f.sales_rep_id = r.sales_rep_id
    WHERE {where_sql} AND {scope_col} = ?
    """
    fin_stats: dict[str, float | int] = {
        "table_gross_brl": 0.0,
        "realized_net_brl": 0.0,
        "units_sold": 0,
        "avg_base_unit_brl": 0.0,
    }
    try:
        fin_df = repo.query(fin_sql, params=[*params, scope_id])
        if not fin_df.empty:
            r0 = fin_df.iloc[0]
            fin_stats = {
                "table_gross_brl": round(float(r0["table_gross_brl"]), 2),
                "realized_net_brl": round(float(r0["realized_net_brl"]), 2),
                "units_sold": int(r0["units_sold"]),
                "avg_base_unit_brl": round(float(r0["avg_base_unit_brl"]), 2),
            }
    except Exception as exc:
        logger.debug("Falha ao consultar totais R$ do SHAP (%s/%s): %s", scope_type, scope_id, exc)

    return drivers_df, fin_stats
