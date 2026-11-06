from __future__ import annotations

import streamlit as st

from src.core.scenarios import load_scenario_config
from src.services.dto import CommercialPageDTO
from src.ui.cache import cached_commercial_dashboard
from src.ui.components.charts import quadrant_scatter
from src.ui.components.commercial_charts import (
    cycle_delay_scatter,
    rfm_treemap,
    white_space_heatmap,
)
from src.ui.components.kpi_card import render_kpi_card
from src.ui.components.prescription import (
    render_prescription_box,
    section_header,
)
from src.ui.formatting import format_brl, format_int
from src.ui.state import get_app_state


def _render_kpi_cards(dto: CommercialPageDTO, customer_plural: str) -> None:
    """Renderiza a faixa de KPI Cards executivos do Radar Comercial."""
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        render_kpi_card(
            title=f"{customer_plural} em Risco",
            value=f"{format_int(dto.kpis.at_risk_customers)} {customer_plural.lower()}",
            subfooter_left=f"{dto.kpis.at_risk_customers_pct:.1f}% da carteira",
            accent="red",
            help_text=(
                f"Total de {customer_plural.lower()} que excederam em mais de 50% seu ciclo médio "
                "de recompra (delay ratio > 1.5), classificados em 'Em Risco Imediato' ou 'Adormecido'.<br><br>"
                "<strong>No rodapé:</strong> participação percentual sobre o total de clientes da carteira."
            ),
        )

    with col2:
        render_kpi_card(
            title="Receita Anual em Risco",
            value=format_brl(dto.kpis.annual_revenue_at_risk_brl, compact=True),
            subfooter_left=f"Margem: {format_brl(dto.kpis.annual_margin_at_risk_brl, compact=True)}",
            accent="gold",
            help_text=(
                "Faturamento histórico anualizado dos clientes em risco multiplicado pela sua "
                "probabilidade individual de evasão (churn).<br><br>"
                "<strong>No rodapé:</strong> Margem de contribuição líquida correspondente exposta ao risco."
            ),
        )

    with col3:
        render_kpi_card(
            title="Oportunidade White Space",
            value=format_brl(dto.kpis.white_space_potential_revenue_brl, compact=True),
            subfooter_left=f"Margem: {format_brl(dto.kpis.white_space_potential_margin_brl, compact=True)}",
            accent="teal",
            help_text=(
                "Potencial financeiro total estimado de pedidos de cross-sell (White Space), "
                "mapeado via afinidade transacional Apriori e clientes similares (lookalike).<br><br>"
                "<strong>No rodapé:</strong> Margem de contribuição estimada nas oportunidades."
            ),
        )

    with col4:
        render_kpi_card(
            title="Positivação de Carteira",
            value=f"{dto.kpis.avg_positivation_pct:.1f}%",
            subfooter_left=f"{dto.kpis.active_customers} de {dto.kpis.total_customers} ativos",
            accent="green",
            help_text=(
                f"Percentual de {customer_plural.lower()} positivados com compras no ciclo regular.<br><br>"
                "<strong>No rodapé:</strong> Clientes ativos versus tamanho total da carteira cadastrada."
            ),
        )


def _render_risk_section(dto: CommercialPageDTO, theme_mode: str, customer_label: str) -> None:
    """Renderiza a seção de risco individual de churn e gráfico de dispersão de atraso."""
    section_header(
        "Radar de Risco de Churn & Dispersão de Recompra",
        "Detecção precoce de lojistas fora do ciclo habitual e priorização por valor em risco",
        help_text=(
            "Cruza a recência real em dias com o ciclo individual esperado de cada cliente. Clientes acima "
            "da linha de 45° estão atrasados; acima de 1.5x entram em risco crítico de abandono."
        ),
    )

    col_table, col_scatter = st.columns([1.1, 0.9])

    with col_table:
        st.markdown(
            "<span style='font-size: 0.9rem; font-weight: 600; color: var(--kyb-text);'>"
            "📋 Clientes Críticos Ordenados por R$ em Risco"
            "</span>",
            unsafe_allow_html=True,
        )

        if not dto.priority_risk_df.empty:
            display_df = dto.priority_risk_df[
                [
                    "customer_name",
                    "state",
                    "sales_rep_name",
                    "risk_status",
                    "delay_ratio",
                    "annual_revenue_at_risk",
                    "top_opportunity_family",
                    "top_opportunity_brl",
                ]
            ].copy()

            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                height=380,
                column_config={
                    "customer_name": st.column_config.TextColumn(customer_label),
                    "state": st.column_config.TextColumn("UF", width="small"),
                    "sales_rep_name": st.column_config.TextColumn("RCA"),
                    "risk_status": st.column_config.TextColumn("Status"),
                    "delay_ratio": st.column_config.NumberColumn("Atraso", format="%.2fx"),
                    "annual_revenue_at_risk": st.column_config.NumberColumn(
                        "R$ em Risco", format="R$ %,.2f"
                    ),
                    "top_opportunity_family": st.column_config.TextColumn("Oportunidade Mix"),
                    "top_opportunity_brl": st.column_config.NumberColumn(
                        "Potencial R$", format="R$ %,.2f"
                    ),
                },
            )
        else:
            st.info("Nenhum cliente em risco encontrado para o filtro selecionado.")

    with col_scatter:
        fig_scatter = cycle_delay_scatter(dto.priority_risk_df, theme_mode=theme_mode)
        st.plotly_chart(fig_scatter, use_container_width=True)


def _render_rfm_and_white_space_section(dto: CommercialPageDTO, theme_mode: str) -> None:
    """Renderiza a seção comparativa em duas colunas: Treemap RFM e Heatmap White Space."""
    section_header(
        "Segmentação RFM B2B & Matriz White Space (Cross-Sell)",
        "Distribuição da carteira por maturidade de relacionamento e potencial de sortimento",
        help_text=(
            "À esquerda, o mapa de segmentação RFM (Recência, Frequência, Margem Líquida). "
            "À direita, a matriz White Space identificando famílias com alta afinidade e potencial de compra."
        ),
    )

    col_rfm, col_ws = st.columns([1, 1])

    with col_rfm:
        fig_rfm = rfm_treemap(dto.rfm_summary_df, theme_mode=theme_mode)
        st.plotly_chart(fig_rfm, use_container_width=True)

    with col_ws:
        fig_ws = white_space_heatmap(dto.white_space_matrix_df, theme_mode=theme_mode)
        st.plotly_chart(fig_ws, use_container_width=True)


def _render_rep_efficiency_section(
    dto: CommercialPageDTO,
    theme_mode: str,
    show_rep_efficiency: bool,
    rep_label: str,
) -> None:
    """Renderiza a matriz dos 4 Quadrantes de Representantes Comerciais."""
    if not show_rep_efficiency:
        return

    section_header(
        f"Eficiência Comercial de {rep_label}s (Quadrante de Gestão)",
        "Dispersão de Faturamento vs. Margem Líquida % com tamanho de bolha = R$ em Risco",
        help_text=(
            "Cortes nas medianas da equipe: 'Estrela' (alto volume e alta margem); "
            "'Volume sem margem' (excesso de descontos); 'Margem sem volume' (preço defendido com baixa escala); "
            "'Atenção' (abaixo da mediana em ambos os eixos)."
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
            f"🎯 Diagnóstico e Prescrição por {rep_label}"
            "</span>",
            unsafe_allow_html=True,
        )

        if not dto.rep_performance_df.empty:
            rep_display_df = dto.rep_performance_df[
                [
                    "sales_rep_name",
                    "quadrant",
                    "gross_revenue",
                    "margin_pct",
                    "avg_discount_pct",
                    "revenue_at_risk_brl",
                    "action_prescription",
                ]
            ].copy()

            st.dataframe(
                rep_display_df,
                use_container_width=True,
                hide_index=True,
                height=380,
                column_config={
                    "sales_rep_name": st.column_config.TextColumn(rep_label),
                    "quadrant": st.column_config.TextColumn("Quadrante"),
                    "gross_revenue": st.column_config.NumberColumn(
                        "Faturamento", format="R$ %,.2f"
                    ),
                    "margin_pct": st.column_config.NumberColumn("Margem %", format="%.1f%%"),
                    "avg_discount_pct": st.column_config.NumberColumn(
                        "Desconto Médio", format="%.1f%%"
                    ),
                    "revenue_at_risk_brl": st.column_config.NumberColumn(
                        "Risco Carteira", format="R$ %,.2f"
                    ),
                    "action_prescription": st.column_config.TextColumn(
                        "Ação Recomendada", width="medium"
                    ),
                },
            )


def render_page() -> None:
    """Entrypoint de renderização da Tela 2 — Radar Comercial, RFM & Antecipação de Churn."""
    state = get_app_state()
    scenario_cfg = load_scenario_config(state.scenario_id)
    labels = scenario_cfg.labels
    theme_mode = state.theme_mode

    # Barra de Manchete Executiva Dinâmica
    st.markdown(
        f"""
        <div class="kpi-headline" style="margin-bottom: 1.25rem;">
            <div class="kpi-headline-title">🎯 Radar Comercial & Antecipação de Churn · {scenario_cfg.display_name}</div>
            <div class="kpi-headline-text">
                Gestão proativa de recompra, detecção precoce de evasão e inteligência de cross-sell por representante.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Consulta com cache Streamlit
    dto = cached_commercial_dashboard(
        state.scenario_id,
        regiao=state.regiao,
        uf=state.uf,
        sales_reps=tuple(state.sales_reps),
    )

    # 1. Faixa de KPI Cards Superiores
    _render_kpi_cards(dto, labels.customer_plural)

    # 2. Radar de Risco Individual e Dispersão de Atraso
    _render_risk_section(dto, theme_mode, labels.customer)

    # 3. Segmentação RFM e Matriz White Space
    _render_rfm_and_white_space_section(dto, theme_mode)

    # 4. Eficiência Comercial de Representantes
    _render_rep_efficiency_section(
        dto,
        theme_mode,
        scenario_cfg.capabilities.rep_efficiency,
        labels.sales_rep,
    )

    # 5. Prescrição Comercial de Impacto
    section_header(
        "Prescrição Tática de Reativação e Gestão de Vendas",
        "Recomendações quantificadas em R$ para direcionamento da equipe comercial",
        help_text=(
            "Diretrizes geradas pelo motor analítico priorizando ações de resgate com maior "
            "retorno em margem de contribuição líquida e menor risco de atrito comercial."
        ),
    )
    render_prescription_box(
        title=dto.prescription_title,
        body_html=dto.prescription_html,
        impact_brl=dto.prescription_impact_brl,
    )
