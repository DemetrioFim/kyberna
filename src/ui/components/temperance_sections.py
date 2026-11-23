from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.services.dto import (
    CommercialPageDTO,
    ExecutivePageDTO,
    FortitudePageDTO,
    TemperancePageDTO,
)
from src.services.inventory_dto import InventoryPageDTO
from src.ui.components.kpi_card import KpiAccent, render_kpi_card
from src.ui.components.prescription import render_prescription_box
from src.ui.formatting import format_brl, format_int
from src.ui.theme import get_theme_tokens


def _fmt_brl(x: object) -> str:
    return format_brl(float(str(x)))


def _fmt_pct(x: object) -> str:
    return f"{float(str(x)):.1f}%"


def _fmt_int(x: object) -> str:
    return format_int(int(float(str(x))))


def render_temperance_kpi_cards(
    dto: TemperancePageDTO,
    inv_dto: InventoryPageDTO | None = None,
) -> None:
    """Renderiza os 5 KPI Cards de disciplina comercial e estoques."""
    kpis = dto.kpis
    c1, c2, c3, c4, c5 = st.columns(5)

    with c1:
        render_kpi_card(
            title="Erosão Comercial Total",
            value=format_brl(kpis.total_commercial_erosion_brl, compact=True, decimals=1),
            subfooter_left=f"Sangria: {kpis.total_commercial_erosion_pct:.1f}% da receita",
            accent="alert_warn",
            help_text="Deduções entre faturamento bruto e lucro: descontos, comissões de RCAs e frete CIF.",
        )

    with c2:
        render_kpi_card(
            title="Descontos Fora de Tabela",
            value=format_brl(kpis.excess_discount_brl, compact=True, decimals=1),
            subfooter_left=f"{kpis.excess_discount_pct_of_discount:.1f}% dos descontos",
            accent="alert_neg",
            help_text="Concedido acima do teto estipulado por porte (P=3%, M=6.5%, G=10.5%).",
        )

    with c3:
        render_kpi_card(
            title="Custo de Prazo Esticado",
            value=format_brl(kpis.financial_term_leak_brl, compact=True, decimals=1),
            subfooter_left="Prazo > 30 dias (1,35% a.m.)",
            accent="brass",
            help_text="Custo de carregamento financeiro de boletos esticados além do padrão de 30 dias.",
        )

    with c4:
        render_kpi_card(
            title="Capital Travado (>120d)",
            value=format_brl(kpis.locked_capital_brl, compact=True, decimals=1),
            subfooter_left=f"{kpis.locked_skus_count} SKUs parados",
            accent="gold",
            help_text="Valor contábil a custo de SKUs com cobertura de vendas > 120 dias.",
        )

    with c5:
        rup_skus_a = (
            inv_dto.kpis.stockout_curve_a_skus_count
            if inv_dto is not None and inv_dto.kpis.stockout_curve_a_skus_count > 0
            else kpis.stockout_risk_skus_count
        )
        rup_rev = (
            inv_dto.kpis.stockout_curve_a_revenue_brl
            if inv_dto is not None and inv_dto.kpis.stockout_curve_a_revenue_brl > 0.0
            else kpis.stockout_risk_revenue_brl
        )
        render_kpi_card(
            title="Ruptura Iminente (Curva A)",
            value=f"{rup_skus_a} SKUs",
            subfooter_left=f"Risco: {format_brl(rup_rev, compact=True, decimals=1)}",
            accent="alert_neg",
            help_text="SKUs Curva A com cobertura abaixo do ponto de pedido (lead time + SS).",
        )


def render_temperance_mix_kpis(
    exec_dto: ExecutivePageDTO,
    fort_dto: FortitudePageDTO,
    comm_dto: CommercialPageDTO,
    temp_dto: TemperancePageDTO,
    inv_dto: InventoryPageDTO,
    *,
    is_scoped: bool = False,
) -> None:
    """Renderiza os 5 KPIs integrados 360 (Financeiro + Comercial + Admin) da Aba 1."""
    ek = exec_dto.kpis
    fk = fort_dto.kpis
    ck = comm_dto.kpis
    tk = temp_dto.kpis
    ik = inv_dto.kpis
    rup_skus_a = (
        ik.stockout_curve_a_skus_count if ik.stockout_curve_a_skus_count > 0 else tk.stockout_risk_skus_count
    )
    scope_suffix = " · Global" if is_scoped else ""

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        m_acc: KpiAccent = "alert_warn" if ek.contribution_margin_pct < ek.margin_target_pct else "green"
        render_kpi_card(
            title="[Finanças] Margem Líquida",
            value=format_brl(ek.contribution_margin, compact=True),
            subfooter_left=f"{ek.contribution_margin_pct:.1f}% vs. Meta {ek.margin_target_pct:.1f}%",
            accent=m_acc,
            help_text="Resultado financeiro líquido após descontos, tributos, CMV, comissões e frete.",
        )
    with c2:
        ccc_acc: KpiAccent = "alert_neg" if fk.cash_conversion_cycle_days > 75.0 else "teal"
        render_kpi_card(
            title="[Finanças] Ciclo & NCG",
            value=f"{fk.cash_conversion_cycle_days:.0f} dias",
            subfooter_left=f"NCG: {format_brl(fk.ncg_brl, compact=True, decimals=1)}",
            accent=ccc_acc,
            help_text="Ciclo Financeiro (PME + PMR - PMP) e Necessidade de Capital de Giro.",
        )
    with c3:
        render_kpi_card(
            title="[Comercial] Risco vs. Mix",
            value=format_brl(ck.annual_revenue_at_risk_brl, compact=True),
            subfooter_left=f"White Space: +{format_brl(ck.white_space_potential_revenue_brl, compact=True)}",
            accent="alert_warn",
            help_text="Contrapõe a receita em risco de evasão ao potencial incremental de cross-sell.",
        )
    with c4:
        render_kpi_card(
            title="[Admin] Capital Travado",
            value=format_brl(tk.locked_capital_brl, compact=True, decimals=1),
            subfooter_left=f"Ruptura Curva A: {rup_skus_a} SKUs{scope_suffix}",
            accent="gold",
            help_text=(
                "Capital excedente parado em estoque >120d confrontado com SKUs Curva A em ruptura iminente "
                "(posição corporativa do armazém)."
            ),
        )
    with c5:
        rec_val = (
            temp_dto.prescription_impact_brl
            if temp_dto.prescription_impact_brl is not None
            else tk.excess_discount_brl
        )
        render_kpi_card(
            title="[Síntese] Ganho Recuperável",
            value=format_brl(rec_val, compact=True, decimals=1),
            subfooter_left=(
                f"Fora teto: {format_brl(tk.excess_discount_brl, compact=True, decimals=1)} · "
                f"Deduções: {format_brl(tk.total_commercial_erosion_brl, compact=True, decimals=1)}"
            ),
            accent="alert_neg",
            help_text=(
                "Ganho imediato reconciliado com o Veredito Integrado (estancamento de descontos "
                "acima do teto de política + liquidação parcial de estoque parado >120d)."
            ),
        )


def render_champions_vampires_kpis(
    exec_dto: ExecutivePageDTO,
    temp_dto: TemperancePageDTO,
    customer_plural: str,
) -> None:
    """Renderiza os 5 KPIs da Aba 3 (Matriz Campeões vs. Vampiros 360) de Temperança."""
    prod_gen_sum = (
        float(exec_dto.top_generators_df["contribution_margin"].sum())
        if not exec_dto.top_generators_df.empty
        else 0.0
    )
    prod_dest_sum = (
        float(exec_dto.top_destroyers_df["contribution_margin"].sum())
        if not exec_dto.top_destroyers_df.empty
        else 0.0
    )
    cust_gen_sum = (
        float(exec_dto.top_customer_generators_df["contribution_margin"].sum())
        if not exec_dto.top_customer_generators_df.empty
        else 0.0
    )
    cust_dest_sum = (
        float(exec_dto.top_customer_destroyers_df["contribution_margin"].sum())
        if not exec_dto.top_customer_destroyers_df.empty
        else 0.0
    )
    prod_dest_disc = (
        float(exec_dto.top_destroyers_df["discount_pct"].mean())
        if not exec_dto.top_destroyers_df.empty
        else 0.0
    )
    cust_dest_disc = (
        float(exec_dto.top_customer_destroyers_df["discount_pct"].mean())
        if not exec_dto.top_customer_destroyers_df.empty
        else 0.0
    )

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        render_kpi_card(
            title="Top 10 SKUs Campeões",
            value=format_brl(prod_gen_sum, compact=True),
            subfooter_left="Maior geração absoluta de lucro",
            accent="green",
            help_text="Margem de contribuição somada pelos 10 SKUs mais rentáveis.",
        )
    with c2:
        render_kpi_card(
            title="Top 10 SKUs Vampiros",
            value=format_brl(prod_dest_sum, compact=True),
            subfooter_left=f"Desc. médio: {prod_dest_disc:.1f}%",
            accent="alert_warn",
            help_text="SKUs com menor ou pior eficiência de margem após descontos e frete.",
        )
    with c3:
        render_kpi_card(
            title=f"Top 10 {customer_plural} Campeões",
            value=format_brl(cust_gen_sum, compact=True),
            subfooter_left="Contas âncora de rentabilidade",
            accent="teal",
            help_text="Margem líquida gerada pelas 10 contas mais lucrativas da carteira.",
        )
    with c4:
        render_kpi_card(
            title=f"Top 10 {customer_plural} Vampiros",
            value=format_brl(cust_dest_sum, compact=True),
            subfooter_left=f"Desc. médio: {cust_dest_disc:.1f}%",
            accent="alert_neg",
            help_text="Contas que concentram descontos elevados ou destruição de margem.",
        )
    with c5:
        render_kpi_card(
            title="Descontos Fora de Tabela",
            value=format_brl(temp_dto.kpis.excess_discount_brl, compact=True, decimals=1),
            subfooter_left=f"{temp_dto.kpis.excess_discount_pct_of_discount:.1f}% do total",
            accent="alert_neg",
            help_text="Parcela dos descontos concedidos acima das alçadas definidas por porte.",
        )


def render_violations_rep_chart(df: pd.DataFrame, theme_mode: str) -> go.Figure:
    """Gera gráfico de barras horizontais com o ranking de excesso de desconto por RCA."""
    tokens = get_theme_tokens(theme_mode)
    template_name = "kyberna_dark" if theme_mode == "dark" else "kyberna_light"

    if df.empty:
        fig = go.Figure()
        fig.update_layout(template=template_name, title="Sem dados de violação", height=245)
        return fig

    top_df = df.head(8).iloc[::-1]
    fig = go.Figure(
        go.Bar(
            x=top_df["excess_discount_brl"].tolist(),
            y=top_df["rep_name"].tolist(),
            orientation="h",
            marker_color=tokens["negative"],
            text=[format_brl(float(v), compact=True, decimals=1) for v in top_df["excess_discount_brl"]],
            textposition="outside",
            cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>Excesso Fora do Teto: R$ %{x:,.2f}<extra></extra>",
        )
    )
    max_x = max(float(top_df["excess_discount_brl"].max()) * 1.25, 1.0)
    fig.update_layout(
        template=template_name,
        title=None,
        xaxis={"title": None, "range": [0, max_x], "automargin": True},
        yaxis={"title": None, "automargin": True},
        margin={"l": 20, "r": 24, "t": 10, "b": 15},
        height=245,
    )
    return fig


def render_rep_policy_violations_table(dto: TemperancePageDTO) -> None:
    """Renderiza tabela direta de auditoria de desvios por representante (sem sub-abas)."""
    if dto.policy_violations_by_rep_df.empty:
        st.info("Nenhuma violação de política identificada para a seleção atual.")
        return
    cols_show = ["rep_name", "total_orders", "gross_revenue", "avg_discount_pct", "excess_discount_brl"]
    df_rep_table = dto.policy_violations_by_rep_df[
        [c for c in cols_show if c in dto.policy_violations_by_rep_df.columns]
    ].copy()
    df_rep_table.columns = [
        "Representante",
        "Pedidos",
        "Faturamento (R$)",
        "Desc. Médio %",
        "Excesso Fora do Teto (R$)",
    ]
    st.dataframe(
        df_rep_table.head(10).style.format(
            {
                "Faturamento (R$)": _fmt_brl,
                "Desc. Médio %": _fmt_pct,
                "Excesso Fora do Teto (R$)": _fmt_brl,
                "Pedidos": _fmt_int,
            }
        ),
        use_container_width=True,
        hide_index=True,
        height=185,
    )


def render_temperance_verdict_section(dto: TemperancePageDTO) -> None:
    """Renderiza a caixa estilizada do veredito executivo e impacto financeiro quantificado."""
    render_prescription_box(
        title=dto.prescription_title,
        recommendation_html=dto.prescription_html,
        impact_brl=dto.prescription_impact_brl,
        help_text=(
            "Impacto calculado como a soma da liberação de capital em estoque parado (>120d) "
            "e da estancagem de descontos acima da tabela."
        ),
    )
