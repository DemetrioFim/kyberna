from __future__ import annotations

import pandas as pd
import streamlit as st

from src.services.dto import CommercialPageDTO, TemperancePageDTO
from src.ui.components.kpi_card import render_kpi_card
from src.ui.formatting import format_brl, format_int


def render_commercial_cross_sell_kpis(comm_dto: CommercialPageDTO) -> None:
    """Renderiza os 5 KPIs exclusivos da Aba 1 (Cross-Sell & Modelo Apriori) sem duplicação."""
    k = comm_dto.kpis
    eligible_cnt = (
        k.white_space_eligible_customers
        if k.white_space_eligible_customers > 0
        else (
            int(comm_dto.top_white_space_deals_df["customer_name"].nunique())
            if not comm_dto.top_white_space_deals_df.empty
            and "customer_name" in comm_dto.top_white_space_deals_df.columns
            else 0
        )
    )
    total_offers = (
        k.white_space_total_offers
        if k.white_space_total_offers > 0
        else len(comm_dto.top_white_space_deals_df)
    )
    avg_gap = k.white_space_potential_revenue_brl / max(eligible_cnt, 1)
    margin_pct = (
        (k.white_space_potential_margin_brl / k.white_space_potential_revenue_brl) * 100.0
        if k.white_space_potential_revenue_brl > 0
        else 0.0
    )

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        render_kpi_card(
            title="Potencial White Space",
            value=format_brl(k.white_space_potential_revenue_brl, compact=True),
            subfooter_left=f"Lacuna média: {format_brl(avg_gap, compact=True)} / loja",
            accent="teal",
            help_text=(
                "Receita incremental anual mapeada pelo algoritmo Apriori + Lookalike "
                "para linhas ausentes no mix dos lojistas."
            ),
        )
    with c2:
        render_kpi_card(
            title="Margem Incremental Estimada",
            value=format_brl(k.white_space_potential_margin_brl, compact=True),
            subfooter_left=f"Rentabilidade média: {margin_pct:.1f}%",
            accent="green",
            help_text="Contribuição líquida estimada ao capturar as oportunidades de expansão de mix.",
        )
    with c3:
        render_kpi_card(
            title="Confiança & Suporte (Apriori)",
            value=f"{k.apriori_avg_confidence_pct:.1f}%",
            subfooter_left=(
                f"Suporte médio: {k.apriori_avg_support_pct:.2f}% · {k.apriori_rules_count} regras"
            ),
            accent="brass",
            help_text=(
                "Confiança mede P(Ofertar B | Já compra A). Suporte mede a frequência conjunta "
                "nas cestas históricas."
            ),
        )
    with c4:
        render_kpi_card(
            title="Alavancagem Máx. (Lift)",
            value=f"{k.apriori_max_lift:.2f}x",
            subfooter_left="Lift > 1,0x confirma sinergia real",
            accent="green" if k.apriori_max_lift >= 1.15 else "teal",
            help_text=(
                "Quantas vezes mais provável é a compra conjunta frente ao acaso. "
                "Valores acima de 1,0x indicam associação positiva."
            ),
        )
    with c5:
        render_kpi_card(
            title="Cobertura de Oportunidades",
            value=f"{format_int(eligible_cnt)} lojas",
            subfooter_left=(
                f"{format_int(total_offers)} ofertas · Mix "
                f"{k.avg_families_per_customer:.1f}/{k.total_catalog_families}"
            ),
            accent="teal",
            help_text=(
                "Total real de lojas elegíveis na carteira com lacuna de mix e média de famílias "
                "compradas por cliente."
            ),
        )


def render_top_apriori_rules_table(rules_df: pd.DataFrame, *, rule_level: str = "sku") -> None:
    """Renderiza micro-tabela com as Top 5 regras Apriori (Suporte, Confiança e Lift)."""
    if rules_df.empty or "rule_level" not in rules_df.columns:
        st.info("Nenhuma regra Apriori disponível para o recorte atual.")
        return

    sub = rules_df[rules_df["rule_level"] == rule_level].copy()
    if sub.empty:
        sub = rules_df.copy()

    top_df = (
        sub.sort_values(by=["lift", "confidence_pct"], ascending=False)
        .head(5)[["rule_label", "support_pct", "confidence_pct", "lift"]]
        .rename(
            columns={
                "rule_label": "Regra (Se compra → Ofertar)",
                "support_pct": "Suporte %",
                "confidence_pct": "Confiança %",
                "lift": "Lift",
            }
        )
    )
    st.dataframe(
        top_df,
        use_container_width=True,
        hide_index=True,
        height=135,
        column_config={
            "Regra (Se compra → Ofertar)": st.column_config.TextColumn(width="large"),
            "Suporte %": st.column_config.NumberColumn(format="%.2f%%", width="small"),
            "Confiança %": st.column_config.NumberColumn(format="%.1f%%", width="small"),
            "Lift": st.column_config.NumberColumn(format="%.2fx", width="small"),
        },
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
