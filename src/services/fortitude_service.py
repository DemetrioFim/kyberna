from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

import numpy as np
import pandas as pd

from src.core.logging import get_logger
from src.core.types import ScenarioId
from src.db.repository import DataRepository
from src.etl.gold.inventory_snapshot import load_working_capital_config
from src.services.dto import FortitudeKpisDTO, FortitudePageDTO
from src.services.fortitude_metrics import (
    compute_fortitude_period_deltas,
    compute_fortitude_window_snapshot,
)
from src.services.fortitude_queries import (
    query_aging_buckets_and_customers,
    query_pme_weighted,
)
from src.services.period_comparison import resolve_effective_comparison_window
from src.ui.formatting import format_brl

logger = get_logger(__name__)

__all__ = [
    "build_breakeven_curve_df",
    "build_cycle_components_df",
    "build_fortitude_dashboard",
    "build_fortitude_headline",
    "build_fortitude_prescription",
]


def build_breakeven_curve_df(
    monthly_gross_revenue_brl: float,
    monthly_contribution_margin_brl: float,
    fixed_costs_monthly_brl: float,
) -> pd.DataFrame:
    """Constrói a trajetória diária (dias 1..30) de cobertura dos custos fixos mensais."""
    days = np.arange(1, 31, dtype=int)
    daily_gross = monthly_gross_revenue_brl / 30.0
    daily_cm = monthly_contribution_margin_brl / 30.0
    cum_rev = np.round(daily_gross * days, 2)
    cum_cm = np.round(daily_cm * days, 2)
    fixed_line = np.full(30, round(fixed_costs_monthly_brl, 2))
    return pd.DataFrame(
        {
            "day_of_month": days,
            "cum_revenue_brl": cum_rev,
            "cum_contribution_margin_brl": cum_cm,
            "fixed_cost_line_brl": fixed_line,
            "is_breakeven_reached": cum_cm >= fixed_line,
        }
    )


def build_cycle_components_df(
    pme_days: float,
    pmr_days: float,
    pmp_days: float,
    ccc_days: float,
) -> pd.DataFrame:
    """Estrutura os pilares do Ciclo de Conversão de Caixa para gráfico waterfall."""
    return pd.DataFrame(
        [
            {
                "component": "PME (Estoque)",
                "days": round(pme_days, 1),
                "display_days": round(pme_days, 1),
                "measure": "relative",
                "direction": "Aplicação (+)",
            },
            {
                "component": "PMR (Clientes)",
                "days": round(pmr_days, 1),
                "display_days": round(pmr_days, 1),
                "measure": "relative",
                "direction": "Aplicação (+)",
            },
            {
                "component": "PMP (Fornecedores)",
                "days": round(-pmp_days, 1),
                "display_days": round(pmp_days, 1),
                "measure": "relative",
                "direction": "Financiamento (-)",
            },
            {
                "component": "Ciclo Financeiro",
                "days": round(ccc_days, 1),
                "display_days": round(ccc_days, 1),
                "measure": "total",
                "direction": "NCG (=)",
            },
        ]
    )


def build_fortitude_headline(kpis: FortitudeKpisDTO) -> tuple[str, str]:
    """Gera a manchete executiva dinâmica de solvência e capital de giro."""
    ncg_str = format_brl(kpis.ncg_brl, compact=True, decimals=2)
    be_str = format_brl(kpis.breakeven_revenue_brl, compact=True, decimals=1)

    if kpis.monthly_gross_revenue_brl <= 0.0:
        return (
            "Justiça Financeira · Recorte sem movimentação nos últimos 12 meses",
            "Nenhuma venda faturada encontrada para a combinação de filtros atual. "
            "Amplie a seleção regional ou de famílias para mensurar o ciclo financeiro.",
        )

    if kpis.cash_runway_months < kpis.cash_reserve_target_months:
        title = (
            f"Alerta de Liquidez · Runway de {kpis.cash_runway_months:.1f} meses "
            f"(abaixo da meta de {kpis.cash_reserve_target_months:.1f} meses)"
        )
    elif kpis.cash_conversion_cycle_days > 70.0:
        title = (
            f"Pressão no Capital de Giro · Ciclo Financeiro de {kpis.cash_conversion_cycle_days:.0f} dias "
            f"imobiliza {ncg_str} em NCG"
        )
    else:
        title = (
            f"Solvência Saudável · Ponto de Equilíbrio no dia {kpis.breakeven_day_of_month} "
            f"e Runway de {kpis.cash_runway_months:.1f} meses"
        )

    text = (
        f"A operação financia <b>{kpis.cash_conversion_cycle_days:.1f} dias</b> de ciclo "
        f"(<b>PME {kpis.pme_days:.0f}d + PMR {kpis.pmr_days:.0f}d - PMP {kpis.pmp_days:.0f}d</b>), "
        f"exigindo <b>{ncg_str}</b> em Necessidade de Capital de Giro. O Ponto de Equilíbrio mensal é "
        f"<b>{be_str}</b> (atingido no <b>dia {kpis.breakeven_day_of_month}</b>) e os Top 5 clientes "
        f"concentram <b>{kpis.top5_customers_share_pct:.1f}%</b> da receita."
    )
    return title, text


def build_fortitude_prescription(kpis: FortitudeKpisDTO) -> tuple[str, str, float | None]:
    """Elabora a prescrição acionável quantificada para liberar caixa e blindar liquidez."""
    if kpis.monthly_gross_revenue_brl <= 0.0:
        return (
            "Sem Recomendações de Liquidez para o Recorte Vazio",
            "<p>Ajuste os filtros laterais para visualizar alavancas de NCG e proteção de caixa.</p>",
            None,
        )

    daily_net = kpis.monthly_net_revenue_brl / 30.0
    ncg_release_10d = max(0.0, daily_net * 10.0)
    top5_risk_level = "Elevada (> 35%)" if kpis.top5_customers_share_pct > 35.0 else "Controlada (≤ 35%)"

    title = "Veredito de Justiça Financeira: Blindagem de Caixa e Redução da NCG"
    html = (
        f"<p>Cada <b>10 dias</b> reduzidos entre estoque excessivo (PME {kpis.pme_days:.0f}d) e "
        f"dilatação de prazo comercial (PMR {kpis.pmr_days:.0f}d) liberam "
        f"<b>{format_brl(ncg_release_10d)}</b> diretamente para o caixa livre.</p>"
        "<ul style='margin-left: 18px; line-height: 1.55;'>"
        f"<li><b>Encurtamento do PMR ({kpis.pmr_days:.0f}d):</b> Travar prazos acima de 42d para pedidos "
        "sem aprovação e priorizar boletos com vencimento escalonado na carteira recorrente.</li>"
        f"<li><b>Desmobilização de Estoque (PME {kpis.pme_days:.0f}d):</b> Suspender compras dos SKUs Z "
        "acima de 120d de cobertura para financiar a folga do Break-Even "
        f"(atual no <b>dia {kpis.breakeven_day_of_month}</b>).</li>"
        f"<li><b>Diversificação e Cobrança:</b> Concentração Top 5 está <b>{top5_risk_level}</b> "
        f"({kpis.top5_customers_share_pct:.1f}%), com <b>{format_brl(kpis.at_risk_portfolio_brl)}</b> "
        f"({kpis.at_risk_customers_count} clientes) em atraso superior a 1,5x o ciclo.</li>"
        "</ul>"
    )
    return title, html, round(ncg_release_10d, 2)


def build_fortitude_dashboard(
    repo: DataRepository,
    scenario_id: ScenarioId,
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
    comparison_label: str = "Histórico Global Consolidado",
) -> FortitudePageDTO:
    """Agrega métricas de solvência, ciclo financeiro, break-even e aging para a Tela 2."""
    wc_cfg = load_working_capital_config(scenario_id)
    fixed_cost_pct = float(wc_cfg.get("fixed_cost_pct", 0.14))
    pmp_days = round(float(wc_cfg.get("pmp", 35.0)), 1)
    reserve_target_months = float(wc_cfg.get("cash_reserve_months_target", 3.5))
    raw_pmr_map = wc_cfg.get("pmr_days_by_size", {"P": 28, "M": 42, "G": 56})
    pmr_by_size = {str(k): float(v) for k, v in dict(raw_pmr_map).items()}
    extra_pmr_days = float(wc_cfg.get("high_discount_rep_extra_pmr_days", 18.0))
    pme_days = round(query_pme_weighted(repo, scenario_id, families=families), 1)

    core, cust_conc_df, fam_conc_df = compute_fortitude_window_snapshot(
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
        start_date_key=start_date_key,
        end_date_key=end_date_key,
    )
    aging_buckets_df, aging_customers_df = query_aging_buckets_and_customers(
        repo,
        scenario_id,
        regiao=regiao,
        uf=uf,
        sales_reps=sales_reps,
        families=families,
        start_date_key=start_date_key,
        end_date_key=end_date_key,
    )

    total_aging_rev = float(aging_buckets_df["revenue_12m_brl"].sum())
    risk_rows = aging_buckets_df[aging_buckets_df["bucket_order"] >= 3]
    at_risk_brl = round(float(risk_rows["revenue_12m_brl"].sum()), 2)
    at_risk_count = int(risk_rows["customers_count"].sum())
    at_risk_pct = round((at_risk_brl / total_aging_rev * 100.0) if total_aging_rev > 0 else 0.0, 1)

    deltas: dict[str, float | None] = {}
    win = resolve_effective_comparison_window(
        repo,
        scenario_id,
        start_date_key=start_date_key,
        end_date_key=end_date_key,
        comp_start_date_key=comp_start_date_key,
        comp_end_date_key=comp_end_date_key,
        comparison_mode=comparison_mode,
    )
    if win is not None:
        deltas = compute_fortitude_period_deltas(
            repo,
            scenario_id,
            win,
            cur_core=core if start_date_key is not None else None,
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
        )

    kpis = FortitudeKpisDTO(
        cash_reserve_brl=core["cash_reserve_brl"],
        cash_runway_months=core["cash_runway_months"],
        cash_reserve_target_months=reserve_target_months,
        fixed_costs_monthly_brl=core["fixed_costs_monthly"],
        monthly_gross_revenue_brl=round(core["monthly_gross"], 2),
        monthly_net_revenue_brl=round(core["monthly_net"], 2),
        monthly_contribution_margin_brl=round(core["monthly_cm"], 2),
        free_cash_generation_brl=core["free_cash_generation"],
        margin_pct_of_gross=core["margin_pct_gross"],
        margin_pct_of_net=core["margin_pct_net"],
        breakeven_revenue_brl=core["breakeven_rev"],
        breakeven_day_of_month=core["breakeven_day"],
        pme_days=pme_days,
        pmr_days=core["pmr_days"],
        pmp_days=pmp_days,
        cash_conversion_cycle_days=core["ccc_days"],
        ncg_brl=core["ncg_brl"],
        top5_customers_share_pct=core["top5_share"],
        top10_customers_share_pct=core["top10_share"],
        top2_families_share_pct=core["top2_fam_share"],
        active_customers_count=core["active_customers_count"],
        at_risk_portfolio_brl=at_risk_brl,
        at_risk_portfolio_pct=at_risk_pct,
        at_risk_customers_count=at_risk_count,
        runway_delta_months=deltas.get("runway_delta_months"),
        breakeven_revenue_delta_pct=deltas.get("breakeven_revenue_delta_pct"),
        ccc_delta_days=deltas.get("ccc_delta_days"),
        ncg_delta_pct=deltas.get("ncg_delta_pct"),
        top10_share_delta_pp=deltas.get("top10_share_delta_pp"),
    )

    headline_title, headline_text = build_fortitude_headline(kpis)
    rx_title, rx_html, rx_impact = build_fortitude_prescription(kpis)

    return FortitudePageDTO(
        scenario_id=scenario_id,
        kpis=kpis,
        headline_title=headline_title,
        headline_text=headline_text,
        breakeven_curve_df=build_breakeven_curve_df(
            core["monthly_gross"],
            core["monthly_cm"],
            core["fixed_costs_monthly"],
        ),
        cycle_components_df=build_cycle_components_df(
            pme_days,
            core["pmr_days"],
            pmp_days,
            core["ccc_days"],
        ),
        customer_concentration_df=cust_conc_df,
        family_concentration_df=fam_conc_df,
        aging_buckets_df=aging_buckets_df,
        aging_customers_df=aging_customers_df,
        prescription_title=rx_title,
        prescription_html=rx_html,
        prescription_impact_brl=rx_impact,
        comparison_label=comparison_label,
    )
