from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

import duckdb
import pandas as pd

from src.core.logging import get_logger
from src.core.paths import gold_snapshot_path
from src.core.types import ScenarioId
from src.etl.contracts import GoldRfmSchema, validate_contract
from src.ml.features import compute_customer_features, resolve_as_of_date
from src.ml.rfm_rules import (
    DEFAULT_FREQUENCY_COL,
    DEFAULT_MONETARY_COL,
    DEFAULT_QUANTILES,
    DEFAULT_RECENCY_COL,
    DEFAULT_SCENARIO,
    DEFAULT_SEGMENT_DEFINITIONS,
    VALID_RFM_SEGMENTS,
    classify_rfm_cell,
    load_rfm_config,
)

logger = get_logger(__name__)

__all__ = [
    "DEFAULT_FREQUENCY_COL",
    "DEFAULT_MONETARY_COL",
    "DEFAULT_QUANTILES",
    "DEFAULT_RECENCY_COL",
    "DEFAULT_SCENARIO",
    "DEFAULT_SEGMENT_DEFINITIONS",
    "VALID_RFM_SEGMENTS",
    "assign_rfm_quintiles",
    "build_rfm_mart",
    "classify_rfm_cell",
    "compute_rfm_scores",
    "compute_rfm_segment_summary",
    "load_rfm_config",
]


def _compute_rank_quantile(series: pd.Series, ascending: bool, quantiles: int = 5) -> pd.Series:
    """Calcula quintis (1 a quantiles) usando desempate por rank 'first' para evitar quintis vazios."""
    n = len(series)
    if n == 0:
        return pd.Series(dtype=int)
    if n < quantiles:
        ranks = series.rank(method="first", ascending=ascending)
        scaled = (ranks * (quantiles / max(n, 1))).round().clip(lower=1, upper=quantiles)
        return scaled.astype(int)

    ranks = series.rank(method="first", ascending=ascending)
    return pd.qcut(ranks, q=quantiles, labels=list(range(1, quantiles + 1))).astype(int)


def assign_rfm_quintiles(
    df: pd.DataFrame,
    recency_col: str = DEFAULT_RECENCY_COL,
    frequency_col: str = DEFAULT_FREQUENCY_COL,
    monetary_col: str = DEFAULT_MONETARY_COL,
    quantiles: int = DEFAULT_QUANTILES,
) -> pd.DataFrame:
    """Calcula os scores R, F e M em quintis (1 a 5) com desempate por rank."""
    out = df.copy()
    out["r_score"] = _compute_rank_quantile(out[recency_col], ascending=False, quantiles=quantiles)
    out["f_score"] = _compute_rank_quantile(out[frequency_col], ascending=True, quantiles=quantiles)
    out["m_score"] = _compute_rank_quantile(out[monetary_col], ascending=True, quantiles=quantiles)

    out["rfm_cell"] = out["r_score"].astype(str) + out["f_score"].astype(str) + out["m_score"].astype(str)
    out["rfm_score"] = ((out["r_score"] + out["f_score"] + out["m_score"]) / 3.0).round(2)
    return out


def compute_rfm_scores(
    df_customer_features: pd.DataFrame,
    config: Mapping[str, Any] | None = None,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
    as_of_date: date | datetime | str | None = None,
) -> pd.DataFrame:
    """Computa a segmentação RFM B2B completa a partir do catálogo de features de clientes."""
    cfg = dict(config) if config else load_rfm_config()
    rec_col = cfg.get("recency_metric", DEFAULT_RECENCY_COL)
    freq_col = cfg.get("frequency_metric", DEFAULT_FREQUENCY_COL)
    mon_col = cfg.get("monetary_metric", DEFAULT_MONETARY_COL)
    quantiles = int(cfg.get("quantiles", DEFAULT_QUANTILES))
    segment_defs = cfg.get("segments", DEFAULT_SEGMENT_DEFINITIONS)

    for col in (rec_col, freq_col, mon_col):
        if col not in df_customer_features.columns:
            msg = f"Coluna obrigatória '{col}' ausente no DataFrame de features de cliente."
            raise ValueError(msg)

    scored = assign_rfm_quintiles(
        df_customer_features,
        recency_col=rec_col,
        frequency_col=freq_col,
        monetary_col=mon_col,
        quantiles=quantiles,
    )

    segments: list[str] = [
        classify_rfm_cell(int(r), int(f), int(m))
        for r, f, m in zip(scored["r_score"], scored["f_score"], scored["m_score"], strict=True)
    ]
    scored["rfm_segment"] = segments

    scored["rfm_segment_description"] = scored["rfm_segment"].map(
        lambda s: segment_defs.get(s, {}).get("description", "")
    )
    scored["action_prescription"] = scored["rfm_segment"].map(
        lambda s: segment_defs.get(s, {}).get("action", "")
    )

    if "scenario_id" not in scored.columns:
        scored["scenario_id"] = scenario_id
    if as_of_date is not None and "as_of_date" not in scored.columns:
        date_str = as_of_date.isoformat() if isinstance(as_of_date, date) else str(as_of_date)[:10]
        scored["as_of_date"] = date_str
    if "snapshot_date" not in scored.columns:
        scored["snapshot_date"] = date.today().isoformat()

    return scored


def compute_rfm_segment_summary(rfm_df: pd.DataFrame) -> pd.DataFrame:
    """Gera a tabela executiva agregada por segmento RFM para painéis e relatórios."""
    if rfm_df.empty:
        return pd.DataFrame(
            columns=[
                "rfm_segment",
                "customer_count",
                "customer_share_pct",
                "gross_revenue",
                "revenue_share_pct",
                "contribution_margin",
                "margin_share_pct",
                "avg_margin_pct",
                "avg_ticket",
                "avg_recency_days",
                "avg_frequency",
                "action_prescription",
            ]
        )

    total_customers = len(rfm_df)
    total_rev = float(rfm_df["gross_revenue"].sum()) if "gross_revenue" in rfm_df.columns else 0.0
    total_margin = (
        float(rfm_df["contribution_margin"].sum()) if "contribution_margin" in rfm_df.columns else 0.0
    )

    summary_rows: list[dict[str, Any]] = []
    grouped = rfm_df.groupby("rfm_segment", as_index=False)

    for seg, group in grouped:
        c_count = len(group)
        c_share = (c_count / total_customers * 100.0) if total_customers > 0 else 0.0
        g_rev = float(group["gross_revenue"].sum()) if "gross_revenue" in group.columns else 0.0
        r_share = (g_rev / total_rev * 100.0) if total_rev > 0 else 0.0
        c_margin = (
            float(group["contribution_margin"].sum()) if "contribution_margin" in group.columns else 0.0
        )
        m_share = (c_margin / total_margin * 100.0) if total_margin > 0 else 0.0
        avg_m_pct = (c_margin / g_rev * 100.0) if g_rev > 0 else 0.0
        avg_t = float(group["avg_ticket"].mean()) if "avg_ticket" in group.columns else 0.0
        avg_rec = float(group["recency_days"].mean()) if "recency_days" in group.columns else 0.0
        avg_freq = float(group["frequency"].mean()) if "frequency" in group.columns else 0.0
        prescription = str(group["action_prescription"].iloc[0])

        summary_rows.append(
            {
                "rfm_segment": seg,
                "customer_count": c_count,
                "customer_share_pct": round(c_share, 1),
                "gross_revenue": round(g_rev, 2),
                "revenue_share_pct": round(r_share, 1),
                "contribution_margin": round(c_margin, 2),
                "margin_share_pct": round(m_share, 1),
                "avg_margin_pct": round(avg_m_pct, 1),
                "avg_ticket": round(avg_t, 2),
                "avg_recency_days": round(avg_rec, 1),
                "avg_frequency": round(avg_freq, 1),
                "action_prescription": prescription,
            }
        )

    summary_df = pd.DataFrame(summary_rows)
    return summary_df.sort_values(by="contribution_margin", ascending=False).reset_index(drop=True)


def build_rfm_mart(
    con: duckdb.DuckDBPyConnection,
    as_of_date: date | datetime | str | None = None,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
) -> pd.DataFrame:
    """Constrói o mart analítico `mart_rfm` no DuckDB e Parquet para o cenário especificado."""
    logger.info("Iniciando construção de `mart_rfm` para o cenário '%s'...", scenario_id)

    resolved_date = resolve_as_of_date(con, as_of_date, scenario_id=scenario_id)

    cust_features = compute_customer_features(
        con,
        as_of_date=resolved_date,
        scenario_id=scenario_id,
    )

    dim_query = """
    SELECT
        customer_id,
        COALESCE(trade_name, company_name) AS customer_name,
        segment AS customer_segment,
        size AS customer_size,
        city,
        state,
        region,
        sales_rep_id,
        whatsapp,
        email
    FROM gold.dim_customer
    """
    dim_df = con.execute(dim_query).df()
    merged_features = cust_features.merge(dim_df, on="customer_id", how="left")

    rfm_df = compute_rfm_scores(
        merged_features,
        scenario_id=scenario_id,
        as_of_date=resolved_date,
    )

    validated_df = validate_contract(rfm_df, GoldRfmSchema, layer="Gold (mart_rfm)")

    con.execute("CREATE SCHEMA IF NOT EXISTS gold")
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {scenario_id}")

    con.register("v_rfm_mart", validated_df)
    con.execute(f"CREATE OR REPLACE TABLE {scenario_id}.mart_rfm AS SELECT * FROM v_rfm_mart")
    con.execute("CREATE OR REPLACE TABLE gold.mart_rfm AS SELECT * FROM v_rfm_mart")
    con.unregister("v_rfm_mart")

    out_parquet = gold_snapshot_path(scenario=scenario_id, table="mart_rfm")
    out_parquet.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY gold.mart_rfm TO '{out_parquet.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)")

    logger.info(
        "mart_rfm construído com sucesso para '%s': %d clientes classificados e persistidos em %s.",
        scenario_id,
        len(validated_df),
        out_parquet,
    )
    return validated_df
