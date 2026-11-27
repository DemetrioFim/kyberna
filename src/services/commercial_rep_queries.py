from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

from src.core.types import ScenarioId
from src.db.repository import DataRepository
from src.ml.rep_performance import DEFAULT_QUADRANTS

__all__ = ["query_rep_performance_data"]


def _query_static_rep_performance(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    regiao: str = "Todas",
    sales_reps: Sequence[str] = (),
    quadrant: str = "Todos",
) -> pd.DataFrame:
    """Caminho rápido sobre `gold.mart_rep_performance` sem filtros de UF, Família ou Período."""
    clauses = ["rp.scenario_id = ?"]
    params: list[Any] = [scenario_id]

    if regiao != "Todas":
        clauses.append("rp.region = ?")
        params.append(regiao)
    if sales_reps:
        rep_list = list(sales_reps)
        placeholders = ", ".join(["?"] * len(rep_list))
        clauses.append(f"(rp.sales_rep_id IN ({placeholders}) OR rp.sales_rep_name IN ({placeholders}))")
        params.extend([*rep_list, *rep_list])
    if quadrant != "Todos":
        clauses.append("rp.quadrant = ?")
        params.append(quadrant)

    sql = f"""
    SELECT
        rp.sales_rep_id, rp.sales_rep_name, rp.region, rp.quadrant,
        rp.portfolio_customers, rp.active_customers, rp.positivation_pct,
        rp.avg_families_per_customer, rp.gross_revenue, rp.avg_discount_pct,
        rp.contribution_margin, rp.margin_pct, rp.revenue_at_risk_brl,
        rp.white_space_potential_brl, rp.action_prescription
    FROM gold.mart_rep_performance rp
    WHERE {" AND ".join(clauses)}
    ORDER BY rp.gross_revenue DESC
    """
    return repo.query(sql, params)


def _build_dynamic_rep_filters(
    scenario_id: ScenarioId,
    *,
    regiao: str,
    uf: str,
    families: Sequence[str],
    sales_reps: Sequence[str],
    start_date_key: int | None,
    end_date_key: int | None,
) -> dict[str, tuple[str, list[Any]]]:
    """Constrói cláusulas SQL e parâmetros para cada CTE da consulta dinâmica de RCAs."""
    rep_clauses: list[str] = ["1=1"]
    rep_params: list[Any] = []
    cust_clauses: list[str] = ["1=1"]
    cust_params: list[Any] = []
    sales_clauses: list[str] = ["f.scenario_id = ?"]
    sales_params: list[Any] = [scenario_id]

    if regiao != "Todas":
        rep_clauses.append("r.region = ?")
        rep_params.append(regiao)
        cust_clauses.append("c.region = ?")
        cust_params.append(regiao)
        sales_clauses.append("c.region = ?")
        sales_params.append(regiao)
    if uf != "Todas":
        cust_clauses.append("c.state = ?")
        cust_params.append(uf)
        sales_clauses.append("c.state = ?")
        sales_params.append(uf)
    if sales_reps:
        rep_list = list(sales_reps)
        ph = ", ".join(["?"] * len(rep_list))
        rep_clauses.append(f"(r.sales_rep_id IN ({ph}) OR r.name IN ({ph}))")
        rep_params.extend([*rep_list, *rep_list])
    if families:
        fam_list = list(families)
        ph = ", ".join(["?"] * len(fam_list))
        sales_clauses.append(f"p.family IN ({ph})")
        sales_params.extend(fam_list)
        ws_fam_sql = f" AND ws.recommended_family IN ({ph})"
        ws_params: list[Any] = [scenario_id, *fam_list]
    else:
        ws_fam_sql = ""
        ws_params = [scenario_id]
    if start_date_key is not None:
        sales_clauses.append("f.date_key >= ?")
        sales_params.append(start_date_key)
    if end_date_key is not None:
        sales_clauses.append("f.date_key <= ?")
        sales_params.append(end_date_key)

    return {
        "rep": (" AND ".join(rep_clauses), rep_params),
        "cust": (" AND ".join(cust_clauses), cust_params),
        "sales": (" AND ".join(sales_clauses), sales_params),
        "ws": (ws_fam_sql, ws_params),
    }


def _classify_rep_quadrants(df: pd.DataFrame, quadrant: str) -> pd.DataFrame:
    """Classifica dinamicamente os 4 quadrantes pela mediana do recorte e aplica filtro."""
    if df.empty:
        return pd.DataFrame(
            columns=[
                "sales_rep_id",
                "sales_rep_name",
                "region",
                "quadrant",
                "portfolio_customers",
                "active_customers",
                "positivation_pct",
                "avg_families_per_customer",
                "gross_revenue",
                "avg_discount_pct",
                "contribution_margin",
                "margin_pct",
                "revenue_at_risk_brl",
                "white_space_potential_brl",
                "action_prescription",
            ]
        )

    med_rev = float(df["gross_revenue"].median())
    med_margin = float(df["margin_pct"].median())
    conditions = [
        (df["gross_revenue"] >= med_rev) & (df["margin_pct"] >= med_margin),
        (df["gross_revenue"] >= med_rev) & (df["margin_pct"] < med_margin),
        (df["gross_revenue"] < med_rev) & (df["margin_pct"] >= med_margin),
        (df["gross_revenue"] < med_rev) & (df["margin_pct"] < med_margin),
    ]
    choices = ["Estrela", "Volume sem margem", "Margem sem volume", "Atenção"]
    df["quadrant"] = np.select(conditions, choices, default="Atenção")

    action_map = {
        "Estrela": DEFAULT_QUADRANTS["star"]["action"],
        "Volume sem margem": DEFAULT_QUADRANTS["volume_no_margin"]["action"],
        "Margem sem volume": DEFAULT_QUADRANTS["margin_no_volume"]["action"],
        "Atenção": DEFAULT_QUADRANTS["attention"]["action"],
    }
    df["action_prescription"] = (
        df["quadrant"].map(action_map).fillna(DEFAULT_QUADRANTS["attention"]["action"])
    )
    if quadrant != "Todos":
        df = df[df["quadrant"] == quadrant].copy()
    return df.reset_index(drop=True)


def query_rep_performance_data(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    families: Sequence[str] = (),
    sales_reps: Sequence[str] = (),
    quadrant: str = "Todos",
    start_date_key: int | None = None,
    end_date_key: int | None = None,
) -> pd.DataFrame:
    """Consulta performance dos RCAs e quadrantes dinâmicos sob todos os 5 filtros globais."""
    if uf == "Todas" and not families and start_date_key is None and end_date_key is None:
        return _query_static_rep_performance(
            repo,
            scenario_id,
            regiao=regiao,
            sales_reps=sales_reps,
            quadrant=quadrant,
        )

    f = _build_dynamic_rep_filters(
        scenario_id,
        regiao=regiao,
        uf=uf,
        families=families,
        sales_reps=sales_reps,
        start_date_key=start_date_key,
        end_date_key=end_date_key,
    )
    rep_sql, rep_params = f["rep"]
    cust_sql, cust_params = f["cust"]
    sales_sql, sales_params = f["sales"]
    ws_fam_sql, ws_params = f["ws"]

    sql = f"""
    WITH scoped_reps AS (
        SELECT r.sales_rep_id, r.name AS sales_rep_name, r.region
        FROM gold.dim_sales_rep r
        WHERE {rep_sql}
    ),
    scoped_customers AS (
        SELECT c.customer_id, c.sales_rep_id
        FROM gold.dim_customer c
        WHERE {cust_sql}
    ),
    portfolio_agg AS (
        SELECT sales_rep_id, COUNT(*)::INTEGER AS portfolio_customers
        FROM scoped_customers
        GROUP BY sales_rep_id
    ),
    cust_fams AS (
        SELECT f.sales_rep_id, f.customer_id, COUNT(DISTINCT p.family) AS fam_cnt
        FROM gold.fact_sales f
        JOIN gold.dim_customer c ON f.customer_id = c.customer_id
        JOIN gold.dim_product p ON f.product_id = p.product_id
        WHERE {sales_sql}
        GROUP BY f.sales_rep_id, f.customer_id
    ),
    sales_agg AS (
        SELECT
            f.sales_rep_id,
            COUNT(DISTINCT f.customer_id)::INTEGER AS active_customers,
            ROUND(COALESCE(SUM(f.gross_revenue), 0.0), 2) AS gross_revenue,
            ROUND(COALESCE(SUM(f.discount_amount) / NULLIF(SUM(f.gross_revenue), 0.0) * 100.0, 0.0), 2)
                AS avg_discount_pct,
            ROUND(COALESCE(SUM(f.contribution_margin), 0.0), 2) AS contribution_margin,
            ROUND(
                COALESCE(SUM(f.contribution_margin) / NULLIF(SUM(f.gross_revenue), 0.0) * 100.0, 0.0),
                2
            ) AS margin_pct
        FROM gold.fact_sales f
        JOIN gold.dim_customer c ON f.customer_id = c.customer_id
        JOIN gold.dim_product p ON f.product_id = p.product_id
        WHERE {sales_sql}
        GROUP BY f.sales_rep_id
    ),
    fam_avg AS (
        SELECT sales_rep_id, ROUND(COALESCE(AVG(fam_cnt), 0.0), 2) AS avg_families_per_customer
        FROM cust_fams
        GROUP BY sales_rep_id
    ),
    risk_agg AS (
        SELECT
            sc.sales_rep_id,
            ROUND(COALESCE(SUM(
                CASE WHEN cr.risk_status IN ('Em Risco Imediato', 'Adormecido / Perdido')
                THEN cr.annual_revenue_at_risk ELSE 0.0 END
            ), 0.0), 2) AS revenue_at_risk_brl
        FROM scoped_customers sc
        JOIN gold.mart_customer_risk cr ON sc.customer_id = cr.customer_id AND cr.scenario_id = ?
        GROUP BY sc.sales_rep_id
    ),
    ws_agg AS (
        SELECT
            sc.sales_rep_id,
            ROUND(COALESCE(SUM(ws.potential_revenue_brl), 0.0), 2) AS white_space_potential_brl
        FROM scoped_customers sc
        JOIN gold.mart_white_space ws ON sc.customer_id = ws.customer_id
        WHERE ws.scenario_id = ? {ws_fam_sql}
        GROUP BY sc.sales_rep_id
    )
    SELECT
        sr.sales_rep_id,
        sr.sales_rep_name,
        sr.region,
        COALESCE(pa.portfolio_customers, 0) AS portfolio_customers,
        COALESCE(sa.active_customers, 0) AS active_customers,
        ROUND(
            COALESCE(sa.active_customers * 100.0 / NULLIF(pa.portfolio_customers, 0), 0.0),
            1
        ) AS positivation_pct,
        COALESCE(fa.avg_families_per_customer, 0.0) AS avg_families_per_customer,
        COALESCE(sa.gross_revenue, 0.0) AS gross_revenue,
        COALESCE(sa.avg_discount_pct, 0.0) AS avg_discount_pct,
        COALESCE(sa.contribution_margin, 0.0) AS contribution_margin,
        COALESCE(sa.margin_pct, 0.0) AS margin_pct,
        COALESCE(ra.revenue_at_risk_brl, 0.0) AS revenue_at_risk_brl,
        COALESCE(wa.white_space_potential_brl, 0.0) AS white_space_potential_brl
    FROM scoped_reps sr
    LEFT JOIN portfolio_agg pa ON sr.sales_rep_id = pa.sales_rep_id
    LEFT JOIN sales_agg sa ON sr.sales_rep_id = sa.sales_rep_id
    LEFT JOIN fam_avg fa ON sr.sales_rep_id = fa.sales_rep_id
    LEFT JOIN risk_agg ra ON sr.sales_rep_id = ra.sales_rep_id
    LEFT JOIN ws_agg wa ON sr.sales_rep_id = wa.sales_rep_id
    WHERE COALESCE(sa.gross_revenue, 0.0) > 0.0 OR COALESCE(pa.portfolio_customers, 0) > 0
    ORDER BY gross_revenue DESC
    """
    params = [*rep_params, *cust_params, *sales_params, *sales_params, scenario_id, *ws_params]
    return _classify_rep_quadrants(repo.query(sql, params), quadrant)
