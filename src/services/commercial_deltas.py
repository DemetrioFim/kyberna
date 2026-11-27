from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

import pandas as pd

from src.core.types import ScenarioId
from src.db.repository import DataRepository
from src.services.commercial_queries import (
    query_commercial_kpis_data,
    query_rep_performance_data,
)
from src.services.period_comparison import (
    abs_delta,
    int_delta,
    pct_delta,
    pp_delta,
    resolve_effective_comparison_window,
)
from src.services.white_space_queries import query_white_space_coverage_kpis

__all__ = ["compute_commercial_period_deltas"]


def _rep_means(rep_df: pd.DataFrame) -> tuple[float, float, float, float]:
    """Extrai médias da força de vendas para comparação temporal consistente."""
    if rep_df.empty:
        return 0.0, 0.0, 0.0, 0.0
    avg_rev = float(rep_df["gross_revenue"].mean()) if "gross_revenue" in rep_df.columns else 0.0
    avg_margin = float(rep_df["margin_pct"].mean()) if "margin_pct" in rep_df.columns else 0.0
    avg_disc = float(rep_df["avg_discount_pct"].mean()) if "avg_discount_pct" in rep_df.columns else 0.0
    avg_pos = float(rep_df["positivation_pct"].mean()) if "positivation_pct" in rep_df.columns else 0.0
    return avg_rev, avg_margin, avg_disc, avg_pos


def compute_commercial_period_deltas(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    cur_kpis_raw: dict[str, Any],
    cur_ws_cov: dict[str, float | int],
    cur_rep_df: pd.DataFrame,
    regiao: str = "Todas",
    uf: str = "Todas",
    families: Sequence[str] = (),
    sales_reps: Sequence[str] = (),
    risk_status: str = "Todos",
    rfm_segment: str = "Todos",
    quadrant: str = "Todos",
    start_date_key: int | None = None,
    end_date_key: int | None = None,
    comp_start_date_key: int | None = None,
    comp_end_date_key: int | None = None,
    comparison_mode: Literal["pop", "yoy"] = "pop",
) -> dict[str, float | int | None]:
    """Calcula os 9 deltas comparativos PoP/YoY dos KPIs de Fortaleza Comercial."""
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
        return {}

    if start_date_key is not None:
        c_raw, c_ws, c_rep_df = cur_kpis_raw, cur_ws_cov, cur_rep_df
    else:
        c_raw = query_commercial_kpis_data(
            repo,
            scenario_id,
            regiao=regiao,
            uf=uf,
            families=families,
            sales_reps=sales_reps,
            risk_status=risk_status,
            rfm_segment=rfm_segment,
            start_date_key=win.cur_start,
            end_date_key=win.cur_end,
        )
        c_ws = query_white_space_coverage_kpis(
            repo,
            scenario_id,
            regiao=regiao,
            uf=uf,
            sales_reps=sales_reps,
            families=families,
            start_date_key=win.cur_start,
            end_date_key=win.cur_end,
        )
        c_rep_df = query_rep_performance_data(
            repo,
            scenario_id,
            regiao=regiao,
            uf=uf,
            families=families,
            sales_reps=sales_reps,
            quadrant=quadrant,
            start_date_key=win.cur_start,
            end_date_key=win.cur_end,
        )

    p_raw = query_commercial_kpis_data(
        repo,
        scenario_id,
        regiao=regiao,
        uf=uf,
        families=families,
        sales_reps=sales_reps,
        risk_status=risk_status,
        rfm_segment=rfm_segment,
        start_date_key=win.prev_start,
        end_date_key=win.prev_end,
    )
    p_ws = query_white_space_coverage_kpis(
        repo,
        scenario_id,
        regiao=regiao,
        uf=uf,
        sales_reps=sales_reps,
        families=families,
        start_date_key=win.prev_start,
        end_date_key=win.prev_end,
    )
    p_rep_df = query_rep_performance_data(
        repo,
        scenario_id,
        regiao=regiao,
        uf=uf,
        families=families,
        sales_reps=sales_reps,
        quadrant=quadrant,
        start_date_key=win.prev_start,
        end_date_key=win.prev_end,
    )

    c_r_rev, c_r_mar, c_r_disc, c_r_pos = _rep_means(c_rep_df)
    p_r_rev, p_r_mar, p_r_disc, p_r_pos = _rep_means(p_rep_df)

    has_rep_cmp = not c_rep_df.empty and not p_rep_df.empty
    return {
        "avg_families_delta": abs_delta(
            float(c_ws.get("avg_families_per_customer", 0.0)),
            float(p_ws.get("avg_families_per_customer", 0.0)),
        ),
        "white_space_revenue_delta_pct": pct_delta(
            float(c_raw.get("white_space_potential_revenue_brl", 0.0)),
            float(p_raw.get("white_space_potential_revenue_brl", 0.0)),
        ),
        "active_customers_delta_pct": pct_delta(
            float(c_raw.get("active_customers", 0)),
            float(p_raw.get("active_customers", 0)),
        ),
        "avg_ltv_delta_pct": pct_delta(
            float(c_raw.get("avg_ltv_brl", 0.0)),
            float(p_raw.get("avg_ltv_brl", 0.0)),
        ),
        "vampire_customers_delta": int_delta(
            int(c_raw.get("vampire_customers_count", 0)),
            int(p_raw.get("vampire_customers_count", 0)),
        ),
        "rep_gross_revenue_delta_pct": pct_delta(c_r_rev, p_r_rev) if has_rep_cmp else None,
        "rep_margin_pct_delta_pp": pp_delta(c_r_mar, p_r_mar) if has_rep_cmp else None,
        "rep_discount_pct_delta_pp": pp_delta(c_r_disc, p_r_disc) if has_rep_cmp else None,
        "rep_positivation_delta_pp": pp_delta(c_r_pos, p_r_pos) if has_rep_cmp else None,
    }
