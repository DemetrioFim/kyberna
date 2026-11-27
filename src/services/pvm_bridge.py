from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

import numpy as np
import pandas as pd

from src.core.types import ScenarioId
from src.db.repository import DataRepository
from src.services.executive_queries import build_filter_clauses
from src.services.period_comparison import resolve_effective_comparison_window

__all__ = [
    "build_pvm_bridge",
    "compute_pvm_bridge_steps",
]


def _query_sku_period_stats(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    regiao: str,
    uf: str,
    families: Sequence[str],
    sales_reps: Sequence[str],
    start_date_key: int | None,
    end_date_key: int | None,
) -> pd.DataFrame:
    """Agrega volume, faturamento de tabela, receita liquida e margem por SKU na janela."""
    where_sql, params, joins = build_filter_clauses(
        scenario_id,
        regiao=regiao,
        uf=uf,
        families=families,
        sales_reps=sales_reps,
        start_date_key=start_date_key,
        end_date_key=end_date_key,
    )
    joins_sql = " ".join(joins)
    sql = f"""
    SELECT
        f.product_id,
        COALESCE(SUM(f.units), 0)::DOUBLE AS units,
        COALESCE(SUM(f.gross_revenue), 0.0) AS gross_revenue,
        COALESCE(SUM(f.net_revenue - f.commission_amount), 0.0) AS net_keep_revenue,
        COALESCE(SUM(f.contribution_margin), 0.0) AS contribution_margin
    FROM gold.fact_sales f
    {joins_sql}
    {where_sql}
    GROUP BY f.product_id
    """
    try:
        return repo.query(sql, params=params)
    except Exception:
        return pd.DataFrame(
            columns=["product_id", "units", "gross_revenue", "net_keep_revenue", "contribution_margin"]
        )


def compute_pvm_bridge_steps(
    prev_df: pd.DataFrame,
    cur_df: pd.DataFrame,
) -> pd.DataFrame:
    """Calcula a decomposicao contabil exata Delta MC = Volume + Preco + Mix + Desc./Custos."""
    if prev_df.empty and cur_df.empty:
        return pd.DataFrame(columns=["step_key", "label", "amount", "measure"])

    cols = ["product_id", "units", "gross_revenue", "net_keep_revenue", "contribution_margin"]
    p_df = prev_df[cols] if not prev_df.empty else pd.DataFrame(columns=cols)
    c_df = cur_df[cols] if not cur_df.empty else pd.DataFrame(columns=cols)

    merged = pd.merge(p_df, c_df, on="product_id", how="outer", suffixes=("_0", "_1")).fillna(0.0)
    if merged.empty:
        return pd.DataFrame(columns=["step_key", "label", "amount", "measure"])

    u0 = merged["units_0"].to_numpy(dtype=np.float64)
    u1 = merged["units_1"].to_numpy(dtype=np.float64)
    g0 = merged["gross_revenue_0"].to_numpy(dtype=np.float64)
    g1 = merged["gross_revenue_1"].to_numpy(dtype=np.float64)
    nk0 = merged["net_keep_revenue_0"].to_numpy(dtype=np.float64)
    mc0_arr = merged["contribution_margin_0"].to_numpy(dtype=np.float64)
    mc1_arr = merged["contribution_margin_1"].to_numpy(dtype=np.float64)

    tot_u0 = float(u0.sum())
    tot_u1 = float(u1.sum())
    tot_mc0 = float(mc0_arr.sum())
    tot_mc1 = float(mc1_arr.sum())

    if tot_u0 <= 0.0 and tot_u1 <= 0.0:
        return pd.DataFrame(columns=["step_key", "label", "amount", "measure"])

    if tot_u0 > 0.0:
        avg_mc_unit0 = tot_mc0 / tot_u0
        vol_eff = (tot_u1 - tot_u0) * avg_mc_unit0

        mc_unit0 = np.divide(
            mc0_arr,
            u0,
            out=np.full_like(u0, avg_mc_unit0, dtype=np.float64),
            where=u0 > 0.0,
        )
        s0 = u0 / tot_u0
        mix_eff = float(np.sum((u1 - tot_u1 * s0) * mc_unit0))

        both_mask = (u0 > 0.0) & (u1 > 0.0) & (g0 > 0.0)
        p0 = np.divide(g0, u0, out=np.zeros_like(u0), where=u0 > 0.0)
        p1 = np.divide(g1, u1, out=np.zeros_like(u1), where=u1 > 0.0)
        keep0 = np.clip(
            np.divide(nk0, g0, out=np.zeros_like(g0), where=g0 > 0.0),
            0.0,
            1.0,
        )
        price_eff = float(np.sum(np.where(both_mask, u1 * (p1 - p0) * keep0, 0.0)))
    else:
        vol_eff = 0.0
        mix_eff = 0.0
        price_eff = 0.0

    mc0_r = round(tot_mc0, 2)
    mc1_r = round(tot_mc1, 2)
    vol_r = round(vol_eff, 2)
    price_r = round(price_eff, 2)
    mix_r = round(mix_eff, 2)
    disc_cost_r = round(mc1_r - mc0_r - vol_r - price_r - mix_r, 2)

    return pd.DataFrame(
        [
            {"step_key": "mc_base", "label": "MC Base (Ant.)", "amount": mc0_r, "measure": "absolute"},
            {"step_key": "volume", "label": "Efeito Volume", "amount": vol_r, "measure": "relative"},
            {"step_key": "price", "label": "Preço Tabela", "amount": price_r, "measure": "relative"},
            {"step_key": "mix", "label": "Mix Produtos", "amount": mix_r, "measure": "relative"},
            {
                "step_key": "disc_cost",
                "label": "Desc. & Custos",
                "amount": disc_cost_r,
                "measure": "relative",
            },
            {"step_key": "mc_final", "label": "MC Atual", "amount": mc1_r, "measure": "total"},
        ]
    )


def build_pvm_bridge(
    repo: DataRepository,
    scenario_id: ScenarioId = "c1_toys",
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    families: Sequence[str] = (),
    sales_reps: Sequence[str] = (),
    start_date_key: int | None = None,
    end_date_key: int | None = None,
    comp_start_date_key: int | None = None,
    comp_end_date_key: int | None = None,
    comparison_mode: Literal["pop", "yoy"] = "pop",
) -> pd.DataFrame:
    """Constroi Bridge PVM de Margem de Contribuicao entre janela atual e comparativa."""
    win = resolve_effective_comparison_window(
        repo,
        scenario_id,
        start_date_key=start_date_key,
        end_date_key=end_date_key,
        comp_start_date_key=comp_start_date_key,
        comp_end_date_key=comp_end_date_key,
        comparison_mode=comparison_mode,
    )
    if win is None:
        return pd.DataFrame(columns=["step_key", "label", "amount", "measure"])

    prev_df = _query_sku_period_stats(
        repo,
        scenario_id,
        regiao=regiao,
        uf=uf,
        families=families,
        sales_reps=sales_reps,
        start_date_key=win.prev_start,
        end_date_key=win.prev_end,
    )
    cur_df = _query_sku_period_stats(
        repo,
        scenario_id,
        regiao=regiao,
        uf=uf,
        families=families,
        sales_reps=sales_reps,
        start_date_key=win.cur_start,
        end_date_key=win.cur_end,
    )
    return compute_pvm_bridge_steps(prev_df, cur_df)
