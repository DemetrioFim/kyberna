from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

import duckdb
import numpy as np
import pandas as pd
from scipy.stats import norm

from src.core.logging import get_logger
from src.core.paths import gold_snapshot_path
from src.core.types import ScenarioId
from src.etl.contracts import GoldCustomerRiskSchema, validate_contract
from src.ml.churn_cycle import (
    DEFAULT_CUTOFFS,
    DEFAULT_SCENARIO,
    DEFAULT_STATUS_DEFINITIONS,
    classify_churn_risk_status,
    compute_individual_cycle,
    load_churn_config,
)
from src.ml.features import compute_customer_features, resolve_as_of_date

logger = get_logger(__name__)

__all__ = [
    "DEFAULT_CUTOFFS",
    "DEFAULT_SCENARIO",
    "DEFAULT_STATUS_DEFINITIONS",
    "build_customer_risk_mart",
    "classify_churn_risk_status",
    "compute_churn_risk",
    "compute_customer_risk_summary",
    "compute_individual_cycle",
    "load_churn_config",
]


def compute_churn_risk(
    df_features: pd.DataFrame,
    *,
    config: Mapping[str, Any] | None = None,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
    as_of_date: date | datetime | str | None = None,
) -> pd.DataFrame:
    """Calcula probabilidade de churn e status de risco com valores financeiros expostos.

    Args:
        df_features: DataFrame com features de clientes e atributos cadastrais.
        config: Dicionário opcional com configurações de churn de pipeline.yaml.
        scenario_id: Identificador do cenário comercial.
        as_of_date: Data de corte temporal de referência.

    Returns:
        DataFrame com colunas canônicas prontas para o mart analítico e conformidade Gold.
    """
    churn_cfg = dict(config or load_churn_config())

    prior_k = int(churn_cfg.get("prior_shrinkage_k", 3))
    min_cycle = float(churn_cfg.get("min_cycle_days", 7.0))
    min_std = float(churn_cfg.get("min_std_days", 5.0))

    cutoffs = (
        float(churn_cfg.get("healthy_ratio_cutoff", DEFAULT_CUTOFFS[0])),
        float(churn_cfg.get("attention_ratio_cutoff", DEFAULT_CUTOFFS[1])),
        float(churn_cfg.get("at_risk_ratio_cutoff", DEFAULT_CUTOFFS[2])),
    )

    # 1. Ciclo individual bayesiano
    df = compute_individual_cycle(
        df_features,
        prior_shrinkage_k=prior_k,
        min_cycle_days=min_cycle,
        min_std_days=min_std,
    )

    # 2. Razão de atraso e z-score
    recency = df["recency_days"].fillna(0).astype(float)
    df["delay_ratio"] = (recency / df["expected_cycle_days"]).round(3)

    z_score = (recency - df["expected_cycle_days"]) / df["cycle_std_days"]
    churn_prob = norm.cdf(z_score)
    df["churn_probability"] = np.clip(churn_prob, 0.0, 1.0).round(4)

    # 3. Classificação em 4 status prescritivos
    df["risk_status"] = [classify_churn_risk_status(r, cutoffs) for r in df["delay_ratio"]]

    # 4. Cálculo financeiro de exposição a risco (R$)
    if "revenue_12m" in df.columns:
        base_rev_series = pd.Series(
            np.where(df["revenue_12m"] > 0, df["revenue_12m"], df["gross_revenue"]),
            index=df.index,
            dtype="float64",
        ).fillna(0.0)
    else:
        base_rev_series = df["gross_revenue"].fillna(0.0).astype(float)

    if "margin_12m" in df.columns:
        base_marg_series = pd.Series(
            np.where(df["margin_12m"].notna(), df["margin_12m"], df["contribution_margin"]),
            index=df.index,
            dtype="float64",
        ).fillna(0.0)
    else:
        base_marg_series = df["contribution_margin"].fillna(0.0).astype(float)

    # Ponderação do risco: 100% para Crítico/Imediato, 50% para Atenção, 0% para No Ciclo
    status_multiplier = (
        df["risk_status"]
        .map(
            {
                "Adormecido / Perdido": 1.0,
                "Em Risco Imediato": 1.0,
                "Atenção": 0.5,
                "No Ciclo": 0.0,
            }
        )
        .fillna(0.0)
    )

    df["annual_revenue_at_risk"] = (base_rev_series * status_multiplier).round(2)
    df["annual_margin_at_risk"] = (base_marg_series * status_multiplier).round(2)

    # 5. Enriquecimento semântico e prescritivo
    descriptions = {k: v["description"] for k, v in DEFAULT_STATUS_DEFINITIONS.items()}
    actions = {k: v["action"] for k, v in DEFAULT_STATUS_DEFINITIONS.items()}
    colors = {k: v["badge_color"] for k, v in DEFAULT_STATUS_DEFINITIONS.items()}

    df["risk_status_description"] = df["risk_status"].map(descriptions).fillna("")
    df["action_prescription"] = df["risk_status"].map(actions).fillna("")
    df["badge_color"] = df["risk_status"].map(colors).fillna("neutral")

    # Metadados de rastreabilidade
    ref_as_of = str(as_of_date) if as_of_date else datetime.now().strftime("%Y-%m-%d")
    df["scenario_id"] = scenario_id
    df["as_of_date"] = ref_as_of
    df["snapshot_date"] = datetime.now().strftime("%Y-%m-%d")

    return df


def compute_customer_risk_summary(df_risk: pd.DataFrame) -> pd.DataFrame:
    """Gera um resumo executivo da distribuição de risco e valores financeiros expostos.

    Args:
        df_risk: DataFrame processado por `compute_churn_risk`.

    Returns:
        DataFrame com colunas agregadas por status de risco.
    """
    total_cust = len(df_risk)
    if total_cust == 0:
        return pd.DataFrame()

    total_rev_risk = df_risk["annual_revenue_at_risk"].sum()
    total_marg_risk = df_risk["annual_margin_at_risk"].sum()

    summary_rows: list[dict[str, Any]] = []
    order = ["Adormecido / Perdido", "Em Risco Imediato", "Atenção", "No Ciclo"]

    for st_name in order:
        subset = df_risk[df_risk["risk_status"] == st_name]
        n_cust = len(subset)
        rev_risk = subset["annual_revenue_at_risk"].sum()
        marg_risk = subset["annual_margin_at_risk"].sum()

        rev_share = round(rev_risk / total_rev_risk * 100.0, 2) if total_rev_risk > 0 else 0.0
        marg_share = round(marg_risk / total_marg_risk * 100.0, 2) if total_marg_risk > 0 else 0.0

        summary_rows.append(
            {
                "risk_status": st_name,
                "customer_count": n_cust,
                "customer_share_pct": round(n_cust / total_cust * 100.0, 2),
                "annual_revenue_at_risk": round(rev_risk, 2),
                "annual_margin_at_risk": round(marg_risk, 2),
                "revenue_share_pct": rev_share,
                "margin_share_pct": marg_share,
                "avg_delay_ratio": round(subset["delay_ratio"].median(), 2) if n_cust > 0 else 0.0,
                "avg_churn_prob": round(subset["churn_probability"].mean(), 4) if n_cust > 0 else 0.0,
            }
        )

    return pd.DataFrame(summary_rows)


def build_customer_risk_mart(
    con: duckdb.DuckDBPyConnection,
    as_of_date: date | datetime | str | None = None,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
) -> pd.DataFrame:
    """Constrói o mart analítico `mart_customer_risk` no DuckDB e Parquet para o cenário especificado."""
    logger.info("Iniciando construção de `mart_customer_risk` para o cenário '%s'...", scenario_id)

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

    churn_df = compute_churn_risk(
        merged_features,
        scenario_id=scenario_id,
        as_of_date=resolved_date,
    )

    validated_df = validate_contract(churn_df, GoldCustomerRiskSchema, layer="Gold (mart_customer_risk)")

    con.execute("CREATE SCHEMA IF NOT EXISTS gold")
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {scenario_id}")

    con.register("v_customer_risk_mart", validated_df)
    con.execute(
        f"CREATE OR REPLACE TABLE {scenario_id}.mart_customer_risk AS SELECT * FROM v_customer_risk_mart"
    )
    con.execute("CREATE OR REPLACE TABLE gold.mart_customer_risk AS SELECT * FROM v_customer_risk_mart")
    con.unregister("v_customer_risk_mart")

    out_parquet = gold_snapshot_path(scenario=scenario_id, table="mart_customer_risk")
    out_parquet.parent.mkdir(parents=True, exist_ok=True)
    con.execute(
        f"COPY gold.mart_customer_risk TO '{out_parquet.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)"
    )

    logger.info(
        "mart_customer_risk construído com sucesso para '%s': %d clientes classificados e persistidos em %s.",
        scenario_id,
        len(validated_df),
        out_parquet,
    )
    return validated_df
