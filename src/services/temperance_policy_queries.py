from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pandas as pd

from src.core.types import ScenarioId
from src.db.repository import DataRepository
from src.etl.finance.margin_waterfall import load_discounts_config
from src.etl.gold.inventory_snapshot import load_working_capital_config


def load_temperance_policy_params(scenario_id: ScenarioId) -> dict[str, Any]:
    """Carrega limites de desconto, PMR por porte e taxa financeira das configs YAML."""
    disc_cfg = load_discounts_config()
    wc_cfg = load_working_capital_config(scenario_id)

    size_base = disc_cfg.size_baseline
    pmr_map = wc_cfg.get("pmr_days_by_size", {"P": 28, "M": 42, "G": 56})
    high_reps = list(disc_cfg.rep_bias.high_discount_reps)

    return {
        "cap_p": float(size_base.get("P", 0.030)),
        "cap_m": float(size_base.get("M", 0.065)),
        "cap_g": float(size_base.get("G", 0.105)),
        "cap_def": float(size_base.get("M", 0.065)),
        "pmr_p": float(pmr_map.get("P", 28)),
        "pmr_m": float(pmr_map.get("M", 42)),
        "pmr_g": float(pmr_map.get("G", 56)),
        "std_term": float(wc_cfg.get("standard_term_days", 30)),
        "extra_pmr": float(wc_cfg.get("high_discount_rep_extra_pmr_days", 18)),
        "rate_monthly": float(wc_cfg.get("monthly_capital_cost_rate", 0.0135)),
        "high_reps": high_reps,
    }


def build_rep_bias_cte_sql(
    scenario_id: ScenarioId,
    policy: dict[str, Any],
) -> tuple[str, list[Any]]:
    """Monta a expressão de penalidade de PMR por RCA e seus parâmetros."""
    high_reps: list[str] = policy["high_reps"]
    if high_reps:
        rep_placeholders = ", ".join(["?"] * len(high_reps))
        rep_bias_expr = f"CASE WHEN f_rep.sales_rep_id IN ({rep_placeholders}) THEN ? ELSE 0 END"
        rep_bias_params: list[Any] = [*high_reps, policy["extra_pmr"], scenario_id]
    else:
        rep_bias_expr = "0"
        rep_bias_params = [scenario_id]
    return rep_bias_expr, rep_bias_params


def build_temperance_filter_clauses(
    scenario_id: ScenarioId,
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    sales_reps: Sequence[str] = (),
    families: Sequence[str] = (),
    start_date_key: int | None = None,
    end_date_key: int | None = None,
) -> tuple[str, list[Any]]:
    """Constrói a cláusula WHERE e lista de parâmetros para tabelas de vendas faturadas."""
    clauses: list[str] = ["f.scenario_id = ?"]
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
    if sales_reps:
        rep_list = list(sales_reps)
        placeholders = ", ".join(["?"] * len(rep_list))
        clauses.append(f"(f.sales_rep_id IN ({placeholders}) OR r.name IN ({placeholders}))")
        params.extend(rep_list)
        params.extend(rep_list)
    if families:
        fam_list = list(families)
        placeholders = ", ".join(["?"] * len(fam_list))
        clauses.append(f"p.family IN ({placeholders})")
        params.extend(fam_list)

    return " AND ".join(clauses), params


def query_discount_policy_violations(
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
    """Retorna tabelas de auditoria de descontos acima do teto por RCA e por Família."""
    policy = load_temperance_policy_params(scenario_id)
    where_sql, params = build_temperance_filter_clauses(
        scenario_id,
        regiao=regiao,
        uf=uf,
        sales_reps=sales_reps,
        families=families,
        start_date_key=start_date_key,
        end_date_key=end_date_key,
    )

    cap_params = [policy["cap_p"], policy["cap_m"], policy["cap_g"], policy["cap_def"], *params]
    rep_sql = f"""
    SELECT
        f.sales_rep_id,
        r.name AS rep_name,
        r.region,
        COUNT(DISTINCT f.order_id)::INTEGER AS total_orders,
        ROUND(SUM(f.gross_revenue), 2) AS gross_revenue,
        ROUND(SUM(f.discount_amount), 2) AS discount_amount,
        ROUND(SUM(f.discount_amount) / NULLIF(SUM(f.gross_revenue), 0) * 100.0, 2) AS avg_discount_pct,
        ROUND(SUM(GREATEST(0.0, f.discount_amount - f.gross_revenue * CASE c.size
            WHEN 'P' THEN ?
            WHEN 'M' THEN ?
            WHEN 'G' THEN ?
            ELSE ? END)), 2) AS excess_discount_brl
    FROM gold.fact_sales f
    JOIN gold.dim_customer c ON f.customer_id = c.customer_id
    JOIN gold.dim_product p ON f.product_id = p.product_id
    JOIN gold.dim_sales_rep r ON f.sales_rep_id = r.sales_rep_id
    WHERE {where_sql}
    GROUP BY f.sales_rep_id, r.name, r.region
    ORDER BY excess_discount_brl DESC
    """
    df_reps = repo.query(rep_sql, params=cap_params)

    fam_sql = f"""
    SELECT
        p.family,
        COUNT(DISTINCT f.order_id)::INTEGER AS total_orders,
        ROUND(SUM(f.gross_revenue), 2) AS gross_revenue,
        ROUND(SUM(f.discount_amount), 2) AS discount_amount,
        ROUND(SUM(f.discount_amount) / NULLIF(SUM(f.gross_revenue), 0) * 100.0, 2) AS avg_discount_pct,
        ROUND(SUM(GREATEST(0.0, f.discount_amount - f.gross_revenue * CASE c.size
            WHEN 'P' THEN ?
            WHEN 'M' THEN ?
            WHEN 'G' THEN ?
            ELSE ? END)), 2) AS excess_discount_brl
    FROM gold.fact_sales f
    JOIN gold.dim_customer c ON f.customer_id = c.customer_id
    JOIN gold.dim_product p ON f.product_id = p.product_id
    JOIN gold.dim_sales_rep r ON f.sales_rep_id = r.sales_rep_id
    WHERE {where_sql}
    GROUP BY p.family
    ORDER BY excess_discount_brl DESC
    """
    df_fams = repo.query(fam_sql, params=cap_params)

    return df_reps, df_fams


def query_term_leak_by_rep(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    sales_reps: Sequence[str] = (),
    families: Sequence[str] = (),
    start_date_key: int | None = None,
    end_date_key: int | None = None,
) -> pd.DataFrame:
    """Rankeia os RCAs pelo custo financeiro de prazos concedidos acima do padrão de 30 dias."""
    policy = load_temperance_policy_params(scenario_id)
    where_sql, params = build_temperance_filter_clauses(
        scenario_id,
        regiao=regiao,
        uf=uf,
        sales_reps=sales_reps,
        families=families,
        start_date_key=start_date_key,
        end_date_key=end_date_key,
    )
    rep_bias_expr, rep_bias_params = build_rep_bias_cte_sql(scenario_id, policy)

    sql = f"""
    WITH rep_bias AS (
        SELECT
            f_rep.sales_rep_id,
            {rep_bias_expr} AS extra_pmr
        FROM (SELECT DISTINCT sales_rep_id FROM gold.fact_sales WHERE scenario_id = ?) f_rep
    ),
    order_pmr AS (
        SELECT
            f.sales_rep_id,
            r.name AS rep_name,
            (f.gross_revenue - f.discount_amount) AS net_price_revenue,
            (CASE c.size WHEN 'P' THEN ? WHEN 'M' THEN ? WHEN 'G' THEN ? ELSE ? END
                + rb.extra_pmr) AS customer_pmr
        FROM gold.fact_sales f
        JOIN gold.dim_customer c ON f.customer_id = c.customer_id
        JOIN rep_bias rb ON f.sales_rep_id = rb.sales_rep_id
        JOIN gold.dim_product p ON f.product_id = p.product_id
        JOIN gold.dim_sales_rep r ON f.sales_rep_id = r.sales_rep_id
        WHERE {where_sql}
    )
    SELECT
        sales_rep_id,
        rep_name,
        ROUND(AVG(customer_pmr), 1) AS avg_pmr_days,
        ROUND(SUM(GREATEST(0, customer_pmr - ?) * (? / 30.0) * net_price_revenue), 2)
            AS term_leak_brl
    FROM order_pmr
    GROUP BY sales_rep_id, rep_name
    ORDER BY term_leak_brl DESC
    """
    full_params = [
        *rep_bias_params,
        policy["pmr_p"],
        policy["pmr_m"],
        policy["pmr_g"],
        policy["std_term"],
        *params,
        policy["std_term"],
        policy["rate_monthly"],
    ]
    return repo.query(sql, params=full_params)
