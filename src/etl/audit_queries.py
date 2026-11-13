from __future__ import annotations

from typing import Any

import duckdb
import pandas as pd

from src.ml.abc_xyz import build_abc_xyz_mart, compute_abc_xyz_matrix_summary


def _extract_dre_data(con: duckdb.DuckDBPyConnection, scenario_id: str) -> dict[str, float]:
    """Extrai os totais consolidados do Waterfall para a DRE."""
    query = f"""
    SELECT
        ROUND(SUM(gross_revenue), 2) AS gross_revenue,
        ROUND(SUM(discount_amount), 2) AS discount_amount,
        ROUND(SUM(gross_revenue - discount_amount), 2) AS net_price_revenue,
        ROUND(SUM(tax_amount), 2) AS tax_amount,
        ROUND(SUM(net_revenue), 2) AS net_revenue,
        ROUND(SUM(cogs), 2) AS cogs,
        ROUND(SUM(net_revenue - cogs), 2) AS gross_margin,
        ROUND(SUM(commission_amount), 2) AS commission_amount,
        ROUND(SUM(freight_amount), 2) AS freight_amount,
        ROUND(SUM(contribution_margin), 2) AS contribution_margin,
        COUNT(*) AS total_lines,
        COUNT(DISTINCT order_id) AS total_orders,
        COUNT(DISTINCT customer_id) AS total_customers,
        COUNT(DISTINCT product_id) AS total_products
    FROM gold.fact_sales
    WHERE scenario_id = '{scenario_id}'
    """
    row = con.execute(query).fetchone()
    if not row:
        return {}
    cols = [
        "gross_revenue",
        "discount_amount",
        "net_price_revenue",
        "tax_amount",
        "net_revenue",
        "cogs",
        "gross_margin",
        "commission_amount",
        "freight_amount",
        "contribution_margin",
        "total_lines",
        "total_orders",
        "total_customers",
        "total_products",
    ]
    return {col: float(val) if val is not None else 0.0 for col, val in zip(cols, row, strict=False)}


def _extract_sample_orders(
    con: duckdb.DuckDBPyConnection, scenario_id: str, limit: int = 100
) -> pd.DataFrame:
    """Extrai amostra balanceada de 100 pedidos com colunas intermediárias abertas."""
    query = f"""
    SELECT
        f.order_id,
        d.full_date AS order_date,
        c.trade_name AS customer_name,
        c.size AS customer_size,
        c.state,
        c.region,
        r.name AS sales_rep,
        p.product_name,
        p.family,
        f.units,
        f.boxes,
        f.unit_list_price,
        f.gross_revenue,
        ROUND(f.discount_amount / NULLIF(f.gross_revenue, 0), 4) AS discount_rate,
        f.discount_amount,
        ROUND(f.gross_revenue - f.discount_amount, 2) AS net_price_revenue,
        ROUND(f.tax_amount / NULLIF(f.gross_revenue - f.discount_amount, 0), 4) AS tax_rate,
        f.tax_amount,
        f.net_revenue,
        ROUND(f.cogs / NULLIF(f.units, 0), 2) AS unit_cost,
        f.cogs,
        ROUND(f.commission_amount / NULLIF(f.gross_revenue - f.discount_amount, 0), 4) AS commission_rate,
        f.commission_amount,
        f.freight_amount,
        f.contribution_margin,
        ROUND(f.contribution_margin / NULLIF(f.gross_revenue, 0) * 100.0, 2) AS margin_pct
    FROM gold.fact_sales f
    JOIN gold.dim_date d ON f.date_key = d.date_key
    JOIN gold.dim_customer c ON f.customer_id = c.customer_id
    JOIN gold.dim_sales_rep r ON f.sales_rep_id = r.sales_rep_id
    JOIN gold.dim_product p ON f.product_id = p.product_id
    WHERE f.scenario_id = '{scenario_id}'
    ORDER BY d.full_date DESC, f.gross_revenue DESC
    LIMIT {limit}
    """
    return con.execute(query).df()


def _extract_families_summary(con: duckdb.DuckDBPyConnection, scenario_id: str) -> pd.DataFrame:
    """Agrega faturamento e margem por família de produtos."""
    query = f"""
    SELECT
        p.family,
        COUNT(DISTINCT f.order_id) AS orders_count,
        SUM(f.units) AS units,
        ROUND(SUM(f.boxes), 2) AS boxes,
        ROUND(SUM(f.gross_revenue), 2) AS gross_revenue,
        ROUND(SUM(f.discount_amount), 2) AS discount_amount,
        ROUND(SUM(f.tax_amount), 2) AS tax_amount,
        ROUND(SUM(f.net_revenue), 2) AS net_revenue,
        ROUND(SUM(f.cogs), 2) AS cogs,
        ROUND(SUM(f.contribution_margin), 2) AS contribution_margin,
        ROUND(SUM(f.contribution_margin) / NULLIF(SUM(f.gross_revenue), 0) * 100.0, 2) AS margin_pct
    FROM gold.fact_sales f
    JOIN gold.dim_product p ON f.product_id = p.product_id
    WHERE f.scenario_id = '{scenario_id}'
    GROUP BY p.family
    ORDER BY gross_revenue DESC
    """
    df = con.execute(query).df()
    total_rev = df["gross_revenue"].sum()
    df["revenue_share_pct"] = (df["gross_revenue"] / total_rev * 100.0).round(2)
    return df


def _extract_rcas_summary(con: duckdb.DuckDBPyConnection, scenario_id: str) -> pd.DataFrame:
    """Extrai performance e comportamento de desconto por RCA."""
    query = f"""
    SELECT
        r.name AS sales_rep,
        r.region,
        COUNT(DISTINCT f.order_id) AS orders_count,
        COUNT(DISTINCT f.customer_id) AS customers_count,
        ROUND(SUM(f.gross_revenue), 2) AS gross_revenue,
        ROUND(SUM(f.discount_amount) / NULLIF(SUM(f.gross_revenue), 0) * 100.0, 2) AS avg_discount_pct,
        ROUND(SUM(f.commission_amount), 2) AS total_commission,
        ROUND(SUM(f.contribution_margin), 2) AS contribution_margin,
        ROUND(SUM(f.contribution_margin) / NULLIF(SUM(f.gross_revenue), 0) * 100.0, 2) AS margin_pct
    FROM gold.fact_sales f
    JOIN gold.dim_sales_rep r ON f.sales_rep_id = r.sales_rep_id
    WHERE f.scenario_id = '{scenario_id}'
    GROUP BY r.name, r.region
    ORDER BY gross_revenue DESC
    """
    return con.execute(query).df()


def _extract_top_customers(con: duckdb.DuckDBPyConnection, scenario_id: str, limit: int = 20) -> pd.DataFrame:
    """Extrai os top lojistas por faturamento e margem."""
    query = f"""
    SELECT
        c.trade_name,
        c.cnpj,
        c.size,
        c.city,
        c.state,
        r.name AS sales_rep,
        COUNT(DISTINCT f.order_id) AS orders_count,
        ROUND(SUM(f.gross_revenue), 2) AS gross_revenue,
        ROUND(SUM(f.contribution_margin), 2) AS contribution_margin,
        ROUND(SUM(f.contribution_margin) / NULLIF(SUM(f.gross_revenue), 0) * 100.0, 2) AS margin_pct
    FROM gold.fact_sales f
    JOIN gold.dim_customer c ON f.customer_id = c.customer_id
    JOIN gold.dim_sales_rep r ON f.sales_rep_id = r.sales_rep_id
    WHERE f.scenario_id = '{scenario_id}'
    GROUP BY c.trade_name, c.cnpj, c.size, c.city, c.state, r.name
    ORDER BY gross_revenue DESC
    LIMIT {limit}
    """
    return con.execute(query).df()


def _extract_integrity_stats(con: duckdb.DuckDBPyConnection, scenario_id: str) -> dict[str, Any]:
    """Audita a conservação e identidade contábil linha a linha."""
    query = f"""
    SELECT
        COUNT(*) AS total_rows,
        COUNT(
            CASE
                WHEN ABS(
                    contribution_margin - (net_revenue - cogs - commission_amount - freight_amount)
                ) > 0.01
                THEN 1
            END
        ) AS math_divergences,
        ROUND(SUM(gross_revenue), 2) AS total_gross_gold,
        (SELECT ROUND(SUM(gross_revenue), 2) FROM {scenario_id}.sales_remapped) AS total_gross_silver
    FROM gold.fact_sales
    WHERE scenario_id = '{scenario_id}'
    """
    row = con.execute(query).fetchone()
    if not row:
        return {}
    return {
        "total_rows": int(row[0]),
        "divergences": int(row[1]),
        "total_gold": float(row[2]),
        "total_silver": float(row[3]) if row[3] is not None else float(row[2]),
    }


def _extract_abc_xyz_data(
    con: duckdb.DuckDBPyConnection, scenario_id: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Extrai os dados da Matriz ABC/XYZ e o resumo executivo das 9 células."""
    table_exists = False
    try:
        res = con.execute(
            f"SELECT COUNT(*) FROM information_schema.tables "
            f"WHERE table_schema IN ('{scenario_id}', 'gold') AND table_name = 'mart_abc_xyz'"
        ).fetchone()
        table_exists = bool(res and res[0] > 0)
    except Exception:
        table_exists = False

    if table_exists:
        df = con.execute(
            f"SELECT * FROM gold.mart_abc_xyz WHERE scenario_id = '{scenario_id}' "
            f"ORDER BY abc_class ASC, contribution_margin DESC, product_id ASC"
        ).df()
    else:
        df = build_abc_xyz_mart(con, scenario_id=scenario_id)  # type: ignore[arg-type]

    summary = compute_abc_xyz_matrix_summary(df)
    return df, summary
