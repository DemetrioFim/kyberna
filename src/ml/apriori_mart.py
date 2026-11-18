from __future__ import annotations

from datetime import datetime

import duckdb
import pandas as pd

from src.core.paths import gold_snapshot_path
from src.core.types import ScenarioId
from src.etl.contracts import GoldAprioriRulesSchema, validate_contract


def build_apriori_rules_mart_df(
    family_rules_df: pd.DataFrame,
    sku_rules_df: pd.DataFrame,
    *,
    scenario_id: ScenarioId,
    as_of_date: str,
    snapshot_date: str | None = None,
) -> pd.DataFrame:
    """Unifica regras Apriori (família e SKU) no formato do contrato `GoldAprioriRulesSchema`."""
    snap = snapshot_date or datetime.now().strftime("%Y-%m-%d")
    frames: list[pd.DataFrame] = []
    if not family_rules_df.empty:
        f_df = family_rules_df.copy()
        f_df["rule_level"] = "family"
        f_df["antecedent_id"] = f_df["antecedent_family"]
        f_df["antecedent_name"] = f_df["antecedent_family"]
        f_df["consequent_id"] = f_df["consequent_family"]
        f_df["consequent_name"] = f_df["consequent_family"]
        frames.append(f_df)
    if not sku_rules_df.empty:
        s_df = sku_rules_df.copy()
        s_df["rule_level"] = "sku"
        frames.append(s_df)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out["scenario_id"] = scenario_id
    out["as_of_date"] = as_of_date
    out["snapshot_date"] = snap
    cols = [
        "scenario_id",
        "as_of_date",
        "rule_level",
        "antecedent_id",
        "antecedent_name",
        "antecedent_family",
        "consequent_id",
        "consequent_name",
        "consequent_family",
        "total_baskets",
        "antecedent_baskets",
        "consequent_baskets",
        "pair_baskets",
        "support",
        "confidence",
        "lift",
        "leverage",
        "snapshot_date",
    ]
    return out[cols].reset_index(drop=True)


def match_best_apriori_rule(
    target_family: str,
    active_families: set[str],
    family_rules_df: pd.DataFrame,
    sku_rules_df: pd.DataFrame | None = None,
) -> tuple[str, float, float, float]:
    """Seleciona a melhor regra Apriori aplicável ao mix ativo do cliente para `target_family`."""
    for df_src, name_col in (
        (sku_rules_df if sku_rules_df is not None else pd.DataFrame(), "antecedent_name"),
        (family_rules_df, "antecedent_family"),
    ):
        if df_src.empty or "consequent_family" not in df_src.columns:
            continue
        sub = df_src[df_src["consequent_family"] == target_family]
        if sub.empty:
            continue
        active_sub = sub[sub["antecedent_family"].isin(active_families)]
        chosen_df = active_sub if not active_sub.empty else sub
        ranked = chosen_df.assign(_score=chosen_df["lift"] * chosen_df["confidence"]).sort_values(
            "_score", ascending=False
        )
        top = ranked.iloc[0]
        return (
            str(top[name_col]),
            float(top["support"]),
            float(top["confidence"]),
            float(top["lift"]),
        )
    return target_family, 0.0, 0.0, 1.0


def persist_apriori_rules_mart(
    con: duckdb.DuckDBPyConnection,
    rules_all_df: pd.DataFrame,
    *,
    scenario_id: ScenarioId,
) -> int:
    """Valida e persiste `mart_apriori_rules` no DuckDB e em Parquet Zstandard."""
    if rules_all_df.empty:
        return 0
    validated = validate_contract(rules_all_df, GoldAprioriRulesSchema, layer="Gold (mart_apriori_rules)")
    con.execute("CREATE SCHEMA IF NOT EXISTS gold")
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {scenario_id}")
    con.register("v_apriori_rules_mart", validated)
    con.execute(
        f"CREATE OR REPLACE TABLE {scenario_id}.mart_apriori_rules AS SELECT * FROM v_apriori_rules_mart"
    )
    con.execute("CREATE OR REPLACE TABLE gold.mart_apriori_rules AS SELECT * FROM v_apriori_rules_mart")
    con.unregister("v_apriori_rules_mart")

    out_parquet = gold_snapshot_path(scenario=scenario_id, table="mart_apriori_rules")
    out_parquet.parent.mkdir(parents=True, exist_ok=True)
    con.execute(
        f"COPY gold.mart_apriori_rules TO '{out_parquet.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)"
    )
    return len(validated)
