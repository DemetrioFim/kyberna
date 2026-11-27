from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

from src.core.types import ScenarioId
from src.db.repository import DataRepository
from src.services.fortitude_queries import (
    query_concentration_data,
    query_fortitude_financial_base,
    query_pmr_weighted,
)
from src.services.period_comparison import ComparisonWindow, abs_delta, pct_delta, pp_delta

__all__ = [
    "compute_fortitude_period_deltas",
    "compute_fortitude_window_snapshot",
]


def compute_fortitude_window_snapshot(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    pme_days: float,
    pmp_days: float,
    fixed_cost_pct: float,
    reserve_target_months: float,
    pmr_by_size: dict[str, float],
    extra_pmr_days: float,
    regiao: str,
    uf: str,
    families: Sequence[str],
    sales_reps: Sequence[str],
    start_date_key: int | None,
    end_date_key: int | None,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    """Calcula metricas centrais de caixa, break-even, ciclo NCG e concentracao para uma janela."""
    fin = query_fortitude_financial_base(
        repo,
        scenario_id,
        regiao=regiao,
        uf=uf,
        sales_reps=sales_reps,
        families=families,
        start_date_key=start_date_key,
        end_date_key=end_date_key,
    )
    monthly_gross = float(fin["monthly_gross_revenue_brl"])
    monthly_net = float(fin["monthly_net_revenue_brl"])
    monthly_cm = float(fin["monthly_contribution_margin_brl"])
    active_customers_count = int(fin["active_customers_count"])

    pmr_days = round(
        query_pmr_weighted(
            repo,
            scenario_id,
            pmr_by_size,
            extra_pmr_days,
            regiao=regiao,
            uf=uf,
            sales_reps=sales_reps,
            families=families,
            start_date_key=start_date_key,
            end_date_key=end_date_key,
        ),
        1,
    )
    ccc_days = round(pme_days + pmr_days - pmp_days, 1)
    ncg_brl = round((monthly_net / 30.0) * max(ccc_days, 0.0), 2)
    fixed_costs_monthly = round(monthly_net * fixed_cost_pct, 2)
    free_cash_generation = round(monthly_cm - fixed_costs_monthly, 2)

    if monthly_gross > 0.0:
        margin_pct_gross = round((monthly_cm / monthly_gross) * 100.0, 1)
        margin_pct_net = round((monthly_cm / max(monthly_net, 1e-6)) * 100.0, 1)
        breakeven_rev = round(fixed_costs_monthly / max(margin_pct_gross / 100.0, 0.01), 2)
        breakeven_day = int(np.clip(np.ceil(30.0 * breakeven_rev / max(monthly_gross, 1.0)), 1, 30))
        if free_cash_generation >= 0.0:
            cash_reserve_brl = round(fixed_costs_monthly * reserve_target_months + free_cash_generation, 2)
            cash_runway_months = round(cash_reserve_brl / max(fixed_costs_monthly, 1.0), 1)
        else:
            cash_reserve_brl = round(
                max(
                    fixed_costs_monthly,
                    fixed_costs_monthly * reserve_target_months + free_cash_generation,
                ),
                2,
            )
            cash_runway_months = round(
                cash_reserve_brl / max(fixed_costs_monthly + abs(free_cash_generation), 1.0), 1
            )
    else:
        margin_pct_gross = 0.0
        margin_pct_net = 0.0
        breakeven_rev = 0.0
        breakeven_day = 30
        cash_reserve_brl = 0.0
        cash_runway_months = 0.0

    cust_conc_df, fam_conc_df, conc_metrics = query_concentration_data(
        repo,
        scenario_id,
        regiao=regiao,
        uf=uf,
        sales_reps=sales_reps,
        families=families,
        start_date_key=start_date_key,
        end_date_key=end_date_key,
    )
    core: dict[str, Any] = {
        "monthly_gross": monthly_gross,
        "monthly_net": monthly_net,
        "monthly_cm": monthly_cm,
        "active_customers_count": active_customers_count,
        "pmr_days": pmr_days,
        "ccc_days": ccc_days,
        "ncg_brl": ncg_brl,
        "fixed_costs_monthly": fixed_costs_monthly,
        "free_cash_generation": free_cash_generation,
        "margin_pct_gross": margin_pct_gross,
        "margin_pct_net": margin_pct_net,
        "breakeven_rev": breakeven_rev,
        "breakeven_day": breakeven_day,
        "cash_reserve_brl": cash_reserve_brl,
        "cash_runway_months": cash_runway_months,
        "top5_share": conc_metrics["top5_customers_share_pct"],
        "top10_share": conc_metrics["top10_customers_share_pct"],
        "top2_fam_share": conc_metrics["top2_families_share_pct"],
    }
    return core, cust_conc_df, fam_conc_df


def compute_fortitude_period_deltas(
    repo: DataRepository,
    scenario_id: ScenarioId,
    win: ComparisonWindow,
    *,
    cur_core: dict[str, Any] | None,
    pme_days: float,
    pmp_days: float,
    fixed_cost_pct: float,
    reserve_target_months: float,
    pmr_by_size: dict[str, float],
    extra_pmr_days: float,
    regiao: str,
    uf: str,
    families: Sequence[str],
    sales_reps: Sequence[str],
) -> dict[str, float | None]:
    """Calcula deltas PoP/YoY dos 5 KPIs de solvencia e capital de giro."""
    if cur_core is not None:
        eff_cur = cur_core
    else:
        eff_cur, _, _ = compute_fortitude_window_snapshot(
            repo,
            scenario_id,
            pme_days=pme_days,
            pmp_days=pmp_days,
            fixed_cost_pct=fixed_cost_pct,
            reserve_target_months=reserve_target_months,
            pmr_by_size=pmr_by_size,
            extra_pmr_days=extra_pmr_days,
            regiao=regiao,
            uf=uf,
            families=families,
            sales_reps=sales_reps,
            start_date_key=win.cur_start,
            end_date_key=win.cur_end,
        )
    prev_c, _, _ = compute_fortitude_window_snapshot(
        repo,
        scenario_id,
        pme_days=pme_days,
        pmp_days=pmp_days,
        fixed_cost_pct=fixed_cost_pct,
        reserve_target_months=reserve_target_months,
        pmr_by_size=pmr_by_size,
        extra_pmr_days=extra_pmr_days,
        regiao=regiao,
        uf=uf,
        families=families,
        sales_reps=sales_reps,
        start_date_key=win.prev_start,
        end_date_key=win.prev_end,
    )
    if eff_cur["monthly_gross"] <= 0.0 or prev_c["monthly_gross"] <= 0.0:
        return {}
    return {
        "runway_delta_months": abs_delta(eff_cur["cash_runway_months"], prev_c["cash_runway_months"]),
        "breakeven_revenue_delta_pct": pct_delta(eff_cur["breakeven_rev"], prev_c["breakeven_rev"]),
        "ccc_delta_days": abs_delta(eff_cur["ccc_days"], prev_c["ccc_days"]),
        "ncg_delta_pct": pct_delta(eff_cur["ncg_brl"], prev_c["ncg_brl"]),
        "top10_share_delta_pp": pp_delta(eff_cur["top10_share"], prev_c["top10_share"]),
    }
