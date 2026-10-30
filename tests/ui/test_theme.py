from __future__ import annotations

import plotly.io as pio
import pytest

from src.ui.theme import (
    KYBERNA_DARK_TOKENS,
    KYBERNA_LIGHT_TOKENS,
    REGIOES_BR,
    UF_REGIAO,
    calculate_contrast_ratio,
    calculate_relative_luminance,
    get_plotly_template_name,
    get_theme_tokens,
    get_ufs_for_regiao,
    register_plotly_templates,
)


def test_theme_tokens_consistency() -> None:
    """Garante que os tokens de Light e Dark mode possuem exatamente as mesmas chaves."""
    assert set(KYBERNA_LIGHT_TOKENS.keys()) == set(KYBERNA_DARK_TOKENS.keys())
    required_keys = {
        "bg_primary",
        "surface_card",
        "border_subtle",
        "text_primary",
        "text_muted",
        "teal_500",
        "brass_500",
        "positive",
        "negative",
        "warning",
    }
    assert required_keys.issubset(set(KYBERNA_LIGHT_TOKENS.keys()))


def test_get_theme_tokens_selector() -> None:
    """Verifica retorno correto dos tokens para cada modo."""
    assert get_theme_tokens("light") == KYBERNA_LIGHT_TOKENS
    assert get_theme_tokens("dark") == KYBERNA_DARK_TOKENS
    assert get_theme_tokens("unknown") == KYBERNA_LIGHT_TOKENS


def test_wcag_contrast_ratios() -> None:
    """DoD: Verifica conformidade WCAG AA (contraste >= 4.5:1 para texto normal) nos dois temas."""
    # Light Mode: Texto primário (#0F172A) sobre fundo (#F8FAFC) e card (#FFFFFF)
    cr_light_bg = calculate_contrast_ratio(
        KYBERNA_LIGHT_TOKENS["text_primary"],
        KYBERNA_LIGHT_TOKENS["bg_primary"],
    )
    assert cr_light_bg >= 10.0, f"Contraste insuficiente no Light BG: {cr_light_bg:.2f}"

    cr_light_card = calculate_contrast_ratio(
        KYBERNA_LIGHT_TOKENS["text_primary"],
        KYBERNA_LIGHT_TOKENS["surface_card"],
    )
    assert cr_light_card >= 10.0, f"Contraste insuficiente no Light Card: {cr_light_card:.2f}"

    # Dark Mode: Texto primário (#E6EDF3) sobre fundo (#0D1117) e card (#161B22)
    cr_dark_bg = calculate_contrast_ratio(
        KYBERNA_DARK_TOKENS["text_primary"],
        KYBERNA_DARK_TOKENS["bg_primary"],
    )
    assert cr_dark_bg >= 10.0, f"Contraste insuficiente no Dark BG: {cr_dark_bg:.2f}"

    cr_dark_card = calculate_contrast_ratio(
        KYBERNA_DARK_TOKENS["text_primary"],
        KYBERNA_DARK_TOKENS["surface_card"],
    )
    assert cr_dark_card >= 10.0, f"Contraste insuficiente no Dark Card: {cr_dark_card:.2f}"


def test_relative_luminance_extremes() -> None:
    """Verifica cálculo de luminância relativa nos extremos preto e branco."""
    assert calculate_relative_luminance("#000000") == pytest.approx(0.0, abs=1e-3)
    assert calculate_relative_luminance("#FFFFFF") == pytest.approx(1.0, abs=1e-3)
    assert calculate_contrast_ratio("#000000", "#FFFFFF") == pytest.approx(21.0, abs=0.1)


def test_uf_regiao_coverage() -> None:
    """Garante que todas as 27 UFs brasileiras estão mapeadas para as 5 regiões."""
    assert len(UF_REGIAO) == 27
    assert set(REGIOES_BR) == {"Sudeste", "Sul", "Nordeste", "Centro-Oeste", "Norte"}

    for uf, regiao in UF_REGIAO.items():
        assert len(uf) == 2
        assert regiao in REGIOES_BR


def test_get_ufs_for_regiao() -> None:
    """Verifica filtragem correta da cascata geográfica."""
    sudeste = get_ufs_for_regiao("Sudeste")
    assert sudeste == ["ES", "MG", "RJ", "SP"]

    sul = get_ufs_for_regiao("Sul")
    assert sul == ["PR", "RS", "SC"]

    todas = get_ufs_for_regiao("Todas")
    assert len(todas) == 27


def test_plotly_templates_registered() -> None:
    """Verifica se os templates duplos foram registrados no Plotly com formatação pt-BR."""
    register_plotly_templates()
    assert "kyberna_light" in pio.templates
    assert "kyberna_dark" in pio.templates

    tpl_light = pio.templates["kyberna_light"]
    assert tpl_light.layout.separators == ",."  # pt-BR: vírgula decimal, ponto de milhar
    assert "Inter" in str(tpl_light.layout.font.family)

    tpl_dark = pio.templates["kyberna_dark"]
    assert tpl_dark.layout.separators == ",."
    assert "Inter" in str(tpl_dark.layout.font.family)

    assert get_plotly_template_name("dark") == "kyberna_dark"
    assert get_plotly_template_name("light") == "kyberna_light"
