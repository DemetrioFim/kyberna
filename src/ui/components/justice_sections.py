from __future__ import annotations

from typing import Any

import streamlit as st

from src.core.scenarios import ScenarioLabels
from src.services.dto import CommercialPageDTO
from src.ui.components.kpi_card import render_kpi_card
from src.ui.components.prescription import section_header
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
            accent="red",
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
            accent="gold",
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
            accent="gold",
            help_text=(
                "Clientes com atraso moderado entre 1.1x e 1.5x do ciclo de compra. "
                "Representam a <strong>janela de ouro de contato proativo</strong> antes "
                "do abandono definitivo.<br><br>"
                "<strong>No rodapé:</strong> faturamento sob monitoramento."
            ),
        )

    with c4:
        render_kpi_card(
            title="Oportunidade White Space",
            value=format_brl(dto.kpis.white_space_potential_revenue_brl, compact=True),
            subfooter_left=f"Margem: {format_brl(dto.kpis.white_space_potential_margin_brl, compact=True)}",
            accent="teal",
            help_text=(
                "Potencial de venda incremental (cross-sell) mapeado via afinidade transacional "
                "e clusters de clientes semelhantes (lookalike).<br><br>"
                "<strong>No rodapé:</strong> Margem líquida estimada no sortimento ausente."
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


def render_champions_vampires_section(dto: CommercialPageDTO, labels: ScenarioLabels) -> None:
    """Renderiza a Matriz de Rentabilidade: Campeões vs. Vampiros (4 Abas)."""
    section_header(
        "Matriz de Rentabilidade: Campeões vs. Vampiros",
        "Volume vs. Margem de Contribuição — separe quem gera lucro líquido real de quem corrói caixa",
        help_text=(
            "Cruza volume e margem líquida. Campeões sustentam o resultado da empresa; "
            "vampiros geram alto volume operacional com margem irrisória ou negativa "
            "por excesso de descontos."
        ),
    )

    t_fam, t_prod, t_cust, t_rep = st.tabs(
        [
            f"Por {labels.product_family}",
            "Por Produto (SKU)",
            f"Por {labels.customer_plural}",
            f"Por {labels.sales_rep}",
        ]
    )

    tabs_data = [
        (t_fam, f"{labels.product_family}", dto.top_family_generators_df, dto.top_family_destroyers_df),
        (t_prod, "Produtos (SKUs)", dto.top_product_generators_df, dto.top_product_destroyers_df),
        (t_cust, f"{labels.customer_plural}", dto.top_customer_generators_df, dto.top_customer_destroyers_df),
        (t_rep, f"{labels.sales_rep}", dto.top_rep_generators_df, dto.top_rep_destroyers_df),
    ]

    for tab, title, gen_df, dest_df in tabs_data:
        with tab:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"##### Campeões de Margem ({title})")
                render_margin_drivers_table(gen_df, is_generator=True)
            with c2:
                st.markdown(f"##### Sangria de Margem / Vampiros ({title})")
                render_margin_drivers_table(dest_df, is_generator=False)


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
        height=210,
        column_config={k: v for k, v in rep_cfg.items() if k in cols},
    )


def render_critical_customers_table(dto: CommercialPageDTO, customer_label: str) -> None:
    """Renderiza a tabela de clientes críticos com scroll interno."""
    if dto.priority_risk_df.empty:
        st.info("Nenhum cliente em risco encontrado para o filtro selecionado.")
        return
    df = dto.priority_risk_df
    target_cols = [
        "customer_name",
        "state",
        "sales_rep_name",
        "risk_status",
        "delay_ratio",
        "annual_revenue_at_risk",
        "top_opportunity_family",
        "top_opportunity_brl",
    ]
    cols = [c for c in target_cols if c in df.columns]
    display_df = df[cols].copy()

    cust_cfg: dict[str, Any] = {
        "customer_name": st.column_config.TextColumn(customer_label),
        "state": st.column_config.TextColumn("UF", width="small"),
        "sales_rep_name": st.column_config.TextColumn("RCA"),
        "risk_status": st.column_config.TextColumn("Status"),
        "delay_ratio": st.column_config.NumberColumn("Atraso", format="%.2fx"),
        "annual_revenue_at_risk": st.column_config.NumberColumn("R$ em Risco", format="R$ %,.2f"),
        "top_opportunity_family": st.column_config.TextColumn("Oportunidade Mix"),
        "top_opportunity_brl": st.column_config.NumberColumn("Potencial R$", format="R$ %,.2f"),
    }
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        height=210,
        column_config={k: v for k, v in cust_cfg.items() if k in cols},
    )


def render_white_space_deals_table(dto: CommercialPageDTO, customer_label: str) -> None:
    """Renderiza a tabela de oportunidades White Space com scroll interno."""
    if dto.top_white_space_deals_df.empty:
        st.info("Nenhuma oportunidade White Space mapeada no recorte selecionado.")
        return
    df = dto.top_white_space_deals_df
    target_cols = [
        "customer_name",
        "recommended_family",
        "anchor_sku_name",
        "recommended_top_sku",
        "potential_revenue_brl",
        "affinity_lift",
        "action_pitch",
    ]
    cols = [c for c in target_cols if c in df.columns]
    deals_df = df[cols].copy()

    col_cfg: dict[str, Any] = {
        "customer_name": st.column_config.TextColumn(customer_label),
        "recommended_family": st.column_config.TextColumn("Família Ausente"),
        "anchor_sku_name": st.column_config.TextColumn("Perfil / Âncora"),
        "recommended_top_sku": st.column_config.TextColumn("SKU Recomendado"),
        "potential_revenue_brl": st.column_config.NumberColumn("Potencial", format="R$ %,.2f"),
        "affinity_lift": st.column_config.NumberColumn("Lift Afinidade", format="%.2fx"),
        "action_pitch": st.column_config.TextColumn("Argumento Comercial (Pitch)", width="large"),
    }
    st.dataframe(
        deals_df,
        use_container_width=True,
        hide_index=True,
        height=210,
        column_config={k: v for k, v in col_cfg.items() if k in cols},
    )
