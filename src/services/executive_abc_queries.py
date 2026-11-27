from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from src.core.logging import get_logger
from src.core.types import ScenarioId
from src.db.repository import DataRepository
from src.ml.abc_xyz import compute_abc_xyz_matrix_summary
from src.services.executive_queries import build_filter_clauses
from src.services.period_comparison import ComparisonWindow, pct_delta

logger = get_logger(__name__)

__all__ = [
    "build_filtered_abc_xyz_matrix",
    "compute_abc_xyz_period_deltas",
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


def _count_sku_metrics(skus_df: pd.DataFrame) -> tuple[int, int, int, int]:
    """Extrai contagens de SKUs ativos, Curva A, AX e CZ de um DataFrame ABC/XYZ."""
    if skus_df.empty:
        return 0, 0, 0, 0
    active_cnt = len(skus_df)
    curve_a_cnt = int((skus_df["abc_class"] == "A").sum()) if "abc_class" in skus_df.columns else 0
    if "abc_xyz_class" in skus_df.columns:
        ax_cnt = int((skus_df["abc_xyz_class"] == "AX").sum())
        cz_cnt = int((skus_df["abc_xyz_class"] == "CZ").sum())
    else:
        ax_cnt, cz_cnt = 0, 0
    return active_cnt, curve_a_cnt, ax_cnt, cz_cnt


def compute_abc_xyz_period_deltas(
    repo: DataRepository,
    scenario_id: ScenarioId,
    win: ComparisonWindow,
    *,
    cur_skus_df: pd.DataFrame | None = None,
    regiao: str = "Todas",
    uf: str = "Todas",
    families: Sequence[str] = (),
    sales_reps: Sequence[str] = (),
) -> dict[str, float | None]:
    """Calcula deltas percentuais dos KPIs de portfolio (ativos, Curva A, AX e CZ)."""
    eff_cur_df = (
        cur_skus_df
        if cur_skus_df is not None
        else query_filtered_abc_xyz_skus(
            repo,
            scenario_id,
            regiao=regiao,
            uf=uf,
            families=families,
            sales_reps=sales_reps,
            start_date_key=win.cur_start,
            end_date_key=win.cur_end,
        )
    )
    prev_df = query_filtered_abc_xyz_skus(
        repo,
        scenario_id,
        regiao=regiao,
        uf=uf,
        families=families,
        sales_reps=sales_reps,
        start_date_key=win.prev_start,
        end_date_key=win.prev_end,
    )
    c_act, c_a, c_ax, c_cz = _count_sku_metrics(eff_cur_df)
    p_act, p_a, p_ax, p_cz = _count_sku_metrics(prev_df)
    return {
        "active_skus_delta_pct": pct_delta(float(c_act), float(p_act)),
        "curve_a_skus_delta_pct": pct_delta(float(c_a), float(p_a)),
        "ax_skus_delta_pct": pct_delta(float(c_ax), float(p_ax)),
        "cz_skus_delta_pct": pct_delta(float(c_cz), float(p_cz)),
    }
