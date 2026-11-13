from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any, Final

import numpy as np
import pandas as pd
import yaml
from sklearn.neighbors import NearestNeighbors

from src.core.logging import get_logger
from src.core.paths import config_path
from src.core.types import ScenarioId

logger = get_logger(__name__)

DEFAULT_SCENARIO: Final[ScenarioId] = "c1_toys"


def load_white_space_config() -> dict[str, Any]:
    """Carrega parâmetros analíticos de White Space e Apriori de `config/pipeline.yaml`."""
    pipeline_file = config_path("pipeline.yaml")
    if pipeline_file.exists():
        try:
            with open(pipeline_file, encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            return dict(cfg.get("thresholds", {}).get("white_space", {}))
        except Exception as exc:
            logger.warning("Falha ao ler bloco white_space de pipeline.yaml: %s. Usando defaults.", exc)
    return {}


def compute_apriori_rules(  # noqa: PLR0912
    orders_items_df: pd.DataFrame,
    *,
    min_support: float = 0.03,
    min_confidence: float = 0.15,
) -> tuple[pd.DataFrame, dict[str, tuple[str, str]]]:
    """Minera regras de associação Apriori A => B em nível de cestas/pedidos e identifica o SKU Âncora."""
    if orders_items_df.empty:
        return pd.DataFrame(), {}

    sku_totals = pd.DataFrame(
        orders_items_df.groupby(["family", "product_id", "product_name"])["gross_revenue"].sum().reset_index()
    ).sort_values(by=["family", "gross_revenue"], ascending=[True, False])

    anchor_skus: dict[str, tuple[str, str]] = {}
    for fam, group in sku_totals.groupby("family"):
        top_row = group.iloc[0]
        anchor_skus[str(fam)] = (str(top_row["product_id"]), str(top_row["product_name"]))

    df_baskets = orders_items_df.copy()
    if "basket_id" in df_baskets.columns:
        basket_col = "basket_id"
    else:
        fam_per_order = df_baskets.groupby("order_id")["family"].nunique()
        if (fam_per_order > 1).any():
            basket_col = "order_id"
        elif "customer_id" in df_baskets.columns and "date" in df_baskets.columns:
            df_baskets["basket_id"] = (
                df_baskets["customer_id"].astype(str) + "_" + df_baskets["date"].astype(str)
            )
            basket_col = "basket_id"
        else:
            basket_col = "order_id"

    baskets = df_baskets.groupby(basket_col)["family"].unique().reset_index()
    total_orders = len(baskets)
    if total_orders == 0:
        return pd.DataFrame(), anchor_skus

    fam_counts: dict[str, int] = {}
    for itemset in baskets["family"]:
        for fam in itemset:
            fam_counts[str(fam)] = fam_counts.get(str(fam), 0) + 1

    fam_support = {fam: count / total_orders for fam, count in fam_counts.items()}

    pair_counts: dict[tuple[str, str], int] = {}
    for itemset in baskets["family"]:
        items = sorted(str(f) for f in itemset)
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                p1, p2 = items[i], items[j]
                pair_counts[(p1, p2)] = pair_counts.get((p1, p2), 0) + 1
                pair_counts[(p2, p1)] = pair_counts.get((p2, p1), 0) + 1

    rules: list[dict[str, Any]] = []
    for (ant, con), pair_cnt in pair_counts.items():
        sup_pair = pair_cnt / total_orders
        if sup_pair < min_support:
            continue

        sup_ant = fam_support.get(ant, 0.0)
        sup_con = fam_support.get(con, 0.0)
        if sup_ant <= 0 or sup_con <= 0:
            continue

        confidence = sup_pair / sup_ant
        if confidence < min_confidence:
            continue

        lift = confidence / sup_con
        rules.append(
            {
                "antecedent_family": ant,
                "consequent_family": con,
                "support": round(sup_pair, 4),
                "confidence": round(confidence, 4),
                "lift": round(lift, 2),
            }
        )

    rules_df = pd.DataFrame(rules)
    if not rules_df.empty:
        rules_df = rules_df.sort_values(by="confidence", ascending=False).reset_index(drop=True)

    return rules_df, anchor_skus


def build_customer_family_matrices(
    sales_df: pd.DataFrame,
    *,
    active_window_days: int = 180,
    min_active_share: float = 0.05,
    reference_date: date | None = None,
) -> dict[str, pd.DataFrame]:
    """Constrói matrizes de compras ativas, históricas e de receita por cliente x família."""
    if sales_df.empty:
        return {}

    ref = reference_date or pd.to_datetime(sales_df["date"]).dt.date.max()
    active_cutoff = ref - pd.Timedelta(days=active_window_days)

    df = sales_df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    all_fams = sorted([str(f) for f in df["family"].unique()])

    annual_cutoff = ref - pd.Timedelta(days=365)
    recent_annual_sales = df[df["date"] >= annual_cutoff]
    if recent_annual_sales.empty:
        recent_annual_sales = df

    annual_revenue_matrix = (
        recent_annual_sales.groupby(["customer_id", "family"])["gross_revenue"].sum().unstack().fillna(0.0)
    )
    annual_revenue_matrix = annual_revenue_matrix.reindex(columns=all_fams, fill_value=0.0)

    row_sums = annual_revenue_matrix.sum(axis=1).replace(0, 1.0)
    relative_mix_matrix = annual_revenue_matrix.div(row_sums, axis=0)

    active_sales = df[df["date"] >= active_cutoff]
    if not active_sales.empty:
        active_rev = (
            active_sales.groupby(["customer_id", "family"])["gross_revenue"].sum().unstack().fillna(0.0)
        )
        active_rev = active_rev.reindex(columns=all_fams, fill_value=0.0)
        active_cust_tot = active_rev.sum(axis=1).replace(0, 1.0)
        active_share = active_rev.div(active_cust_tot, axis=0)
        active_bought_matrix = (active_share >= min_active_share).astype(int)
    else:
        active_bought_matrix = pd.DataFrame(0, index=annual_revenue_matrix.index, columns=all_fams)

    active_bought_matrix = active_bought_matrix.reindex(
        index=annual_revenue_matrix.index, columns=all_fams, fill_value=0
    )

    has_cm = "contribution_margin" in recent_annual_sales.columns
    customer_totals = (
        recent_annual_sales.groupby("customer_id")
        .agg(
            annual_gross_revenue=("gross_revenue", "sum"),
            annual_contribution_margin=("contribution_margin" if has_cm else "gross_revenue", "sum"),
            last_order_date=("date", "max"),
        )
        .reset_index()
    )

    return {
        "active_bought": active_bought_matrix,
        "annual_revenue": annual_revenue_matrix,
        "relative_mix": relative_mix_matrix,
        "customer_totals": customer_totals,
    }


def compute_item_affinity_scores(
    rules_df: pd.DataFrame,
    active_bought_matrix: pd.DataFrame,
    relative_mix_matrix: pd.DataFrame,
    *,
    all_families: Sequence[str],
) -> pd.DataFrame:
    """Calcula score de afinidade produto x produto combinando regras Apriori com mix do cliente."""
    customers = list(active_bought_matrix.index)
    families = list(all_families)

    if rules_df.empty:
        return pd.DataFrame(0.0, index=customers, columns=families)

    fam_scores: dict[tuple[str, str], float] = {}
    for _, row in rules_df.iterrows():
        ant = str(row["antecedent_family"])
        con = str(row["consequent_family"])
        if ant in families and con in families:
            lift_factor = min(float(row["lift"]), 3.0) / 3.0
            score = float(row["confidence"]) * (0.5 + 0.5 * lift_factor)
            fam_scores[(ant, con)] = max(fam_scores.get((ant, con), 0.0), score)

    fam_matrix = pd.DataFrame(0.0, index=families, columns=families)
    for (ant, con), val in fam_scores.items():
        fam_matrix.loc[ant, con] = val

    mix_aligned = relative_mix_matrix.reindex(columns=families, fill_value=0.0)
    affinity_scores = mix_aligned.dot(fam_matrix)

    for col in affinity_scores.columns:
        max_val = affinity_scores[col].max()
        if max_val > 0:
            affinity_scores[col] = (affinity_scores[col] / max_val).clip(0.0, 1.0)

    return affinity_scores


def compute_lookalike_scores(
    customers_df: pd.DataFrame,
    relative_mix_matrix: pd.DataFrame,
    annual_revenue_matrix: pd.DataFrame,
    *,
    all_families: Sequence[str],
    n_neighbors: int = 15,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Calcula scores de Lookalike via NearestNeighbors (Cosseno) sobre mix, porte e segmento."""
    cust_ids = list(relative_mix_matrix.index)
    families = list(all_families)

    cust_meta = customers_df.set_index("customer_id").reindex(cust_ids)
    mix_features = relative_mix_matrix.reindex(columns=families, fill_value=0.0).copy()

    size_map = {"Pequeno": 0.33, "Médio": 0.66, "Grande": 1.0}
    mix_features["feature_size"] = cust_meta["size"].map(size_map).fillna(0.5)

    if "segment" in cust_meta.columns:
        seg_dummies = pd.get_dummies(cust_meta["segment"], prefix="seg", dtype=float) * 0.5
        features_df = pd.concat([mix_features, seg_dummies], axis=1)
    else:
        features_df = mix_features

    k = min(n_neighbors, len(features_df) - 1)
    if k < 2:
        zero_df = pd.DataFrame(0.0, index=cust_ids, columns=families)
        return zero_df, zero_df, zero_df

    nn = NearestNeighbors(n_neighbors=k + 1, metric="cosine")
    nn.fit(features_df.values)
    distances, indices = nn.kneighbors(features_df.values)

    lookalike_scores = pd.DataFrame(0.0, index=cust_ids, columns=families)
    peer_penetration = pd.DataFrame(0.0, index=cust_ids, columns=families)
    peer_median_rev = pd.DataFrame(0.0, index=cust_ids, columns=families)

    bought_bool = (annual_revenue_matrix.reindex(columns=families, fill_value=0.0) > 0).values

    for i, cid in enumerate(cust_ids):
        peer_idx = indices[i, 1:]
        peer_dists = distances[i, 1:]
        peer_weights = 1.0 - np.clip(peer_dists, 0.0, 1.0)
        weight_sum = np.sum(peer_weights)
        if weight_sum <= 0:
            weight_sum = 1.0

        for f_idx, fam in enumerate(families):
            peer_buys = bought_bool[peer_idx, f_idx]
            pen_pct = (np.sum(peer_buys) / len(peer_idx)) * 100.0
            lk_score = np.sum(peer_weights * peer_buys) / weight_sum

            peer_revs = annual_revenue_matrix.iloc[peer_idx, f_idx].values
            active_revs = peer_revs[peer_revs > 0]
            med_rev = float(np.median(active_revs)) if len(active_revs) > 0 else 0.0

            lookalike_scores.loc[cid, fam] = round(float(lk_score), 4)
            peer_penetration.loc[cid, fam] = round(float(pen_pct), 2)
            peer_median_rev.loc[cid, fam] = round(float(med_rev), 2)

    return lookalike_scores, peer_penetration, peer_median_rev
