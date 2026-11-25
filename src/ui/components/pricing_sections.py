from __future__ import annotations

from collections.abc import Callable
from typing import Any

import streamlit as st

from src.core.types import ScenarioId
from src.services.pricing_dto import PricingPageDTO
from src.ui.cache import cached_pricing_shap
from src.ui.components.kpi_card import KpiAccent, render_kpi_card
from src.ui.components.prescription import render_prescription_box
from src.ui.components.pricing_charts import (
    price_band_boxplot_chart,
    pricing_shap_waterfall_chart,
)
from src.ui.formatting import fmt_brl_cell, fmt_pct_cell, format_brl


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
    shap_dto = cached_pricing_shap(scenario_id, scope_type=sel_type, scope_id=sel_id)

    gap_color = "var(--kyb-neg)" if shap_dto.unjustified_gap_pp < -0.5 else "var(--kyb-pos)"
    st.markdown(
        "<div style='font-size:0.78rem; color:var(--kyb-text-muted); margin-bottom:0.2rem;'>"
        f"Esperado (Modelo): <strong>{shap_dto.expected_idx:.1f}%</strong> · "
        f"Praticado: <strong>{shap_dto.realized_idx:.1f}%</strong> · "
        f"Resíduo s/ lastro: <strong style='color:{gap_color};'>"
        f"{shap_dto.unjustified_gap_pp:+.2f} pp</strong></div>",
        unsafe_allow_html=True,
    )
    st.plotly_chart(
        pricing_shap_waterfall_chart(shap_dto, theme_mode=theme_mode),
        use_container_width=True,
        theme=None,
    )


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
        column_config={"Realiz. %": st.column_config.TextColumn("Realiz. %", width="small")},
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


def render_pricing_boxplot_chart(pricing_dto: PricingPageDTO, *, theme_mode: str = "light") -> None:
    """Renderiza o Boxplot contextual de realização de preço com faixa [P25, P75]."""
    st.plotly_chart(
        price_band_boxplot_chart(pricing_dto.boxplot_df, theme_mode=theme_mode),
        use_container_width=True,
        theme=None,
    )
