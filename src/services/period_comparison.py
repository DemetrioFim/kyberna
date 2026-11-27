from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

import pandas as pd

from src.core.types import ScenarioId
from src.db.repository import DataRepository

__all__ = [
    "ComparisonWindow",
    "abs_delta",
    "int_delta",
    "pct_delta",
    "pp_delta",
    "resolve_effective_comparison_window",
]


@dataclass(frozen=True)
class ComparisonWindow:
    """Janela efetiva atual e comparativa resolvida para calculo padronizado de deltas."""

    cur_start: int | None
    cur_end: int | None
    prev_start: int
    prev_end: int


def _key_to_date(date_key: int) -> date:
    """Converte chave inteira `YYYYMMDD` em `datetime.date`."""
    year, rem = divmod(date_key, 10000)
    month, day = divmod(rem, 100)
    return date(year, month, day)


def _shift_year_back(dt: date) -> date:
    """Recua exatamente 1 ano mantendo seguranca para 29/02."""
    try:
        return dt.replace(year=dt.year - 1)
    except ValueError:
        return dt.replace(year=dt.year - 1, day=28)


def _fetch_scenario_min_max_keys(repo: DataRepository, scenario_id: ScenarioId) -> tuple[int, int] | None:
    """Consulta `(min_date_key, max_date_key)` disponiveis para o cenario."""
    sql = """
    SELECT MIN(date_key) AS min_key, MAX(date_key) AS max_key
    FROM gold.fact_sales
    WHERE scenario_id = ?
    """
    try:
        df = repo.query(sql, params=[scenario_id])
    except Exception:
        return None
    if df.empty or pd.isna(df.iloc[0]["min_key"]) or pd.isna(df.iloc[0]["max_key"]):
        return None
    return int(df.iloc[0]["min_key"]), int(df.iloc[0]["max_key"])


def resolve_effective_comparison_window(
    repo: DataRepository,
    scenario_id: ScenarioId,
    *,
    start_date_key: int | None = None,
    end_date_key: int | None = None,
    comp_start_date_key: int | None = None,
    comp_end_date_key: int | None = None,
    comparison_mode: Literal["pop", "yoy"] = "pop",
    min_max_keys: tuple[int, int] | None = None,
) -> ComparisonWindow | None:
    """Resolve a janela comparativa canonica para PoP e YoY em todos os servicos.

    Regras:
    - Janelas explicitas (`start_date_key` + `comp_start_date_key`/`comp_end_date_key`):
      comparam `(start_date_key, end_date_key)` vs. `(comp_start_date_key, comp_end_date_key)`.
    - `all + yoy` (`start_date_key is None` e `comparison_mode == "yoy"`):
      compara simetricamente ano mais recente vs. ano anterior equivalente.
    - `all + pop`: retorna `None` (sem comparacao espuria).
    """
    if start_date_key is not None and comp_start_date_key is not None and comp_end_date_key is not None:
        return ComparisonWindow(
            cur_start=start_date_key,
            cur_end=end_date_key,
            prev_start=comp_start_date_key,
            prev_end=comp_end_date_key,
        )

    if start_date_key is None and end_date_key is None and comparison_mode == "yoy":
        bounds = min_max_keys if min_max_keys is not None else _fetch_scenario_min_max_keys(repo, scenario_id)
        if bounds is None:
            return None
        min_key, max_key = bounds
        min_dt = _key_to_date(min_key)
        max_dt = _key_to_date(max_key)
        if max_dt.year <= min_dt.year:
            return None
        cur_y_start = max_dt.year * 10000 + 101
        cur_y_end = max_key
        prev_y_start = (max_dt.year - 1) * 10000 + 101
        prev_y_end = int(_shift_year_back(max_dt).strftime("%Y%m%d"))
        return ComparisonWindow(
            cur_start=cur_y_start,
            cur_end=cur_y_end,
            prev_start=prev_y_start,
            prev_end=prev_y_end,
        )

    return None


def pct_delta(cur: float, prev: float, *, decimals: int = 1) -> float | None:
    """Variacao percentual `(cur - prev) / prev * 100`, retornando `None` se `prev <= 0`."""
    if prev <= 0.0:
        return None
    return round(((cur - prev) / prev) * 100.0, decimals)


def pp_delta(cur: float, prev: float, *, decimals: int = 1) -> float | None:
    """Diferenca em pontos percentuais `(cur - prev)`."""
    return round(cur - prev, decimals)


def abs_delta(cur: float, prev: float, *, decimals: int = 1) -> float | None:
    """Diferenca absoluta `(cur - prev)`."""
    return round(cur - prev, decimals)


def int_delta(cur: int, prev: int) -> int | None:
    """Diferenca inteira `(cur - prev)`."""
    return int(cur - prev)
