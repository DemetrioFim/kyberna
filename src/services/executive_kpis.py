from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Literal

import pandas as pd

from src.core.types import ScenarioId
from src.db.repository import DataRepository
from src.services.dto import ExecutiveKpisDTO
from src.services.executive_queries import (
    build_filter_clauses,
    query_raw_kpis,
)
from src.services.period_comparison import (
    pct_delta,
    pp_delta,
    resolve_effective_comparison_window,
)


def _key_to_date(date_key: int) -> date:
    """Converte chave inteira `YYYYMMDD` em `datetime.date`."""
    year, rem = divmod(date_key, 10000)
    month, day = divmod(rem, 100)
    return date(year, month, day)


def _compute_deltas(
    *,
    cur_gross: float,
    cur_net: float,
    cur_cm: float,
    cur_cm_pct: float,
    cur_custs: int,
    cur_deductions_pct: float,
    prev_row: pd.Series,
) -> tuple[float | None, float | None, float | None, float | None, float | None, float | None, float]:
    """Calcula deltas percentuais e de p.p. entre período atual e base comparativa."""
    prev_gross = float(prev_row["gross_revenue"])
    if prev_gross <= 0:
        return None, None, None, None, None, None, prev_gross

    prev_net = float(prev_row["net_revenue"])
    prev_cm = float(prev_row["contribution_margin"])
    prev_cm_pct = prev_cm / prev_gross * 100.0
    prev_custs = int(prev_row["active_customers"])
    prev_ded = float(prev_row["discount_amount"]) + float(prev_row["tax_amount"])
    prev_ded_pct = (prev_ded / prev_gross) * 100.0

    return (
        pct_delta(cur_gross, prev_gross),
        pct_delta(cur_net, prev_net),
        pct_delta(cur_cm, prev_cm),
        pp_delta(cur_cm_pct, prev_cm_pct),
        pct_delta(float(cur_custs), float(prev_custs)),
        pp_delta(cur_deductions_pct, prev_ded_pct),
        prev_gross,
    )


def compute_executive_kpis(
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
) -> ExecutiveKpisDTO:
    """Calcula indicadores executivos consolidados, conciliação e deltas do período."""
    where_sql, params, joins = build_filter_clauses(
        scenario_id,
        regiao=regiao,
        uf=uf,
        families=families,
        sales_reps=sales_reps,
        start_date_key=start_date_key,
        end_date_key=end_date_key,
    )
    df = query_raw_kpis(repo, where_sql, params, joins)
    if df.empty:
        return ExecutiveKpisDTO(
            gross_revenue=0.0,
            discount_amount=0.0,
            net_price_revenue=0.0,
            tax_amount=0.0,
            net_revenue=0.0,
            cogs=0.0,
            commission_amount=0.0,
            freight_amount=0.0,
            contribution_margin=0.0,
            contribution_margin_pct=0.0,
            total_orders=0,
            active_customers=0,
            avg_ticket=0.0,
            total_boxes=0.0,
            total_units=0,
        )

    row = df.iloc[0]
    gross, net_rev, cm = (
        float(row["gross_revenue"]),
        float(row["net_revenue"]),
        float(row["contribution_margin"]),
    )
    disc_amt, tax_amt = float(row["discount_amount"]), float(row["tax_amount"])
    cm_pct = round((cm / gross * 100.0), 2) if gross > 0 else 0.0
    cur_ded_pct = ((disc_amt + tax_amt) / gross * 100.0) if gross > 0 else 0.0
    orders, custs = int(row["total_orders"]), int(row["active_customers"])
    avg_ticket = round(gross / orders, 2) if orders > 0 else 0.0

    has_min_max = (
        "min_date_key" in row.index
        and "max_date_key" in row.index
        and pd.notna(row["min_date_key"])
        and pd.notna(row["max_date_key"])
    )
    min_max_keys = (int(row["min_date_key"]), int(row["max_date_key"])) if has_min_max else None
    if start_date_key is not None and end_date_key is not None:
        window_days = max((_key_to_date(end_date_key) - _key_to_date(start_date_key)).days + 1, 1)
    elif has_min_max:
        window_days = max(
            (_key_to_date(int(row["max_date_key"])) - _key_to_date(int(row["min_date_key"]))).days + 1,
            1,
        )
    else:
        window_days = 365

    gross_delta, net_delta, cm_delta, margin_delta_pp, cust_delta, ded_delta_pp = (
        None,
        None,
        None,
        None,
        None,
        None,
    )
    prev_gross = 0.0

    win = resolve_effective_comparison_window(
        repo,
        scenario_id,
        start_date_key=start_date_key,
        end_date_key=end_date_key,
        comp_start_date_key=comp_start_date_key,
        comp_end_date_key=comp_end_date_key,
        comparison_mode=comparison_mode,
        min_max_keys=min_max_keys,
    )
    if win is not None:
        if start_date_key is not None:
            cur_g, cur_n, cur_c, cur_cp, cur_cu, cur_dp = (
                gross,
                net_rev,
                cm,
                cm_pct,
                custs,
                cur_ded_pct,
            )
            has_cur = True
        else:
            cur_w, cur_p, cur_j = build_filter_clauses(
                scenario_id,
                regiao=regiao,
                uf=uf,
                families=families,
                sales_reps=sales_reps,
                start_date_key=win.cur_start,
                end_date_key=win.cur_end,
            )
            cur_df = query_raw_kpis(repo, cur_w, cur_p, cur_j)
            has_cur = not cur_df.empty
            if has_cur:
                c0 = cur_df.iloc[0]
                cur_g = float(c0["gross_revenue"])
                cur_n = float(c0["net_revenue"])
                cur_c = float(c0["contribution_margin"])
                cur_cp = round((cur_c / cur_g * 100.0), 2) if cur_g > 0 else 0.0
                cur_cu = int(c0["active_customers"])
                cur_dp = (
                    ((float(c0["discount_amount"]) + float(c0["tax_amount"])) / cur_g * 100.0)
                    if cur_g > 0
                    else 0.0
                )
            else:
                cur_g = cur_n = cur_c = cur_cp = cur_dp = 0.0
                cur_cu = 0

        if has_cur:
            prev_w, prev_p, prev_j = build_filter_clauses(
                scenario_id,
                regiao=regiao,
                uf=uf,
                families=families,
                sales_reps=sales_reps,
                start_date_key=win.prev_start,
                end_date_key=win.prev_end,
            )
            prev_df = query_raw_kpis(repo, prev_w, prev_p, prev_j)
            if not prev_df.empty:
                (
                    gross_delta,
                    net_delta,
                    cm_delta,
                    margin_delta_pp,
                    cust_delta,
                    ded_delta_pp,
                    prev_gross,
                ) = _compute_deltas(
                    cur_gross=cur_g,
                    cur_net=cur_n,
                    cur_cm=cur_c,
                    cur_cm_pct=cur_cp,
                    cur_custs=cur_cu,
                    cur_deductions_pct=cur_dp,
                    prev_row=prev_df.iloc[0],
                )

    target_rev = (
        round(prev_gross * 1.08, 2)
        if start_date_key is not None and prev_gross > 0
        else round(gross * 1.05, 2)
    )
    pacing_pct = round(gross / max(target_rev, 1.0) * 100.0, 1)
    projected_rev = round((gross / max(window_days, 1)) * 90.0, 2)

    return ExecutiveKpisDTO(
        gross_revenue=gross,
        discount_amount=disc_amt,
        net_price_revenue=float(row["net_price_revenue"]),
        tax_amount=tax_amt,
        net_revenue=net_rev,
        cogs=float(row["cogs"]),
        commission_amount=float(row["commission_amount"]),
        freight_amount=float(row["freight_amount"]),
        contribution_margin=cm,
        contribution_margin_pct=cm_pct,
        total_orders=orders,
        active_customers=custs,
        avg_ticket=avg_ticket,
        total_boxes=float(row["total_boxes"]),
        total_units=int(row["total_units"]),
        gross_revenue_delta_pct=gross_delta,
        net_revenue_delta_pct=net_delta,
        contribution_margin_delta_pct=cm_delta,
        margin_pct_delta_pp=margin_delta_pp,
        active_customers_delta_pct=cust_delta,
        deductions_pct_delta_pp=ded_delta_pp,
        revenue_target_brl=target_rev,
        revenue_pacing_pct=pacing_pct,
        margin_target_pct=26.0,
        projected_quarter_revenue_brl=projected_rev,
    )
