from __future__ import annotations

import streamlit as st

from src.core.scenarios import ScenarioConfig, load_scenario_config
from src.services.dto import CommercialPageDTO, TemperancePageDTO
from src.ui.cache import cached_commercial_dashboard, cached_temperance_dashboard
from src.ui.components.charts import quadrant_scatter
from src.ui.components.commercial_charts import (
    cycle_delay_scatter,
    cycle_health_funnel_chart,
    rfm_treemap,
    white_space_family_chart,
    white_space_heatmap,
)
from src.ui.components.commercial_sections import (
    render_commercial_cross_sell_kpis,
    render_commercial_reps_kpis,
)
from src.ui.components.export_bar import render_commercial_export_bar
from src.ui.components.justice_sections import (
    render_critical_customers_table,
    render_justice_kpi_cards,
    render_sales_reps_table,
    render_white_space_deals_table,
)
from src.ui.components.prescription import (
    render_cockpit_header,
    render_prescription_box,
    section_header,
)
from src.ui.components.temperance_sections import render_violations_rep_chart
from src.ui.formatting import format_brl
from src.ui.state import AppState, get_app_state


def _pluralize_rep_label(rep_label: str) -> str:
    """Pluraliza corretamente rótulos de força de vendas com ou sem parênteses."""
    overrides = {
        "RCA (Representante)": "RCAs (Representantes)",
        "Vendedor de Rota": "Vendedores de Rota",
        "Gerente de Loja": "Gerentes de Loja",
        "Balconista / Atendente": "Balconistas / Atendentes",
    }
    if rep_label in overrides:
        return overrides[rep_label]
    if "(" in rep_label:
        base, rest = rep_label.split("(", 1)
        return f"{base.strip()}s ({rest.rstrip(')')}s)"
    return f"{rep_label}s"


def _render_tab_cross_sell(
    state: AppState,
    scenario_cfg: ScenarioConfig,
    comm_dto: CommercialPageDTO,
) -> None:
    """Aba 1: Cross-Sell & Mix (Modelo Apriori)."""
    labels = scenario_cfg.labels
    theme_mode = state.theme_mode
    render_commercial_cross_sell_kpis(comm_dto)

    col_l, col_r = st.columns([1.05, 1.0])
    with col_l:
        section_header(
            "Matriz de Afinidade — Modelo Apriori (White Space)",
            "Potencial financeiro cruzando família recomendada x segmento RFM do cliente",
            help_text=(
                "Regras de associação Apriori combinadas com similaridade lookalike apontam "
                "famílias ausentes com alta probabilidade de adoção."
            ),
        )
        st.plotly_chart(
            white_space_heatmap(comm_dto.white_space_matrix_df, theme_mode=theme_mode),
            use_container_width=True,
        )
    with col_r:
        section_header(
            "Potencial de Expansão por Família",
            "Ranqueamento das famílias com maior receita incremental pronta para oferta",
            help_text="Soma de receita potencial mapeada pelo motor Apriori por linha de produto.",
        )
        st.plotly_chart(
            white_space_family_chart(comm_dto.white_space_matrix_df, theme_mode=theme_mode),
            use_container_width=True,
        )

    col_bl, col_br = st.columns([1.35, 1.0])
    with col_bl:
        section_header(
            f"Pitches Prontos de Cross-Sell ({labels.customer_plural})",
            "Recomendações individuais com argumento técnico e acionamento em 1 clique no WhatsApp",
        )
        render_white_space_deals_table(comm_dto, labels.customer)
    with col_br:
        section_header("Plano de Expansão Comercial", "Captura de mix e exportação para roteiro de vendas")
        ws_rev = format_brl(comm_dto.kpis.white_space_potential_revenue_brl, compact=True)
        render_prescription_box(
            title="Diretriz Comercial de Cross-Sell",
            recommendation_html=(
                f"Priorize os top pitches do modelo <b>Apriori + Lookalike</b> em contas "
                f"<b>Campeãs</b> e <b>Fiéis</b> para destravar <b>{ws_rev}</b> "
                "em receita incremental sem custo de aquisição (CAC zero)."
            ),
            impact_brl=comm_dto.kpis.white_space_potential_margin_brl,
            action_hint="Exporte a lista para a equipe de campo ou acione via WhatsApp.",
            help_text="Estimativa baseada nas oportunidades recomendadas com confiança validada.",
        )
        render_commercial_export_bar(
            comm_dto.priority_risk_df,
            comm_dto.top_white_space_deals_df,
            scenario_id=state.scenario_id,
            scenario_name=scenario_cfg.display_name,
        )


def _render_tab_risk_opportunities(
    comm_dto: CommercialPageDTO,
    scenario_cfg: ScenarioConfig,
    theme_mode: str,
) -> None:
    """Aba 2: Lojas em Risco (Churn) & Oportunidades."""
    labels = scenario_cfg.labels
    render_justice_kpi_cards(comm_dto, labels.customer_plural)

    col_l, col_r = st.columns([1.0, 1.0])
    with col_l:
        section_header(
            "Atraso de Recompra vs. Ciclo Histórico",
            "Identifica contas que ultrapassaram o ciclo normal (pré-churn 1,1x e risco >1,5x)",
            help_text=("Acima da diagonal tracejada laranja/vermelha o cliente já passou do ponto habitual."),
        )
        st.plotly_chart(
            cycle_delay_scatter(comm_dto.priority_risk_df, theme_mode=theme_mode),
            use_container_width=True,
        )
    with col_r:
        section_header(
            "Segmentação RFM & LTV da Carteira",
            "Distribuição dos clientes ponderada por Margem de Contribuição e rentabilidade",
            help_text="Treemap agrupado nos 9 segmentos RFM B2B priorizando lucro líquido.",
        )
        st.plotly_chart(
            rfm_treemap(comm_dto.rfm_summary_df, theme_mode=theme_mode),
            use_container_width=True,
        )

    col_bl, col_br = st.columns([1.35, 1.0])
    with col_bl:
        section_header(
            f"{labels.customer_plural} com Maior Risco de Perda & Oportunidade",
            "Lista priorizada por receita em risco e mix complementar com WhatsApp direto",
        )
        render_critical_customers_table(comm_dto, labels.customer)
    with col_br:
        section_header(
            "Funil de Saúde do Ciclo de Recompra",
            "Proporção de clientes saudáveis, em janela pré-churn e adormecidos",
        )
        if not comm_dto.cycle_funnel_df.empty:
            st.plotly_chart(
                cycle_health_funnel_chart(comm_dto.cycle_funnel_df, theme_mode=theme_mode),
                use_container_width=True,
            )
        else:
            st.info("Sem dados de funil no filtro atual.")


def _render_tab_sales_reps(
    comm_dto: CommercialPageDTO,
    temp_dto: TemperancePageDTO,
    scenario_cfg: ScenarioConfig,
    rep_plural: str,
    theme_mode: str,
) -> None:
    """Aba 3: Desempenho da Equipe Comercial (RCAs)."""
    labels = scenario_cfg.labels
    render_commercial_reps_kpis(comm_dto, temp_dto, rep_plural)

    col_l, col_r = st.columns([1.0, 1.0])
    with col_l:
        section_header(
            f"Quadrante de Eficiência ({rep_plural})",
            "Volume Faturado vs. Margem Líquida % — separa Estrelas de vendedores de desconto",
            help_text="Tamanho da bolha representa receita em risco na carteira do representante.",
        )
        if not comm_dto.rep_performance_df.empty:
            fig_quad = quadrant_scatter(
                comm_dto.rep_performance_df,
                x_col="gross_revenue",
                y_col="margin_pct",
                label_col="sales_rep_name",
                size_col="revenue_at_risk_brl",
                theme_mode=theme_mode,
            )
            st.plotly_chart(fig_quad, use_container_width=True)
        else:
            st.info("Nenhum dado de representantes disponível no filtro atual.")
    with col_r:
        section_header(
            "Top RCAs por Desconto Fora do Teto",
            "Ranking de representantes com maior concessão acima da política autorizada",
            help_text="Destaca exatamente quem concentra os desvios de tabela de preços.",
        )
        st.plotly_chart(
            render_violations_rep_chart(temp_dto.policy_violations_by_rep_df, theme_mode=theme_mode),
            use_container_width=True,
        )

    col_bl, col_br = st.columns([1.35, 1.0])
    with col_bl:
        section_header(
            f"Desempenho e Prescrição por {labels.sales_rep}",
            "Indicadores completos de faturamento, margem, desconto médio e risco de carteira",
        )
        render_sales_reps_table(comm_dto, labels.sales_rep)
    with col_br:
        section_header("Coaching & Governança da Equipe", "Ações gerenciais para elevar margem média")
        render_prescription_box(
            title=f"Diretriz de Performance ({rep_plural})",
            recommendation_html=(
                "Replicate as práticas dos RCAs <b>Estrela</b>, trave alçadas de desconto acima da "
                "tabela no quadrante <b>Volume sem Margem</b> e direcione roteiros para clientes em "
                "<b>Janela Pré-Churn</b>."
            ),
            impact_brl=temp_dto.kpis.excess_discount_brl,
            action_hint="Condicione bonificações à margem de contribuição líquida, não ao bruto.",
            help_text="Economia potencial estimada ao conter descontos concedidos acima da política.",
        )


def render_page() -> None:
    """Renderiza a Página 2 — 2. Fortaleza (Visão Comercial) estilo PowerBI."""
    state = get_app_state()
    scenario_cfg = load_scenario_config(state.scenario_id)
    rep_plural = _pluralize_rep_label(scenario_cfg.labels.sales_rep)

    comm_dto = cached_commercial_dashboard(
        state.scenario_id,
        regiao=state.regiao,
        uf=state.uf,
        families=tuple(state.families),
        sales_reps=tuple(state.sales_reps),
        risk_status="Todos",
        rfm_segment="Todos",
        quadrant="Todos",
        period_preset=state.period_preset,
        comparison_mode=state.comparison_mode,
        selected_month=state.selected_month,
        selected_quarter=state.selected_quarter,
        selected_semester=state.selected_semester,
        custom_start_date=state.custom_start_date,
        custom_end_date=state.custom_end_date,
    )
    temp_dto = cached_temperance_dashboard(
        state.scenario_id,
        regiao=state.regiao,
        uf=state.uf,
        families=tuple(state.families),
        sales_reps=tuple(state.sales_reps),
        period_preset=state.period_preset,
        comparison_mode=state.comparison_mode,
        selected_month=state.selected_month,
        selected_quarter=state.selected_quarter,
        selected_semester=state.selected_semester,
        custom_start_date=state.custom_start_date,
        custom_end_date=state.custom_end_date,
    )

    render_cockpit_header(
        title="Fortaleza · Inteligência Comercial, Carteira & Expansão",
        virtue_badge="2. Fortaleza",
        headline_title=comm_dto.headline_title,
        headline_text=comm_dto.headline_text,
        as_of_date_label=comm_dto.as_of_date_label,
        help_text=(
            "Visão comercial dedicada estilo PowerBI: Cross-Sell com Modelo Apriori, "
            "risco de evasão da carteira (Churn/RFM) e produtividade dos RCAs."
        ),
    )

    tab_cs, tab_risk, tab_rca = st.tabs(
        [
            "Cross-Sell & Mix (Modelo Apriori)",
            f"Lojas em Risco (Churn) & Oportunidades ({scenario_cfg.labels.customer_plural})",
            f"Desempenho da Equipe ({rep_plural})",
        ]
    )
    with tab_cs:
        _render_tab_cross_sell(state, scenario_cfg, comm_dto)
    with tab_risk:
        _render_tab_risk_opportunities(comm_dto, scenario_cfg, state.theme_mode)
    with tab_rca:
        _render_tab_sales_reps(comm_dto, temp_dto, scenario_cfg, rep_plural, state.theme_mode)


render_page()
