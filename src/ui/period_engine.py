from __future__ import annotations

from datetime import date, timedelta

from src.ui.period_options import (
    COMPARISON_MODE_LABELS,
    DEFAULT_MAX_DATE,
    DEFAULT_MIN_DATE,
    MONTH_ABBR_PT,
    MONTH_LABELS,
    MONTH_NAMES_PT,
    PERIOD_PRESETS,
    ComparisonMode,
    PeriodBounds,
    add_months,
    build_month_options,
    build_quarter_options,
    build_semester_options,
    coerce_date,
    date_to_key,
    fetch_date_bounds,
    fmt_br,
    month_bounds,
    shift_years,
)

__all__ = [
    "COMPARISON_MODE_LABELS",
    "DEFAULT_MAX_DATE",
    "MONTH_LABELS",
    "PERIOD_PRESETS",
    "ComparisonMode",
    "PeriodBounds",
    "build_month_options",
    "build_quarter_options",
    "build_semester_options",
    "fetch_date_bounds",
    "resolve_period_bounds",
]


def _parse_ym(raw: str | None, fallback: date) -> tuple[int, int]:
    """Extrai `(ano, mes)` de `'YYYY-MM'` com fallback seguro."""
    if raw and "-" in raw:
        try:
            y_s, m_s = raw.split("-", maxsplit=1)
            y, m = int(y_s), int(m_s)
            if 1 <= m <= 12 and 2000 <= y <= 2100:
                return y, m
        except ValueError:
            pass
    return fallback.year, fallback.month


def _parse_quarter(raw: str | None, fallback: date) -> tuple[int, int]:
    """Extrai `(ano, trimestre 1..4)` de `'YYYY-Qn'`."""
    if raw and "-Q" in raw:
        try:
            y_s, q_s = raw.split("-Q", maxsplit=1)
            y, q = int(y_s), int(q_s)
            if 1 <= q <= 4 and 2000 <= y <= 2100:
                return y, q
        except ValueError:
            pass
    return fallback.year, ((fallback.month - 1) // 3) + 1


def _parse_semester(raw: str | None, fallback: date) -> tuple[int, int]:
    """Extrai `(ano, semestre 1..2)` de `'YYYY-Sn'`."""
    if raw and "-S" in raw:
        try:
            y_s, s_s = raw.split("-S", maxsplit=1)
            y, s = int(y_s), int(s_s)
            if s in (1, 2) and 2000 <= y <= 2100:
                return y, s
        except ValueError:
            pass
    return fallback.year, (1 if fallback.month <= 6 else 2)


def _quarter_bounds(year: int, q: int) -> tuple[date, date]:
    start_m = (q - 1) * 3 + 1
    end_m = start_m + 2
    start, _ = month_bounds(year, start_m)
    _, end = month_bounds(year, end_m)
    return start, end


def _semester_bounds(year: int, s: int) -> tuple[date, date]:
    if s == 1:
        return date(year, 1, 1), date(year, 6, 30)
    return date(year, 7, 1), date(year, 12, 31)


def _normalize_preset(preset: str) -> str:
    """Mapeia aliases legados (`last_12m`, `last_6m`, `last_3m`) para presets canônicos."""
    aliases = {
        "last_12m": "ytd",
        "last_6m": "s2",
        "last_3m": "q4",
    }
    return aliases.get(preset, preset)


def _build_ytd_bounds(eff_max: date, mode: ComparisonMode) -> PeriodBounds:
    start = date(eff_max.year, 1, 1)
    end = eff_max
    is_full_year = eff_max == date(eff_max.year, 12, 31)
    if mode == "yoy" or is_full_year:
        comp_start = date(eff_max.year - 1, 1, 1)
        comp_end = date(eff_max.year - 1, 12, 31) if is_full_year else shift_years(eff_max, -1)
        comp_tag = "Ano Anterior - YoY" if is_full_year else "YTD Anterior - YoY"
    else:
        span_days = (end - start).days + 1
        comp_end = start - timedelta(days=1)
        comp_start = comp_end - timedelta(days=span_days - 1)
        comp_tag = "Período Anterior - PoP"

    label_suffix = "Ano Atual / 12m" if is_full_year else f"YTD {eff_max.year}"
    return PeriodBounds(
        preset="ytd",
        start_date_key=date_to_key(start),
        end_date_key=date_to_key(end),
        comparison_start_date_key=date_to_key(comp_start),
        comparison_end_date_key=date_to_key(comp_end),
        period_label=f"{fmt_br(start)} a {fmt_br(end)} ({label_suffix})",
        comparison_label=f"vs. {fmt_br(comp_start)} a {fmt_br(comp_end)} ({comp_tag})",
        as_of_date_label=fmt_br(eff_max),
    )


def _build_quarter_bounds(
    preset: str,
    selected_quarter: str | None,
    eff_max: date,
    mode: ComparisonMode,
) -> PeriodBounds:
    q_default = f"{eff_max.year}-Q4" if preset == "q4" else None
    year, q = _parse_quarter(selected_quarter or q_default, eff_max)
    start, end = _quarter_bounds(year, q)
    if year == eff_max.year:
        end = min(end, eff_max)
    if mode == "yoy":
        comp_start = shift_years(start, -1)
        comp_end = shift_years(end, -1)
        comp_desc = f"{q}º Tri/{str(year - 1)[-2:]} - YoY"
    else:
        prev_y, prev_q = (year - 1, 4) if q == 1 else (year, q - 1)
        comp_start, comp_end = _quarter_bounds(prev_y, prev_q)
        comp_desc = f"{prev_q}º Tri/{str(prev_y)[-2:]} - PoP"

    return PeriodBounds(
        preset=preset,
        start_date_key=date_to_key(start),
        end_date_key=date_to_key(end),
        comparison_start_date_key=date_to_key(comp_start),
        comparison_end_date_key=date_to_key(comp_end),
        period_label=f"{fmt_br(start)} a {fmt_br(end)} ({q}º Trimestre/{year})",
        comparison_label=f"vs. {fmt_br(comp_start)} a {fmt_br(comp_end)} ({comp_desc})",
        as_of_date_label=fmt_br(eff_max),
    )


def _build_rolling_quarter_bounds(
    end_month: str | None,
    eff_max: date,
    mode: ComparisonMode,
) -> PeriodBounds:
    end_y, end_m = _parse_ym(end_month, eff_max)
    start_y, start_m = add_months(end_y, end_m, -2)
    start, _ = month_bounds(start_y, start_m)
    _, end = month_bounds(end_y, end_m)
    end = min(end, eff_max)

    if mode == "yoy":
        comp_start = shift_years(start, -1)
        comp_end = shift_years(end, -1)
        comp_desc = f"{MONTH_ABBR_PT[start_m]}-{MONTH_ABBR_PT[end_m]}/{end_y - 1} - YoY"
    else:
        c_end_y, c_end_m = add_months(start_y, start_m, -1)
        c_start_y, c_start_m = add_months(c_end_y, c_end_m, -2)
        comp_start, _ = month_bounds(c_start_y, c_start_m)
        _, comp_end = month_bounds(c_end_y, c_end_m)
        comp_desc = f"{MONTH_ABBR_PT[c_start_m]}-{MONTH_ABBR_PT[c_end_m]}/{c_end_y} - PoP"

    window_tag = f"Tri Móvel {MONTH_ABBR_PT[start_m]}-{MONTH_ABBR_PT[end_m]}/{end_y}"
    return PeriodBounds(
        preset="rolling_quarter",
        start_date_key=date_to_key(start),
        end_date_key=date_to_key(end),
        comparison_start_date_key=date_to_key(comp_start),
        comparison_end_date_key=date_to_key(comp_end),
        period_label=f"{fmt_br(start)} a {fmt_br(end)} ({window_tag})",
        comparison_label=f"vs. {fmt_br(comp_start)} a {fmt_br(comp_end)} ({comp_desc})",
        as_of_date_label=fmt_br(eff_max),
    )


def _build_semester_bounds(
    preset: str,
    selected_semester: str | None,
    eff_max: date,
    mode: ComparisonMode,
) -> PeriodBounds:
    s_default = f"{eff_max.year}-S2" if preset == "s2" else None
    year, s = _parse_semester(selected_semester or s_default, eff_max)
    start, end = _semester_bounds(year, s)
    if year == eff_max.year:
        end = min(end, eff_max)
    if mode == "yoy":
        comp_start = shift_years(start, -1)
        comp_end = shift_years(end, -1)
        comp_desc = f"{s}º Sem/{year - 1} - YoY"
    else:
        prev_y, prev_s = (year, 1) if s == 2 else (year - 1, 2)
        comp_start, comp_end = _semester_bounds(prev_y, prev_s)
        comp_desc = f"{prev_s}º Sem/{prev_y} - PoP"

    return PeriodBounds(
        preset=preset,
        start_date_key=date_to_key(start),
        end_date_key=date_to_key(end),
        comparison_start_date_key=date_to_key(comp_start),
        comparison_end_date_key=date_to_key(comp_end),
        period_label=f"{fmt_br(start)} a {fmt_br(end)} ({s}º Semestre/{year})",
        comparison_label=f"vs. {fmt_br(comp_start)} a {fmt_br(comp_end)} ({comp_desc})",
        as_of_date_label=fmt_br(eff_max),
    )


def _build_month_bounds(
    preset: str,
    selected_month: str | None,
    eff_max: date,
    mode: ComparisonMode,
) -> PeriodBounds:
    target = None if preset == "last_month" else selected_month
    year, month = _parse_ym(target, eff_max)
    start, end = month_bounds(year, month)
    if mode == "yoy":
        comp_start, comp_end = month_bounds(year - 1, month)
        comp_tag = f"{MONTH_NAMES_PT[month]} / {year - 1} - YoY"
    else:
        prev_y, prev_m = add_months(year, month, -1)
        comp_start, comp_end = month_bounds(prev_y, prev_m)
        comp_tag = f"{MONTH_NAMES_PT[prev_m]} / {prev_y} - MoM"

    return PeriodBounds(
        preset=preset,
        start_date_key=date_to_key(start),
        end_date_key=date_to_key(end),
        comparison_start_date_key=date_to_key(comp_start),
        comparison_end_date_key=date_to_key(comp_end),
        period_label=f"{fmt_br(start)} a {fmt_br(end)} ({MONTH_NAMES_PT[month]} / {year})",
        comparison_label=f"vs. {fmt_br(comp_start)} a {fmt_br(comp_end)} ({comp_tag})",
        as_of_date_label=fmt_br(eff_max),
    )


def _build_custom_range_bounds(
    custom_start: date | str | None,
    custom_end: date | str | None,
    eff_max: date,
    mode: ComparisonMode,
) -> PeriodBounds:
    default_start = date(eff_max.year, eff_max.month, 1)
    start = coerce_date(custom_start, default_start)
    end = coerce_date(custom_end, eff_max)
    if start > end:
        start, end = end, start

    if mode == "yoy":
        comp_start = shift_years(start, -1)
        comp_end = shift_years(end, -1)
        comp_tag = "YoY"
    else:
        span_days = (end - start).days + 1
        comp_end = start - timedelta(days=1)
        comp_start = comp_end - timedelta(days=span_days - 1)
        comp_tag = "PoP"

    return PeriodBounds(
        preset="custom_range",
        start_date_key=date_to_key(start),
        end_date_key=date_to_key(end),
        comparison_start_date_key=date_to_key(comp_start),
        comparison_end_date_key=date_to_key(comp_end),
        period_label=f"{fmt_br(start)} a {fmt_br(end)} (Intervalo Livre)",
        comparison_label=f"vs. {fmt_br(comp_start)} a {fmt_br(comp_end)} ({comp_tag})",
        as_of_date_label=fmt_br(eff_max),
    )


def resolve_period_bounds(
    preset: str = "all",
    selected_month: str | None = None,
    *,
    comparison_mode: ComparisonMode = "pop",
    selected_quarter: str | None = None,
    selected_semester: str | None = None,
    rolling_end_month: str | None = None,
    custom_start: date | str | None = None,
    custom_end: date | str | None = None,
    min_date: date | None = None,
    max_date: date | None = None,
) -> PeriodBounds:
    """Calcula os limites temporais do período ativo e de seu comparativo (`PoP` ou `YoY`)."""
    eff_min = min_date or DEFAULT_MIN_DATE
    eff_max = max_date or DEFAULT_MAX_DATE
    if eff_min > eff_max:
        eff_min, eff_max = eff_max, eff_min

    norm_preset = _normalize_preset(preset)
    mode: ComparisonMode = "yoy" if comparison_mode == "yoy" else "pop"

    if norm_preset == "ytd":
        result = _build_ytd_bounds(eff_max, mode)
    elif norm_preset in ("fixed_quarter", "q4"):
        result = _build_quarter_bounds(norm_preset, selected_quarter, eff_max, mode)
    elif norm_preset == "rolling_quarter":
        result = _build_rolling_quarter_bounds(rolling_end_month or selected_month, eff_max, mode)
    elif norm_preset in ("fixed_semester", "s2"):
        result = _build_semester_bounds(norm_preset, selected_semester, eff_max, mode)
    elif norm_preset in ("custom_month", "last_month"):
        result = _build_month_bounds(norm_preset, selected_month, eff_max, mode)
    elif norm_preset == "custom_range":
        result = _build_custom_range_bounds(custom_start, custom_end, eff_max, mode)
    else:
        total_months = (eff_max.year - eff_min.year) * 12 + (eff_max.month - eff_min.month) + 1
        if mode == "yoy" and eff_max.year > eff_min.year:
            prev_year = eff_max.year - 1
            comp_start = date(prev_year, 1, 1)
            comp_end = (
                date(prev_year, 12, 31) if eff_max == date(eff_max.year, 12, 31) else shift_years(eff_max, -1)
            )
            comp_start_key: int | None = date_to_key(comp_start)
            comp_end_key: int | None = date_to_key(comp_end)
            comp_label = f"Ano {eff_max.year} vs. {prev_year} (YoY · Base 12m)"
        elif mode == "yoy":
            comp_start_key = None
            comp_end_key = None
            comp_label = "Histórico Global Consolidado (sem ano anterior)"
        else:
            comp_start_key = None
            comp_end_key = None
            comp_label = f"Histórico Global Consolidado ({total_months}m · sem PoP)"
        result = PeriodBounds(
            preset="all",
            start_date_key=None,
            end_date_key=None,
            comparison_start_date_key=comp_start_key,
            comparison_end_date_key=comp_end_key,
            period_label=f"{fmt_br(eff_min)} a {fmt_br(eff_max)} ({total_months} Meses)",
            comparison_label=comp_label,
            as_of_date_label=fmt_br(eff_max),
        )
    return result
