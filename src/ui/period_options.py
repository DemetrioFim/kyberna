from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Final, Literal

from src.core.logging import get_logger
from src.core.types import ScenarioId

if TYPE_CHECKING:
    from src.db.repository import DataRepository

logger = get_logger(__name__)

ComparisonMode = Literal["pop", "yoy"]


def get_default_date_bounds(reference_date: date | None = None) -> tuple[date, date]:
    """Retorna `(01/01 de 2 anos atrás, D-1)` mantendo 2 anos cheios + ano corrente."""
    max_d = reference_date or (date.today() - timedelta(days=1))
    min_d = date(max_d.year - 2, 1, 1)
    return min_d, max_d


DEFAULT_MIN_DATE, DEFAULT_MAX_DATE = get_default_date_bounds()

COMPARISON_MODE_LABELS: Final[dict[ComparisonMode, str]] = {
    "pop": "vs. Período Anterior (PoP)",
    "yoy": "vs. Ano Anterior (YoY)",
}

PERIOD_PRESETS: Final[dict[str, str]] = {
    "all": "Histórico Completo",
    "ytd": "Ano Atual (YTD / 12m)",
    "fixed_quarter": "Trimestre Fixo (Calendário)",
    "rolling_quarter": "Trimestre Móvel (3 Meses)",
    "fixed_semester": "Semestre Fixo (S1 / S2)",
    "custom_month": "Mês Específico...",
    "custom_range": "Intervalo Personalizado (Calendário)...",
}

MONTH_NAMES_PT: Final[dict[int, str]] = {
    1: "Janeiro",
    2: "Fevereiro",
    3: "Março",
    4: "Abril",
    5: "Maio",
    6: "Junho",
    7: "Julho",
    8: "Agosto",
    9: "Setembro",
    10: "Outubro",
    11: "Novembro",
    12: "Dezembro",
}

MONTH_ABBR_PT: Final[dict[int, str]] = {
    1: "Jan",
    2: "Fev",
    3: "Mar",
    4: "Abr",
    5: "Mai",
    6: "Jun",
    7: "Jul",
    8: "Ago",
    9: "Set",
    10: "Out",
    11: "Nov",
    12: "Dez",
}

QUARTER_RANGE_PT: Final[dict[int, str]] = {
    1: "Jan-Mar",
    2: "Abr-Jun",
    3: "Jul-Set",
    4: "Out-Dez",
}

SEMESTER_RANGE_PT: Final[dict[int, str]] = {
    1: "Jan-Jun",
    2: "Jul-Dez",
}


@dataclass(frozen=True)
class PeriodBounds:
    """Delimitação de datas inteiras (YYYYMMDD) e rótulos de apresentação."""

    preset: str
    start_date_key: int | None
    end_date_key: int | None
    comparison_start_date_key: int | None
    comparison_end_date_key: int | None
    period_label: str
    comparison_label: str
    as_of_date_label: str = DEFAULT_MAX_DATE.strftime("%d/%m/%Y")


def coerce_date(value: object, fallback: date) -> date:
    """Converte Timestamp, datetime, str ISO ou date em `datetime.date`."""
    if value is None:
        return fallback
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if hasattr(value, "date") and callable(value.date):
        converted = value.date()
        if isinstance(converted, date):
            return converted
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return fallback


def key_to_date(value: object, fallback: date) -> date:
    """Converte chave inteira YYYYMMDD (ou date/str) em `datetime.date`."""
    if value is None:
        return fallback
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        key = int(str(value).strip())
        return date(key // 10000, (key % 10000) // 100, key % 100)
    except (ValueError, TypeError):
        return coerce_date(value, fallback)


def fetch_date_bounds(repo: DataRepository | None, scenario_id: ScenarioId) -> tuple[date, date]:
    """Consulta `MIN(date_key)` e `MAX(date_key)` reais de `fact_sales` com fallback seguro."""
    if repo is None:
        return DEFAULT_MIN_DATE, DEFAULT_MAX_DATE
    try:
        df = repo.table("fact_sales", scenario_id=scenario_id, columns=["date_key"])
        if not df.empty and "date_key" in df.columns:
            min_d = key_to_date(df["date_key"].min(), DEFAULT_MIN_DATE)
            max_d = key_to_date(df["date_key"].max(), DEFAULT_MAX_DATE)
            if min_d <= max_d:
                return min_d, max_d
    except Exception as exc:
        logger.debug("Fallback de limites de data para %s: %s", scenario_id, exc)
    return DEFAULT_MIN_DATE, DEFAULT_MAX_DATE


def date_to_key(d: date) -> int:
    """Converte `datetime.date` para chave inteira YYYYMMDD."""
    return d.year * 10000 + d.month * 100 + d.day


def fmt_br(d: date) -> str:
    """Formata data em dd/mm/aaaa."""
    return d.strftime("%d/%m/%Y")


def shift_years(d: date, years: int) -> date:
    """Desloca N anos tratando 29/02 em anos não bissextos com fallback para 28/02."""
    target_year = d.year + years
    try:
        return d.replace(year=target_year)
    except ValueError:
        return date(target_year, d.month, 28)


def add_months(year: int, month: int, delta_months: int) -> tuple[int, int]:
    """Soma/subtrai meses calendário retornando `(ano, mes)`."""
    idx = (year * 12 + (month - 1)) + delta_months
    out_year, out_m0 = divmod(idx, 12)
    return out_year, out_m0 + 1


def month_bounds(year: int, month: int) -> tuple[date, date]:
    """Retorna `(primeiro_dia, ultimo_dia)` do mês."""
    _, last_day = calendar.monthrange(year, month)
    return date(year, month, 1), date(year, month, last_day)


def build_month_options(
    min_date: date = DEFAULT_MIN_DATE,
    max_date: date = DEFAULT_MAX_DATE,
) -> dict[str, str]:
    """Constrói mapa ordenado `{YYYY-MM: 'Mês / Ano'}` do mais recente ao mais antigo."""
    if min_date > max_date:
        min_date, max_date = max_date, min_date
    cur_y, cur_m = max_date.year, max_date.month
    min_idx = min_date.year * 12 + min_date.month
    options: dict[str, str] = {}
    while (cur_y * 12 + cur_m) >= min_idx:
        options[f"{cur_y:04d}-{cur_m:02d}"] = f"{MONTH_NAMES_PT[cur_m]} / {cur_y}"
        cur_y, cur_m = add_months(cur_y, cur_m, -1)
    return options


MONTH_LABELS: Final[dict[str, str]] = build_month_options()


def build_quarter_options(
    min_date: date = DEFAULT_MIN_DATE,
    max_date: date = DEFAULT_MAX_DATE,
) -> dict[str, str]:
    """Constrói mapa `{YYYY-Qn: 'nº Tri / YYYY (...)'}` dos trimestres disponíveis."""
    if min_date > max_date:
        min_date, max_date = max_date, min_date
    min_q_idx = min_date.year * 4 + ((min_date.month - 1) // 3)
    max_q_idx = max_date.year * 4 + ((max_date.month - 1) // 3)
    options: dict[str, str] = {}
    for q_idx in range(max_q_idx, min_q_idx - 1, -1):
        year, q0 = divmod(q_idx, 4)
        q = q0 + 1
        options[f"{year}-Q{q}"] = f"{q}º Tri / {year} ({QUARTER_RANGE_PT[q]})"
    return options


def build_semester_options(
    min_date: date = DEFAULT_MIN_DATE,
    max_date: date = DEFAULT_MAX_DATE,
) -> dict[str, str]:
    """Constrói mapa `{YYYY-Sn: 'nº Sem / YYYY (...)'}` dos semestres disponíveis."""
    if min_date > max_date:
        min_date, max_date = max_date, min_date
    min_s_idx = min_date.year * 2 + (0 if min_date.month <= 6 else 1)
    max_s_idx = max_date.year * 2 + (0 if max_date.month <= 6 else 1)
    options: dict[str, str] = {}
    for s_idx in range(max_s_idx, min_s_idx - 1, -1):
        year, s0 = divmod(s_idx, 2)
        s = s0 + 1
        options[f"{year}-S{s}"] = f"{s}º Sem / {year} ({SEMESTER_RANGE_PT[s]})"
    return options
