from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from src.core.logging import get_logger
from src.core.types import ScenarioId
from src.db.repository import DataRepository
from src.ml.abc_xyz import compute_abc_xyz_matrix_summary
from src.services.executive_queries import build_filter_clauses

logger = get_logger(__name__)

__all__ = [
    "build_filtered_abc_xyz_matrix",
    "query_filtered_abc_xyz_skus",
]


def query_filtered_abc_xyz_skus(
    repo: DataRepository,
    scenario_id: ScenarioId = "c1_toys",
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    families: Sequence[str] = (),
    sales_reps: Sequence[str] = (),
    start_date_key: int | None = None,
    end_date_key: int | None = None,
) -> pd.DataFrame:
    """Consulta SKUs ABC/XYZ com receita e margem recalculadas sob os 5 filtros globais."""
    is_unscoped = (
        regiao == "Todas"
        and uf == "Todas"
        and not sales_reps
        and start_date_key is None
        and end_date_key is None
    )
    if is_unscoped:
        try:
            mart_df = repo.table("mart_abc_xyz", scenario_id)
        except Exception as exc:
            logger.warning("Falha ao carregar mart_abc_xyz: %s", exc)
            return pd.DataFrame()
        if mart_df.empty:
            return pd.DataFrame()
        if families:
            mart_df = mart_df[mart_df["family"].isin(families)].copy()
        return mart_df

    where_sql, params, joins = build_filter_clauses(
        scenario_id,
        regiao=regiao,
        uf=uf,
        families=families,
        sales_reps=sales_reps,
        start_date_key=start_date_key,
        end_date_key=end_date_key,
    )
    joins_copy = list(joins)
    product_join = "JOIN gold.dim_product p ON f.product_id = p.product_id"
    if product_join not in joins_copy:
        joins_copy.append(product_join)
    joins_sql = " ".join(joins_copy)

    sql = f"""
    SELECT
        f.product_id,
        p.product_name,
        p.family,
        COALESCE(m.abc_class, 'C') AS abc_class,
        COALESCE(m.xyz_class, 'Z') AS xyz_class,
        COALESCE(m.abc_xyz_class, 'CZ') AS abc_xyz_class,
        ROUND(COALESCE(SUM(f.gross_revenue), 0.0), 2) AS gross_revenue,
        ROUND(COALESCE(SUM(f.contribution_margin), 0.0), 2) AS contribution_margin,
        ROUND(
            COALESCE(SUM(f.contribution_margin) / NULLIF(SUM(f.gross_revenue), 0.0) * 100.0, 0.0),
            2
        ) AS margin_pct,
        COALESCE(MAX(m.weekly_cv), 0.0) AS weekly_cv,
        COALESCE(MAX(m.policy), 'Sob encomenda ou descontinuar') AS policy
    FROM gold.fact_sales f
    {joins_sql}
    LEFT JOIN gold.mart_abc_xyz m
        ON f.product_id = m.product_id AND f.scenario_id = m.scenario_id
    {where_sql}
    GROUP BY
        f.product_id,
        p.product_name,
        p.family,
        COALESCE(m.abc_class, 'C'),
        COALESCE(m.xyz_class, 'Z'),
        COALESCE(m.abc_xyz_class, 'CZ')
    ORDER BY contribution_margin DESC, gross_revenue DESC
    """
    try:
        return repo.query(sql, params=params)
    except Exception as exc:
        logger.warning("Falha ao consultar ABC/XYZ filtrado: %s", exc)
        return pd.DataFrame()


def build_filtered_abc_xyz_matrix(skus_df: pd.DataFrame) -> pd.DataFrame:
    """Constrói resumo 3x3 da Matriz ABC/XYZ compatível com Prudência e Temperança."""
    if skus_df.empty:
        return pd.DataFrame()

    matrix_summary = compute_abc_xyz_matrix_summary(skus_df)
    matrix_summary["abc_xyz_cell"] = matrix_summary["cell"]
    matrix_summary["sku_share_pct"] = matrix_summary["sku_pct"]
    matrix_summary["margin_share_pct"] = matrix_summary["margin_pct"]
    matrix_summary["recommended_policy"] = matrix_summary["policy"]
    return matrix_summary
