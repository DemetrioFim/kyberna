from __future__ import annotations

import streamlit as st

from src.services.dto import FortitudePageDTO, TemperancePageDTO
from src.ui.components.kpi_card import KpiAccent, render_kpi_card
from src.ui.components.prescription import render_prescription_box
from src.ui.formatting import fmt_brl_cell, fmt_pct_cell, format_brl, get_delta_html


def _style_aging_stage(val: object) -> str:
    """Destaca severidade do estagio de atraso com cor de fundo suave."""
    txt = str(val)
    if "Crítico" in txt:
        return "background-color: rgba(209, 73, 91, 0.14); color: #D1495B; font-weight: 600;"
    if "Risco" in txt or "Atenção" in txt:
        return "background-color: rgba(229, 159, 58, 0.16); color: #B45309; font-weight: 600;"
    return ""


def render_fortitude_kpi_cards(
    dto: FortitudePageDTO,
    *,
    temp_dto: TemperancePageDTO | None = None,
) -> None:
    """Renderiza os 5 KPI Cards de solvência, break-even, ciclo, prazo e concentração."""
    k = dto.kpis
    term_leak = temp_dto.kpis.financial_term_leak_brl if temp_dto is not None else 0.0
    c1, c2, c3, c4, c5 = st.columns(5)

    with c1:
        runway_ok = k.cash_runway_months >= k.cash_reserve_target_months
        render_kpi_card(
            title="Runway de Caixa",
            value=f"{k.cash_runway_months:.1f} meses",
            subfooter_left=(
                f"Reserva: {format_brl(k.cash_reserve_brl, compact=True, decimals=1)} · "
                f"Meta {k.cash_reserve_target_months:.1f}m"
            ),
            delta_html=get_delta_html(k.runway_delta_months, kind="float", label_suffix="m"),
            accent="green" if runway_ok else "alert_neg",
            help_text=(
                "Meses de cobertura dos custos fixos pela reserva operacional caso o faturamento zere "
                "(Reserva de Caixa / Custo Fixo Mensal)."
            ),
        )

    with c2:
        render_kpi_card(
            title="Break-Even Mensal",
            value=f"Dia {k.breakeven_day_of_month}",
            subfooter_left=(
                f"Fat. mín.: {format_brl(k.breakeven_revenue_brl, compact=True, decimals=1)} | "
                f"Fixo: {format_brl(k.fixed_costs_monthly_brl, compact=True, decimals=1)}"
            ),
            delta_html=get_delta_html(k.breakeven_revenue_delta_pct, kind="pct", invert_color=True),
            accent="teal" if k.breakeven_day_of_month <= 22 else "alert_warn",
            help_text=(
                "Dia do mês em que a Margem de Contribuição acumulada cobre 100% dos Custos Fixos "
                "(Custo Fixo / Margem % sobre Receita Bruta)."
            ),
        )

    with c3:
        ccc_accent: KpiAccent = (
            "alert_neg"
            if k.cash_conversion_cycle_days > 75.0
            else "alert_warn"
            if k.cash_conversion_cycle_days > 50.0
            else "teal"
        )
        render_kpi_card(
            title="Ciclo Financeiro & NCG",
            value=f"{k.cash_conversion_cycle_days:.0f} dias",
            subfooter_left=f"NCG: {format_brl(k.ncg_brl, compact=True, decimals=2)}",
            delta_html=get_delta_html(k.ccc_delta_days, kind="float", invert_color=True, label_suffix="d"),
            accent=ccc_accent,
            help_text=(
                f"PME {k.pme_days:.0f}d + PMR {k.pmr_days:.0f}d - PMP {k.pmp_days:.0f}d. "
                "NCG = (Receita Líquida Mensal / 30) x Ciclo Financeiro."
            ),
        )

    with c4:
        term_delta = temp_dto.kpis.financial_term_leak_delta_pct if temp_dto is not None else None
        render_kpi_card(
            title="Custo Financeiro de Prazo",
            value=format_brl(term_leak, compact=True, decimals=1),
            subfooter_left="Prazo > 30d (1,35% a.m.)",
            delta_html=get_delta_html(term_delta, kind="pct", invert_color=True),
            accent="alert_warn" if term_leak > 0 else "green",
            help_text=("Custo financeiro implícito de carregar duplicatas acima do prazo padrão de 30 dias."),
        )

    with c5:
        conc_high = k.top5_customers_share_pct > 35.0
        render_kpi_card(
            title="Concentração Top 10",
            value=f"{k.top10_customers_share_pct:.1f}%",
            subfooter_left=(
                f"Top 5: {k.top5_customers_share_pct:.1f}% · Top 2 fam.: {k.top2_families_share_pct:.1f}%"
            ),
            delta_html=get_delta_html(k.top10_share_delta_pp, kind="pp", invert_color=True),
            accent="alert_warn" if conc_high else "teal",
            help_text=(
                "Percentual da receita líquida concentrado nos 10 maiores clientes "
                "(e nos 5 maiores / 2 maiores famílias no rodapé)."
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
    styled = view.style.map(_style_aging_stage, subset=["Estágio Aging"]).format(
        {
            "Atraso": lambda v: f"{float(str(v)):.2f}x",
            "Dias s/ Compra": lambda v: f"{int(float(str(v)))} d",
            "Receita 12m": lambda v: fmt_brl_cell(v, decimals=0),
        }
    )
    st.dataframe(
        styled,
        height=185,
        hide_index=True,
        use_container_width=True,
        column_config={"UF": st.column_config.TextColumn("UF", width="small")},
    )


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
    st.dataframe(
        view.style.format(
            {
                "Receita 12m": lambda v: fmt_brl_cell(v, decimals=0),
                "Margem 12m": lambda v: fmt_brl_cell(v, decimals=0),
                "% Base": fmt_pct_cell,
                "% Acum.": fmt_pct_cell,
            }
        ),
        height=185,
        hide_index=True,
        use_container_width=True,
        column_config={"Porte": st.column_config.TextColumn("Porte", width="small")},
    )


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
