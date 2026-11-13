from __future__ import annotations

import html

import streamlit as st

from src.ui.components.kpi_card import info_tooltip_html
from src.ui.formatting import format_brl


def section_header(
    title: str,
    subtitle: str = "",
    badge: str | None = None,
    help_text: str | None = None,
) -> None:
    """Renderiza cabeçalho visual de seção executiva com subtítulo, badge e tooltip opcional."""
    badge_html = f' <span class="badge badge-source">{html.escape(badge)}</span>' if badge else ""
    info_html = f" {info_tooltip_html(help_text, align='left')}" if help_text else ""
    subtitle_html = (
        '<div style="font-size: 0.78rem; color: var(--kyb-text-muted); '
        f'margin-bottom: 0.35rem;">{html.escape(subtitle)}</div>'
        if subtitle
        else ""
    )

    content = (
        f'<div style="margin-top: 0.35rem; margin-bottom: 0.2rem;">'
        f'<h5 style="margin: 0; display: inline-flex; align-items: center; gap: 0.4rem; '
        f'font-weight: 700; font-size: 0.92rem;">'
        f"{html.escape(title)}{badge_html}{info_html}</h5>"
        f"{subtitle_html}"
        f"</div>"
    )
    st.markdown(content, unsafe_allow_html=True)


def _sanitize_inline_bold_html(raw_text: str) -> str:
    """Escapa HTML preservando apenas marcações simples de ênfase (<b> e <strong>)."""
    escaped = html.escape(raw_text)
    for tag in ("b", "strong"):
        escaped = escaped.replace(f"&lt;{tag}&gt;", f"<{tag}>").replace(f"&lt;/{tag}&gt;", f"</{tag}>")
    return escaped


def render_cockpit_header(
    title: str,
    subtitle: str,
    *,
    headline_title: str,
    headline_text: str,
    virtue_badge: str | None = None,
    period_badge: str | None = None,
    as_of_date_label: str = "31/12/2024",
    help_text: str | None = None,
) -> None:
    """Renderiza o cabeçalho executivo compacto de cockpit (Faixa 1 — Topo em 2 linhas)."""
    info_html = f" {info_tooltip_html(help_text, align='right')}" if help_text else ""
    virtue_html = (
        f'<span class="badge badge-source">{html.escape(virtue_badge)}</span>' if virtue_badge else ""
    )
    period_html = f'<span class="cockpit-date-tag">{html.escape(period_badge)}</span>' if period_badge else ""
    header_html = (
        f'<div class="cockpit-header">'
        f'<div class="cockpit-header-top">'
        f'<div class="cockpit-title-group">'
        f"{virtue_html}"
        f'<h2 class="cockpit-title">{html.escape(title)}</h2>'
        f'<span class="cockpit-subtitle">{html.escape(subtitle)}</span>'
        f"</div>"
        f'<div class="cockpit-meta-group">'
        f'<span class="cockpit-headline-pill">{html.escape(headline_title)}{info_html}</span>'
        f"{period_html}"
        f'<span class="cockpit-date-tag">Corte: <strong>{html.escape(as_of_date_label)}</strong></span>'
        f"</div>"
        f"</div>"
        f'<div class="cockpit-header-bottom">{_sanitize_inline_bold_html(headline_text)}</div>'
        f"</div>"
    )
    st.markdown(header_html, unsafe_allow_html=True)


def prescription_box_html(
    title: str,
    recommendation_html: str,
    impact_brl: float | None = None,
    action_hint: str | None = None,
    help_text: str | None = None,
) -> str:
    """Gera o HTML do bloco de prescrição executiva com borda âmbar e impacto em R$."""
    info_html = f" {info_tooltip_html(help_text, align='left')}" if help_text else ""
    impact_html = ""
    if impact_brl is not None and impact_brl > 0:
        impact_formatted = format_brl(impact_brl, compact=True, decimals=1)
        impact_html = (
            f'<div style="margin-top: 0.6rem; font-weight: 600; color: var(--kyb-brass);">'
            f"<strong>Impacto Estimado:</strong> Proteção / Ganho de <u>+{impact_formatted}</u> no bolso."
            f"</div>"
        )

    action_html = ""
    if action_hint:
        action_html = (
            f'<div style="margin-top: 0.4rem; font-size: 0.85rem; color: var(--kyb-text-muted);">'
            f"<em>{html.escape(action_hint)}</em>"
            f"</div>"
        )

    return (
        f'<div class="prescription-box">'
        f'<div class="prescription-title"><span>{html.escape(title)}</span>{info_html}</div>'
        f'<div class="prescription-content">{recommendation_html}{impact_html}{action_html}</div>'
        f"</div>"
    )


def render_prescription_box(
    title: str,
    recommendation_html: str,
    impact_brl: float | None = None,
    action_hint: str | None = None,
    help_text: str | None = None,
) -> None:
    """Renderiza a caixa de prescrição executiva diretamente no Streamlit."""
    content = prescription_box_html(
        title=title,
        recommendation_html=recommendation_html,
        impact_brl=impact_brl,
        action_hint=action_hint,
        help_text=help_text,
    )
    st.markdown(content, unsafe_allow_html=True)
