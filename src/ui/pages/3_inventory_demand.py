from __future__ import annotations

import streamlit as st

from src.core.scenarios import load_scenario_config
from src.ui.cache import cached_temperance_dashboard
from src.ui.components.charts import abc_xyz_heatmap, waterfall_margin
from src.ui.components.prescription import section_header
from src.ui.components.temperance_inventory_section import (
    render_locked_inventory_table,
    render_stockout_risk_table,
)
from src.ui.components.temperance_sections import (
    render_policy_violations_tabs,
    render_temperance_banner,
    render_temperance_headline,
    render_temperance_kpi_cards,
    render_temperance_verdict_section,
    render_violations_rep_chart,
)
from src.ui.state import get_app_state


def render_page() -> None:
    """Renderiza a Página 4 — Temperança em formato Cockpit Z-Pattern (1080p sem scroll)."""
    state = get_app_state()
    scenario_cfg = load_scenario_config(state.scenario_id)
    theme_mode = state.theme_mode

    # 1. Faixa 1 — Topo (Status em 5s): Título + Subtítulo + Manchete + 5 KPI Cards
    st.title("Eficiência Operacional & Capital de Giro")
    st.caption(
        f"Auditoria de erosão comercial, disciplina de descontos e destravamento de capital em estoque: "
        f"**{scenario_cfg.display_name}** ({scenario_cfg.company_profile})."
    )

    dto = cached_temperance_dashboard(
        state.scenario_id,
        regiao=state.regiao,
        uf=state.uf,
        families=tuple(state.families),
        sales_reps=tuple(state.sales_reps),
    )

    render_temperance_banner(dto)
    render_temperance_headline(dto)
    render_temperance_kpi_cards(dto)

    # 2. Faixa 2 — Meio (Diagnóstico Visual em 2 Colunas lado a lado)
    col_diag_left, col_diag_right = st.columns([1.0, 1.0])

    with col_diag_left:
        section_header(
            "Decomposição da Margem Real",
            "Do faturamento bruto até o lucro líquido no bolso com % de perda em cada degrau",
            help_text="Deduções da receita bruta. As barras exibem o valor e a % do faturamento bruto.",
        )
        t_wat, t_rep = st.tabs(["Waterfall da Margem Real", "Top RCAs por Desconto Fora do Teto"])
        with t_wat:
            fig_wat = waterfall_margin(dto.waterfall_df, theme_mode=theme_mode)
            st.plotly_chart(fig_wat, use_container_width=True)
        with t_rep:
            if not dto.policy_violations_by_rep_df.empty:
                fig_rep = render_violations_rep_chart(dto.policy_violations_by_rep_df, theme_mode=theme_mode)
                st.plotly_chart(fig_rep, use_container_width=True)
            else:
                st.info("Nenhuma violação de política comercial identificada.")

    with col_diag_right:
        section_header(
            "Gestão Prescritiva de Estoque",
            "Matriz 3x3 ABC/XYZ cruzada com controle de capital imobilizado",
            help_text="Cruza contribuição na margem (ABC) com a regularidade semanal da demanda (XYZ).",
        )
        matrix_df = dto.abc_xyz_summary_df.copy()
        if not matrix_df.empty and "recommended_policy" not in matrix_df.columns:
            matrix_df["recommended_policy"] = matrix_df["policy"]
        fig_abc = abc_xyz_heatmap(matrix_df, theme_mode=theme_mode)
        st.plotly_chart(fig_abc, use_container_width=True)

    # 3. Faixa 3 — Base (Detalhamento & Ação em 2 Colunas lado a lado)
    col_act_left, col_act_right = st.columns([1.35, 1.0])

    with col_act_left:
        section_header(
            "Auditoria de Política Comercial & Estoque",
            "Ações imediatas para estancar sangrias e destravar capital",
            help_text="Detalhamento operacional de estoques e auditoria de políticas comerciais.",
        )
        t_rup, t_lock, t_audit = st.tabs(
            [
                f"🚨 Ruptura Iminente ({dto.kpis.stockout_risk_skus_count} SKUs)",
                f"🛑 Capital Travado >120d ({dto.kpis.locked_skus_count} SKUs)",
                "Auditoria de Política Comercial",
            ]
        )
        with t_rup:
            render_stockout_risk_table(dto)
        with t_lock:
            render_locked_inventory_table(dto)
        with t_audit:
            render_policy_violations_tabs(dto)

    with col_act_right:
        section_header(
            "Veredito de Temperança",
            "Diagnóstico prescritivo e quantificação de recuperação",
            help_text="Cálculo consolidado de impacto financeiro no caixa operacional.",
        )
        render_temperance_verdict_section(dto)


render_page()
