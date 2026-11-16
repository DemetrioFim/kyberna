from __future__ import annotations

import pandas as pd
import streamlit as st

from src.services.dto import ExecutivePageDTO, SimulationLevers, SimulationResult
from src.services.simulator import simulate
from src.ui.cache import cached_family_elasticity, cached_simulation_baseline
from src.ui.components.kpi_card import KpiAccent, render_kpi_card
from src.ui.components.simulator_charts import (
    profit_curve_chart,
    tornado_sensitivity_chart,
)
from src.ui.formatting import format_brl

_ALL_FAMILIES_OPT = "Todas as Famílias (Média)"


def _resolve_active_beta(elasticity_df: pd.DataFrame, selected_scope: str) -> tuple[float, str]:
    """Resolve o coeficiente beta ativo e seu rótulo de classificação."""
    if elasticity_df.empty:
        return -1.2, "Padrão (-1.20)"
    if selected_scope != _ALL_FAMILIES_OPT:
        match = elasticity_df[elasticity_df["family"] == selected_scope]
        if not match.empty:
            beta_val = float(match["beta_hat"].iloc[0])
            cls_label = str(match["elasticity_classification"].iloc[0])
            return beta_val, f"{cls_label} ({beta_val:.2f})"
    mean_beta = float(elasticity_df["beta_hat"].mean())
    cls_label = "Elástica" if mean_beta < -1.0 else "Inelástica"
    return mean_beta, f"Média {cls_label} ({mean_beta:.2f})"


def _render_simulator_kpis(res: SimulationResult, baseline_margin_pct: float) -> None:
    """Renderiza os 5 KPI Cards reativos do Simulador What-If (sem sub-abas)."""
    delta_pp = res.margin_pct_1 - baseline_margin_pct
    delta_accent: KpiAccent = (
        "green" if res.margin_delta_brl > 0 else "alert_neg" if res.margin_delta_brl < 0 else "teal"
    )
    be_str = (
        f"{res.breakeven_volume_change_pct:+.1f}%"
        if res.breakeven_volume_change_pct is not None
        else "Inviável"
    )

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        render_kpi_card(
            title="Receita Bruta Simulada",
            value=format_brl(res.gross_revenue_1, compact=True),
            subfooter_left=f"Volume β: {res.projected_volume_change_pct:+.1f}%",
            accent="teal",
            help_text="Faturamento bruto projetado considerando preço simulado e elasticidade de demanda.",
        )
    base_cm_str = format_brl(res.contribution_margin_1 - res.margin_delta_brl, compact=True)
    delta_prefix = "+" if res.margin_delta_brl > 0 else ""
    delta_cm_str = f"{delta_prefix}{format_brl(res.margin_delta_brl, compact=True)}"
    with c2:
        render_kpi_card(
            title="Margem Simulada",
            value=format_brl(res.contribution_margin_1, compact=True),
            subfooter_left=f"Base: {base_cm_str}",
            accent=delta_accent,
            help_text="Margem de contribuição líquida resultante após todas as alavancas ajustadas.",
        )
    with c3:
        render_kpi_card(
            title="Nova Margem Líquida %",
            value=f"{res.margin_pct_1:.1f}%",
            subfooter_left=f"Delta: {delta_pp:+.1f} pp",
            accent=delta_accent,
            help_text="Rentabilidade percentual sobre faturamento comparada ao cenário base.",
        )
    with c4:
        render_kpi_card(
            title="Impacto Direto no Lucro",
            value=delta_cm_str,
            subfooter_left=res.verdict,
            accent=delta_accent,
            help_text="Ganho ou perda líquida no bolso decorrente da combinação de alavancas.",
        )
    with c5:
        render_kpi_card(
            title="Equilíbrio vs. Projetado",
            value=be_str,
            subfooter_left=f"Volume proj. (β): {res.projected_volume_change_pct:+.1f}%",
            accent="brass",
            help_text="Variação mínima de volume para empatar o lucro comparada ao volume esperado via β.",
        )


def _render_breakeven_callout(res: SimulationResult) -> None:
    """Renderiza o card resumo de Margem Projetada, Impacto e Breakeven vs. Volume."""
    delta_color = (
        "var(--kyb-pos)"
        if res.margin_delta_brl > 0
        else "var(--kyb-neg)"
        if res.margin_delta_brl < 0
        else "var(--kyb-text-muted)"
    )
    delta_sign = "+" if res.margin_delta_brl > 0 else ""

    be_str = (
        f"{res.breakeven_volume_change_pct:+.1f}%"
        if res.breakeven_volume_change_pct is not None
        else "Inviável (m_unit ≤ 0)"
    )
    proj_str = f"{res.projected_volume_change_pct:+.1f}%"

    lbl_style = (
        'style="font-size: 0.74rem; font-weight: 700; text-transform: uppercase; '
        'letter-spacing: 0.04em; color: var(--kyb-text-muted); margin-bottom: 0.15rem;"'
    )
    card_html = (
        '<div style="background: var(--kyb-card-bg); border: 1px solid var(--kyb-border); '
        'border-radius: 8px; padding: 0.7rem 0.95rem; margin: 0.25rem 0 0.45rem 0;">'
        '<div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem;">'
        "<div>"
        f"<div {lbl_style}>Margem Projetada</div>"
        '<div style="font-size: 1.25rem; font-weight: 700; color: var(--kyb-text); line-height: 1.15;">'
        f"{format_brl(res.contribution_margin_1, compact=True)}</div>"
        f'<div style="font-size: 0.78rem; color: var(--kyb-text-muted); margin-top: 0.15rem;">'
        f"Receita: {format_brl(res.gross_revenue_1, compact=True)} • Margem: {res.margin_pct_1:.1f}%</div>"
        "</div>"
        '<div style="text-align: right;">'
        f"<div {lbl_style}>Impacto no Lucro</div>"
        f'<div style="font-size: 1.25rem; font-weight: 700; color: {delta_color}; line-height: 1.15;">'
        f"{delta_sign}{format_brl(res.margin_delta_brl, compact=True)}</div>"
        f'<div style="font-size: 0.76rem; color: {delta_color}; margin-top: 0.15rem; font-weight: 600;">'
        f"{res.verdict}</div>"
        "</div>"
        "</div>"
        '<div style="display: flex; justify-content: space-between; gap: 1rem; margin-top: 0.45rem; '
        "padding-top: 0.4rem; border-top: 1px dashed var(--kyb-border); font-size: 0.8rem; "
        'color: var(--kyb-text);">'
        f"<span><strong>Volume de Equilíbrio (Breakeven):</strong> {be_str}</span>"
        f"<span><strong>Volume Projetado (β):</strong> {proj_str}</span>"
        "</div>"
        "</div>"
    )
    st.markdown(card_html, unsafe_allow_html=True)


def _render_scenario_comparator(
    res: SimulationResult,
    *,
    scope_label: str,
    price_pct: float,
    discount_pp: float,
    cost_pct: float,
    comm_pp: float,
) -> None:
    """Gerencia e exibe até 3 cenários salvos na sessão para comparação lado a lado."""
    if "saved_simulations" not in st.session_state:
        st.session_state.saved_simulations = []

    saved: list[dict[str, str]] = st.session_state.saved_simulations
    c_save, c_clear = st.columns([1.0, 1.0])
    with c_save:
        if st.button("Salvar Cenário", key="sim_save_btn", use_container_width=True):
            entry = {
                "Cenário": f"C{len(saved) + 1} · {scope_label[:16]}",
                "Preço (%)": f"{price_pct:+.1f}%",
                "Desc. (pp)": f"{discount_pp:+.1f}",
                "CMV (%)": f"{cost_pct:+.1f}%",
                "Comiss. (pp)": f"{comm_pp:+.1f}",
                "Receita (R$)": format_brl(res.gross_revenue_1, compact=True),
                "Δ Margem (R$)": format_brl(res.margin_delta_brl, compact=True),
            }
            if len(saved) >= 3:
                saved.pop(0)
            saved.append(entry)
            st.session_state.saved_simulations = saved
    with c_clear:
        if st.button("Limpar Comparação", key="sim_clear_btn", use_container_width=True):
            st.session_state.saved_simulations = []

    if st.session_state.saved_simulations:
        st.dataframe(
            pd.DataFrame(st.session_state.saved_simulations),
            use_container_width=True,
            hide_index=True,
            height=120,
        )


@st.fragment
def render_what_if_quick_fragment(dto: ExecutivePageDTO, *, theme_mode: str = "light") -> None:
    """Fragmento prescritivo What-If com KPIs ao vivo, Curva Lucro x Preço e Tornado (sem sub-abas)."""
    elasticity_df = cached_family_elasticity(dto.scenario_id)
    family_opts = [_ALL_FAMILIES_OPT]
    if not elasticity_df.empty:
        family_opts.extend(elasticity_df["family"].astype(str).tolist())

    kpi_slot = st.container()
    c_ctrl, c_summary = st.columns([1.15, 1.0])
    with c_ctrl:
        c_scope, c_el = st.columns([1.35, 1.0])
        with c_scope:
            selected_scope = st.selectbox(
                "Escopo de Elasticidade",
                options=family_opts,
                key="sim_scope_family",
                label_visibility="collapsed",
            )
        beta_active, beta_badge = _resolve_active_beta(elasticity_df, str(selected_scope))
        with c_el:
            apply_elasticity = st.toggle(
                f"Elasticidade β: {beta_badge}",
                value=True,
                key="sim_use_elasticity",
            )

        c1, c2 = st.columns(2)
        with c1:
            price_delta = st.slider(
                "Ajuste de Preço (%)",
                min_value=-30.0,
                max_value=30.0,
                value=0.0,
                step=0.5,
                key="_what_if_price",
            )
            cost_delta = st.slider(
                "Variação Custo/CMV (%)",
                min_value=-25.0,
                max_value=25.0,
                value=0.0,
                step=0.5,
                key="_what_if_cost",
            )
        with c2:
            discount_delta = st.slider(
                "Variação no Desconto (p.p.)",
                min_value=-10.0,
                max_value=25.0,
                value=0.0,
                step=0.5,
                key="_what_if_disc",
            )
            comm_delta = st.slider(
                "Variação Comissão RCA (p.p.)",
                min_value=-5.0,
                max_value=5.0,
                value=0.0,
                step=0.5,
                key="sim_comm_pp",
            )

    baseline = cached_simulation_baseline(dto.kpis, beta_elasticity=beta_active)
    levers = SimulationLevers(
        delta_price_pct=float(price_delta) / 100.0,
        delta_discount_pp=float(discount_delta) / 100.0,
        delta_commission_pp=float(comm_delta) / 100.0,
        delta_cogs_pct=float(cost_delta) / 100.0,
        apply_elasticity=bool(apply_elasticity),
    )
    res = simulate(baseline, levers)

    with kpi_slot:
        _render_simulator_kpis(res, dto.kpis.contribution_margin_pct)

    with c_summary:
        _render_breakeven_callout(res)
        _render_scenario_comparator(
            res,
            scope_label=str(selected_scope),
            price_pct=float(price_delta),
            discount_pp=float(discount_delta),
            cost_pct=float(cost_delta),
            comm_pp=float(comm_delta),
        )

    c_chart_l, c_chart_r = st.columns(2)
    with c_chart_l:
        st.plotly_chart(
            profit_curve_chart(res, float(price_delta), theme_mode=theme_mode),
            use_container_width=True,
        )
    with c_chart_r:
        st.plotly_chart(
            tornado_sensitivity_chart(res.tornado_df, theme_mode=theme_mode),
            use_container_width=True,
        )
