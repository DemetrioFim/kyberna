from __future__ import annotations

from collections.abc import Sequence

from src.core.types import ScenarioId
from src.db.repository import DataRepository
from src.services.dto import ExecutiveKpisDTO
from src.services.executive_queries import (
    build_filter_clauses,
    query_raw_kpis,
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

    c_start, c_end = comp_start_date_key, comp_end_date_key
    if c_start is None and start_date_key is None:
        c_start, c_end = 20230101, 20231231

    gross_delta, net_delta, cm_delta, margin_delta_pp, cust_delta = None, None, None, None, None
    prev_gross = 0.0

    if c_start is not None and c_end is not None:
        c_where, c_params, c_joins = build_filter_clauses(
            scenario_id,
            regiao=regiao,
            uf=uf,
            families=families,
            sales_reps=sales_reps,
            start_date_key=c_start,
            end_date_key=c_end,
        )
        c_df = query_raw_kpis(repo, c_where, c_params, c_joins)
        if not c_df.empty:
            c_row = c_df.iloc[0]
            prev_gross = float(c_row["gross_revenue"])
            prev_net, prev_cm = float(c_row["net_revenue"]), float(c_row["contribution_margin"])
            prev_cm_pct = (prev_cm / prev_gross * 100.0) if prev_gross > 0 else 0.0
            prev_custs = int(c_row["active_customers"])

            if prev_gross > 0:
                gross_delta = round((gross - prev_gross) / prev_gross * 100.0, 1)
                net_delta = round((net_rev - prev_net) / prev_net * 100.0, 1) if prev_net > 0 else None
                cm_delta = round((cm - prev_cm) / prev_cm * 100.0, 1) if prev_cm > 0 else None
                margin_delta_pp = round(cm_pct - prev_cm_pct, 1)
                cust_delta = round((custs - prev_custs) / prev_custs * 100.0, 1) if prev_custs > 0 else None

    target_rev = round(prev_gross * 1.08, 2) if prev_gross > 0 else round(gross * 1.05, 2)
    pacing_pct = round(gross / max(target_rev, 1.0) * 100.0, 1)
    projected_rev = round(gross * (1.0 + (gross_delta or 2.0) / 100.0), 2)

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
