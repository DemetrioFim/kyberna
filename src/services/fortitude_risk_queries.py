from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

from src.core.types import ScenarioId
from src.db.repository import DataRepository
from src.services.temperance_queries import build_temperance_filter_clauses

__all__ = [
    "AGING_BUCKET_ORDER",
    "build_fortitude_date_scope",
    "query_aging_buckets_and_customers",
    "query_concentration_data",
    "trailing_12m_cte",
]

AGING_BUCKET_ORDER: tuple[tuple[int, str], ...] = (
    (1, "Em Dia (<=1,1x)"),
    (2, "Atenção (1,1x-1,5x)"),
    (3, "Risco 31-60d (1,5x-2,5x)"),
    (4, "Crítico >60d (>2,5x)"),
)


def trailing_12m_cte() -> str:
    """Retorna CTE padrão para o recorte móvel dos últimos 12 meses de vendas."""
    return """
    WITH max_dt AS (
        SELECT MAX(d2.full_date) AS max_full_date
        FROM gold.fact_sales f2
        JOIN gold.dim_date d2 ON f2.date_key = d2.date_key
        WHERE f2.scenario_id = ?
    )
    """


def build_fortitude_date_scope(
    scenario_id: ScenarioId,
    start_date_key: int | None = None,
    end_date_key: int | None = None,
    *,
    date_alias: str = "d",
) -> tuple[str, str, str, list[Any]]:
    """Retorna (cte_sql, join_sql, extra_where_sql, params) para o escopo temporal de Fortitude."""
    if start_date_key is None and end_date_key is None:
        return (
            trailing_12m_cte(),
            "CROSS JOIN max_dt m",
            f"AND {date_alias}.full_date > (m.max_full_date - INTERVAL 12 MONTH)",
            [scenario_id],
        )
    return "", "", "", []


def query_concentration_data(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    sales_reps: Sequence[str] = (),
    families: Sequence[str] = (),
    start_date_key: int | None = None,
    end_date_key: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
    """Retorna concentração Pareto por cliente, por família e indicadores Top 5/10/2."""
    where_sql, filter_params = build_temperance_filter_clauses(
        scenario_id,
        regiao=regiao,
        uf=uf,
        sales_reps=sales_reps,
        families=families,
        start_date_key=start_date_key,
        end_date_key=end_date_key,
    )
    cte_sql, cross_join_sql, date_where_sql, date_params = build_fortitude_date_scope(
        scenario_id,
        start_date_key=start_date_key,
        end_date_key=end_date_key,
    )

    cust_sql = f"""
    {cte_sql}
    SELECT
        c.customer_id,
        COALESCE(c.trade_name, c.company_name) AS customer_name,
        c.size AS segment_size,
        c.region,
        c.state,
        COALESCE(cr.risk_status, 'Sem Histórico') AS risk_status,
        ROUND(COALESCE(SUM(f.net_revenue), 0.0), 2) AS revenue_12m_brl,
        ROUND(COALESCE(SUM(f.contribution_margin), 0.0), 2) AS margin_12m_brl
    FROM gold.fact_sales f
    JOIN gold.dim_date d ON f.date_key = d.date_key
    JOIN gold.dim_customer c ON f.customer_id = c.customer_id
    JOIN gold.dim_product p ON f.product_id = p.product_id
    JOIN gold.dim_sales_rep r ON f.sales_rep_id = r.sales_rep_id
    LEFT JOIN gold.mart_customer_risk cr
        ON f.customer_id = cr.customer_id AND f.scenario_id = cr.scenario_id
    {cross_join_sql}
    WHERE {where_sql}
      {date_where_sql}
    GROUP BY 1, 2, 3, 4, 5, 6
    ORDER BY revenue_12m_brl DESC
    """
    cust_df = repo.query(cust_sql, params=[*date_params, *filter_params])

    if cust_df.empty:
        empty_cust = pd.DataFrame(
            columns=[
                "customer_id",
                "customer_name",
                "segment_size",
                "region",
                "state",
                "risk_status",
                "revenue_12m_brl",
                "margin_12m_brl",
                "share_pct",
                "cum_share_pct",
            ]
        )
        top5_share = 0.0
        top10_share = 0.0
    else:
        total_cust_rev = float(cust_df["revenue_12m_brl"].sum())
        denom = max(total_cust_rev, 1e-6)
        cust_df["share_pct"] = np.round((cust_df["revenue_12m_brl"] / denom) * 100.0, 2)
        cust_df["cum_share_pct"] = np.round(cust_df["share_pct"].cumsum(), 1)
        top5_share = float(cust_df.head(5)["share_pct"].sum())
        top10_share = float(cust_df.head(10)["share_pct"].sum())
        empty_cust = cust_df.head(20).reset_index(drop=True)

    fam_sql = f"""
    {cte_sql}
    SELECT
        p.family AS family,
        ROUND(COALESCE(SUM(f.net_revenue), 0.0), 2) AS revenue_12m_brl,
        ROUND(COALESCE(SUM(f.contribution_margin), 0.0), 2) AS margin_12m_brl
    FROM gold.fact_sales f
    JOIN gold.dim_date d ON f.date_key = d.date_key
    JOIN gold.dim_customer c ON f.customer_id = c.customer_id
    JOIN gold.dim_product p ON f.product_id = p.product_id
    JOIN gold.dim_sales_rep r ON f.sales_rep_id = r.sales_rep_id
    {cross_join_sql}
    WHERE {where_sql}
      {date_where_sql}
    GROUP BY 1
    ORDER BY revenue_12m_brl DESC
    """
    fam_df = repo.query(fam_sql, params=[*date_params, *filter_params])

    if fam_df.empty:
        empty_fam = pd.DataFrame(
            columns=["family", "revenue_12m_brl", "margin_12m_brl", "share_pct", "cum_share_pct"]
        )
        top2_share = 0.0
    else:
        total_fam_rev = float(fam_df["revenue_12m_brl"].sum())
        denom = max(total_fam_rev, 1e-6)
        fam_df["share_pct"] = np.round((fam_df["revenue_12m_brl"] / denom) * 100.0, 2)
        fam_df["cum_share_pct"] = np.round(fam_df["share_pct"].cumsum(), 1)
        top2_share = float(fam_df.head(2)["share_pct"].sum())
        empty_fam = fam_df.reset_index(drop=True)

    metrics = {
        "top5_customers_share_pct": round(min(top5_share, 100.0), 1),
        "top10_customers_share_pct": round(min(top10_share, 100.0), 1),
        "top2_families_share_pct": round(min(top2_share, 100.0), 1),
    }
    return empty_cust, empty_fam, metrics


def _build_aging_date_scope(
    scenario_id: ScenarioId,
    start_date_key: int | None,
    end_date_key: int | None,
) -> tuple[str, str, str, list[Any], list[Any], bool]:
    """Constrói CTE e filtros temporais para a consulta de aging."""
    is_date_scoped = start_date_key is not None or end_date_key is not None
    if not is_date_scoped:
        max_dt_cte = """
    max_dt AS (
        SELECT MAX(d2.full_date) AS max_full_date
        FROM gold.fact_sales f2
        JOIN gold.dim_date d2 ON f2.date_key = d2.date_key
        WHERE f2.scenario_id = ?
    ),"""
        return (
            max_dt_cte,
            "CROSS JOIN max_dt m",
            "AND d2.full_date > (m.max_full_date - INTERVAL 12 MONTH)",
            [scenario_id],
            [],
            False,
        )

    date_clauses: list[str] = []
    date_params: list[Any] = []
    if start_date_key is not None:
        date_clauses.append("AND f2.date_key >= ?")
        date_params.append(start_date_key)
    if end_date_key is not None:
        date_clauses.append("AND f2.date_key <= ?")
        date_params.append(end_date_key)
    return "", "", " ".join(date_clauses), [], date_params, True


def query_aging_buckets_and_customers(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    sales_reps: Sequence[str] = (),
    families: Sequence[str] = (),
    start_date_key: int | None = None,
    end_date_key: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Consulta a carteira de clientes agrupada por faixas de atraso/aging e o detalhe acionável."""
    clauses: list[str] = ["cr.scenario_id = ?"]
    cust_params: list[Any] = []
    if regiao != "Todas":
        clauses.append("c.region = ?")
        cust_params.append(regiao)
    if uf != "Todas":
        clauses.append("c.state = ?")
        cust_params.append(uf)
    if sales_reps:
        rep_list = list(sales_reps)
        ph = ", ".join(["?"] * len(rep_list))
        clauses.append(f"(c.sales_rep_id IN ({ph}) OR r.name IN ({ph}))")
        cust_params.extend([*rep_list, *rep_list])

    fam_filter_sql = ""
    fam_params: list[Any] = []
    if families:
        fam_list = list(families)
        fam_filter_sql = f" AND p2.family IN ({', '.join(['?'] * len(fam_list))})"
        fam_params.extend(fam_list)

    max_dt_cte, max_dt_join, date_filter_sql, max_dt_params, date_params, is_date_scoped = (
        _build_aging_date_scope(scenario_id, start_date_key, end_date_key)
    )
    where_sql = " AND ".join(clauses)
    fam_exists_clause = "AND cust_12m.revenue_12m_brl > 0.0" if (families or is_date_scoped) else ""

    sql = f"""
    WITH {max_dt_cte}
    cust_12m AS (
        SELECT
            f2.customer_id,
            SUM(f2.net_revenue) AS revenue_12m_brl
        FROM gold.fact_sales f2
        JOIN gold.dim_date d2 ON f2.date_key = d2.date_key
        JOIN gold.dim_product p2 ON f2.product_id = p2.product_id
        {max_dt_join}
        WHERE f2.scenario_id = ?
          {date_filter_sql}
          {fam_filter_sql}
        GROUP BY f2.customer_id
    )
    SELECT
        c.customer_id,
        COALESCE(c.trade_name, c.company_name) AS customer_name,
        COALESCE(r.name, 'Sem RCA') AS sales_rep_name,
        c.region,
        c.state,
        cr.risk_status,
        ROUND(cr.delay_ratio, 2) AS delay_ratio,
        cr.recency_days,
        ROUND(cr.expected_cycle_days, 1) AS expected_cycle_days,
        ROUND(COALESCE(cust_12m.revenue_12m_brl, cr.annual_revenue_at_risk, 0.0), 2) AS revenue_12m_brl,
        ROUND(COALESCE(cr.annual_margin_at_risk, 0.0), 2) AS annual_margin_at_risk_brl,
        CASE
            WHEN cr.delay_ratio <= 1.1 THEN 1
            WHEN cr.delay_ratio <= 1.5 THEN 2
            WHEN cr.delay_ratio <= 2.5 THEN 3
            ELSE 4
        END AS bucket_order
    FROM gold.mart_customer_risk cr
    JOIN gold.dim_customer c ON cr.customer_id = c.customer_id
    LEFT JOIN gold.dim_sales_rep r ON c.sales_rep_id = r.sales_rep_id
    LEFT JOIN cust_12m ON c.customer_id = cust_12m.customer_id
    WHERE {where_sql}
      {fam_exists_clause}
    ORDER BY cr.delay_ratio DESC, revenue_12m_brl DESC
    """
    params: list[Any] = [*max_dt_params, scenario_id, *date_params, *fam_params, scenario_id, *cust_params]
    raw_df = repo.query(sql, params=params)

    bucket_label_map = dict(AGING_BUCKET_ORDER)
    if raw_df.empty:
        buckets_df = pd.DataFrame(
            [
                {
                    "bucket_order": order,
                    "bucket": label,
                    "customers_count": 0,
                    "revenue_12m_brl": 0.0,
                    "revenue_share_pct": 0.0,
                    "annual_margin_at_risk_brl": 0.0,
                }
                for order, label in AGING_BUCKET_ORDER
            ]
        )
        return buckets_df, raw_df

    raw_df["aging_bucket"] = raw_df["bucket_order"].map(bucket_label_map)
    grouped = raw_df.groupby("bucket_order", as_index=False).agg(
        customers_count=("customer_id", "count"),
        revenue_12m_brl=("revenue_12m_brl", "sum"),
        annual_margin_at_risk_brl=("annual_margin_at_risk_brl", "sum"),
    )

    scaffold = pd.DataFrame(AGING_BUCKET_ORDER, columns=["bucket_order", "bucket"])
    buckets_df = scaffold.merge(grouped, on="bucket_order", how="left").fillna(
        {"customers_count": 0, "revenue_12m_brl": 0.0, "annual_margin_at_risk_brl": 0.0}
    )
    buckets_df["customers_count"] = buckets_df["customers_count"].astype(int)
    total_rev = float(buckets_df["revenue_12m_brl"].sum())
    if total_rev > 0.0:
        buckets_df["revenue_share_pct"] = np.round((buckets_df["revenue_12m_brl"] / total_rev) * 100.0, 1)
    else:
        buckets_df["revenue_share_pct"] = 0.0

    # Prioriza clientes com atraso (delay > 1.1) ordenados por valor exposto; fallback para maior valor
    delayed_df = raw_df[raw_df["delay_ratio"] > 1.1]
    action_df = delayed_df if not delayed_df.empty else raw_df
    action_df = (
        action_df.sort_values(
            by=["bucket_order", "revenue_12m_brl", "delay_ratio"],
            ascending=[False, False, False],
        )
        .head(40)
        .reset_index(drop=True)
    )
    return buckets_df, action_df
