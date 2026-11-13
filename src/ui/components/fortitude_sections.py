from __future__ import annotations

import pandas as pd
import streamlit as st

from src.services.dto import FortitudePageDTO
from src.ui.components.kpi_card import KpiAccent, render_kpi_card
from src.ui.components.prescription import render_prescription_box
from src.ui.formatting import format_brl


def _fmt_brl(val: object) -> str:
    if isinstance(val, (int, float)) and not pd.isna(val):
        return format_brl(float(val), compact=False, decimals=0)
    return "—"


def _fmt_pct(val: object) -> str:
    if isinstance(val, (int, float)) and not pd.isna(val):
        return f"{float(val):.1f}%"
    return "—"


def _fmt_ratio(val: object) -> str:
    if isinstance(val, (int, float)) and not pd.isna(val):
        return f"{float(val):.2f}x"
    return "—"


def render_fortitude_kpi_cards(dto: FortitudePageDTO) -> None:
    """Renderiza os 5 KPI Cards de solvência, break-even, ciclo, concentração e aging."""
    k = dto.kpis
    c1, c2, c3, c4, c5 = st.columns(5)

    with c1:
        runway_ok = k.cash_runway_months >= k.cash_reserve_target_months
        render_kpi_card(
            title="Runway de Caixa",
            value=f"{k.cash_runway_months:.1f} meses",
            subfooter_left=f"Reserva: {format_brl(k.cash_reserve_brl, compact=True, decimals=1)}",
            delta_html=(
                f"Meta: {k.cash_reserve_target_months:.1f}m"
                if runway_ok
                else f"Abaixo meta ({k.cash_reserve_target_months:.1f}m)"
            ),
            accent="green" if runway_ok else "red",
            help_text=(
                "Meses de cobertura dos custos fixos pela reserva operacional caso o faturamento zere "
                "(Reserva de Caixa / Custo Fixo Mensal)."
            ),
        )

    with c2:
        slack_days = max(0, 30 - k.breakeven_day_of_month)
        render_kpi_card(
            title="Break-Even Mensal",
            value=f"Dia {k.breakeven_day_of_month}",
            subfooter_left=f"Meta: {format_brl(k.breakeven_revenue_brl, compact=True, decimals=1)}/mês",
            delta_html=f"Folga operacional: {slack_days}d",
            accent="teal" if k.breakeven_day_of_month <= 22 else "brass",
            help_text=(
                "Dia do mês em que a Margem de Contribuição acumulada cobre 100% dos Custos Fixos "
                "(Custo Fixo / Margem % sobre Receita Bruta)."
            ),
        )

    with c3:
        ccc_accent: KpiAccent = (
            "red"
            if k.cash_conversion_cycle_days > 75.0
            else "brass"
            if k.cash_conversion_cycle_days > 50.0
            else "teal"
        )
        render_kpi_card(
            title="Ciclo Financeiro & NCG",
            value=f"{k.cash_conversion_cycle_days:.0f} dias",
            subfooter_left=f"NCG: {format_brl(k.ncg_brl, compact=True, decimals=2)}",
            delta_html=f"PME {k.pme_days:.0f}d + PMR {k.pmr_days:.0f}d - PMP {k.pmp_days:.0f}d",
            accent=ccc_accent,
            help_text=(
                "Diferença entre prazo de estoque + recebimento e prazo de fornecedores. "
                "NCG = (Receita Líquida Mensal / 30) x Ciclo Financeiro."
            ),
        )

    with c4:
        conc_high = k.top5_customers_share_pct > 35.0
        render_kpi_card(
            title="Concentração Top 5",
            value=f"{k.top5_customers_share_pct:.1f}%",
            subfooter_left=f"Top 10: {k.top10_customers_share_pct:.1f}%",
            delta_html=f"Top 2 fam.: {k.top2_families_share_pct:.1f}%",
            accent="brass" if conc_high else "teal",
            help_text=(
                "Percentual da receita líquida dos últimos 12 meses concentrado nos 5 maiores "
                "clientes. Acima de 35% eleva o risco de ruptura comercial."
            ),
        )

    with c5:
        risk_accent: KpiAccent = "red" if k.at_risk_portfolio_pct >= 20.0 else "brass"
        render_kpi_card(
            title="Carteira em Risco (>1,5x)",
            value=format_brl(k.at_risk_portfolio_brl, compact=True, decimals=1),
            subfooter_left=f"{k.at_risk_portfolio_pct:.1f}% da base",
            delta_html=f"{k.at_risk_customers_count} clientes em atraso",
            accent=risk_accent,
            help_text=(
                "Soma da receita anualizada de clientes cujo atraso de recompra ultrapassou 1,5x "
                "o ciclo médio histórico (buckets Risco 31-60d e Crítico >60d)."
            ),
        )


def render_aging_customers_table(dto: FortitudePageDTO) -> None:
    """Renderiza tabela compacta com clientes priorizados para cobrança/resgate."""
    df = dto.aging_customers_df
    if df.empty:
        st.info("Nenhum cliente encontrado no recorte atual.")
        return

    cols = [
        "customer_name",
        "sales_rep_name",
        "state",
        "aging_bucket",
        "delay_ratio",
        "recency_days",
        "revenue_12m_brl",
    ]
    view = df[cols].rename(
        columns={
            "customer_name": "Cliente",
            "sales_rep_name": "RCA",
            "state": "UF",
            "aging_bucket": "Estágio Aging",
            "delay_ratio": "Atraso",
            "recency_days": "Dias s/ Compra",
            "revenue_12m_brl": "Receita 12m",
        }
    )
    styled = view.style.format({"Atraso": _fmt_ratio, "Receita 12m": _fmt_brl})
    st.dataframe(styled, height=210, hide_index=True, use_container_width=True)


def render_concentration_tables(dto: FortitudePageDTO) -> None:
    """Renderiza ranking de concentração dos Top 20 clientes com Pareto acumulado."""
    df = dto.customer_concentration_df
    if df.empty:
        st.info("Sem histórico de vendas no recorte atual.")
        return

    cols = [
        "customer_name",
        "segment_size",
        "region",
        "revenue_12m_brl",
        "margin_12m_brl",
        "share_pct",
        "cum_share_pct",
    ]
    view = df[cols].rename(
        columns={
            "customer_name": "Cliente",
            "segment_size": "Porte",
            "region": "Região",
            "revenue_12m_brl": "Receita 12m",
            "margin_12m_brl": "Margem 12m",
            "share_pct": "% Base",
            "cum_share_pct": "% Acum.",
        }
    )
    styled = view.style.format(
        {
            "Receita 12m": _fmt_brl,
            "Margem 12m": _fmt_brl,
            "% Base": _fmt_pct,
            "% Acum.": _fmt_pct,
        }
    )
    st.dataframe(styled, height=210, hide_index=True, use_container_width=True)


def render_fortitude_verdict_section(dto: FortitudePageDTO) -> None:
    """Renderiza o Veredito da Fortaleza com impacto quantificado de liberação de NCG."""
    render_prescription_box(
        title=dto.prescription_title,
        recommendation_html=dto.prescription_html,
        impact_brl=dto.prescription_impact_brl,
        action_hint="Cada -10d no ciclo PME+PMR libera caixa imediato sem depender de bancos.",
        help_text=(
            "Simulação direta de desmobilização de Capital de Giro considerando 10 dias de redução "
            "combinada entre estoque excessivo (PME) e prazo concedido (PMR)."
        ),
    )
