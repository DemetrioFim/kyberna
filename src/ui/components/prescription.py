from __future__ import annotations

import html

import streamlit as st

from src.ui.formatting import format_brl


def section_header(
    title: str,
    subtitle: str = "",
    badge: str | None = None,
) -> None:
    """Renderiza cabeçalho visual de seção executiva com subtítulo e badge opcional."""
    badge_html = f' <span class="badge badge-source">{html.escape(badge)}</span>' if badge else ""
    subtitle_html = (
        '<div style="font-size: 0.88rem; color: var(--kyb-text-muted); '
        f'margin-bottom: 0.8rem;">{html.escape(subtitle)}</div>'
        if subtitle
        else ""
    )

    content = f"""
    <div style="margin-top: 1.5rem; margin-bottom: 0.5rem;">
        <h4 style="margin: 0; display: inline-flex; align-items: center; gap: 0.5rem; font-weight: 700;">
            {html.escape(title)}{badge_html}
        </h4>
        {subtitle_html}
    </div>
    """
    st.markdown(content, unsafe_allow_html=True)


def prescription_box_html(
    title: str,
    recommendation_html: str,
    impact_brl: float | None = None,
    action_hint: str | None = None,
) -> str:
    """Gera o HTML do bloco de prescrição executiva com borda âmbar e impacto em R$."""
    impact_html = ""
    if impact_brl is not None and impact_brl > 0:
        impact_formatted = format_brl(impact_brl, compact=True, decimals=1)
        impact_html = f"""
        <div style="margin-top: 0.6rem; font-weight: 600; color: var(--kyb-brass);">
            🎯 <strong>Impacto Estimado:</strong> Proteção / Ganho de <u>+{impact_formatted}</u> no bolso.
        </div>
        """

    action_html = ""
    if action_hint:
        action_html = f"""
        <div style="margin-top: 0.4rem; font-size: 0.85rem; color: var(--kyb-text-muted);">
            ⚡ <em>{html.escape(action_hint)}</em>
        </div>
        """

    return f"""
    <div class="prescription-box">
        <div class="prescription-title">
            <span>💡</span>
            <span>{html.escape(title)}</span>
        </div>
        <div class="prescription-content">
            {recommendation_html}
            {impact_html}
            {action_html}
        </div>
    </div>
    """


def render_prescription_box(
    title: str,
    recommendation_html: str,
    impact_brl: float | None = None,
    action_hint: str | None = None,
) -> None:
    """Renderiza a caixa de prescrição executiva diretamente no Streamlit."""
    content = prescription_box_html(
        title=title,
        recommendation_html=recommendation_html,
        impact_brl=impact_brl,
        action_hint=action_hint,
    )
    st.markdown(content, unsafe_allow_html=True)
