from __future__ import annotations

import streamlit as st

from src.services.dto import ExecutivePageDTO, TemperancePageDTO
from src.services.inventory_dto import InventoryPageDTO
from src.ui.cache import (
    cached_executive_dashboard,
    cached_inventory_dashboard,
    cached_temperance_dashboard,
)
from src.ui.components.charts import family_margin_chart
from src.ui.components.inventory_charts import abc_xyz_heatmap
from src.ui.components.prescription import (
    render_cockpit_header,
    render_prescription_box,
    section_header,
)
from src.ui.components.prudence_admin_sections import (
    render_admin_inventory_kpis,
    render_admin_pcp_kpis,
    render_admin_portfolio_kpis,
    render_pcp_plan_table,
    render_sku_portfolio_table,
)
from src.ui.components.prudence_sections import render_prudence_anomalies_section
from src.ui.components.supply_charts import (
    sop_demand_vs_stock_chart,
    stockout_by_family_chart,
)
from src.ui.components.temperance_inventory_section import (
    render_locked_capital_treemap_tab,
    render_locked_inventory_table,
    render_sku_forecast_fragment,
    render_stockout_risk_table,
)
from src.ui.formatting import format_brl, format_int
from src.ui.state import AppState, get_app_state


def _render_tab_portfolio(
    exec_dto: ExecutivePageDTO,
    temp_dto: TemperancePageDTO,
    inv_dto: InventoryPageDTO,
    theme_mode: str,
) -> None:
    """Aba 1: Portfólio & Curva ABC/XYZ."""
    render_admin_portfolio_kpis(exec_dto, inv_dto)
    col_l, col_r = st.columns([1.05, 1.0])
    with col_l:
        section_header(
            "Matriz Estratégica ABC/XYZ 3x3",
            "Cruza relevância na margem (ABC) com previsibilidade semanal de demanda (XYZ)",
            help_text="A=80% da MC, B=15%, C=5% | X=regular, Y=sazonal, Z=intermitente.",
        )
        matrix_df = temp_dto.abc_xyz_summary_df.copy()
        if not matrix_df.empty and "recommended_policy" not in matrix_df.columns:
            matrix_df["recommended_policy"] = matrix_df["policy"]
        st.plotly_chart(
            abc_xyz_heatmap(matrix_df, theme_mode=theme_mode),
            use_container_width=True,
            theme=None,
        )
        st.markdown(
            "<div style='font-size:0.72rem; color:var(--kyb-text-muted); line-height:1.35; "
            "margin-top:-0.35rem; padding:0.2rem 0.45rem; background:var(--kyb-card-bg); "
            "border-radius:4px; border:1px solid var(--kyb-border);'>"
            "<strong>Legenda:</strong> <b>MC = Margem de Contribuição</b> (mais escuro = maior % da MC) "
            "&nbsp;|&nbsp; <b>ABC:</b> A=80% · B=15% · C=5% &nbsp;|&nbsp; "
            "<b>XYZ (Giro):</b> X=constante · Y=sazonal · Z=intermitente</div>",
            unsafe_allow_html=True,
        )
    with col_r:
        section_header(
            "Margem de Contribuição por Família",
            "Contribuição líquida gerada por cada linha de produto do catálogo",
            help_text="Compara geração absoluta de margem (R$) e rentabilidade (%) por família.",
        )
        st.plotly_chart(
            family_margin_chart(exec_dto.abc_xyz_skus_df, theme_mode=theme_mode),
            use_container_width=True,
            theme=None,
        )

    col_bl, col_br = st.columns([1.35, 1.0])
    with col_bl:
        section_header("Auditoria de Portfólio (SKUs)", "Desempenho detalhado por SKU")
        render_sku_portfolio_table(exec_dto)
    with col_br:
        section_header("Diretriz de Mix & Sortimento", "Racionalização da cauda longa CZ")
        render_prescription_box(
            title="Governança de Portfólio ABC/XYZ",
            recommendation_html=(
                "Priorizar disponibilidade integral nos itens <b>AX/AY</b> e converter itens "
                "<b>CZ</b> para venda sob encomenda, liberando espaço de armazenagem e giro."
            ),
            impact_brl=exec_dto.prescription_impact_brl,
            action_hint="Revise trimestralmente a cauda CZ com baixa recorrência.",
            help_text="Diretriz administrativa para otimização de estoque ativo e catálogo.",
        )


def _render_tab_inventory(
    temp_dto: TemperancePageDTO,
    inv_dto: InventoryPageDTO,
    theme_mode: str,
    *,
    is_scoped: bool = False,
) -> None:
    """Aba 2: Estoque, Ruptura & Capital Travado."""
    render_admin_inventory_kpis(temp_dto, inv_dto, is_scoped=is_scoped)
    col_l, col_r = st.columns([1.0, 1.0])
    with col_l:
        section_header(
            "Mapa de Capital Travado (>120d)",
            "Hierarquia Família -> SKU dos itens com excesso crônico de cobertura",
            help_text="Quanto maior o bloco, maior o capital imobilizado acima de 120 dias de giro.",
        )
        render_locked_capital_treemap_tab(inv_dto, theme_mode=theme_mode)
    with col_r:
        section_header(
            "Receita em Risco de Ruptura por Família",
            "Distribuição do faturamento 30d exposto abaixo do ROP entre Curva A e B/C",
            help_text="Conecta diretamente o risco de desabastecimento à fila de reposição abaixo.",
        )
        st.caption(
            f"Exposição (<ROP): **{format_brl(inv_dto.kpis.protected_revenue_brl)}** em "
            f"**{format_int(inv_dto.kpis.stockout_risk_skus_count)} SKUs** · "
            f"Curva A: **{format_int(inv_dto.kpis.stockout_curve_a_skus_count)} SKUs**"
        )
        st.plotly_chart(
            stockout_by_family_chart(inv_dto.family_supply_df, theme_mode=theme_mode),
            use_container_width=True,
            theme=None,
        )

    col_bl, col_br = st.columns([1.0, 1.05])
    with col_bl:
        section_header(
            "SKUs Imobilizados (>120d Cobertura)",
            "Alvos prioritários para campanhas de liquidação e combo",
            help_text="Liquidar 25% do excesso injeta caixa operacional imediato.",
        )
        render_locked_inventory_table(temp_dto)
    with col_br:
        section_header(
            "Ordem de Reposição (Ruptura Iminente)",
            "Itens abaixo do Ponto de Pedido com caixas master sugeridas",
            help_text="Prioridade imediata de compra/produção para evitar perda de faturamento.",
        )
        render_stockout_risk_table(temp_dto, inv_dto=inv_dto)


def _render_tab_pcp(
    state: AppState,
    exec_dto: ExecutivePageDTO,
    inv_dto: InventoryPageDTO,
) -> None:
    """Aba 3: Previsão de Demanda 30d & Planejamento PCP."""
    render_admin_pcp_kpis(inv_dto)
    col_l, col_r = st.columns([1.05, 1.0])
    with col_l:
        section_header(
            "Forecast Diário 30d por SKU (StatsForecast)",
            "Histórico recente (90d) + projeção estatística 30d com bandas IC 80%/95%",
            help_text="Seleção automática entre AutoETS e CrostonOptimized conforme intermitência.",
        )
        render_sku_forecast_fragment(state.scenario_id, inv_dto, theme_mode=state.theme_mode)
    with col_r:
        section_header(
            "Demanda Prevista 30d vs. Estoque Atual por Família",
            "Balanço físico S&OP entre saldo em armazém e saída projetada nos próximos 30 dias",
            help_text="Evidencia famílias onde a demanda prevista ultrapassa ou pressiona o estoque atual.",
        )
        tot_stock_u = (
            int(inv_dto.family_supply_df["stock_units"].sum()) if not inv_dto.family_supply_df.empty else 0
        )
        tot_fc_u = (
            int(inv_dto.family_supply_df["forecast_30d_units"].sum())
            if not inv_dto.family_supply_df.empty
            else 0
        )
        st.caption(
            f"Balanço S&OP: Estoque Atual **{format_int(tot_stock_u)} un** vs. "
            f"Demanda 30d Prevista **{format_int(tot_fc_u)} un**"
        )
        st.plotly_chart(
            sop_demand_vs_stock_chart(inv_dto.family_supply_df, theme_mode=state.theme_mode),
            use_container_width=True,
            theme=None,
        )

    col_bl, col_br = st.columns([1.05, 1.0])
    with col_bl:
        section_header(
            "Plano de Necessidade de Compra/Produção (por SKU)",
            "Agenda PCP priorizada por caixas master sugeridas e receita protegida",
            help_text="Lista de trabalho para compras e PCP considerando ROP, cobertura e demanda 30d.",
        )
        render_pcp_plan_table(inv_dto)
    with col_br:
        section_header(
            "Radar de Anomalias de Supply",
            "Alertas operacionais prioritários de ruptura Curva A, excesso >120d e S&OP",
            help_text="Sinais automáticos de operação e abastecimento que demandam ação imediata.",
        )
        render_prudence_anomalies_section(exec_dto)


def render_page() -> None:
    """Renderiza a Página 1 — 1. Prudência (Visão Administrativa & Operações) estilo PowerBI."""
    state = get_app_state()
    exec_dto = cached_executive_dashboard(
        state.scenario_id,
        regiao=state.regiao,
        uf=state.uf,
        families=state.families,
        sales_reps=state.sales_reps,
        selected_cell=state.selected_abc_xyz_cell,
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
        families=state.families,
        sales_reps=state.sales_reps,
        period_preset=state.period_preset,
        comparison_mode=state.comparison_mode,
        selected_month=state.selected_month,
        selected_quarter=state.selected_quarter,
        selected_semester=state.selected_semester,
        custom_start_date=state.custom_start_date,
        custom_end_date=state.custom_end_date,
    )
    inv_dto = cached_inventory_dashboard(state.scenario_id, families=state.families)
    is_inv_scoped = (
        state.regiao != "Todas"
        or state.uf != "Todas"
        or bool(state.sales_reps)
        or state.period_preset != "all"
    )
    rup_a_cnt = (
        inv_dto.kpis.stockout_curve_a_skus_count
        if inv_dto.kpis.stockout_curve_a_skus_count > 0
        else temp_dto.kpis.stockout_risk_skus_count
    )

    render_cockpit_header(
        title="Visão Administrativa & Operações",
        virtue_badge="1. Prudência",
        headline_title="Governança de Portfólio, Estoques & Planejamento PCP",
        headline_text=(
            f"<b>{len(exec_dto.abc_xyz_skus_df)} SKUs</b> ativos | "
            f"<b>{rup_a_cnt} SKUs Curva A</b> em ruptura "
            f"({inv_dto.kpis.stockout_risk_skus_count} abaixo ROP) e "
            f"<b>{format_brl(inv_dto.kpis.locked_capital_brl, compact=True)}</b> imobilizados (>120d)."
        ),
        as_of_date_label=exec_dto.as_of_date_label,
        comparison_label=exec_dto.comparison_label,
        help_text=(
            "Painel administrativo estilo PowerBI 100% operacional: Portfólio ABC/XYZ, "
            "Gestão de Estoque/Ruptura e Previsão de Demanda 30d & PCP."
        ),
    )

    tab_port, tab_inv, tab_pcp = st.tabs(
        [
            "Portfólio & Curva ABC/XYZ",
            "Estoque, Ruptura & Capital Travado",
            "Previsão de Demanda 30d & PCP",
        ]
    )
    with tab_port:
        _render_tab_portfolio(exec_dto, temp_dto, inv_dto, state.theme_mode)
    with tab_inv:
        _render_tab_inventory(temp_dto, inv_dto, state.theme_mode, is_scoped=is_inv_scoped)
    with tab_pcp:
        _render_tab_pcp(state, exec_dto, inv_dto)


render_page()
