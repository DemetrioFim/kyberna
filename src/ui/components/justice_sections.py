from __future__ import annotations

from typing import Any

import streamlit as st

from src.core.scenarios import ScenarioLabels
from src.services.dto import CommercialPageDTO
from src.ui.components.charts import quadrant_scatter
from src.ui.components.commercial_charts import (
    cycle_delay_scatter,
    cycle_health_funnel_chart,
    rfm_treemap,
    white_space_heatmap,
)
from src.ui.components.kpi_card import render_kpi_card
from src.ui.components.prescription import section_header
from src.ui.components.tables import render_margin_drivers_table
from src.ui.formatting import format_brl, format_int


def render_justice_banner(dto: CommercialPageDTO) -> None:
    """Renderiza o banner de identidade da 3ª Virtude Cardeal — Justiça."""
    b_style = (
        "background: linear-gradient(135deg, rgba(13, 148, 136, 0.12) 0%, "
        "rgba(217, 119, 6, 0.08) 100%); "
        "border-left: 4px solid var(--kyb-teal); border-radius: 8px; "
        "padding: 0.9rem 1.25rem; margin-bottom: 1.25rem;"
    )
    h_style = (
        "font-size: 0.82rem; font-weight: 700; text-transform: uppercase; "
        "letter-spacing: 0.06em; color: var(--kyb-teal); margin-bottom: 0.25rem;"
    )
    t_style = "font-size: 0.92rem; color: var(--kyb-text); line-height: 1.45;"

    h_title = "3. Justiça — Rentabilidade Comercial, Margem & Carteira (Radar Comercial)"
    html = (
        f'<div style="{b_style}">'
        f'<div style="{h_style}">{h_title}</div>'
        f'<div style="{t_style}">'
        '<strong>A premissa executiva:</strong> <em>"A troca de valor entre a empresa, seus clientes '
        'e sua força de vendas está justa e saudável?"</em> Vender muito com margem ruim destrói caixa — '
        "a Justiça identifica quem gera lucro líquido real e quem sangra a margem da companhia."
        "</div>"
        "</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


def render_justice_headline(dto: CommercialPageDTO) -> None:
    """Renderiza a caixa de manchete executiva dinâmica da página de Justiça."""
    st.markdown(
        (
            "<div class='kpi-headline' style='margin-bottom: 1.25rem;'>"
            f"<div class='kpi-headline-title'>{dto.headline_title}</div>"
            f"<div class='kpi-headline-text'>{dto.headline_text}</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


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


def render_sales_rep_justice_section(
    dto: CommercialPageDTO,
    rep_label: str,
    show_rep_efficiency: bool,
    theme_mode: str,
) -> None:
    """Renderiza a seção de Justiça da Força de Vendas (Quadrante + Tabela de Desempenho)."""
    if not show_rep_efficiency:
        return

    section_header(
        f"Justiça da Força de Vendas ({rep_label}s)",
        "Avaliação meritocrática: volume faturado vs. margem líquida preservada e disciplina de descontos",
        help_text=(
            "Cortes nas medianas da equipe: 'Estrela' (alto volume e alta margem); "
            "'Volume sem margem' (excesso de desconto); 'Margem sem volume' "
            "(preço defendido com baixa escala); 'Atenção' (abaixo da mediana em ambos os eixos)."
        ),
    )

    col_quad, col_tbl = st.columns([1.1, 0.9])

    with col_quad:
        if not dto.rep_performance_df.empty:
            fig_quad = quadrant_scatter(
                dto.rep_performance_df,
                x_col="gross_revenue",
                y_col="margin_pct",
                label_col="sales_rep_name",
                size_col="revenue_at_risk_brl",
                theme_mode=theme_mode,
            )
            st.plotly_chart(fig_quad, use_container_width=True)
        else:
            st.info("Nenhum dado de representantes disponível no filtro.")

    with col_tbl:
        st.markdown(
            "<span style='font-size: 0.9rem; font-weight: 600; color: var(--kyb-text);'>"
            f"Diagnóstico e Prescrição por {rep_label}"
            "</span>",
            unsafe_allow_html=True,
        )

        if not dto.rep_performance_df.empty:
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
            active_rep_cfg: dict[str, Any] = {k: v for k, v in rep_cfg.items() if k in cols}

            st.dataframe(
                rep_display_df,
                use_container_width=True,
                hide_index=True,
                height=380,
                column_config=active_rep_cfg,
            )


def render_portfolio_health_section(
    dto: CommercialPageDTO,
    customer_label: str,
    theme_mode: str,
) -> None:
    """Renderiza a Saúde da Carteira: Funil de Ciclo, Dispersão de Atraso e Treemap RFM com LTV."""
    section_header(
        "Saúde da Carteira & Ciclo de Recompra",
        "Detecção precoce de atrasos em relação ao ciclo individual de cada cliente e segmentação RFM",
        help_text=(
            "O funil horizontal estratifica a base entre clientes no ciclo regular, na janela ideal "
            "pré-churn, em risco crítico e adormecidos. À direita, a dispersão cartesiana de atraso."
        ),
    )

    # 1. Funil horizontal do ciclo
    if not dto.cycle_funnel_df.empty:
        fig_funnel = cycle_health_funnel_chart(dto.cycle_funnel_df, theme_mode=theme_mode)
        st.plotly_chart(fig_funnel, use_container_width=True)

    # 2. Clientes em risco e dispersão de atraso
    col_table, col_scatter = st.columns([1.1, 0.9])

    with col_table:
        st.markdown(
            "<span style='font-size: 0.9rem; font-weight: 600; color: var(--kyb-text);'>"
            "Clientes Críticos Ordenados por R$ em Risco"
            "</span>",
            unsafe_allow_html=True,
        )

        if not dto.priority_risk_df.empty:
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
            active_cust_cfg: dict[str, Any] = {k: v for k, v in cust_cfg.items() if k in cols}

            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                height=380,
                column_config=active_cust_cfg,
            )
        else:
            st.info("Nenhum cliente em risco encontrado para o filtro selecionado.")

    with col_scatter:
        fig_scatter = cycle_delay_scatter(dto.priority_risk_df, theme_mode=theme_mode)
        st.plotly_chart(fig_scatter, use_container_width=True)

    # 3. Treemap RFM
    st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)
    fig_rfm = rfm_treemap(dto.rfm_summary_df, theme_mode=theme_mode)
    st.plotly_chart(fig_rfm, use_container_width=True)


def render_white_space_opportunities_section(
    dto: CommercialPageDTO,
    customer_label: str,
    theme_mode: str,
) -> None:
    """Renderiza a Matriz White Space: Heatmap de Afinidade e Top 20 Oportunidades com Argumento Comercial."""
    section_header(
        "Oportunidades White Space (Cross-Sell Inteligente)",
        "Sortimento ausente com alta afinidade estatística, SKU âncora e argumento comercial de venda",
        help_text=(
            "À esquerda, o mapa de calor de sortimento ausente por segmento RFM. À direita, "
            "negócios recomendados com o produto âncora que embasa a recomendação e a fala sugerida (Pitch)."
        ),
    )

    col_heat, col_deals = st.columns([0.9, 1.1])

    with col_heat:
        fig_ws = white_space_heatmap(dto.white_space_matrix_df, theme_mode=theme_mode)
        st.plotly_chart(fig_ws, use_container_width=True)

    with col_deals:
        st.markdown(
            "<span style='font-size: 0.9rem; font-weight: 600; color: var(--kyb-text);'>"
            "Top Oportunidades com SKU Âncora e Argumento de Venda"
            "</span>",
            unsafe_allow_html=True,
        )

        if not dto.top_white_space_deals_df.empty:
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
            active_cfg: dict[str, Any] = {k: v for k, v in col_cfg.items() if k in cols}

            st.dataframe(
                deals_df,
                use_container_width=True,
                hide_index=True,
                height=380,
                column_config=active_cfg,
            )
        else:
            st.info("Nenhuma oportunidade White Space mapeada no recorte selecionado.")
