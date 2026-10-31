from __future__ import annotations

from typing import Any, Final

import plotly.graph_objects as go
import plotly.io as pio

# ==============================================================================
# Tokens de Cores Kyberna (Light Mode ☀️ & Dark Mode 🌙 — §5.6 do GEMINI.md)
# ==============================================================================

KYBERNA_LIGHT_TOKENS: Final[dict[str, str]] = {
    "bg_primary": "#F8FAFC",
    "surface_card": "#FFFFFF",
    "sidebar_bg": "#FFFFFF",
    "border_subtle": "#E2E8F0",
    "text_primary": "#0F172A",
    "text_muted": "#475569",
    "teal_500": "#1F7A8C",
    "brass_500": "#C9A227",
    "positive": "#2E9E6A",
    "negative": "#D1495B",
    "warning": "#E59F3A",
    "chart_grid": "#E2E8F0",
    "chart_zero_line": "#CBD5E1",
}

KYBERNA_DARK_TOKENS: Final[dict[str, str]] = {
    "bg_primary": "#0B111A",
    "surface_card": "#131B26",
    "sidebar_bg": "#0D131D",
    "border_subtle": "#222F3E",
    "text_primary": "#F1F5F9",
    "text_muted": "#94A3B8",
    "teal_500": "#38BDF8",
    "brass_500": "#FBBF24",
    "positive": "#34D399",
    "negative": "#F87171",
    "warning": "#FBBF24",
    "chart_grid": "#1E293B",
    "chart_zero_line": "#334155",
}

# ==============================================================================
# Mapeamento Geográfico Brasileiro (Cascata Região -> UF)
# ==============================================================================

UF_REGIAO: Final[dict[str, str]] = {
    "SP": "Sudeste",
    "RJ": "Sudeste",
    "MG": "Sudeste",
    "ES": "Sudeste",
    "PR": "Sul",
    "SC": "Sul",
    "RS": "Sul",
    "BA": "Nordeste",
    "PE": "Nordeste",
    "CE": "Nordeste",
    "RN": "Nordeste",
    "PB": "Nordeste",
    "AL": "Nordeste",
    "SE": "Nordeste",
    "PI": "Nordeste",
    "MA": "Nordeste",
    "DF": "Centro-Oeste",
    "GO": "Centro-Oeste",
    "MT": "Centro-Oeste",
    "MS": "Centro-Oeste",
    "AM": "Norte",
    "PA": "Norte",
    "AC": "Norte",
    "RO": "Norte",
    "RR": "Norte",
    "AP": "Norte",
    "TO": "Norte",
}

REGIOES_BR: Final[list[str]] = ["Sudeste", "Sul", "Nordeste", "Centro-Oeste", "Norte"]


def get_theme_tokens(mode: str = "light") -> dict[str, str]:
    """Retorna o dicionário de tokens de cores conforme o modo ativo ('light' ou 'dark')."""
    return KYBERNA_DARK_TOKENS if mode == "dark" else KYBERNA_LIGHT_TOKENS


def get_ufs_for_regiao(regiao: str | None = None) -> list[str]:
    """Retorna as UFs brasileiras filtradas por região ou todas se None / 'Todas'."""
    if not regiao or regiao == "Todas":
        return sorted(UF_REGIAO.keys())
    return sorted([uf for uf, reg in UF_REGIAO.items() if reg == regiao])


# ==============================================================================
# Cálculo de Contraste WCAG
# ==============================================================================


def _channel_to_linear(c_srgb: float) -> float:
    """Converte canal sRGB [0..1] para luminância linear."""
    if c_srgb <= 0.04045:
        return c_srgb / 12.92
    return float(((c_srgb + 0.055) / 1.055) ** 2.4)


def calculate_relative_luminance(hex_color: str) -> float:
    """Calcula a luminância relativa (0 a 1) segundo a especificação WCAG 2.1."""
    color = hex_color.lstrip("#")
    r = int(color[0:2], 16) / 255.0
    g = int(color[2:4], 16) / 255.0
    b = int(color[4:6], 16) / 255.0

    r_lin = _channel_to_linear(r)
    g_lin = _channel_to_linear(g)
    b_lin = _channel_to_linear(b)

    return 0.2126 * r_lin + 0.7152 * g_lin + 0.0722 * b_lin


def calculate_contrast_ratio(hex1: str, hex2: str) -> float:
    """Calcula a taxa de contraste entre duas cores hexadecimais (mínimo 1.0, máximo 21.0)."""
    l1 = calculate_relative_luminance(hex1)
    l2 = calculate_relative_luminance(hex2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


# ==============================================================================
# Templates Plotly Duplos ("kyberna_light" e "kyberna_dark")
# ==============================================================================


def create_plotly_template(mode: str = "light") -> go.layout.Template:
    """Cria objeto go.layout.Template tipado e padronizado para a Kyberna."""
    tokens = get_theme_tokens(mode)
    is_dark = mode == "dark"

    font_family = "Inter, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif"

    color_sequence = (
        ["#58A6FF", "#D29922", "#3FB950", "#F85149", "#BC8CFF", "#79C0FF", "#8B949E", "#E3B341"]
        if is_dark
        else ["#1F7A8C", "#C9A227", "#2E9E6A", "#D1495B", "#022B3A", "#64748B", "#8B5CF6", "#E59F3A"]
    )

    layout: dict[str, Any] = {
        "font": {
            "family": font_family,
            "color": tokens["text_primary"],
            "size": 12,
        },
        "title": {
            "font": {
                "family": font_family,
                "color": tokens["text_primary"],
                "size": 15,
            },
            "x": 0.0,
            "xanchor": "left",
        },
        "paper_bgcolor": tokens["surface_card"],
        "plot_bgcolor": tokens["surface_card"],
        "colorway": color_sequence,
        "separators": ",.",  # pt-BR: vírgula decimal, ponto de milhar
        "margin": {"l": 40, "r": 20, "t": 40, "b": 40, "pad": 4},
        "hoverlabel": {
            "bgcolor": tokens["surface_card"],
            "bordercolor": tokens["border_subtle"],
            "font": {"family": font_family, "size": 12, "color": tokens["text_primary"]},
        },
        "xaxis": {
            "gridcolor": tokens["chart_grid"],
            "zerolinecolor": tokens["chart_zero_line"],
            "linecolor": tokens["border_subtle"],
            "tickcolor": tokens["border_subtle"],
            "tickfont": {"family": font_family, "color": tokens["text_muted"], "size": 11},
            "title": {"font": {"family": font_family, "color": tokens["text_muted"], "size": 12}},
        },
        "yaxis": {
            "gridcolor": tokens["chart_grid"],
            "zerolinecolor": tokens["chart_zero_line"],
            "linecolor": tokens["border_subtle"],
            "tickcolor": tokens["border_subtle"],
            "tickfont": {"family": font_family, "color": tokens["text_muted"], "size": 11},
            "title": {"font": {"family": font_family, "color": tokens["text_muted"], "size": 12}},
        },
        "legend": {
            "font": {"family": font_family, "color": tokens["text_muted"], "size": 11},
            "bgcolor": "rgba(0,0,0,0)",
            "bordercolor": "rgba(0,0,0,0)",
        },
    }

    template = go.layout.Template(layout=layout)
    return template


def register_plotly_templates() -> None:
    """Registra os templates 'kyberna_light' e 'kyberna_dark' no ecossistema Plotly."""
    pio.templates["kyberna_light"] = create_plotly_template("light")
    pio.templates["kyberna_dark"] = create_plotly_template("dark")


def get_plotly_template_name(mode: str = "light") -> str:
    """Retorna o identificador do template Plotly ativo ('kyberna_dark' ou 'kyberna_light')."""
    return "kyberna_dark" if mode == "dark" else "kyberna_light"


# Registra automaticamente ao importar o módulo
register_plotly_templates()
