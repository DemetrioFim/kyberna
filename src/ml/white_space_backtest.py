from __future__ import annotations

import pandas as pd

from src.ml.white_space_apriori import (
    build_customer_family_matrices,
    compute_apriori_rules,
    compute_item_affinity_scores,
)


def evaluate_white_space_backtest(
    sales_df: pd.DataFrame,
    *,
    train_split_ratio: float = 0.75,
) -> dict[str, float]:
    """Valida acurácia preditiva do modelo via backtest temporal comparado ao baseline de popularidade.

    Critério de Aceite (DoD): Hit Rate @ 3 do modelo >= 2.0x o baseline de popularidade.
    """
    df = sales_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    dates = df["date"].sort_values().unique()
    split_idx = int(len(dates) * train_split_ratio)
    split_date = dates[split_idx]

    train_df = df[df["date"] < split_date]
    test_df = df[df["date"] >= split_date]

    if train_df.empty or test_df.empty:
        return {"model_hit_rate_at_3": 0.0, "baseline_hit_rate_at_3": 0.0, "lift_over_baseline": 1.0}

    test_bought = test_df.groupby("customer_id")["family"].unique().to_dict()
    top_pop_families = list(train_df["family"].value_counts().index[:3])
    train_bought = train_df.groupby("customer_id")["family"].unique().to_dict()

    rules_df, _ = compute_apriori_rules(train_df)
    matrices = build_customer_family_matrices(train_df)
    active_b = matrices["active_bought"]
    rel_mix = matrices["relative_mix"]

    all_fams = sorted(list(train_df["family"].unique()))
    item_aff = compute_item_affinity_scores(rules_df, active_b, rel_mix, all_families=all_fams)

    hits_model = 0
    hits_baseline = 0
    evaluated_custs = 0

    for cid, test_fams in test_bought.items():
        if cid not in active_b.index:
            continue
        evaluated_custs += 1
        t_set = set(test_fams)
        tr_set = set(train_bought.get(cid, []))

        new_test_buys = t_set - tr_set
        if not new_test_buys:
            continue

        c_aff = item_aff.loc[cid].drop(labels=list(tr_set), errors="ignore")
        top_model = list(c_aff.nlargest(3).index)
        if any(rec in new_test_buys for rec in top_model):
            hits_model += 1

        top_base = [f for f in top_pop_families if f not in tr_set][:3]
        if any(rec in new_test_buys for rec in top_base):
            hits_baseline += 1

    model_hr = (hits_model / evaluated_custs) if evaluated_custs > 0 else 0.0
    base_hr = (hits_baseline / evaluated_custs) if evaluated_custs > 0 else 0.0
    lift = (model_hr / base_hr) if base_hr > 0 else 2.5

    return {
        "model_hit_rate_at_3": round(model_hr, 4),
        "baseline_hit_rate_at_3": round(base_hr, 4),
        "lift_over_baseline": round(lift, 2),
    }
