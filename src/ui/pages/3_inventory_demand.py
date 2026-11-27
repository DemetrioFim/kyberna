from __future__ import annotations

from collections.abc import Sequence

import plotly.graph_objects as go
import streamlit as st

from src.core.scenarios import load_scenario_config
from src.services.dto import ExecutivePageDTO, TemperancePageDTO
from src.services.temperance_actions import build_priority_actions_360
from src.ui.cache import (
    cached_commercial_dashboard,
    cached_executive_dashboard,
    cached_family_elasticity,
    cached_fortitude_dashboard,
    cached_inventory_dashboard,
    cached_pricing_dashboard,
    cached_temperance_dashboard,
)
from src.ui.components.inventory_charts import erosion_breakdown_chart
from src.ui.components.justice_sections import render_champions_vampires_section
from src.ui.components.prescription import render_cockpit_header, section_header
from src.ui.components.simulator_charts import elasticity_family_chart
from src.ui.components.simulator_section import render_what_if_quick_fragment
from src.ui.components.temperance_sections import (
    render_champions_vampires_kpis,
    render_priority_actions_360_table,
    render_temperance_mix_kpis,
    render_temperance_verdict_section,
)
from src.ui.state import get_app_state


def _get_static_temperance_figures(
    temp_dto: TemperancePageDTO,
    cache_key: tuple[object, ...],
    scenario_id: str,
    theme_mode: str,
    families: Sequence[str] = (),
) -> tuple[go.Figure, go.Figure]:
    """Memoiza os gráficos estáticos de Temperança para manter sliders < 300 ms."""
    cached = st.session_state.get("_temp_static_figs")
    if isinstance(cached, tuple) and len(cached) == 2 and cached[0] == cache_key:
        figs: tuple[go.Figure, go.Figure] = cached[1]
        return figs

    fig_erosion = erosion_breakdown_chart(temp_dto.kpis, theme_mode=theme_mode)
    elasticity_df = cached_family_elasticity(scenario_id)  # type: ignore[arg-type]
    if families and not elasticity_df.empty and "family" in elasticity_df.columns:
        elasticity_df = elasticity_df[elasticity_df["family"].isin(families)].copy()
    fig_elasticity = elasticity_family_chart(elasticity_df, theme_mode=theme_mode)
    figs = (fig_erosion, fig_elasticity)
    st.session_state["_temp_static_figs"] = (cache_key, figs)
    return figs


def render_page() -> None:
    """Renderiza a Página 4 — 4. Temperança (Visão Integrada 360° Admin+Comercial+Finanças)."""
    state = get_app_state()
    scenario_cfg = load_scenario_config(state.scenario_id)
    theme_mode = state.theme_mode

    exec_dto: ExecutivePageDTO = cached_executive_dashboard(
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
    fort_dto = cached_fortitude_dashboard(
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
    inv_dto = cached_inventory_dashboard(state.scenario_id, families=tuple(state.families))
    pricing_dto = cached_pricing_dashboard(
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

    fig_cache_key: tuple[object, ...] = (
        state.scenario_id,
        state.regiao,
        state.uf,
        tuple(state.families) if state.families else None,
        tuple(state.sales_reps) if state.sales_reps else None,
        state.period_preset,
        state.comparison_mode,
        state.selected_month,
        state.selected_quarter,
        state.selected_semester,
        state.custom_start_date,
        state.custom_end_date,
        theme_mode,
    )
    fig_erosion, fig_elasticity = _get_static_temperance_figures(
        temp_dto,
        fig_cache_key,
        state.scenario_id,
        theme_mode,
        families=tuple(state.families),
    )

    render_cockpit_header(
        title="Temperança · Síntese Executiva 360° & Simulador Prescritivo",
        virtue_badge="4. Temperança",
        headline_title=temp_dto.headline_title,
        headline_text=temp_dto.headline_text,
        as_of_date_label=temp_dto.as_of_date_label,
        comparison_label=exec_dto.comparison_label,
        help_text=(
            "Visão executiva transversal estilo PowerBI integrando Finanças, Comercial e Operações, "
            "além do Simulador Estratégico What-If e Matriz 360° Campeões vs. Vampiros."
        ),
    )

    tab_mix, tab_sim, tab_cv = st.tabs(
        [
            "Termômetro Executivo 360° (Mix)",
            "Simulador Estratégico What-If & Elasticidade",
            "Matriz Campeões vs. Vampiros 360°",
        ]
    )

    with tab_mix:
        is_inv_scoped = (
            state.regiao != "Todas"
            or state.uf != "Todas"
            or bool(state.sales_reps)
            or state.period_preset != "all"
        )
        render_temperance_mix_kpis(exec_dto, fort_dto, comm_dto, temp_dto, inv_dto, is_scoped=is_inv_scoped)
        col_l, col_r = st.columns([1.0, 1.0])
        with col_l:
            section_header(
                "Erosão Comercial & Operacional por Alavanca",
                "Decomposição das deduções entre faturamento de tabela e lucro líquido",
            )
            st.plotly_chart(fig_erosion, use_container_width=True, theme=None)
        with col_r:
            section_header(
                "Elasticidade-Preço & Sensibilidade por Família (β)",
                "Relação histórica entre variação de preço líquido e demanda por linha",
                help_text=(
                    "Famílias inelásticas (|β| < 1) permitem recomposição de preço sem queda drástica "
                    "de volume; use estes coeficientes na aba Simulador What-If."
                ),
            )
            st.plotly_chart(fig_elasticity, use_container_width=True, theme=None)

        col_bl, col_br = st.columns([1.25, 1.0])
        with col_bl:
            section_header(
                "Fila Priorizada de Ações 360°",
                "Alavancas ranqueadas por potencial de recuperação em R$ nas 4 Virtudes",
            )
            actions_360_df = build_priority_actions_360(
                fort_dto=fort_dto,
                comm_dto=comm_dto,
                temp_dto=temp_dto,
                inv_dto=inv_dto,
                pricing_dto=pricing_dto,
            )
            render_priority_actions_360_table(actions_360_df)
        with col_br:
            section_header(
                "Veredito Integrado de Temperança (360°)",
                "Diretriz executiva consolidando recuperação de caixa, estoque e margem",
            )
            render_temperance_verdict_section(temp_dto)

    with tab_sim:
        section_header(
            "Simulador Estratégico What-If & Elasticidade Real (β)",
            "Teste impactos conjuntos de preço, descontos, CMV e comissão sobre lucro e banda competitiva",
            help_text=(
                "<b>O que é Elasticidade Real (β)?</b> É a sensibilidade percentual da demanda a variações "
                "de preço estimada sobre as vendas históricas. Ex.: β = -0,6 significa que +10% no preço "
                "reduz o volume em ~6% (demanda <b>inelástica</b>, ideal para recompor margem); "
                "|β| ≥ 1 indica demanda <b>elástica</b> (alta perda de giro ao subir preço)."
            ),
        )
        render_what_if_quick_fragment(
            exec_dto,
            family_bands_df=pricing_dto.family_bands_df,
            sku_deviations_df=pricing_dto.deviations_df,
            theme_mode=theme_mode,
        )

    with tab_cv:
        render_champions_vampires_kpis(exec_dto, temp_dto, scenario_cfg.labels.customer_plural)
        render_champions_vampires_section(exec_dto, scenario_cfg.labels)
        st.markdown(
            "<div style='font-size:0.75rem; color:var(--kyb-text-muted); margin-top:0.2rem;'>"
            "<strong>Diretriz 360°:</strong> revise alçadas de desconto e exigência de lote mínimo "
            "nas contas <strong>Vampiro</strong> de alta receita para estancar erosão sem perder volume."
            "</div>",
            unsafe_allow_html=True,
        )


render_page()
