from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from src.core.scenarios import ScenarioLabels
from src.services.dto import CommercialPageDTO, ExecutivePageDTO, FortitudePageDTO, TemperancePageDTO
from src.services.export_service import attach_whatsapp_links
from src.ui.components.kpi_card import KpiAccent, render_kpi_card
from src.ui.components.tables import render_margin_drivers_table
from src.ui.formatting import format_brl, format_int


def render_justice_kpi_cards(dto: CommercialPageDTO, customer_plural: str) -> None:
    """Renderiza os 5 KPI Cards executivos do pilar de Justiça."""
    c1, c2, c3, c4, c5 = st.columns(5)

    with c1:
        render_kpi_card(
            title=f"{customer_plural} em Risco",
            value=f"{format_int(dto.kpis.at_risk_customers)} {customer_plural.lower()}",
            subfooter_left=f"{dto.kpis.at_risk_customers_pct:.1f}% da carteira",
            accent="alert_neg",
            help_text=(
                f"Total de {customer_plural.lower()} com atraso crítico no ciclo habitual "
                "(delay ratio > 1.5x) classificados em 'Risco Imediato' ou 'Adormecido'.<br><br>"
                "<strong>No rodapé:</strong> percentual sobre a base ativa total."
            ),
        )

    with c2:
        render_kpi_card(
            title="Receita Anual em Risco",
            value=format_brl(dto.kpis.annual_revenue_at_risk_brl, compact=True),
            subfooter_left=f"Margem: {format_brl(dto.kpis.annual_margin_at_risk_brl, compact=True)}",
            accent="alert_warn",
            help_text=(
                "Faturamento histórico anualizado dos lojistas em risco ponderado pela "
                "probabilidade estatística individual de evasão (churn).<br><br>"
                "<strong>No rodapé:</strong> Margem de contribuição líquida correspondente."
            ),
        )

    with c3:
        render_kpi_card(
            title="Janela Ideal Pré-Churn",
            value=f"{format_int(dto.kpis.attention_customers)} {customer_plural.lower()}",
            subfooter_left=f"Fat.: {format_brl(dto.kpis.attention_revenue_brl, compact=True)}",
            accent="alert_warn",
            help_text=(
                "Clientes com atraso moderado entre 1.1x e 1.5x do ciclo de compra. "
                "Representam a <strong>janela de ouro de contato proativo</strong> antes "
                "do abandono definitivo.<br><br>"
                "<strong>No rodapé:</strong> faturamento sob monitoramento."
            ),
        )

    with c4:
        vamp_cnt = dto.kpis.vampire_customers_count
        render_kpi_card(
            title="Clientes Vampiros (<15% MC)",
            value=f"{format_int(vamp_cnt)} contas",
            subfooter_left="Alto volume com margem comprimida",
            accent="alert_neg" if vamp_cnt > 0 else "green",
            help_text=(
                f"{customer_plural} com faturamento relevante (> R$ 15 mil), mas margem de "
                "contribuição líquida abaixo de 15% por excesso de descontos ou frete."
            ),
        )

    with c5:
        render_kpi_card(
            title="Positivação de Carteira",
            value=f"{dto.kpis.avg_positivation_pct:.1f}%",
            subfooter_left=f"LTV Médio: {format_brl(dto.kpis.avg_ltv_brl, compact=True)}",
            accent="green",
            help_text=(
                f"Percentual de {customer_plural.lower()} cadastrados que compraram regularmente "
                f"({dto.kpis.active_customers} de {dto.kpis.total_customers}).<br><br>"
                "<strong>No rodapé:</strong> LTV (Lifetime Value) médio estimado por cliente."
            ),
        )


def render_champions_vampires_section(
    dto: ExecutivePageDTO | CommercialPageDTO,
    labels: ScenarioLabels,
) -> None:
    """Renderiza Campeões vs. Vampiros em Grid 2x2 limpo (Produtos à esq., Clientes à dir., sem sub-abas)."""
    prod_gen = getattr(dto, "top_product_generators_df", getattr(dto, "top_generators_df", None))
    prod_dest = getattr(dto, "top_product_destroyers_df", getattr(dto, "top_destroyers_df", None))

    c_left, c_right = st.columns(2)
    with c_left:
        st.markdown("##### Visão Administrativa · Top Produtos Campeões")
        if prod_gen is not None:
            render_margin_drivers_table(prod_gen, is_generator=True, height=180)
        st.markdown("##### Visão Administrativa · Produtos Vampiros")
        if prod_dest is not None:
            render_margin_drivers_table(prod_dest, is_generator=False, height=180)
    with c_right:
        st.markdown(f"##### Visão Comercial · {labels.customer_plural} Campeões")
        render_margin_drivers_table(dto.top_customer_generators_df, is_generator=True, height=180)
        st.markdown(f"##### Visão Comercial · {labels.customer_plural} Vampiros")
        render_margin_drivers_table(dto.top_customer_destroyers_df, is_generator=False, height=180)


def render_financial_aging_kpis(fort_dto: FortitudePageDTO, temp_dto: TemperancePageDTO) -> None:
    """Renderiza os 5 KPIs da Aba 3 (Aging de Recebíveis & Concentração) de Justiça Financeira."""
    fk = fort_dto.kpis
    tk = temp_dto.kpis
    risk_accent: KpiAccent = "alert_neg" if fk.at_risk_portfolio_pct >= 20.0 else "alert_warn"
    conc_accent: KpiAccent = "alert_warn" if fk.top5_customers_share_pct > 35.0 else "teal"

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        render_kpi_card(
            title="Carteira em Atraso (>1,5x)",
            value=format_brl(fk.at_risk_portfolio_brl, compact=True, decimals=1),
            subfooter_left=f"{fk.at_risk_portfolio_pct:.1f}% da receita 12m",
            accent=risk_accent,
            help_text="Faturamento anualizado em contas cujo atraso excedeu 1,5x o ciclo habitual.",
        )
    with c2:
        render_kpi_card(
            title="Clientes em Atraso Crítico",
            value=f"{format_int(fk.at_risk_customers_count)} clientes",
            subfooter_left=f"De {format_int(fk.active_customers_count)} ativos",
            accent="alert_neg",
            help_text="Quantidade de contas classificadas em Risco 31-60d ou Crítico >60d.",
        )
    with c3:
        render_kpi_card(
            title="Concentração Top 5 Clientes",
            value=f"{fk.top5_customers_share_pct:.1f}%",
            subfooter_left="Limite saudável <= 35%",
            accent=conc_accent,
            help_text="Dependência financeira sobre os 5 maiores compradores dos últimos 12 meses.",
        )
    with c4:
        render_kpi_card(
            title="Concentração Top 10 Clientes",
            value=f"{fk.top10_customers_share_pct:.1f}%",
            subfooter_left=f"Top 2 fam.: {fk.top2_families_share_pct:.1f}%",
            accent="brass",
            help_text="Parcela da receita concentrada nos 10 maiores clientes e 2 maiores famílias.",
        )
    with c5:
        render_kpi_card(
            title="Custo Financeiro de Prazo",
            value=format_brl(tk.financial_term_leak_brl, compact=True, decimals=1),
            subfooter_left="Prazo > 30d (1,35% a.m.)",
            accent="alert_warn",
            help_text="Despesa financeira implícita de carregar duplicatas acima do prazo padrão de 30 dias.",
        )


def render_term_leak_table(temp_dto: TemperancePageDTO) -> None:
    """Renderiza a tabela direta de custo financeiro de prazo concedido (sem sub-abas)."""
    df = temp_dto.term_leak_by_rep_df
    if df.empty:
        st.info("Nenhum custo excedente de prazo identificado no filtro atual.")
        return
    cols = [c for c in ("rep_name", "avg_pmr_days", "term_leak_brl") if c in df.columns]
    view = (
        df[cols]
        .head(12)
        .rename(
            columns={
                "rep_name": "Representante (RCA)",
                "avg_pmr_days": "Prazo Médio (dias)",
                "term_leak_brl": "Custo Financeiro (R$)",
            }
        )
    )
    st.dataframe(
        view,
        use_container_width=True,
        hide_index=True,
        height=185,
        column_config={
            "Prazo Médio (dias)": st.column_config.NumberColumn(format="%.1f d"),
            "Custo Financeiro (R$)": st.column_config.NumberColumn(format="R$ %,.2f"),
        },
    )


def render_sales_reps_table(dto: CommercialPageDTO, rep_label: str) -> None:
    """Renderiza a tabela de desempenho dos RCAs com scroll interno."""
    if dto.rep_performance_df.empty:
        st.info("Nenhum dado de representantes disponível no filtro.")
        return
    df = dto.rep_performance_df
    target_cols = [
        "sales_rep_name",
        "quadrant",
        "gross_revenue",
        "margin_pct",
        "avg_discount_pct",
        "revenue_at_risk_brl",
        "action_prescription",
    ]
    cols = [c for c in target_cols if c in df.columns]
    rep_display_df = df[cols].copy()

    rep_cfg: dict[str, Any] = {
        "sales_rep_name": st.column_config.TextColumn(rep_label),
        "quadrant": st.column_config.TextColumn("Quadrante"),
        "gross_revenue": st.column_config.NumberColumn("Faturamento", format="R$ %,.2f"),
        "margin_pct": st.column_config.NumberColumn("Margem %", format="%.1f%%"),
        "avg_discount_pct": st.column_config.NumberColumn("Desconto Médio", format="%.1f%%"),
        "revenue_at_risk_brl": st.column_config.NumberColumn("Risco Carteira", format="R$ %,.2f"),
        "action_prescription": st.column_config.TextColumn("Ação Recomendada", width="medium"),
    }
    st.dataframe(
        rep_display_df,
        use_container_width=True,
        hide_index=True,
        height=185,
        column_config={k: v for k, v in rep_cfg.items() if k in cols},
    )


def render_critical_customers_table(dto: CommercialPageDTO, customer_label: str) -> None:
    """Renderiza a tabela de clientes críticos com link direto WhatsApp e scroll interno."""
    if dto.priority_risk_df.empty:
        st.info("Nenhum cliente em risco encontrado para o filtro selecionado.")
        return
    df = attach_whatsapp_links(
        dto.priority_risk_df,
        pitch_col="top_opportunity_pitch",
        fallback_pitch="Condição especial de reativação de pedido",
    )
    target_cols = [
        "customer_name",
        "rfm_segment",
        "state",
        "sales_rep_name",
        "risk_status",
        "delay_ratio",
        "annual_revenue_at_risk",
        "top_opportunity_family",
        "top_opportunity_brl",
        "whatsapp_link",
    ]
    cols = [c for c in target_cols if c in df.columns]
    display_df = df[cols].copy()

    cust_cfg: dict[str, Any] = {
        "customer_name": st.column_config.TextColumn(customer_label),
        "rfm_segment": st.column_config.TextColumn("Segmento RFM", width="small"),
        "state": st.column_config.TextColumn("UF", width="small"),
        "sales_rep_name": st.column_config.TextColumn("RCA"),
        "risk_status": st.column_config.TextColumn("Status", width="small"),
        "delay_ratio": st.column_config.NumberColumn("Atraso", format="%.2fx"),
        "annual_revenue_at_risk": st.column_config.NumberColumn("R$ em Risco", format="R$ %,.2f"),
        "top_opportunity_family": st.column_config.TextColumn("Oportunidade Mix", width="small"),
        "top_opportunity_brl": st.column_config.NumberColumn("Potencial R$", format="R$ %,.2f"),
        "whatsapp_link": st.column_config.LinkColumn(
            "WhatsApp",
            display_text="Chamar",
            width="small",
            help="Abre conversa pré-preenchida no WhatsApp Web/App.",
        ),
    }
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        height=185,
        column_config={k: v for k, v in cust_cfg.items() if k in cols},
    )


def _style_rfm_segment(val: object) -> str:
    """Destaca visualmente o segmento RFM sem privilegiar um único grupo."""
    seg = str(val)
    if seg in ("Campeões", "Fiéis"):
        return "color: #0D9488; font-weight: 600;"
    if seg in ("Em Risco", "Não Pode Perder", "Perdidos"):
        return "color: #D1495B; font-weight: 600;"
    if seg in ("Promissores", "Novos Clientes"):
        return "color: #C9A227; font-weight: 600;"
    return "font-weight: 500;"


def render_white_space_deals_table(
    source: CommercialPageDTO | pd.DataFrame,
    customer_label: str,
) -> None:
    """Renderiza oportunidades de Cross-Sell com Segmento RFM, Apriori (Suporte/Conf/Lift) e WhatsApp."""
    raw_df = source if isinstance(source, pd.DataFrame) else source.top_white_space_deals_df
    if raw_df.empty:
        st.info("Nenhuma oportunidade White Space mapeada no recorte selecionado.")
        return
    df = attach_whatsapp_links(
        raw_df,
        pitch_col="action_pitch",
        fallback_pitch="Sugestão de ampliação de mix",
    )
    ants = (
        df["best_rule_antecedent"].astype(str).tolist()
        if "best_rule_antecedent" in df.columns
        else df["recommended_family"].astype(str).tolist()
    )
    fams = df["recommended_family"].astype(str).tolist()
    df["apriori_rule_view"] = [f"{ant[:18]} → {fam}" for ant, fam in zip(ants, fams, strict=False)]

    target_cols = [
        "customer_name",
        "rfm_segment",
        "apriori_rule_view",
        "apriori_support_pct",
        "apriori_confidence_pct",
        "apriori_lift",
        "potential_revenue_brl",
        "whatsapp_link",
    ]
    cols = [c for c in target_cols if c in df.columns]
    deals_df = df[cols].copy()

    col_cfg: dict[str, Any] = {
        "customer_name": st.column_config.TextColumn(customer_label, width="medium"),
        "rfm_segment": st.column_config.TextColumn("Segmento RFM", width="small"),
        "apriori_rule_view": st.column_config.TextColumn("Regra Apriori (Compra → Oferta)", width="medium"),
        "apriori_support_pct": st.column_config.NumberColumn("Suporte", format="%.2f%%", width="small"),
        "apriori_confidence_pct": st.column_config.NumberColumn("Confiança", format="%.1f%%", width="small"),
        "apriori_lift": st.column_config.NumberColumn("Lift", format="%.2fx", width="small"),
        "potential_revenue_brl": st.column_config.NumberColumn("Potencial", format="R$ %,.0f", width="small"),
        "whatsapp_link": st.column_config.LinkColumn(
            "WhatsApp",
            display_text="Chamar",
            width="small",
            help="Abre conversa pré-preenchida no WhatsApp Web/App com o pitch e SKU âncora.",
        ),
    }
    styled = (
        deals_df.style.map(_style_rfm_segment, subset=["rfm_segment"])
        if "rfm_segment" in deals_df.columns
        else deals_df
    )
    st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True,
        height=185,
        column_config={k: v for k, v in col_cfg.items() if k in cols},
    )
