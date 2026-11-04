from __future__ import annotations

from datetime import date, datetime

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
