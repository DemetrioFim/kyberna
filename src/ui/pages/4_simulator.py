from __future__ import annotations

import streamlit as st

from src.core.scenarios import ScenarioConfig, load_scenario_config
from src.services.dto import CommercialPageDTO, TemperancePageDTO
from src.ui.cache import cached_commercial_dashboard, cached_temperance_dashboard
from src.ui.components.apriori_charts import (
    RFM_SEGMENT_ORDER,
    apriori_rules_scatter,
    white_space_heatmap_v2,
)
from src.ui.components.charts import quadrant_scatter
from src.ui.components.commercial_charts import (
    cycle_delay_scatter,
    cycle_health_funnel_chart,
    rfm_treemap,
)
from src.ui.components.commercial_sections import (
    render_commercial_cross_sell_kpis,
    render_commercial_reps_kpis,
    render_top_apriori_rules_table,
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


def _format_apriori_level(level: str) -> str:
    """Formata rótulo legível do alternador de granularidade Apriori."""
    return "Regras por Produto (SKU)" if level == "sku" else "Regras por Família (Linha)"


def _render_tab_cross_sell(
    state: AppState,
    scenario_cfg: ScenarioConfig,
    comm_dto: CommercialPageDTO,
) -> None:
    """Aba 1: Cross-Sell & Mix (Modelo Apriori Explicável + RFM Explícito)."""
    labels = scenario_cfg.labels
    theme_mode = state.theme_mode
    render_commercial_cross_sell_kpis(comm_dto)

    col_l, col_r = st.columns([1.0, 1.05])
    with col_l:
        section_header(
            "Mapa de Oportunidades: Família x Segmento RFM",
            "Potencial financeiro e lojas elegíveis nos 9 segmentos RFM",
            help_text=(
                "Cruza famílias recomendadas com os 9 segmentos RFM (do maior engajamento à "
                "recuperação), exibindo receita potencial e quantidade de lojas por célula."
            ),
        )
        st.plotly_chart(
            white_space_heatmap_v2(comm_dto.white_space_matrix_df, theme_mode=theme_mode),
            use_container_width=True,
            theme=None,
        )
    with col_r:
        section_header(
            "Regras de Associação Apriori (Suporte x Confiança x Lift)",
            "Associações reais descobertas nas cestas de compra",
            help_text=(
                "<b>Suporte (%):</b> frequência conjunta nas cestas.<br>"
                "<b>Confiança (%):</b> prob. P(Ofertar B | Já compra A).<br>"
                "<b>Lift (x):</b> alavancagem acima do acaso (Lift > 1,0x = sinergia real)."
            ),
        )
        apriori_level = st.radio(
            "Granularidade Apriori",
            options=["sku", "family"],
            index=0,
            format_func=_format_apriori_level,
            key="ws_apriori_level",
            horizontal=True,
            label_visibility="collapsed",
        )
        st.plotly_chart(
            apriori_rules_scatter(
                comm_dto.apriori_rules_df,
                rule_level=str(apriori_level),
                theme_mode=theme_mode,
            ),
            use_container_width=True,
            theme=None,
        )
        st.caption("Suporte = freq. conjunta · Confiança = prob. P(B|A) · Lift > 1,0x = sinergia real.")

    deals_df = comm_dto.top_white_space_deals_df
    present_rfm = (
        [str(s) for s in deals_df["rfm_segment"].dropna().unique().tolist()]
        if not deals_df.empty and "rfm_segment" in deals_df.columns
        else []
    )
    rfm_opts = ["Todos", *[s for s in RFM_SEGMENT_ORDER if s in present_rfm]]
    rfm_opts.extend(sorted(s for s in present_rfm if s not in rfm_opts))
    fam_opts = ["Todas"]
    if not deals_df.empty and "recommended_family" in deals_df.columns:
        fam_opts.extend(sorted(deals_df["recommended_family"].dropna().astype(str).unique().tolist()))

    col_bl, col_br = st.columns([1.4, 1.0])
    with col_bl:
        section_header(
            f"Oportunidades de Cross-Sell ({labels.customer_plural} · RFM + Apriori)",
            "Explore livremente por Segmento RFM ou Família com ação direta no WhatsApp",
        )
        c_rfm, c_fam = st.columns(2)
        with c_rfm:
            sel_rfm = st.selectbox(
                "Segmento RFM",
                options=rfm_opts,
                index=0,
                key="ws_filter_rfm",
            )
        with c_fam:
            sel_fam = st.selectbox(
                "Família Recomendada",
                options=fam_opts,
                index=0,
                key="ws_filter_family",
            )
        filtered_deals = deals_df.copy()
        if sel_rfm != "Todos" and "rfm_segment" in filtered_deals.columns:
            filtered_deals = filtered_deals[filtered_deals["rfm_segment"] == sel_rfm]
        if sel_fam != "Todas" and "recommended_family" in filtered_deals.columns:
            filtered_deals = filtered_deals[filtered_deals["recommended_family"] == sel_fam]

        render_white_space_deals_table(filtered_deals, labels.customer)

    with col_br:
        section_header(
            "Top 5 Regras Apriori & Plano de Expansão",
            "Combos líderes e exportação da carteira filtrada",
        )
        render_top_apriori_rules_table(comm_dto.apriori_rules_df, rule_level=str(apriori_level))
        filt_rev = (
            float(filtered_deals["potential_revenue_brl"].sum())
            if not filtered_deals.empty and "potential_revenue_brl" in filtered_deals.columns
            else 0.0
        )
        filt_margin = (
            float(filtered_deals["potential_margin_brl"].sum())
            if not filtered_deals.empty and "potential_margin_brl" in filtered_deals.columns
            else 0.0
        )
        filt_custs = (
            int(filtered_deals["customer_id"].nunique())
            if not filtered_deals.empty and "customer_id" in filtered_deals.columns
            else len(filtered_deals)
        )
        scope_desc = (
            f"no segmento <b>{sel_rfm}</b>" if sel_rfm != "Todos" else "em <b>todos os segmentos RFM</b>"
        )
        render_prescription_box(
            title="Diretriz Comercial de Cross-Sell",
            recommendation_html=(
                f"Recorte atual ({scope_desc}): <b>{filt_custs} lojas</b> somam "
                f"<b>{format_brl(filt_rev, compact=True)}</b> em potencial incremental "
                f"com base nas regras Apriori e SKU âncora real (CAC zero)."
            ),
            impact_brl=filt_margin,
            action_hint="Exporte para os RCAs ou acione o cliente em 1 clique no WhatsApp.",
            help_text="Recalcula automaticamente conforme os filtros de Segmento RFM e Família.",
        )
        render_commercial_export_bar(
            comm_dto.priority_risk_df,
            filtered_deals,
            scenario_id=state.scenario_id,
            scenario_name=scenario_cfg.display_name,
            apriori_rules_df=comm_dto.apriori_rules_df,
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
            theme=None,
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
            theme=None,
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
                theme=None,
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
            st.plotly_chart(fig_quad, use_container_width=True, theme=None)
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
            theme=None,
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
