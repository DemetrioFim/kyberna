from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

import duckdb
import pandas as pd

from src.core.logging import get_logger
from src.core.paths import get_duckdb_path, gold_snapshot_path
from src.core.types import ScenarioId
from src.etl.contracts import GoldWhiteSpaceSchema, validate_contract
from src.ml.apriori_mart import (
    build_apriori_rules_mart_df,
    match_best_apriori_rule,
    persist_apriori_rules_mart,
)
from src.ml.features import resolve_as_of_date
from src.ml.white_space_apriori import (
    DEFAULT_SCENARIO,
    build_customer_family_matrices,
    compute_apriori_rules,
    compute_item_affinity_scores,
    compute_lookalike_scores,
    compute_sku_apriori_rules,
    load_white_space_config,
)
from src.ml.white_space_backtest import evaluate_white_space_backtest

logger = get_logger(__name__)

__all__ = [
    "DEFAULT_SCENARIO",
    "build_customer_family_matrices",
    "build_white_space_mart",
    "compute_apriori_rules",
    "compute_item_affinity_scores",
    "compute_lookalike_scores",
    "compute_sku_apriori_rules",
    "compute_white_space_recommendations",
    "evaluate_white_space_backtest",
    "generate_recommendation_pitch",
    "load_white_space_config",
]


def generate_recommendation_pitch(
    *,
    family: str,
    anchor_name: str,
    peer_penetration: float,
    confidence_score: float,
    lift: float | None,
    customer_size: str,
    region: str,
    potential_brl: float,
    margin_pct: float,
) -> tuple[str, str]:
    """Gera texto explicativo em linguagem natural para o RCA e pitch acionável de vendas."""
    lift_str = f", Lift: {lift:.1f}x" if lift and lift > 1.0 else ""
    explanation_text = (
        f"{peer_penetration:.0f}% dos lojistas de porte {customer_size} em {region} com mix similar "
        f"compram '{family}' (Afinidade: {confidence_score * 100:.0f}%{lift_str}). "
        f"Item âncora recomendado: {anchor_name}."
    )
    action_pitch = (
        f"Apresentar a linha de {family} na próxima abordagem, iniciando pelo SKU campeão '{anchor_name}'. "
        f"Potencial estimado de {potential_brl:,.2f} com margem esperada de {margin_pct:.1f}%."
    )
    return explanation_text, action_pitch


def compute_white_space_recommendations(
    *,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
    as_of_date: str,
    active_bought_matrix: pd.DataFrame,
    item_affinity_df: pd.DataFrame,
    lookalike_df: pd.DataFrame,
    peer_penetration_df: pd.DataFrame,
    peer_median_rev_df: pd.DataFrame,
    customer_totals_df: pd.DataFrame,
    customers_df: pd.DataFrame,
    anchor_skus: dict[str, tuple[str, str]],
    family_margins: dict[str, float],
    rules_df: pd.DataFrame,
    churn_probs: dict[str, float],
    sku_rules_df: pd.DataFrame | None = None,
    all_families: Sequence[str] | None = None,
    top_k: int = 3,
    item_weight: float = 0.40,
    lookalike_weight: float = 0.60,
    max_total_potential_share: float = 0.30,
) -> pd.DataFrame:
    """Gera as Top-K recomendações de White Space por cliente respeitando todas as regras de negócio."""
    cust_meta = customers_df.set_index("customer_id")
    cust_totals = customer_totals_df.set_index("customer_id")
    families = list(all_families) if all_families is not None else list(active_bought_matrix.columns)

    rows: list[dict[str, Any]] = []

    for cid in active_bought_matrix.index:
        active_fams = {str(f) for f in active_bought_matrix.columns if active_bought_matrix.loc[cid, f] == 1}
        c_size = (
            str(cust_meta.loc[cid, "size"])
            if cid in cust_meta.index and "size" in cust_meta.columns
            else "Médio"
        )
        c_region = (
            str(cust_meta.loc[cid, "region"])
            if cid in cust_meta.index and "region" in cust_meta.columns
            else "Sudeste"
        )
        annual_rev = (
            float(cust_totals.loc[cid, "annual_gross_revenue"]) if cid in cust_totals.index else 10000.0
        )
        p_churn = churn_probs.get(cid, 0.15)
        retention_weight = max(1.0 - p_churn, 0.05)

        candidate_families = [
            fam
            for fam in families
            if fam not in active_bought_matrix.columns or active_bought_matrix.loc[cid, fam] == 0
        ]
        if not candidate_families:
            candidate_families = list(families)

        candidate_scores: list[dict[str, Any]] = []
        for fam in candidate_families:
            aff_score = (
                float(item_affinity_df.loc[cid, fam])
                if cid in item_affinity_df.index and fam in item_affinity_df.columns
                else 0.0
            )
            lk_score = (
                float(lookalike_df.loc[cid, fam])
                if cid in lookalike_df.index and fam in lookalike_df.columns
                else 0.0
            )
            pen_pct = (
                float(peer_penetration_df.loc[cid, fam])
                if cid in peer_penetration_df.index and fam in peer_penetration_df.columns
                else 0.0
            )
            med_rev = (
                float(peer_median_rev_df.loc[cid, fam])
                if cid in peer_median_rev_df.index and fam in peer_median_rev_df.columns
                else 0.0
            )

            if med_rev <= 0:
                med_rev = max(annual_rev * 0.05, 500.0)

            opp_score = item_weight * aff_score + lookalike_weight * lk_score

            candidate_scores.append(
                {
                    "family": fam,
                    "opportunity_score": round(float(opp_score), 4),
                    "item_affinity_score": round(float(aff_score), 4),
                    "lookalike_score": round(float(lk_score), 4),
                    "peer_penetration_pct": round(float(pen_pct), 2),
                    "peer_median_annual_revenue": round(float(med_rev), 2),
                }
            )

        candidate_scores.sort(key=lambda x: x["opportunity_score"], reverse=True)
        top_candidates = candidate_scores[:top_k]

        max_allowed_total = max(annual_rev * max_total_potential_share, 1000.0)
        raw_potentials = [c["peer_median_annual_revenue"] * retention_weight for c in top_candidates]
        sum_raw = sum(raw_potentials)
        scaling = min(max_allowed_total / sum_raw, 1.0) if sum_raw > 0 else 1.0

        for rank, c_info in enumerate(top_candidates, start=1):
            fam = c_info["family"]
            pot_rev = round(raw_potentials[rank - 1] * scaling, 2)
            margin_rate = family_margins.get(fam, 0.25)
            pot_cm = round(pot_rev * margin_rate, 2)

            _anchor_id, anchor_name = anchor_skus.get(fam, ("SKU-PADRAO", f"Linha Principal {fam}"))
            ant_label, ap_sup, ap_conf, ap_lift = match_best_apriori_rule(
                fam, active_fams, rules_df, sku_rules_df
            )

            exp_text, pitch_text = generate_recommendation_pitch(
                family=fam,
                anchor_name=anchor_name,
                peer_penetration=c_info["peer_penetration_pct"],
                confidence_score=ap_conf if ap_conf > 0 else c_info["opportunity_score"],
                lift=ap_lift,
                customer_size=c_size,
                region=c_region,
                potential_brl=pot_rev,
                margin_pct=margin_rate * 100.0,
            )

            rows.append(
                {
                    "scenario_id": scenario_id,
                    "as_of_date": as_of_date,
                    "customer_id": cid,
                    "recommended_family": fam,
                    "rank_order": rank,
                    "opportunity_score": c_info["opportunity_score"],
                    "item_affinity_score": c_info["item_affinity_score"],
                    "lookalike_score": c_info["lookalike_score"],
                    "peer_penetration_pct": c_info["peer_penetration_pct"],
                    "peer_median_annual_revenue": c_info["peer_median_annual_revenue"],
                    "churn_probability": round(float(p_churn), 4),
                    "potential_revenue_brl": pot_rev,
                    "potential_margin_brl": pot_cm,
                    "best_rule_antecedent": ant_label,
                    "recommended_anchor_sku": anchor_name,
                    "apriori_support": round(ap_sup, 4),
                    "apriori_confidence": round(ap_conf, 4),
                    "apriori_lift": round(ap_lift, 2),
                    "explanation_text": exp_text,
                    "action_pitch": pitch_text,
                    "snapshot_date": datetime.now().strftime("%Y-%m-%d"),
                }
            )

    return pd.DataFrame(rows)


def build_white_space_mart(  # noqa: PLR0915
    con: duckdb.DuckDBPyConnection | None = None,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
    *,
    as_of_date: str | None = None,
) -> pd.DataFrame:
    """Executa o pipeline completo de White Space, valida o contrato e persiste em DuckDB e Parquet."""
    own_con = False
    if con is None:
        db_path = get_duckdb_path()
        con = duckdb.connect(str(db_path))
        own_con = True

    try:
        resolved_date_obj = resolve_as_of_date(con, as_of_date=as_of_date, scenario_id=scenario_id)
        resolved_date = resolved_date_obj.strftime("%Y-%m-%d")
        cfg = load_white_space_config()

        logger.info(
            "Iniciando construção de mart_white_space para cenário '%s' (as_of_date: %s)...",
            scenario_id,
            resolved_date,
        )

        sales_query = f"""
        SELECT
            f.order_id,
            f.customer_id,
            f.product_id,
            p.product_name,
            p.family,
            d.full_date AS date,
            f.gross_revenue,
            f.contribution_margin
        FROM {scenario_id}.fact_sales f
        JOIN {scenario_id}.dim_product p ON f.product_id = p.product_id
        JOIN {scenario_id}.dim_date d ON f.date_key = d.date_key
        """
        sales_df = con.execute(sales_query).df()

        cust_query = f"""
        SELECT
            customer_id,
            trade_name,
            company_name,
            segment,
            size,
            region,
            state
        FROM {scenario_id}.dim_customer
        """
        cust_df = con.execute(cust_query).df()

        churn_map: dict[str, float] = {}
        try:
            churn_df = con.execute(
                f"SELECT customer_id, churn_probability FROM {scenario_id}.mart_customer_risk"
            ).df()
            churn_map = dict(zip(churn_df["customer_id"], churn_df["churn_probability"], strict=False))
        except Exception:
            logger.debug("mart_customer_risk não encontrado; usando estimativas padrão de churn.")

        margin_df = (
            sales_df.groupby("family")
            .agg(tot_gross=("gross_revenue", "sum"), tot_cm=("contribution_margin", "sum"))
            .reset_index()
        )
        margin_rates = (margin_df["tot_cm"] / margin_df["tot_gross"]).clip(0.10, 0.50)
        family_margins = dict(zip(margin_df["family"], margin_rates, strict=False))

        min_sup = float(cfg.get("apriori_min_support", 0.03))
        min_conf = float(cfg.get("apriori_min_confidence", 0.15))
        rules_df, anchor_skus = compute_apriori_rules(sales_df, min_support=min_sup, min_confidence=min_conf)
        sku_rules_df = compute_sku_apriori_rules(
            sales_df,
            min_support=float(cfg.get("sku_min_support", 0.005)),
            min_confidence=float(cfg.get("sku_min_confidence", 0.10)),
            min_lift=float(cfg.get("sku_min_lift", 1.05)),
            max_rules=int(cfg.get("sku_max_rules", 150)),
        )
        rules_all_df = build_apriori_rules_mart_df(
            rules_df, sku_rules_df, scenario_id=scenario_id, as_of_date=resolved_date
        )
        persist_apriori_rules_mart(con, rules_all_df, scenario_id=scenario_id)

        act_days = int(cfg.get("active_window_days", 180))
        act_share = float(cfg.get("min_active_share", 0.05))
        ref_d = datetime.strptime(resolved_date, "%Y-%m-%d").date()
        matrices = build_customer_family_matrices(
            sales_df, active_window_days=act_days, min_active_share=act_share, reference_date=ref_d
        )
        active_b = matrices["active_bought"]
        annual_rev = matrices["annual_revenue"]
        rel_mix = matrices["relative_mix"]
        cust_totals = matrices["customer_totals"]

        all_fams = sorted(list(sales_df["family"].unique()))

        item_aff = compute_item_affinity_scores(rules_df, active_b, rel_mix, all_families=all_fams)
        n_neighbors = int(cfg.get("lookalike_n_neighbors", 15))
        lookalike_df, peer_pen_df, peer_med_df = compute_lookalike_scores(
            cust_df, rel_mix, annual_rev, all_families=all_fams, n_neighbors=n_neighbors
        )

        top_k = int(cfg.get("top_n_recommendations", 3))
        w_item = float(cfg.get("item_affinity_weight", 0.40))
        w_look = float(cfg.get("lookalike_weight", 0.60))
        max_pot_share = float(cfg.get("max_total_potential_share", 0.30))

        recs_df = compute_white_space_recommendations(
            scenario_id=scenario_id,
            as_of_date=resolved_date,
            active_bought_matrix=active_b,
            item_affinity_df=item_aff,
            lookalike_df=lookalike_df,
            peer_penetration_df=peer_pen_df,
            peer_median_rev_df=peer_med_df,
            customer_totals_df=cust_totals,
            customers_df=cust_df,
            anchor_skus=anchor_skus,
            family_margins=family_margins,
            rules_df=rules_df,
            churn_probs=churn_map,
            sku_rules_df=sku_rules_df,
            top_k=top_k,
            item_weight=w_item,
            lookalike_weight=w_look,
            max_total_potential_share=max_pot_share,
        )

        validated_df = validate_contract(recs_df, GoldWhiteSpaceSchema, layer="Gold (mart_white_space)")

        con.execute("CREATE SCHEMA IF NOT EXISTS gold")
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {scenario_id}")

        con.register("v_white_space_mart", validated_df)
        con.execute(
            f"CREATE OR REPLACE TABLE {scenario_id}.mart_white_space AS SELECT * FROM v_white_space_mart"
        )
        con.execute("CREATE OR REPLACE TABLE gold.mart_white_space AS SELECT * FROM v_white_space_mart")
        con.unregister("v_white_space_mart")

        out_parquet = gold_snapshot_path(scenario=scenario_id, table="mart_white_space")
        out_parquet.parent.mkdir(parents=True, exist_ok=True)
        con.execute(
            f"COPY gold.mart_white_space TO '{out_parquet.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)"
        )

        logger.info(
            "mart_white_space construído com sucesso para '%s': %d recomendações salvas em %s.",
            scenario_id,
            len(validated_df),
            out_parquet,
        )
        return validated_df

    finally:
        if own_con:
            con.close()
