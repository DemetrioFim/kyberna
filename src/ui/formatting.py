from __future__ import annotations

import math
from datetime import date, datetime
from typing import Literal


def format_brl(
    value: float | int | None,
    compact: bool = False,
    decimals: int = 2,
) -> str:
    """Formata valor numérico em moeda Real brasileira (R$) com separadores pt-BR.

    Exemplos:
        format_brl(1234567.89) -> "R$ 1.234.567,89"
        format_brl(1234567.89, compact=True, decimals=1) -> "R$ 1,2 mi"
        format_brl(-450000.0, compact=True, decimals=1) -> "-R$ 450,0 mil"
    """
    if value is None:
        return "—"

    val = float(value)
    is_neg = val < 0
    abs_val = abs(val)

    if compact:
        if abs_val >= 1_000_000_000:
            num_str = f"{abs_val / 1e9:.{decimals}f}".replace(".", ",")
            unit = "bi"
        elif abs_val >= 1_000_000:
            num_str = f"{abs_val / 1e6:.{decimals}f}".replace(".", ",")
            unit = "mi"
        elif abs_val >= 1_000:
            num_str = f"{abs_val / 1e3:.{decimals}f}".replace(".", ",")
            unit = "mil"
        else:
            num_str = f"{abs_val:.{decimals}f}".replace(".", ",")
            unit = ""

        prefix = "-R$ " if is_neg else "R$ "
        suffix = f" {unit}" if unit else ""
        return f"{prefix}{num_str}{suffix}"

    # Formatação completa sem compactação
    raw_str = f"{abs_val:,.{decimals}f}"
    # Troca separadores: vírgula vira ponto e ponto vira vírgula
    formatted_num = raw_str.replace(",", "X").replace(".", ",").replace("X", ".")
    prefix = "-R$ " if is_neg else "R$ "
    return f"{prefix}{formatted_num}"


def format_pct(
    value: float | int | None,
    decimals: int = 1,
    is_ratio: bool = False,
    signed: bool = False,
) -> str:
    """Formata valor percentual no padrão brasileiro (ex: '27,0%' ou '+4,4%')."""
    if value is None:
        return "—"

    val = float(value) * 100 if is_ratio else float(value)
    sign = "+" if signed and val > 0 else ""
    formatted_num = f"{val:.{decimals}f}".replace(".", ",")
    return f"{sign}{formatted_num}%"


def format_pp(
    value: float | int | None,
    decimals: int = 1,
    signed: bool = True,
) -> str:
    """Formata variação em pontos percentuais (ex: '+3,1 p.p.' ou '-1,5 p.p.')."""
    if value is None:
        return "—"

    val = float(value)
    sign = "+" if signed and val > 0 else ""
    formatted_num = f"{val:.{decimals}f}".replace(".", ",")
    return f"{sign}{formatted_num} p.p."


def format_int(value: int | float | None) -> str:
    """Formata número inteiro com separador de milhar brasileiro (ex: 19.578)."""
    if value is None:
        return "—"

    int_val = round(value)
    raw_str = f"{int_val:,}"
    return raw_str.replace(",", ".")


def format_date_br(value: date | datetime | str | None) -> str:
    """Formata data no padrão brasileiro dd/mm/aaaa."""
    if value is None:
        return "—"

    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value[:10])
            return parsed.strftime("%d/%m/%Y")
        except ValueError:
            return value

    return value.strftime("%d/%m/%Y")


def get_delta_html(
    delta: float | None,
    kind: Literal["pct", "pp", "brl", "int"] = "pct",
    invert_color: bool = False,
    label_suffix: str = "",
) -> str:
    """Gera tag HTML de badge semântico com classes do tema Kyberna.

    Argumentos:
        delta: Variação numérica absoluta ou percentual.
        kind: Tipo de formatação ('pct', 'pp', 'brl', 'int').
        invert_color: Inverte semântica de cor (positivo vira vermelho para custos/impostos/perdas).
        label_suffix: Sufixo adicional no texto (ex: 'vs. mês anterior').
    """
    if delta is None:
        return '<span class="badge badge-source">—</span>'

    is_positive = delta > 0
    is_zero = abs(delta) < 1e-6

    if is_zero:
        badge_class = "badge-source"
    elif is_positive:
        badge_class = "badge-negative" if invert_color else "badge-positive"
    else:
        badge_class = "badge-positive" if invert_color else "badge-negative"

    if kind == "pct":
        val_str = format_pct(delta, decimals=1, signed=True)
    elif kind == "pp":
        val_str = format_pp(delta, decimals=1, signed=True)
    elif kind == "brl":
        prefix = "+R$ " if is_positive else "-R$ "
        val_str = f"{prefix}{format_brl(abs(delta), compact=True, decimals=1)[3:]}"
    else:
        prefix = "+" if is_positive else ""
        val_str = f"{prefix}{format_int(delta)}"

    suffix = f" {label_suffix}" if label_suffix else ""
    return f'<span class="badge {badge_class}">{val_str}{suffix}</span>'


def _to_valid_float(value: object) -> float | None:
    """Converte entrada tabular para float ou retorna None quando nulo/NaN."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        num = float(value)
        return None if math.isnan(num) or math.isinf(num) else num
    text = str(value).strip()
    if not text or text.lower() in {"none", "nan", "nat", "<na>"}:
        return None
    try:
        num = float(text)
    except ValueError:
        return None
    return None if math.isnan(num) or math.isinf(num) else num


def fmt_brl_cell(value: object, decimals: int = 2) -> str:
    """Formata célula numérica de DataFrame em BRL pt-BR (ou '—' para nulos/NaN)."""
    num = _to_valid_float(value)
    return "—" if num is None else format_brl(num, compact=False, decimals=decimals)


def fmt_pct_cell(value: object, decimals: int = 1, signed: bool = False) -> str:
    """Formata célula percentual de DataFrame em pt-BR (ou '—' para nulos/NaN)."""
    num = _to_valid_float(value)
    return "—" if num is None else format_pct(num, decimals=decimals, signed=signed)


def fmt_int_cell(value: object) -> str:
    """Formata célula inteira de DataFrame com separador pt-BR (ou '—' para nulos/NaN)."""
    num = _to_valid_float(value)
    return "—" if num is None else format_int(num)
