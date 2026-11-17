from __future__ import annotations

import pandas as pd
import streamlit as st

from src.services.dto import ExecutivePageDTO, TemperancePageDTO
from src.services.inventory_dto import InventoryPageDTO
from src.ui.cache import (
    cached_executive_dashboard,
    cached_inventory_dashboard,
    cached_temperance_dashboard,
)
from src.ui.components.charts import family_margin_chart
from src.ui.components.inventory_charts import abc_xyz_heatmap, erosion_breakdown_chart
from src.ui.components.prescription import (
    render_cockpit_header,
    render_prescription_box,
    section_header,
)
from src.ui.components.prudence_admin_sections import (
    family_policy_violations_chart,
    render_admin_demand_policy_kpis,
    render_admin_inventory_kpis,
    render_admin_portfolio_kpis,
    render_sku_portfolio_table,
)
from src.ui.components.prudence_sections import render_prudence_anomalies_section
from src.ui.components.temperance_inventory_section import (
    render_locked_capital_treemap_tab,
    render_locked_inventory_table,
    render_sku_forecast_fragment,
    render_stockout_risk_table,
)
from src.ui.formatting import format_brl
from src.ui.state import AppState, get_app_state


def _render_family_policy_table(df: pd.DataFrame) -> None:
    """Tabela direta de desvios de política de desconto por família (sem sub-abas)."""
    if df.empty:
        st.info("Nenhuma violação de política identificada por família.")
        return
    cols = ["family", "total_orders", "gross_revenue", "avg_discount_pct", "excess_discount_brl"]
    view = df[[c for c in cols if c in df.columns]].rename(
        columns={
            "family": "Família",
            "total_orders": "Pedidos",
            "gross_revenue": "Faturamento (R$)",
            "avg_discount_pct": "Desc. Médio %",
            "excess_discount_brl": "Excesso Fora do Teto (R$)",
        }
    )
    st.dataframe(
        view,
        use_container_width=True,
        hide_index=True,
        height=185,
        column_config={
            "Faturamento (R$)": st.column_config.NumberColumn(format="R$ %,.2f"),
            "Desc. Médio %": st.column_config.NumberColumn(format="%.1f%%"),
            "Excesso Fora do Teto (R$)": st.column_config.NumberColumn(format="R$ %,.2f"),
        },
    )


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
        st.plotly_chart(abc_xyz_heatmap(matrix_df, theme_mode=theme_mode), use_container_width=True)
        st.markdown(
            "<div style='font-size:0.72rem; color:var(--kyb-text-muted); line-height:1.35; "
            "margin-top:-0.35rem; padding:0.2rem 0.45rem; background:var(--kyb-card-bg); "
            "border-radius:4px; border:1px solid var(--kyb-border);'>"
            "<strong>Legenda:</strong> <b>ABC (Lucro):</b> A=80% · B=15% · C=5% &nbsp;|&nbsp; "
            "<b>XYZ (Giro):</b> X=constante · Y=sazonal · Z=intermitente</div>",
            unsafe_allow_html=True,
        )
    with col_r:
        section_header(
            "Margem de Contribuição por Família",
            "Contribuição líquida gerada por cada linha de produto do catálogo",
            help_text="Compara geração absoluta de lucro (R$) e rentabilidade (%) por família.",
        )
        st.plotly_chart(
            family_margin_chart(exec_dto.abc_xyz_skus_df, theme_mode=theme_mode),
            use_container_width=True,
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
) -> None:
    """Aba 2: Estoque, Ruptura & Capital Travado."""
    render_admin_inventory_kpis(temp_dto, inv_dto)
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
            "Decomposição de Custos & Erosão Operacional",
            "Distribuição de vazamentos comerciais e logísticos sobre a receita",
            help_text="Evidencia onde a margem operacional escapa antes de chegar ao caixa.",
        )
        st.plotly_chart(
            erosion_breakdown_chart(temp_dto.kpis, theme_mode=theme_mode), use_container_width=True
        )

    col_bl, col_br = st.columns([1.05, 1.0])
    with col_bl:
        section_header(
            "Ordem de Reposição (Ruptura Iminente)",
            "Itens abaixo do Ponto de Pedido com caixas master sugeridas",
            help_text="Prioridade imediata de compra/produção para evitar perda de faturamento.",
        )
        render_stockout_risk_table(temp_dto, inv_dto=inv_dto)
    with col_br:
        section_header(
            "SKUs Imobilizados (>120d Cobertura)",
            "Alvos prioritários para campanhas de liquidação e combo",
            help_text="Liquidar 25% do excesso injeta caixa operacional imediato.",
        )
        render_locked_inventory_table(temp_dto)


def _render_tab_forecast_policy(
    state: AppState,
    exec_dto: ExecutivePageDTO,
    temp_dto: TemperancePageDTO,
    inv_dto: InventoryPageDTO,
) -> None:
    """Aba 3: Previsão de Demanda 30d & Alçadas."""
    render_admin_demand_policy_kpis(exec_dto, temp_dto, inv_dto)
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
            "Descontos Fora do Teto por Família",
            "Excesso financeiro concedido acima das alçadas por linha de produto",
            help_text=(
                "Ranqueia as famílias com maior concessão de descontos acima do teto autorizado "
                "(P=3%, M=6,5%, G=10,5%)."
            ),
        )
        st.plotly_chart(
            family_policy_violations_chart(
                temp_dto.policy_violations_by_family_df, theme_mode=state.theme_mode
            ),
            use_container_width=True,
        )

    col_bl, col_br = st.columns([1.05, 1.0])
    with col_bl:
        section_header(
            "Auditoria de Alçadas por Família",
            "Concessão de descontos médios e excesso acima do teto por linha",
            help_text="Aponta quais famílias estão sofrendo maior erosão de tabela comercial.",
        )
        _render_family_policy_table(temp_dto.policy_violations_by_family_df)
    with col_br:
        section_header(
            "Radar de Anomalias Operacionais",
            "Alertas prioritários de desvio de margem e exceções semanais",
            help_text="Sinais automáticos que demandam verificação administrativa imediata.",
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

    render_cockpit_header(
        title="Visão Administrativa & Operações",
        virtue_badge="1. Prudência",
        headline_title="Governança de Portfólio, Estoques & Alçadas",
        headline_text=(
            f"<b>{len(exec_dto.abc_xyz_skus_df)} SKUs</b> ativos | "
            f"<b>{inv_dto.kpis.stockout_risk_skus_count} SKUs</b> em ruptura iminente e "
            f"<b>{format_brl(temp_dto.kpis.locked_capital_brl, compact=True)}</b> imobilizados (>120d)."
        ),
        as_of_date_label=exec_dto.as_of_date_label,
        help_text=(
            "Painel administrativo estilo PowerBI com 3 páginas temáticas: Portfólio ABC/XYZ, "
            "Gestão de Estoque/Ruptura e Previsão de Demanda 30d & Alçadas."
        ),
    )

    tab_port, tab_inv, tab_fc = st.tabs(
        [
            "Portfólio & Curva ABC/XYZ",
            "Estoque, Ruptura & Capital Travado",
            "Previsão de Demanda 30d & Alçadas",
        ]
    )
    with tab_port:
        _render_tab_portfolio(exec_dto, temp_dto, inv_dto, state.theme_mode)
    with tab_inv:
        _render_tab_inventory(temp_dto, inv_dto, state.theme_mode)
    with tab_fc:
        _render_tab_forecast_policy(state, exec_dto, temp_dto, inv_dto)


render_page()
