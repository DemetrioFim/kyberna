from __future__ import annotations

import pandas as pd
import streamlit as st

from src.services.dto import SimulationResult
from src.ui.components.kpi_card import KpiAccent, render_kpi_card
from src.ui.formatting import format_brl

ALL_FAMILIES_OPT = "Todas as Famílias (Média)"
NO_SKU_OPT = "Sem SKUs em desvio no recorte"


def resolve_active_beta(elasticity_df: pd.DataFrame, selected_family: str) -> tuple[float, str]:
    """Resolve o coeficiente beta ativo e seu rótulo de classificação."""
    if elasticity_df.empty:
        return -1.2, "Padrão (-1.20)"
    if selected_family != ALL_FAMILIES_OPT:
        match = elasticity_df[elasticity_df["family"] == selected_family]
        if not match.empty:
            beta_val = float(match["beta_hat"].iloc[0])
            cls_label = str(match["elasticity_classification"].iloc[0])
            return beta_val, f"{cls_label} ({beta_val:.2f})"
    mean_beta = float(elasticity_df["beta_hat"].mean())
    cls_label = "Elástica" if mean_beta < -1.0 else "Inelástica"
    return mean_beta, f"Média {cls_label} ({mean_beta:.2f})"


def build_sku_band_options(sku_deviations_df: pd.DataFrame | None) -> dict[str, tuple[str, float, float]]:
    """Mapeia rótulos de SKU para (family, band_low_frac, band_high_frac)."""
    if sku_deviations_df is None or sku_deviations_df.empty:
        return {}
    needed = {
        "product_name",
        "family",
        "realized_idx_mean",
        "contextual_band_low_idx",
        "contextual_band_high_idx",
    }
    if not needed.issubset(set(sku_deviations_df.columns)):
        return {}
    mapping: dict[str, tuple[str, float, float]] = {}
    head_df = sku_deviations_df.head(30)
    for name, fam, realized_v, low_v, high_v in zip(
        head_df["product_name"].tolist(),
        head_df["family"].tolist(),
        head_df["realized_idx_mean"].tolist(),
        head_df["contextual_band_low_idx"].tolist(),
        head_df["contextual_band_high_idx"].tolist(),
        strict=False,
    ):
        label = f"{name} ({fam})"
        realized = float(realized_v)
        low_frac = (float(low_v) - realized) / 100.0
        high_frac = (float(high_v) - realized) / 100.0
        if low_frac > high_frac:
            low_frac, high_frac = high_frac, low_frac
        mapping[label] = (str(fam), round(low_frac, 4), round(high_frac, 4))
    return mapping


def resolve_active_band(
    family_bands_df: pd.DataFrame | None,
    sku_map: dict[str, tuple[str, float, float]],
    *,
    scope_mode: str,
    selected_family: str,
    selected_sku: str,
) -> tuple[float, float, str, str]:
    """Retorna (band_low_frac, band_high_frac, resolved_family, band_caption)."""
    if scope_mode == "Tático por SKU" and selected_sku in sku_map:
        fam, low_f, high_f = sku_map[selected_sku]
        return low_f, high_f, fam, f"[{low_f * 100.0:+.1f}%, {high_f * 100.0:+.1f}%]"

    if family_bands_df is not None and not family_bands_df.empty:
        if selected_family != ALL_FAMILIES_OPT:
            match = family_bands_df[family_bands_df["family"] == selected_family]
            if not match.empty:
                low_f = float(match["band_low_delta_pct"].iloc[0])
                high_f = float(match["band_high_delta_pct"].iloc[0])
                if low_f > high_f:
                    low_f, high_f = high_f, low_f
                return low_f, high_f, selected_family, f"[{low_f * 100.0:+.1f}%, {high_f * 100.0:+.1f}%]"
        low_f = float(family_bands_df["band_low_delta_pct"].mean())
        high_f = float(family_bands_df["band_high_delta_pct"].mean())
        if low_f > high_f:
            low_f, high_f = high_f, low_f
        return low_f, high_f, selected_family, f"[{low_f * 100.0:+.1f}%, {high_f * 100.0:+.1f}%]"

    return -0.25, 0.25, selected_family, ""


def render_simulator_kpis(res: SimulationResult, baseline_margin_pct: float) -> None:
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
            help_text="Margem de contribuição resultante após todas as alavancas ajustadas.",
        )
    with c3:
        render_kpi_card(
            title="Nova Margem Contr. %",
            value=f"{res.margin_pct_1:.1f}%",
            subfooter_left=f"Delta: {delta_pp:+.1f} pp",
            accent=delta_accent,
            help_text="Rentabilidade de contribuição sobre faturamento comparada ao cenário base.",
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


def render_breakeven_callout(res: SimulationResult) -> None:
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
        else "Inviável (m_unit <= 0)"
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


def render_scenario_comparator(
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
                "Cenário": f"C{len(saved) + 1} · {scope_label}",
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
            column_config={"Cenário": st.column_config.TextColumn("Cenário", width="medium")},
            use_container_width=True,
            hide_index=True,
            height=120,
        )
