from __future__ import annotations

from collections.abc import Callable
from typing import Any

import streamlit as st

from src.core.types import ScenarioId
from src.services.pricing_dto import PricingPageDTO
from src.ui.cache import cached_pricing_dashboard, cached_pricing_shap
from src.ui.components.kpi_card import KpiAccent, render_kpi_card
from src.ui.components.prescription import render_prescription_box, section_header
from src.ui.components.pricing_charts import (
    UnitMode,
    price_band_boxplot_chart,
    pricing_shap_waterfall_chart,
)
from src.ui.formatting import fmt_brl_cell, fmt_pct_cell, format_brl, get_delta_html
from src.ui.state import AppState


def render_pricing_kpis(pricing_dto: PricingPageDTO) -> None:
    """Renderiza os 5 KPIs da Aba 3 de 3. Justiça (Precificação, Banda & SHAP)."""
    k = pricing_dto.kpis
    below_acc: KpiAccent = "alert_neg" if k.below_band_sales_pct >= 20.0 else "alert_warn"

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        render_kpi_card(
            title="Índice de Realização",
            value=f"{k.realization_index_pct:.1f}%",
            subfooter_left=f"{k.skus_count} SKUs · {k.orders_count} pedidos",
            delta_html=get_delta_html(k.realization_idx_delta_pp, kind="pp"),
            accent="teal",
            help_text=(
                "Relação média entre o preço líquido praticado e o preço base de tabela "
                "(100% = tabela cheia)."
            ),
        )
    with c2:
        render_kpi_card(
            title="Dispersão de Preço (CV%)",
            value=f"{k.price_cv_pct:.1f}%",
            subfooter_left="Variabilidade entre clientes/pedidos",
            delta_html=get_delta_html(k.price_cv_delta_pp, kind="pp", invert_color=True),
            accent="brass",
            help_text=(
                "Coeficiente de variação do índice de preço realizado. Dispersão elevada sem lastro "
                "indica falta de governança comercial."
            ),
        )
    with c3:
        render_kpi_card(
            title="Vendas Abaixo da Banda",
            value=f"{k.below_band_sales_pct:.1f}%",
            subfooter_left="Pedidos abaixo do piso P25",
            delta_html=get_delta_html(k.below_band_delta_pp, kind="pp", invert_color=True),
            accent=below_acc,
            help_text=(
                "Percentual de linhas faturadas abaixo do limite inferior (P25) previsto pela regressão "
                "quantílica para porte, volume e frete."
            ),
        )
    with c4:
        render_kpi_card(
            title="Vazamento Subprecificação",
            value=format_brl(k.subpricing_leakage_brl, compact=True, decimals=1),
            subfooter_left="Perda abaixo do piso contextual",
            delta_html=get_delta_html(k.subpricing_leakage_delta_pct, kind="pct", invert_color=True),
            accent="alert_neg",
            help_text=(
                "Soma financeira das vendas realizadas abaixo da banda justa P25 sem contrapartida "
                "de volume ou prazo curto."
            ),
        )
    with c5:
        render_kpi_card(
            title="Potencial Reajuste (Inelást.)",
            value=format_brl(k.inelastic_reprice_upside_brl, compact=True, decimals=1),
            subfooter_left="Upside anual em famílias |β| < 1",
            delta_html=get_delta_html(k.inelastic_upside_delta_pct, kind="pct"),
            accent="green" if k.inelastic_reprice_upside_brl > 0 else "teal",
            help_text=(
                "Ganho anualizado estimado ao recompor preços de SKUs inelásticos até o esperado "
                "contextual sem perda relevante de giro."
            ),
        )


@st.fragment
def render_pricing_shap_fragment(
    scenario_id: ScenarioId,
    pricing_dto: PricingPageDTO,
    *,
    state: AppState | None = None,
    unit_mode: UnitMode = "pct",
    theme_mode: str = "light",
) -> None:
    """Fragmento reativo com seletor de Família/SKU e SHAP Waterfall de Formação de Preço."""
    opts_df = pricing_dto.shap_options_df
    if opts_df.empty:
        st.info("Decomposição SHAP ainda não disponível para os filtros atuais.")
        return

    keys: list[str] = []
    labels_map: dict[str, str] = {}
    for scope_type, scope_id, scope_label, gap_pp in zip(
        opts_df["scope_type"],
        opts_df["scope_id"],
        opts_df["scope_label"],
        opts_df["unjustified_gap_pp"],
        strict=False,
    ):
        key_val = f"{scope_type}::{scope_id}"
        prefix = "Família" if str(scope_type) == "family" else "SKU"
        keys.append(key_val)
        labels_map[key_val] = f"[{prefix}] {scope_label} (Gap: {float(gap_pp):+.1f} pp)"

    selected_key = st.selectbox(
        "Escopo SHAP de Preço",
        options=keys,
        format_func=lambda k_val: labels_map.get(str(k_val), str(k_val)),
        key="pricing_shap_scope_select",
        label_visibility="collapsed",
    )
    sel_type, sel_id = str(selected_key).split("::", maxsplit=1)
    shap_dto = cached_pricing_shap(
        scenario_id,
        scope_type=sel_type,
        scope_id=sel_id,
        regiao=state.regiao if state is not None else "Todas",
        uf=state.uf if state is not None else "Todas",
        families=tuple(state.families) if state is not None else (),
        sales_reps=tuple(state.sales_reps) if state is not None else (),
        period_preset=state.period_preset if state is not None else "all",
        comparison_mode=state.comparison_mode if state is not None else "pop",
        selected_month=state.selected_month if state is not None else None,
        selected_quarter=state.selected_quarter if state is not None else "2024-Q4",
        selected_semester=state.selected_semester if state is not None else "2024-S2",
        custom_start_date=state.custom_start_date if state is not None else None,
        custom_end_date=state.custom_end_date if state is not None else None,
    )

    gap_color = "var(--kyb-neg)" if shap_dto.unjustified_gap_pp < -0.5 else "var(--kyb-pos)"
    if unit_mode == "brl" and shap_dto.table_gross_brl > 0.0:
        exp_txt = format_brl(shap_dto.expected_net_brl, compact=True, decimals=1)
        real_txt = format_brl(shap_dto.realized_net_brl, compact=True, decimals=1)
        gap_txt = format_brl(shap_dto.unjustified_gap_brl, compact=True, decimals=1)
        if shap_dto.unjustified_gap_brl > 0:
            gap_txt = f"+{gap_txt}"
    else:
        exp_txt = f"{shap_dto.expected_idx:.1f}%"
        real_txt = f"{shap_dto.realized_idx:.1f}%"
        gap_txt = f"{shap_dto.unjustified_gap_pp:+.2f} pp"

    st.markdown(
        "<div style='font-size:0.78rem; color:var(--kyb-text-muted); margin-bottom:0.2rem;'>"
        f"Esperado (Modelo): <strong>{exp_txt}</strong> · "
        f"Praticado: <strong>{real_txt}</strong> · "
        f"Resíduo s/ lastro: <strong style='color:{gap_color};'>{gap_txt}</strong></div>",
        unsafe_allow_html=True,
    )
    st.plotly_chart(
        pricing_shap_waterfall_chart(shap_dto, unit_mode=unit_mode, theme_mode=theme_mode),
        use_container_width=True,
        theme=None,
    )


def _render_shap_panel(
    state: AppState,
    *,
    sel_type: str,
    sel_id: str,
    unit_mode: UnitMode,
) -> None:
    """Renderiza o painel direito de Drivers SHAP com resumo financeiro/percentual."""
    if not sel_type:
        st.info("Decomposição SHAP ainda não disponível para os filtros atuais.")
        return
    shap_dto = cached_pricing_shap(
        state.scenario_id,
        scope_type=sel_type,
        scope_id=sel_id,
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
    gap_color = "var(--kyb-neg)" if shap_dto.unjustified_gap_pp < -0.5 else "var(--kyb-pos)"
    if unit_mode == "brl" and shap_dto.table_gross_brl > 0.0:
        exp_txt = format_brl(shap_dto.expected_net_brl, compact=True, decimals=1)
        real_txt = format_brl(shap_dto.realized_net_brl, compact=True, decimals=1)
        gap_txt = format_brl(shap_dto.unjustified_gap_brl, compact=True, decimals=1)
        if shap_dto.unjustified_gap_brl > 0:
            gap_txt = f"+{gap_txt}"
    else:
        exp_txt = f"{shap_dto.expected_idx:.1f}%"
        real_txt = f"{shap_dto.realized_idx:.1f}%"
        gap_txt = f"{shap_dto.unjustified_gap_pp:+.2f} pp"

    st.markdown(
        "<div style='font-size:0.78rem; color:var(--kyb-text-muted); margin-bottom:0.15rem;'>"
        f"Escopo: <strong>{shap_dto.scope_label}</strong> · "
        f"Esperado: <strong>{exp_txt}</strong> · "
        f"Praticado: <strong>{real_txt}</strong> · "
        f"Resíduo: <strong style='color:{gap_color};'>{gap_txt}</strong></div>",
        unsafe_allow_html=True,
    )
    st.plotly_chart(
        pricing_shap_waterfall_chart(shap_dto, unit_mode=unit_mode, theme_mode=state.theme_mode),
        use_container_width=True,
        theme=None,
    )


@st.fragment
def render_pricing_analytics_fragment(state: AppState, pricing_dto: PricingPageDTO) -> None:
    """Faixa 2 da Aba 3 de Justiça com filtro de escopo unificado (Boxplot + SHAP) e toggle R$."""
    opts_df = pricing_dto.shap_options_df
    keys: list[str] = ["all::portfolio"]
    labels_map: dict[str, str] = {"all::portfolio": "[Portfólio] Todas as Famílias (Visão Geral)"}
    scope_family_map: dict[str, str] = {}

    if not opts_df.empty:
        for scope_type, scope_id, scope_label, fam_val, gap_pp in zip(
            opts_df["scope_type"],
            opts_df["scope_id"],
            opts_df["scope_label"],
            opts_df["family"],
            opts_df["unjustified_gap_pp"],
            strict=False,
        ):
            key_val = f"{scope_type}::{scope_id}"
            prefix = "Família" if str(scope_type) == "family" else "SKU"
            keys.append(key_val)
            labels_map[key_val] = f"[{prefix}] {scope_label} (Gap: {float(gap_pp):+.1f} pp)"
            scope_family_map[key_val] = str(fam_val)

    st.markdown("<div style='height:0.45rem;'></div>", unsafe_allow_html=True)
    c_scope, c_toggle = st.columns([1.85, 0.85], vertical_alignment="center")
    with c_scope:
        selected_key = st.selectbox(
            "Escopo de Precificação (Boxplot e SHAP)",
            options=keys,
            format_func=lambda k_val: labels_map.get(str(k_val), str(k_val)),
            key="pricing_shap_scope_select",
            label_visibility="collapsed",
        )
    with c_toggle:
        show_brl = st.toggle(
            "Exibir em R$ Absoluto",
            value=False,
            key="pricing_unit_mode_toggle",
            help="Alterna Boxplot (R$/un.) e SHAP Waterfall (R$ no recorte) entre % da Tabela e R$.",
        )
    unit_mode: UnitMode = "brl" if show_brl else "pct"

    sel_key_str = str(selected_key)
    active_boxplot_df = pricing_dto.boxplot_df
    if sel_key_str == "all::portfolio":
        sel_type = str(opts_df["scope_type"].iloc[0]) if not opts_df.empty else ""
        sel_id = str(opts_df["scope_id"].iloc[0]) if not opts_df.empty else ""
    else:
        sel_type, sel_id = sel_key_str.split("::", maxsplit=1)
        target_fam = scope_family_map.get(sel_key_str, "")
        if target_fam:
            scoped_dto = cached_pricing_dashboard(
                state.scenario_id,
                regiao=state.regiao,
                uf=state.uf,
                families=(target_fam,),
                sales_reps=tuple(state.sales_reps),
                period_preset=state.period_preset,
                comparison_mode=state.comparison_mode,
                selected_month=state.selected_month,
                selected_quarter=state.selected_quarter,
                selected_semester=state.selected_semester,
                custom_start_date=state.custom_start_date,
                custom_end_date=state.custom_end_date,
            )
            if not scoped_dto.boxplot_df.empty:
                active_boxplot_df = scoped_dto.boxplot_df

    col_l, col_r = st.columns([1.0, 1.05])
    with col_l:
        section_header(
            "Banda de Preço Realizado vs. Contextual (Boxplot)",
            "Dispersão real (P05-P95) sobre a banda justa [P25-P75] e piso de 15% MC",
            help_text=(
                "Vendas abaixo da faixa verde translúcida ocorreram abaixo do esperado para porte, "
                "volume e frete regionais."
            ),
        )
        if not active_boxplot_df.empty:
            med_val = (
                format_brl(float(active_boxplot_df["p50_brl"].mean()))
                if unit_mode == "brl" and "p50_brl" in active_boxplot_df.columns
                else f"{float(active_boxplot_df['p50'].mean()):.1f}%"
            )
            leak_sum = float(active_boxplot_df["price_leakage_brl"].sum())
            leak_val = format_brl(leak_sum, compact=True, decimals=1)
            box_scope = (
                scope_family_map.get(sel_key_str, "Portfólio")
                if sel_key_str != "all::portfolio"
                else "Todas as Famílias"
            )
            st.markdown(
                "<div style='font-size:0.78rem; color:var(--kyb-text-muted); margin-bottom:0.15rem;'>"
                f"Escopo: <strong>{box_scope}</strong> · Mediana: <strong>{med_val}</strong> · "
                f"Vazamento: <strong style='color:var(--kyb-neg);'>{leak_val}</strong></div>",
                unsafe_allow_html=True,
            )
        st.plotly_chart(
            price_band_boxplot_chart(active_boxplot_df, unit_mode=unit_mode, theme_mode=state.theme_mode),
            use_container_width=True,
            theme=None,
        )
    with col_r:
        section_header(
            "Drivers de Preço — SHAP Waterfall (Regressão)",
            "Decomposição exata da tabela base até o preço esperado vs. praticado real",
            help_text=(
                "Explica quanto do desconto decorre de contrapartidas legítimas e escancara o "
                "resíduo sem lastro comercial."
            ),
        )
        _render_shap_panel(state, sel_type=sel_type, sel_id=sel_id, unit_mode=unit_mode)


def render_pricing_deviations_table(pricing_dto: PricingPageDTO) -> None:
    """Renderiza a Auditoria de Desvios de Preço (Fora da Banda) em pt-BR."""
    df = pricing_dto.deviations_df
    if df.empty:
        st.info("Nenhum desvio crítico abaixo da banda contextual nos filtros atuais.")
        return

    work = df.head(30).copy()
    work["band_range"] = [
        f"{float(lo):.1f}% - {float(hi):.1f}%"
        for lo, hi in zip(work["contextual_band_low_idx"], work["contextual_band_high_idx"], strict=False)
    ]
    cols_src = [
        "product_name",
        "family",
        "realized_idx_mean",
        "band_range",
        "price_leakage_brl",
        "primary_offender_rep",
    ]
    view = work[cols_src].rename(
        columns={
            "product_name": "SKU",
            "family": "Família",
            "realized_idx_mean": "Realiz. %",
            "band_range": "Banda [P25-P75]",
            "price_leakage_brl": "Vazamento (R$)",
            "primary_offender_rep": "RCA Ofensor",
        }
    )
    fmt_map: dict[Any, str | Callable[[object], str] | None] = {
        "Realiz. %": fmt_pct_cell,
        "Vazamento (R$)": fmt_brl_cell,
    }
    st.dataframe(
        view.style.format(fmt_map),
        use_container_width=True,
        hide_index=True,
        height=185,
        column_config={
            "SKU": st.column_config.TextColumn("SKU", width="medium"),
            "Realiz. %": st.column_config.TextColumn("Realiz. %", width="small"),
            "RCA Ofensor": st.column_config.TextColumn("RCA Ofensor", width="small"),
        },
    )


def render_pricing_verdict_section(pricing_dto: PricingPageDTO) -> None:
    """Renderiza o Veredito de Política de Preços com impacto quantificado."""
    render_prescription_box(
        title=pricing_dto.prescription_title,
        recommendation_html=pricing_dto.prescription_html,
        impact_brl=pricing_dto.prescription_impact_brl,
        action_hint="Trave alçadas fora da banda P25 e simule reajustes inelásticos na 4. Temperança.",
        help_text="Estimativa de recuperação de margem contendo subprecificação sem contrapartida.",
    )
