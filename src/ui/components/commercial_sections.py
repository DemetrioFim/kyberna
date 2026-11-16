from __future__ import annotations

import streamlit as st

from src.services.dto import CommercialPageDTO, TemperancePageDTO
from src.ui.components.kpi_card import render_kpi_card
from src.ui.formatting import format_brl, format_int


def render_commercial_cross_sell_kpis(comm_dto: CommercialPageDTO) -> None:
    """Renderiza os 5 KPIs da Aba 1 (Cross-Sell & Mix — Modelo Apriori) de Fortaleza."""
    k = comm_dto.kpis
    deals_df = comm_dto.top_white_space_deals_df
    n_deals = len(deals_df)
    unique_cust = (
        int(deals_df["customer_name"].nunique())
        if not deals_df.empty and "customer_name" in deals_df.columns
        else n_deals
    )

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        render_kpi_card(
            title="Oportunidade White Space",
            value=format_brl(k.white_space_potential_revenue_brl, compact=True),
            subfooter_left="Potencial anual de expansão",
            accent="teal",
            help_text=(
                "Receita incremental mapeada pelo modelo Apriori (cestas frequentes) e cluster "
                "Lookalike para famílias ausentes nos clientes."
            ),
        )
    with c2:
        render_kpi_card(
            title="Margem Incremental Estimada",
            value=format_brl(k.white_space_potential_margin_brl, compact=True),
            subfooter_left="Lucro líquido potencial",
            accent="green",
            help_text="Contribuição líquida estimada ao capturar as recomendações de mix.",
        )
    with c3:
        render_kpi_card(
            title="Lojas com Oferta Prioritária",
            value=f"{format_int(unique_cust)} lojas",
            subfooter_left=f"{format_int(n_deals)} pitches prontos",
            accent="brass",
            help_text="Quantidade de lojas com recomendação acionável imediata no pipeline White Space.",
        )
    with c4:
        render_kpi_card(
            title="Positivação de Carteira",
            value=f"{k.avg_positivation_pct:.1f}%",
            subfooter_left=f"{format_int(k.active_customers)}/{format_int(k.total_customers)} ativos",
            accent="green" if k.avg_positivation_pct >= 70.0 else "alert_warn",
            help_text="Proporção da base de clientes comprando de forma recorrente.",
        )
    with c5:
        render_kpi_card(
            title="LTV Médio Estimado",
            value=format_brl(k.avg_ltv_brl, compact=True),
            subfooter_left="Valor do ciclo de vida",
            accent="teal",
            help_text="Lifetime Value médio por cliente ativo; cross-sell eleva diretamente este indicador.",
        )


def render_commercial_reps_kpis(
    comm_dto: CommercialPageDTO,
    temp_dto: TemperancePageDTO,
    rep_plural: str,
) -> None:
    """Renderiza os 5 KPIs da Aba 3 (Desempenho da Equipe Comercial / RCAs) de Fortaleza."""
    df = comm_dto.rep_performance_df
    n_reps = len(df)
    avg_rev = float(df["gross_revenue"].mean()) if not df.empty and "gross_revenue" in df.columns else 0.0
    avg_margin = float(df["margin_pct"].mean()) if not df.empty and "margin_pct" in df.columns else 0.0
    stars = (
        int((df["quadrant"].astype(str) == "Estrela").sum())
        if not df.empty and "quadrant" in df.columns
        else 0
    )
    excess_disc = temp_dto.kpis.excess_discount_brl

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        render_kpi_card(
            title=f"Equipe Ativa ({rep_plural})",
            value=f"{format_int(n_reps)} RCAs",
            subfooter_left=f"{stars} no quadrante Estrela",
            accent="teal",
            help_text="Representantes comerciais ativos com vendas faturadas no recorte.",
        )
    with c2:
        render_kpi_card(
            title="Faturamento Médio / RCA",
            value=format_brl(avg_rev, compact=True),
            subfooter_left="Receita média por vendedor",
            accent="brass",
            help_text="Receita bruta média gerada por representante no período filtrado.",
        )
    with c3:
        render_kpi_card(
            title="Margem Líquida Média Equipe",
            value=f"{avg_margin:.1f}%",
            subfooter_left="Rentabilidade média dos RCAs",
            accent="green" if avg_margin >= 25.0 else "alert_warn",
            help_text="Margem média obtida pela equipe após descontos, comissões e frete.",
        )
    with c4:
        render_kpi_card(
            title="Destaques (Quadrante Estrela)",
            value=f"{format_int(stars)} RCAs",
            subfooter_left="Alto volume + alta margem",
            accent="green",
            help_text="Vendedores acima das medianas de faturamento e margem simultaneamente.",
        )
    with c5:
        render_kpi_card(
            title="Descontos Fora do Teto",
            value=format_brl(excess_disc, compact=True, decimals=1),
            subfooter_left=f"{temp_dto.kpis.excess_discount_pct_of_discount:.1f}% dos descontos",
            accent="alert_neg",
            help_text="Concessão comercial acima da alçada autorizada por porte do cliente.",
        )

