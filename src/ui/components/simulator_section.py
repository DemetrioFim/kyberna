from __future__ import annotations

import pandas as pd
import streamlit as st

from src.services.dto import ExecutivePageDTO, SimulationLevers, SimulationResult
from src.services.simulator import simulate
from src.ui.cache import cached_family_elasticity, cached_simulation_baseline
from src.ui.components.simulator_charts import (
    profit_curve_chart,
    tornado_sensitivity_chart,
)
from src.ui.components.simulator_controls import (
    ALL_FAMILIES_OPT,
    NO_SKU_OPT,
    build_sku_band_options,
    render_breakeven_callout,
    render_scenario_comparator,
    render_simulator_kpis,
    resolve_active_band,
    resolve_active_beta,
)
from src.ui.formatting import format_brl


def _render_simulator_charts(
    res: SimulationResult,
    *,
    price_delta: float,
    band_low_frac: float,
    band_high_frac: float,
    band_caption: str,
    theme_mode: str,
) -> None:
    """Renderiza Curva Lucro x Preço com Banda Ideal e gráfico Tornado."""
    c_chart_l, c_chart_r = st.columns(2)
    with c_chart_l:
        st.plotly_chart(
            profit_curve_chart(
                res,
                price_delta,
                band_low_pct=band_low_frac * 100.0 if band_caption else None,
                band_high_pct=band_high_frac * 100.0 if band_caption else None,
                theme_mode=theme_mode,
            ),
            use_container_width=True,
            theme=None,
        )
        if res.is_outside_band and band_caption:
            st.markdown(
                "<div style='font-size:0.75rem; color:var(--kyb-neg); "
                "font-weight:600; margin-top:-0.25rem;'>"
                f"Fora da Banda Ideal ({band_caption}): "
                "risco competitivo ou erosão abaixo do piso contextual."
                "</div>",
                unsafe_allow_html=True,
            )
        elif abs(res.optimal_price_change_pct) >= 0.249 and not band_caption:
            st.markdown(
                "<div style='font-size:0.73rem; color:var(--kyb-text-muted); margin-top:-0.25rem;'>"
                "Ótimo matemático no teto da grade "
                f"(<strong>{res.optimal_price_change_pct * 100.0:+.0f}%</strong>): "
                "validar teto competitivo de mercado antes de reajustar."
                "</div>",
                unsafe_allow_html=True,
            )
    with c_chart_r:
        st.plotly_chart(
            tornado_sensitivity_chart(res.tornado_df, theme_mode=theme_mode),
            use_container_width=True,
            theme=None,
        )


@st.fragment
def render_what_if_quick_fragment(
    dto: ExecutivePageDTO,
    *,
    family_bands_df: pd.DataFrame | None = None,
    sku_deviations_df: pd.DataFrame | None = None,
    theme_mode: str = "light",
) -> None:
    """Fragmento prescritivo What-If conectado à Banda Ideal de Preço (sem sub-abas)."""
    elasticity_df = cached_family_elasticity(dto.scenario_id)
    family_opts = [ALL_FAMILIES_OPT]
    if not elasticity_df.empty:
        family_opts.extend(elasticity_df["family"].astype(str).tolist())

    sku_map = build_sku_band_options(sku_deviations_df)
    sku_opts = list(sku_map.keys()) if sku_map else [NO_SKU_OPT]

    kpi_slot = st.container()
    c_ctrl, c_summary = st.columns([1.15, 1.0])
    with c_ctrl:
        scope_mode = st.radio(
            "Modo de Escopo",
            options=["Macro por Família", "Tático por SKU"],
            horizontal=True,
            key="sim_scope_mode",
            label_visibility="collapsed",
        )
        c_scope, c_el = st.columns([1.35, 1.0])
        selected_family = ALL_FAMILIES_OPT
        selected_sku = NO_SKU_OPT
        with c_scope:
            if scope_mode == "Macro por Família":
                selected_family = str(
                    st.selectbox(
                        "Escopo de Elasticidade",
                        options=family_opts,
                        key="sim_scope_family",
                        label_visibility="collapsed",
                    )
                )
            else:
                selected_sku = str(
                    st.selectbox(
                        "Escopo Tático por SKU",
                        options=sku_opts,
                        key="sim_scope_sku",
                        label_visibility="collapsed",
                    )
                )

        band_low_frac, band_high_frac, active_family, band_caption = resolve_active_band(
            family_bands_df,
            sku_map,
            scope_mode=str(scope_mode),
            selected_family=selected_family,
            selected_sku=selected_sku,
        )
        beta_active, beta_badge = resolve_active_beta(elasticity_df, active_family)

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
        band_low_change_pct=band_low_frac,
        band_high_change_pct=band_high_frac,
    )
    res = simulate(baseline, levers)

    scope_label = selected_sku if scope_mode == "Tático por SKU" else selected_family
    if scope_label != ALL_FAMILIES_OPT:
        with c_ctrl:
            st.markdown(
                "<div style='font-size:0.74rem; color:var(--kyb-text-muted); margin-top:0.2rem;'>"
                f"Elasticidade β de <strong>{active_family}</strong> aplicada sobre a base atual "
                f"(<strong>{format_brl(res.gross_revenue_0)}</strong>); "
                f"Banda Ideal: <strong>{band_caption or 'Global'}</strong>."
                "</div>",
                unsafe_allow_html=True,
            )

    with kpi_slot:
        render_simulator_kpis(res, dto.kpis.contribution_margin_pct)

    with c_summary:
        render_breakeven_callout(res)
        render_scenario_comparator(
            res,
            scope_label=scope_label,
            price_pct=float(price_delta),
            discount_pp=float(discount_delta),
            cost_pct=float(cost_delta),
            comm_pp=float(comm_delta),
        )

    _render_simulator_charts(
        res,
        price_delta=float(price_delta),
        band_low_frac=band_low_frac,
        band_high_frac=band_high_frac,
        band_caption=band_caption,
        theme_mode=theme_mode,
    )
