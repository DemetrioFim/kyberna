from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pandas as pd

from src.core.logging import get_logger
from src.core.types import ScenarioId
from src.db.repository import DataRepository

logger = get_logger(__name__)


def _build_fact_clauses(
    scenario_id: ScenarioId,
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    families: Sequence[str] = (),
    sales_reps: Sequence[str] = (),
    start_date_key: int | None = None,
    end_date_key: int | None = None,
) -> tuple[str, list[Any]]:
    """Constrói cláusula WHERE parametrizada para consultas de precificação sobre `fact_sales`."""
    clauses: list[str] = ["f.scenario_id = ?", "f.units > 0", "p.base_unit_price > 0"]
    params: list[Any] = [scenario_id]

    if start_date_key is not None and end_date_key is not None:
        clauses.append("f.date_key BETWEEN ? AND ?")
        params.extend([start_date_key, end_date_key])
    if regiao != "Todas":
        clauses.append("c.region = ?")
        params.append(regiao)
    if uf != "Todas":
        clauses.append("c.state = ?")
        params.append(uf)
    if families:
        fam_list = list(families)
        placeholders = ", ".join(["?"] * len(fam_list))
        clauses.append(f"p.family IN ({placeholders})")
        params.extend(fam_list)
    if sales_reps:
        rep_list = list(sales_reps)
        placeholders = ", ".join(["?"] * len(rep_list))
        clauses.append(f"(f.sales_rep_id IN ({placeholders}) OR r.name IN ({placeholders}))")
        params.extend(rep_list)
        params.extend(rep_list)

    return " AND ".join(clauses), params


def query_filtered_pricing_kpis(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    families: Sequence[str] = (),
    sales_reps: Sequence[str] = (),
    start_date_key: int | None = None,
    end_date_key: int | None = None,
) -> dict[str, float | int]:
    """Calcula os 5 KPIs de realização e vazamento de preço respeitando os filtros globais."""
    where_sql, params = _build_fact_clauses(
        scenario_id,
        regiao=regiao,
        uf=uf,
        families=families,
        sales_reps=sales_reps,
        start_date_key=start_date_key,
        end_date_key=end_date_key,
    )
    sql = f"""
    WITH line_eval AS (
        SELECT
            f.order_id,
            f.product_id,
            f.units,
            (f.unit_net_price / p.base_unit_price) * 100.0 AS idx,
            COALESCE(pr.contextual_band_low_idx, 88.0) AS band_low_idx,
            p.base_unit_price,
            f.unit_net_price
        FROM gold.fact_sales f
        JOIN gold.dim_product p ON f.product_id = p.product_id
        JOIN gold.dim_customer c ON f.customer_id = c.customer_id
        JOIN gold.dim_sales_rep r ON f.sales_rep_id = r.sales_rep_id
        LEFT JOIN gold.mart_price_realization pr
          ON f.scenario_id = pr.scenario_id AND f.product_id = pr.product_id
        WHERE {where_sql}
    )
    SELECT
        COALESCE(AVG(idx), 0.0) AS realization_index_pct,
        COALESCE(STDDEV(idx) / NULLIF(AVG(idx), 0.0) * 100.0, 0.0) AS price_cv_pct,
        COALESCE(AVG(CASE WHEN idx < band_low_idx THEN 100.0 ELSE 0.0 END), 0.0) AS below_band_sales_pct,
        COALESCE(
            SUM(GREATEST(0.0, (band_low_idx / 100.0) * base_unit_price - unit_net_price) * units),
            0.0
        ) AS subpricing_leakage_brl,
        COUNT(DISTINCT order_id)::INTEGER AS orders_count,
        COUNT(DISTINCT product_id)::INTEGER AS skus_count
    FROM line_eval
    """
    try:
        df = repo.query(sql, params=params)
    except Exception as exc:
        logger.warning("Falha ao consultar KPIs de precificação para %s: %s", scenario_id, exc)
        return {
            "realization_index_pct": 0.0,
            "price_cv_pct": 0.0,
            "below_band_sales_pct": 0.0,
            "subpricing_leakage_brl": 0.0,
            "inelastic_reprice_upside_brl": 0.0,
            "orders_count": 0,
            "skus_count": 0,
        }

    r0 = df.iloc[0] if not df.empty else None
    fam_clause = ""
    fam_params: list[Any] = [scenario_id]
    if families:
        fam_list = list(families)
        placeholders = ", ".join(["?"] * len(fam_list))
        fam_clause = f" AND family IN ({placeholders})"
        fam_params.extend(fam_list)

    upside_sql = (
        "SELECT COALESCE(SUM(inelastic_upside_brl), 0.0) AS upside "
        f"FROM gold.mart_price_realization WHERE scenario_id = ?{fam_clause}"
    )
    try:
        up_df = repo.query(upside_sql, params=fam_params)
        upside = float(up_df["upside"].iloc[0]) if not up_df.empty else 0.0
    except Exception:
        upside = 0.0

    if r0 is None:
        return {
            "realization_index_pct": 0.0,
            "price_cv_pct": 0.0,
            "below_band_sales_pct": 0.0,
            "subpricing_leakage_brl": 0.0,
            "inelastic_reprice_upside_brl": round(upside, 2),
            "orders_count": 0,
            "skus_count": 0,
        }
    return {
        "realization_index_pct": round(float(r0["realization_index_pct"]), 2),
        "price_cv_pct": round(float(r0["price_cv_pct"]), 2),
        "below_band_sales_pct": round(float(r0["below_band_sales_pct"]), 1),
        "subpricing_leakage_brl": round(float(r0["subpricing_leakage_brl"]), 2),
        "inelastic_reprice_upside_brl": round(upside, 2),
        "orders_count": int(r0["orders_count"]),
        "skus_count": int(r0["skus_count"]),
    }


def query_pricing_boxplot_data(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    families: Sequence[str] = (),
) -> pd.DataFrame:
    """Retorna quantis realizados e banda contextual agrupados por Família (ou Top 10 SKUs)."""
    fam_clause = ""
    params: list[Any] = [scenario_id]
    if families:
        fam_list = list(families)
        placeholders = ", ".join(["?"] * len(fam_list))
        fam_clause = f" AND family IN ({placeholders})"
        params.extend(fam_list)

    if len(families) == 1:
        sql = f"""
        SELECT
            product_name AS group_label,
            family,
            realized_idx_p05 AS p05,
            realized_idx_p25 AS p25,
            realized_idx_p50 AS p50,
            realized_idx_p75 AS p75,
            realized_idx_p95 AS p95,
            realized_idx_mean AS realized_mean,
            contextual_band_low_idx AS band_low,
            contextual_band_expected_idx AS band_expected,
            contextual_band_high_idx AS band_high,
            min_healthy_idx,
            price_leakage_brl
        FROM gold.mart_price_realization
        WHERE scenario_id = ?{fam_clause}
        ORDER BY price_leakage_brl DESC, units_sold DESC
        LIMIT 10
        """
    else:
        sql = f"""
        SELECT
            family AS group_label,
            family,
            ROUND(AVG(realized_idx_p05), 2) AS p05,
            ROUND(AVG(realized_idx_p25), 2) AS p25,
            ROUND(AVG(realized_idx_p50), 2) AS p50,
            ROUND(AVG(realized_idx_p75), 2) AS p75,
            ROUND(AVG(realized_idx_p95), 2) AS p95,
            ROUND(AVG(realized_idx_mean), 2) AS realized_mean,
            ROUND(AVG(contextual_band_low_idx), 2) AS band_low,
            ROUND(AVG(contextual_band_expected_idx), 2) AS band_expected,
            ROUND(AVG(contextual_band_high_idx), 2) AS band_high,
            ROUND(AVG(min_healthy_idx), 2) AS min_healthy_idx,
            ROUND(SUM(price_leakage_brl), 2) AS price_leakage_brl
        FROM gold.mart_price_realization
        WHERE scenario_id = ?{fam_clause}
        GROUP BY family
        ORDER BY price_leakage_brl DESC
        """
    try:
        return repo.query(sql, params=params)
    except Exception as exc:
        logger.warning("mart_price_realization indisponível para %s: %s", scenario_id, exc)
        return pd.DataFrame()


def query_pricing_deviations(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    families: Sequence[str] = (),
    sales_reps: Sequence[str] = (),
) -> pd.DataFrame:
    """Lista os SKUs com maior vazamento financeiro abaixo da banda contextual."""
    clauses: list[str] = ["scenario_id = ?", "price_leakage_brl > 0"]
    params: list[Any] = [scenario_id]
    if families:
        fam_list = list(families)
        placeholders = ", ".join(["?"] * len(fam_list))
        clauses.append(f"family IN ({placeholders})")
        params.extend(fam_list)
    if sales_reps:
        rep_list = list(sales_reps)
        placeholders = ", ".join(["?"] * len(rep_list))
        clauses.append(f"primary_offender_rep IN ({placeholders})")
        params.extend(rep_list)

    sql = f"""
    SELECT
        product_id,
        product_name,
        family,
        abc_class,
        realized_idx_mean,
        contextual_band_low_idx,
        contextual_band_high_idx,
        min_healthy_idx,
        below_band_orders_pct,
        price_leakage_brl,
        inelastic_upside_brl,
        primary_offender_rep
    FROM gold.mart_price_realization
    WHERE {" AND ".join(clauses)}
    ORDER BY price_leakage_brl DESC, below_band_orders_pct DESC
    LIMIT 50
    """
    try:
        return repo.query(sql, params=params)
    except Exception as exc:
        logger.warning("Falha ao consultar desvios de preço para %s: %s", scenario_id, exc)
        return pd.DataFrame()


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
) -> pd.DataFrame:
    """Retorna os 5 drivers Linear SHAP de um escopo específico."""
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
        return repo.query(sql, params=[scenario_id, scope_type, scope_id])
    except Exception as exc:
        logger.warning("Falha ao consultar drivers SHAP (%s/%s): %s", scope_type, scope_id, exc)
        return pd.DataFrame()


def query_family_pricing_bands(
    repo: DataRepository,
    scenario_id: ScenarioId,
) -> pd.DataFrame:
    """Retorna faixas competitivas relativas (delta vs. preço atual) por família para o Simulador."""
    sql = """
    SELECT
        family,
        ROUND((AVG(contextual_band_low_idx) - AVG(realized_idx_mean)) / 100.0, 4) AS band_low_delta_pct,
        ROUND((AVG(contextual_band_high_idx) - AVG(realized_idx_mean)) / 100.0, 4) AS band_high_delta_pct,
        ROUND((AVG(min_healthy_idx) - AVG(realized_idx_mean)) / 100.0, 4) AS min_healthy_delta_pct
    FROM gold.mart_price_realization
    WHERE scenario_id = ?
    GROUP BY family
    ORDER BY family ASC
    """
    try:
        return repo.query(sql, params=[scenario_id])
    except Exception:
        return pd.DataFrame()
