from __future__ import annotations

import streamlit as st

from src.core.scenarios import load_scenario_config
from src.ui.cache import cached_fortitude_dashboard
from src.ui.components.fortitude_charts import (
    build_aging_buckets_chart,
    build_breakeven_curve_chart,
    build_concentration_chart,
    build_cycle_comparison_chart,
)
from src.ui.components.fortitude_sections import (
    render_aging_customers_table,
    render_concentration_tables,
    render_fortitude_kpi_cards,
    render_fortitude_verdict_section,
)
from src.ui.components.prescription import render_cockpit_header, section_header
from src.ui.formatting import format_brl
from src.ui.state import get_app_state


def render_page() -> None:
    """Renderiza a Página 2 — Fortaleza em formato Cockpit Z-Pattern (1080p sem scroll)."""
    state = get_app_state()
    scenario_cfg = load_scenario_config(state.scenario_id)
    theme_mode = state.theme_mode

    dto = cached_fortitude_dashboard(
        state.scenario_id,
        regiao=state.regiao,
        uf=state.uf,
        families=tuple(state.families),
        sales_reps=tuple(state.sales_reps),
    )

    # 1. Faixa 1 — Topo (Status em 5s): Cabeçalho Cockpit unificado + 5 KPI Cards
    k = dto.kpis
    render_cockpit_header(
        title="Fortaleza · Solvência & Resiliência do Caixa",
        subtitle=(
            f"{scenario_cfg.display_name} · Fat./Mês "
            f"{format_brl(k.monthly_gross_revenue_brl, compact=True, decimals=1)} · "
            f"Custo Fixo/Mês {format_brl(k.fixed_costs_monthly_brl, compact=True, decimals=1)}"
        ),
        virtue_badge="2. Fortaleza",
        headline_title=dto.headline_title,
        headline_text=dto.headline_text,
        period_badge=f"Janela 12m · {k.active_customers_count} clientes ativos",
        as_of_date_label=dto.as_of_date_label,
        help_text=(
            "Síntese da saúde de caixa: compara fôlego de reserva (Runway), dia do Ponto de Equilíbrio, "
            "Necessidade de Capital de Giro (NCG) e dependência dos maiores clientes."
        ),
    )
    render_fortitude_kpi_cards(dto)

    # 2. Faixa 2 — Meio (Diagnóstico Visual em 2 Colunas lado a lado)
    col_diag_left, col_diag_right = st.columns([1.0, 1.0])

    with col_diag_left:
        section_header(
            "Fôlego Financeiro & Equilíbrio",
            "Composição do Ciclo Financeiro (PME + PMR - PMP) e curva diária do Break-Even",
            help_text=(
                "Exibe quantos dias a operação financia entre estoque e recebimento antes da cobertura "
                "pelos fornecedores, e o dia exato do mês em que o lucro paga o custo fixo."
            ),
        )
        t_cycle, t_be = st.tabs(["Ciclo Financeiro (Dias)", "Break-Even Acumulado (Mês)"])
        with t_cycle:
            fig_cycle = build_cycle_comparison_chart(dto.cycle_components_df, theme_mode=theme_mode)
            st.plotly_chart(fig_cycle, use_container_width=True)
        with t_be:
            fig_be = build_breakeven_curve_chart(dto.breakeven_curve_df, dto.kpis, theme_mode=theme_mode)
            st.plotly_chart(fig_be, use_container_width=True)

    with col_diag_right:
        section_header(
            "Risco de Carteira & Concentração",
            "Exposição por faixa de atraso na recompra e dependência dos Top 10 clientes",
            help_text=(
                "Mapeia inadimplência latente (aging por atraso de ciclo) e o peso dos maiores "
                "compradores sobre o faturamento líquido dos últimos 12 meses."
            ),
        )
        t_aging, t_conc = st.tabs(["Aging de Carteira (Atraso)", "Pareto Top 10 Clientes"])
        with t_aging:
            fig_aging = build_aging_buckets_chart(dto.aging_buckets_df, theme_mode=theme_mode)
            st.plotly_chart(fig_aging, use_container_width=True)
        with t_conc:
            fig_conc = build_concentration_chart(dto.customer_concentration_df, theme_mode=theme_mode)
            st.plotly_chart(fig_conc, use_container_width=True)

    # 3. Faixa 3 — Base (Detalhamento & Ação em 2 Colunas lado a lado)
    col_act_left, col_act_right = st.columns([1.35, 1.0])

    with col_act_left:
        section_header(
            "Auditoria de Vencimentos & Pareto",
            "Listas operacionais com scroll interno para cobrança e blindagem comercial",
            help_text=(
                "Priorize a reativação ou cobrança preventiva nos clientes críticos e acompanhe a "
                "fatia acumulada da carteira nos 20 maiores clientes."
            ),
        )
        t_tbl_aging, t_tbl_pareto = st.tabs(
            [
                f"Carteira em Atraso ({dto.kpis.at_risk_customers_count} clientes)",
                "Concentração Pareto (Top 20)",
            ]
        )
        with t_tbl_aging:
            render_aging_customers_table(dto)
        with t_tbl_pareto:
            render_concentration_tables(dto)

    with col_act_right:
        section_header(
            "Veredito da Fortaleza",
            "Plano prescritivo para reduzir NCG e fortalecer a reserva de caixa",
            help_text="Simulação imediata de liberação de caixa operacional via ajuste de ciclo.",
        )
        render_fortitude_verdict_section(dto)


render_page()
