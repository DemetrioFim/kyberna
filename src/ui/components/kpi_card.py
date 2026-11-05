from __future__ import annotations

import html
from typing import Literal

import streamlit as st

KpiAccent = Literal["teal", "brass", "green", "red", "pos", "neg", "blue", "gold"]


def info_tooltip_html(
    help_text: str,
    *,
    align: Literal["left", "right"] = "right",
) -> str:
    """Gera o HTML do ícone azul de informação (ⓘ) com popover flutuante no hover.

    Argumentos:
        help_text: Texto ou HTML formatado explicativo do indicador ou seção.
        align: Alinhamento horizontal do balão ('left' ou 'right').
    """
    if not help_text or not help_text.strip():
        raise ValueError("help_text é obrigatório e não pode ser vazio.")

    align_class = f"kyb-tooltip-align-{align}"
    return (
        f'<span class="kyb-info-wrapper">'
        f'<span class="kyb-info-icon" tabindex="0" aria-label="Informações">ⓘ</span>'
        f'<span class="kyb-tooltip-popover {align_class}">{help_text.strip()}</span>'
        f"</span>"
    )


def kpi_card_html(
    title: str,
    value: str,
    *,
    subfooter_left: str = "",
    delta_html: str = "",
    accent: KpiAccent = "teal",
    help_text: str,
) -> str:
    """Gera o HTML estruturado do card executivo Kyberna com barra superior e sub-rodapé duplo.

    Argumentos:
        title: Rótulo principal do indicador (ex: 'Faturamento Bruto', 'Margem Líquida').
        value: Valor formatado (ex: 'R$ 4.280.000', '27,0%').
        subfooter_left: Texto de apoio à esquerda no rodapé (ex: 'Meta: R$ 4,1 mi').
        delta_html: Tag HTML de badge com a variação semântica gerada por `get_delta_html`.
        accent: Cor da borda superior gradiente ('teal', 'brass', 'green', 'red', 'pos', 'neg').
        help_text: Tooltip explicativo obrigatório exibido no ícone azul de informação (ⓘ).
    """
    if not help_text or not help_text.strip():
        raise ValueError("help_text é obrigatório para todos os KPI cards.")

    accent_map: dict[str, str] = {
        "teal": "kpi-card-teal",
        "brass": "kpi-card-brass",
        "green": "kpi-card-pos",
        "pos": "kpi-card-pos",
        "red": "kpi-card-neg",
        "neg": "kpi-card-neg",
        "blue": "kpi-card-teal",
        "gold": "kpi-card-brass",
    }
    card_class = accent_map.get(accent, "kpi-card-teal")

    title_escaped = html.escape(title)
    value_escaped = html.escape(value)
    info_html = info_tooltip_html(help_text, align="right")

    subfooter_content = ""
    if subfooter_left or delta_html:
        left_span = f"<span>{html.escape(subfooter_left)}</span>" if subfooter_left else "<span></span>"
        subfooter_content = f'<div class="kpi-subfooter">{left_span}{delta_html}</div>'

    return (
        f'<div class="kpi-card {card_class}">'
        f'<div class="kpi-header">'
        f'<div class="kpi-title">{title_escaped}</div>'
        f"{info_html}"
        f"</div>"
        f'<div class="kpi-value">{value_escaped}</div>'
        f"{subfooter_content}"
        f"</div>"
    )


def render_kpi_card(
    title: str,
    value: str,
    *,
    subfooter_left: str = "",
    delta_html: str = "",
    accent: KpiAccent = "teal",
    help_text: str,
) -> None:
    """Renderiza um KPI card diretamente no container ou coluna ativa do Streamlit."""
    content = kpi_card_html(
        title=title,
        value=value,
        subfooter_left=subfooter_left,
        delta_html=delta_html,
        accent=accent,
        help_text=help_text,
    )
    st.markdown(content, unsafe_allow_html=True)
