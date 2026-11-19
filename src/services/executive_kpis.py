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


def _key_to_date(date_key: int) -> date:
    """Converte chave inteira `YYYYMMDD` em `datetime.date`."""
    year, rem = divmod(date_key, 10000)
    month, day = divmod(rem, 100)
    return date(year, month, day)


def _shift_year_back(dt: date) -> date:
    """Recua exatamente 1 ano mantendo segurança para 29/02."""
    try:
        return dt.replace(year=dt.year - 1)
    except ValueError:
        return dt.replace(year=dt.year - 1, day=28)


def _compute_deltas(
    *,
    cur_gross: float,
    cur_net: float,
    cur_cm: float,
    cur_cm_pct: float,
    cur_custs: int,
    prev_row: pd.Series,
) -> tuple[float | None, float | None, float | None, float | None, float | None, float]:
    """Calcula deltas percentuais e de p.p. entre período atual e base comparativa."""
    prev_gross = float(prev_row["gross_revenue"])
    if prev_gross <= 0:
        return None, None, None, None, None, prev_gross

    prev_net = float(prev_row["net_revenue"])
    prev_cm = float(prev_row["contribution_margin"])
    prev_cm_pct = prev_cm / prev_gross * 100.0
    prev_custs = int(prev_row["active_customers"])

    return (
        round((cur_gross - prev_gross) / prev_gross * 100.0, 1),
        round((cur_net - prev_net) / prev_net * 100.0, 1) if prev_net > 0 else None,
        round((cur_cm - prev_cm) / prev_cm * 100.0, 1) if prev_cm > 0 else None,
        round(cur_cm_pct - prev_cm_pct, 1),
        round((cur_custs - prev_custs) / prev_custs * 100.0, 1) if prev_custs > 0 else None,
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
    cm_pct = round((cm / gross * 100.0), 2) if gross > 0 else 0.0
    orders, custs = int(row["total_orders"]), int(row["active_customers"])
    avg_ticket = round(gross / orders, 2) if orders > 0 else 0.0

    has_min_max = (
        "min_date_key" in row.index
        and "max_date_key" in row.index
        and pd.notna(row["min_date_key"])
        and pd.notna(row["max_date_key"])
    )
    if start_date_key is not None and end_date_key is not None:
        window_days = max((_key_to_date(end_date_key) - _key_to_date(start_date_key)).days + 1, 1)
    elif has_min_max:
        window_days = max(
            (_key_to_date(int(row["max_date_key"])) - _key_to_date(int(row["min_date_key"]))).days + 1,
            1,
        )
    else:
        window_days = 365

    gross_delta, net_delta, cm_delta, margin_delta_pp, cust_delta = None, None, None, None, None
    prev_gross = 0.0

    if start_date_key is not None and comp_start_date_key is not None and comp_end_date_key is not None:
        c_where, c_params, c_joins = build_filter_clauses(
            scenario_id,
            regiao=regiao,
            uf=uf,
            families=families,
            sales_reps=sales_reps,
            start_date_key=comp_start_date_key,
            end_date_key=comp_end_date_key,
        )
        c_df = query_raw_kpis(repo, c_where, c_params, c_joins)
        if not c_df.empty:
            gross_delta, net_delta, cm_delta, margin_delta_pp, cust_delta, prev_gross = _compute_deltas(
                cur_gross=gross,
                cur_net=net_rev,
                cur_cm=cm,
                cur_cm_pct=cm_pct,
                cur_custs=custs,
                prev_row=c_df.iloc[0],
            )
    elif start_date_key is None and end_date_key is None and comparison_mode == "yoy" and has_min_max:
        min_dt = _key_to_date(int(row["min_date_key"]))
        max_dt = _key_to_date(int(row["max_date_key"]))
        if max_dt.year > min_dt.year:
            cur_y_start = max_dt.year * 10000 + 101
            cur_y_end = int(row["max_date_key"])
            prev_y_start = (max_dt.year - 1) * 10000 + 101
            prev_y_end = int(_shift_year_back(max_dt).strftime("%Y%m%d"))
            cur_w, cur_p, cur_j = build_filter_clauses(
                scenario_id,
                regiao=regiao,
                uf=uf,
                families=families,
                sales_reps=sales_reps,
                start_date_key=cur_y_start,
                end_date_key=cur_y_end,
            )
            prev_w, prev_p, prev_j = build_filter_clauses(
                scenario_id,
                regiao=regiao,
                uf=uf,
                families=families,
                sales_reps=sales_reps,
                start_date_key=prev_y_start,
                end_date_key=prev_y_end,
            )
            cur_df = query_raw_kpis(repo, cur_w, cur_p, cur_j)
            prev_df = query_raw_kpis(repo, prev_w, prev_p, prev_j)
            if not cur_df.empty and not prev_df.empty:
                c0 = cur_df.iloc[0]
                cg, cn, cc = (
                    float(c0["gross_revenue"]),
                    float(c0["net_revenue"]),
                    float(c0["contribution_margin"]),
                )
                cc_pct = round((cc / cg * 100.0), 2) if cg > 0 else 0.0
                gross_delta, net_delta, cm_delta, margin_delta_pp, cust_delta, prev_gross = _compute_deltas(
                    cur_gross=cg,
                    cur_net=cn,
                    cur_cm=cc,
                    cur_cm_pct=cc_pct,
                    cur_custs=int(c0["active_customers"]),
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
        discount_amount=float(row["discount_amount"]),
        net_price_revenue=float(row["net_price_revenue"]),
        tax_amount=float(row["tax_amount"]),
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
        revenue_target_brl=target_rev,
        revenue_pacing_pct=pacing_pct,
        margin_target_pct=26.0,
        projected_quarter_revenue_brl=projected_rev,
    )
