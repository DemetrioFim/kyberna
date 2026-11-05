from __future__ import annotations

from datetime import date, datetime

from src.ui.components.kpi_card import info_tooltip_html, kpi_card_html
from src.ui.components.prescription import prescription_box_html
from src.ui.formatting import (
    format_brl,
    format_date_br,
    format_int,
    format_pct,
    format_pp,
    get_delta_html,
)


def test_format_brl_regular_and_compact() -> None:
    """Valida formatação de moeda em Real brasileiro nos modos padrão e compacto."""
    assert format_brl(1234567.89) == "R$ 1.234.567,89"
    assert format_brl(0.0) == "R$ 0,00"
    assert format_brl(1234567.89, compact=True, decimals=1) == "R$ 1,2 mi"
    assert format_brl(450000.0, compact=True, decimals=1) == "R$ 450,0 mil"
    assert format_brl(2500000000.0, compact=True, decimals=2) == "R$ 2,50 bi"
    assert format_brl(75.5, compact=True) == "R$ 75,50"


def test_format_brl_negative_and_none() -> None:
    """Valida formatação de valores negativos e nulos em BRL."""
    assert format_brl(None) == "—"
    assert format_brl(-1234.56) == "-R$ 1.234,56"
    assert format_brl(-450000.0, compact=True, decimals=1) == "-R$ 450,0 mil"


def test_format_pct_and_pp() -> None:
    """Valida formatação de percentuais e pontos percentuais com separadores pt-BR."""
    assert format_pct(27.0) == "27,0%"
    assert format_pct(0.27, is_ratio=True) == "27,0%"
    assert format_pct(4.4, signed=True) == "+4,4%"
    assert format_pct(-2.1, signed=True) == "-2,1%"
    assert format_pct(None) == "—"

    assert format_pp(3.1) == "+3,1 p.p."
    assert format_pp(-1.5) == "-1,5 p.p."
    assert format_pp(None) == "—"


def test_format_int_and_date_br() -> None:
    """Valida formatação de inteiros e datas no padrão brasileiro."""
    assert format_int(19578) == "19.578"
    assert format_int(1000000) == "1.000.000"
    assert format_int(None) == "—"

    d = date(2026, 11, 4)
    dt = datetime(2026, 11, 4, 15, 30)
    assert format_date_br(d) == "04/11/2026"
    assert format_date_br(dt) == "04/11/2026"
    assert format_date_br("2026-11-04") == "04/11/2026"
    assert format_date_br(None) == "—"


def test_get_delta_html_colors_and_inversion() -> None:
    """Testa geração de tags HTML de deltas e inversão semântica para custos/perdas."""
    # Positivo normal -> Verde (badge-positive)
    pos_html = get_delta_html(4.4, kind="pct")
    assert "badge-positive" in pos_html
    assert "+4,4%" in pos_html

    # Negativo normal -> Vermelho (badge-negative)
    neg_html = get_delta_html(-2.1, kind="pct")
    assert "badge-negative" in neg_html
    assert "-2,1%" in neg_html

    # Invertido: aumento de custo/imposto (+5%) é ruim -> Vermelho (badge-negative)
    cost_increase_html = get_delta_html(5.0, kind="pct", invert_color=True)
    assert "badge-negative" in cost_increase_html

    # Invertido: redução de custo (-3%) é bom -> Verde (badge-positive)
    cost_decrease_html = get_delta_html(-3.0, kind="pct", invert_color=True)
    assert "badge-positive" in cost_decrease_html

    # Nulo ou zero -> Neutro (badge-source)
    assert "badge-source" in get_delta_html(None)
    assert "badge-source" in get_delta_html(0.0)


def test_info_tooltip_html_rendering_and_validation() -> None:
    """Valida geração do ícone azul de informação ⓘ e obrigatoriedade de texto não-vazio."""
    import pytest

    # Alinhamento padrão (right)
    html_out = info_tooltip_html("Explicação detalhada da métrica.")
    assert "kyb-info-wrapper" in html_out
    assert "kyb-info-icon" in html_out
    assert "ⓘ" in html_out
    assert "kyb-tooltip-popover" in html_out
    assert "kyb-tooltip-align-right" in html_out
    assert "Explicação detalhada da métrica." in html_out

    # Alinhamento à esquerda (para cabeçalhos de seção)
    html_left = info_tooltip_html("Ajuda à esquerda", align="left")
    assert "kyb-tooltip-align-left" in html_left

    # Validação de obrigatoriedade: texto vazio levanta ValueError
    with pytest.raises(ValueError, match="help_text é obrigatório"):
        info_tooltip_html("")

    with pytest.raises(ValueError, match="help_text é obrigatório"):
        info_tooltip_html("   ")


def test_kpi_card_html_with_mandatory_tooltip() -> None:
    """Valida que kpi_card_html exige help_text e renderiza estrutura de cabeçalho completa."""
    import pytest

    card_html = kpi_card_html(
        title="Margem Real",
        value="R$ 1.000.000",
        subfooter_left="CPV: R$ 400 mil",
        delta_html='<span class="badge badge-positive">+5,0%</span>',
        accent="green",
        help_text="Explicação executiva da margem real líquida.",
    )

    assert "kpi-card-pos" in card_html
    assert "kpi-header" in card_html
    assert "kpi-title" in card_html
    assert "Margem Real" in card_html
    assert "kyb-info-icon" in card_html
    assert "kyb-tooltip-popover" in card_html
    assert "Explicação executiva da margem real líquida." in card_html
    assert "kpi-value" in card_html
    assert "R$ 1.000.000" in card_html
    assert "kpi-subfooter" in card_html
    assert "CPV: R$ 400 mil" in card_html

    # Tentar criar card com help_text vazio deve falhar
    with pytest.raises(ValueError, match="help_text é obrigatório para todos os KPI cards"):
        kpi_card_html("Título", "R$ 0", help_text="")

    with pytest.raises(ValueError, match="help_text é obrigatório para todos os KPI cards"):
        kpi_card_html("Título", "R$ 0", help_text="   ")


def test_prescription_box_html_with_tooltip() -> None:
    """Valida inclusão opcional do ícone azul explicativo no bloco prescritivo."""
    box_html = prescription_box_html(
        title="Oportunidade de Margem",
        recommendation_html="Ajustar tabela de descontos.",
        impact_brl=125000.0,
        action_hint="Definir tabela regressiva.",
        help_text="Metodologia de cálculo do potencial em R$.",
    )
    assert "prescription-box" in box_html
    assert "prescription-title" in box_html
    assert "kyb-info-icon" in box_html
    assert "Metodologia de cálculo do potencial em R$." in box_html
    assert "R$ 125,0 mil" in box_html
