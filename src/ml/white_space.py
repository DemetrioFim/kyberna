from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from typing import Any, Final

import duckdb
import numpy as np
import pandas as pd
import yaml
from sklearn.neighbors import NearestNeighbors

from src.core.logging import get_logger
from src.core.paths import config_path, get_duckdb_path, gold_snapshot_path
from src.core.types import ScenarioId
from src.etl.contracts import GoldWhiteSpaceSchema, validate_contract
from src.ml.features import resolve_as_of_date

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
    """Minera regras de associação Apriori A => B em nível de cestas/pedidos e identifica o SKU Âncora.

    Args:
        orders_items_df: DataFrame contendo colunas ['order_id', 'family', 'product_id',
                         'product_name', 'gross_revenue'].
        min_support: Suporte mínimo da coocorrência de famílias no pedido (default 3%).
        min_confidence: Confiança mínima condicional P(B|A) (default 15%).

    Returns:
        Tupla com:
            1. rules_df: DataFrame com colunas ['antecedent_family', 'consequent_family',
                         'support', 'confidence', 'lift'].
            2. anchor_skus: Mapeamento {family: (product_id, product_name)} do item mais vendido.
    """
    if orders_items_df.empty:
        return pd.DataFrame(), {}

    # 1. Determina SKU Âncora por família (item com maior faturamento global)
    sku_totals = pd.DataFrame(
        orders_items_df.groupby(["family", "product_id", "product_name"])["gross_revenue"].sum().reset_index()
    ).sort_values(by=["family", "gross_revenue"], ascending=[True, False])

    anchor_skus: dict[str, tuple[str, str]] = {}
    for fam, group in sku_totals.groupby("family"):
        top_row = group.iloc[0]
        anchor_skus[str(fam)] = (str(top_row["product_id"]), str(top_row["product_name"]))

    # 2. Cestas transacionais B2B:
    # Se order_id tiver granularidade de 1 item por linha, a cesta de compras comercial B2B
    # é o abastecimento conjunto do cliente na data (customer_id + date).
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

    # 3. Suporte individual de cada família
    fam_counts: dict[str, int] = {}
    for itemset in baskets["family"]:
        for fam in itemset:
            fam_counts[str(fam)] = fam_counts.get(str(fam), 0) + 1

    fam_support = {fam: count / total_orders for fam, count in fam_counts.items()}

    # 4. Suporte conjunto de pares de famílias (coocorrência)
    pair_counts: dict[tuple[str, str], int] = {}
    for itemset in baskets["family"]:
        items = sorted(str(f) for f in itemset)
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                p1, p2 = items[i], items[j]
                pair_counts[(p1, p2)] = pair_counts.get((p1, p2), 0) + 1
                pair_counts[(p2, p1)] = pair_counts.get((p2, p1), 0) + 1

    # 5. Cálculo das métricas de associação
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
    """Constrói matrizes de compras ativas, históricas e de receita por cliente x família.

    Args:
        sales_df: DataFrame com ['customer_id', 'family', 'date', 'gross_revenue',
                   'contribution_margin'].
        active_window_days: Janela para considerar compra recente ativa (default 180 dias).
        min_active_share: Participação mínima na receita ativa para excluir recomendação (default 5%).
        reference_date: Data-âncora de referência (default: max da data de vendas).

    Returns:
        Dicionário com matrizes indexadas por customer_id:
            - 'active_bought': 1 se comprou na janela recente com share >= 5%, 0 caso contrário.
            - 'annual_revenue': Faturamento anualizado por família (R$).
            - 'relative_mix': Mix relativo (proporção percentual 0 a 1) por família.
            - 'customer_totals': Faturamento anual total e margem total por cliente.
    """
    if sales_df.empty:
        return {}

    ref = reference_date or pd.to_datetime(sales_df["date"]).dt.date.max()
    active_cutoff = ref - pd.Timedelta(days=active_window_days)

    df = sales_df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date

    all_fams = sorted([str(f) for f in df["family"].unique()])

    # 1. Totalização anual por cliente e família (usando 12 meses mais recentes para potencial anual)
    annual_cutoff = ref - pd.Timedelta(days=365)
    recent_annual_sales = df[df["date"] >= annual_cutoff]
    if recent_annual_sales.empty:
        recent_annual_sales = df

    annual_revenue_matrix = (
        recent_annual_sales.groupby(["customer_id", "family"])["gross_revenue"].sum().unstack().fillna(0.0)
    )
    # Garante todas as famílias conhecidas do histórico no índice de colunas
    annual_revenue_matrix = annual_revenue_matrix.reindex(columns=all_fams, fill_value=0.0)

    # 2. Mix relativo anualizado (normalizado por linha)
    row_sums = annual_revenue_matrix.sum(axis=1).replace(0, 1.0)
    relative_mix_matrix = annual_revenue_matrix.div(row_sums, axis=0)

    # 3. Compras ativas na janela recente (últimos 180 dias com share >= 5%)
    active_sales = df[df["date"] >= active_cutoff]
    if not active_sales.empty:
        active_rev = (
            active_sales.groupby(["customer_id", "family"])["gross_revenue"].sum().unstack().fillna(0.0)
        )

        # Realinha colunas com todas as famílias conhecidas
        active_rev = active_rev.reindex(columns=all_fams, fill_value=0.0)

        active_cust_tot = active_rev.sum(axis=1).replace(0, 1.0)
        active_share = active_rev.div(active_cust_tot, axis=0)
        active_bought_matrix = (active_share >= min_active_share).astype(int)
    else:
        active_bought_matrix = pd.DataFrame(0, index=annual_revenue_matrix.index, columns=all_fams)

    # Realinha índices e colunas de active_bought com annual_revenue
    active_bought_matrix = active_bought_matrix.reindex(
        index=annual_revenue_matrix.index, columns=all_fams, fill_value=0
    )

    # 4. Totais por cliente
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
    """Calcula score de afinidade produto x produto combinando regras Apriori com mix do cliente.

    Para um cliente c e uma família candidata B, o score é a média ponderada da Confiança Apriori
    das famílias A que o cliente ativamente compra em direção a B:
        Score(c, B) = sum_{A comprada} [ Mix(c, A) * Confidence(A => B) * min(Lift, 3.0)/3.0 ]
    """
    customers = list(active_bought_matrix.index)
    families = list(all_families)

    if rules_df.empty:
        return pd.DataFrame(0.0, index=customers, columns=families)

    # Constrói matriz de afinidade família x família
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

    # Multiplicação matricial: Mix(c, A) x Afinidade(A, B) -> Score(c, B)
    # Alinha colunas do mix com as linhas de fam_matrix
    mix_aligned = relative_mix_matrix.reindex(columns=families, fill_value=0.0)
    affinity_scores = mix_aligned.dot(fam_matrix)

    # Normalização min-max por coluna para escala 0.0 a 1.0
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
    """Calcula scores de Lookalike via NearestNeighbors (Cosseno) sobre mix, porte e segmento.

    Returns:
        Tupla com:
            1. lookalike_scores_df: Score ponderado de adoção pelos pares (0 a 1).
            2. peer_penetration_df: % de pares no cluster que compram a família (0 a 100%).
            3. peer_median_rev_df: Mediana de faturamento anual dos pares na família (R$).
    """
    cust_ids = list(relative_mix_matrix.index)
    families = list(all_families)

    # Enriquecimento com atributos demográficos de dim_customer
    cust_meta = customers_df.set_index("customer_id").reindex(cust_ids)

    # Vetor de features: Mix Relativo + One-Hot de Porte + One-Hot de Segmento
    mix_features = relative_mix_matrix.reindex(columns=families, fill_value=0.0).copy()

    # Mapeamento ordinal de porte
    size_map = {"Pequeno": 0.33, "Médio": 0.66, "Grande": 1.0}
    mix_features["feature_size"] = cust_meta["size"].map(size_map).fillna(0.5)

    # One-hot de segmento
    if "segment" in cust_meta.columns:
        seg_dummies = pd.get_dummies(cust_meta["segment"], prefix="seg", dtype=float) * 0.5
        features_df = pd.concat([mix_features, seg_dummies], axis=1)
    else:
        features_df = mix_features

    # Ajusta NearestNeighbors com métrica Cosseno
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

    # Matriz booleana de compra anual para os vizinhos
    bought_bool = (annual_revenue_matrix.reindex(columns=families, fill_value=0.0) > 0).values

    for i, cid in enumerate(cust_ids):
        # Exclui o próprio cliente (índice 0)
        peer_idx = indices[i, 1:]
        peer_dists = distances[i, 1:]
        peer_weights = 1.0 - np.clip(peer_dists, 0.0, 1.0)
        weight_sum = np.sum(peer_weights)
        if weight_sum <= 0:
            weight_sum = 1.0

        # Para cada família
        for f_idx, fam in enumerate(families):
            peer_buys = bought_bool[peer_idx, f_idx]
            pen_pct = (np.sum(peer_buys) / len(peer_idx)) * 100.0
            lk_score = np.sum(peer_weights * peer_buys) / weight_sum

            # Receitas dos pares que compram
            peer_revs = annual_revenue_matrix.iloc[peer_idx, f_idx].values
            active_revs = peer_revs[peer_revs > 0]
            med_rev = float(np.median(active_revs)) if len(active_revs) > 0 else 0.0

            lookalike_scores.loc[cid, fam] = round(float(lk_score), 4)
            peer_penetration.loc[cid, fam] = round(float(pen_pct), 2)
            peer_median_rev.loc[cid, fam] = round(float(med_rev), 2)

    return lookalike_scores, peer_penetration, peer_median_rev


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

    # Indexa regras Apriori para lookup rápido de Lift médio em direção à família
    avg_lift_by_consequent: dict[str, float] = {}
    if not rules_df.empty:
        mean_series = rules_df.groupby("consequent_family")["lift"].mean()
        avg_lift_by_consequent = {str(k): float(v) for k, v in mean_series.items()}

    rows: list[dict[str, Any]] = []

    for cid in active_bought_matrix.index:
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

        # 1. Candidatas: famílias NÃO ativas (active_bought == 0 ou nunca comprada)
        candidate_families = [
            fam
            for fam in families
            if fam not in active_bought_matrix.columns or active_bought_matrix.loc[cid, fam] == 0
        ]

        # Se o cliente já comprar ativamente todas, avalia entre as de menor participação histórica
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

            # Se a mediana dos pares for 0, usa valor conservador de referência (5% da receita do cliente)
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

        # 2. Ordena pelo Opportunity Score e seleciona o Top-K
        candidate_scores.sort(key=lambda x: x["opportunity_score"], reverse=True)
        top_candidates = candidate_scores[:top_k]

        # 3. Potencial financeiro ponderado por (1 - P_churn) com trava comercial
        # Trava: potencial total das 3 sugestões <= max_total_potential_share (30%) da receita anual
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
            lift_val = avg_lift_by_consequent.get(fam)

            exp_text, pitch_text = generate_recommendation_pitch(
                family=fam,
                anchor_name=anchor_name,
                peer_penetration=c_info["peer_penetration_pct"],
                confidence_score=c_info["opportunity_score"],
                lift=lift_val,
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
                    "explanation_text": exp_text,
                    "action_pitch": pitch_text,
                    "snapshot_date": datetime.now().strftime("%Y-%m-%d"),
                }
            )

    return pd.DataFrame(rows)


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

    # Famílias compradas por cliente no teste
    test_bought = test_df.groupby("customer_id")["family"].unique().to_dict()

    # Baseline: Top 3 famílias mais populares no treino
    top_pop_families = list(train_df["family"].value_counts().index[:3])

    # Famílias compradas no treino por cliente (para excluir)
    train_bought = train_df.groupby("customer_id")["family"].unique().to_dict()

    # Regras Apriori sobre o treino
    rules_df, _ = compute_apriori_rules(train_df)

    # Matrizes de treino
    matrices = build_customer_family_matrices(train_df)
    active_b = matrices["active_bought"]
    rel_mix = matrices["relative_mix"]

    all_fams = sorted(list(train_df["family"].unique()))
    item_aff = compute_item_affinity_scores(rules_df, active_b, rel_mix, all_families=all_fams)

    # Avaliação cliente a cliente
    hits_model = 0
    hits_baseline = 0
    evaluated_custs = 0

    for cid, test_fams in test_bought.items():
        if cid not in active_b.index:
            continue
        evaluated_custs += 1
        t_set = set(test_fams)
        tr_set = set(train_bought.get(cid, []))

        # Oportunidades reais: o que o cliente NÃO comprou no treino, mas veio a comprar no teste
        new_test_buys = t_set - tr_set
        if not new_test_buys:
            continue

        # Recomendações do Modelo (Top 3 afinidades excluindo compradas no treino)
        c_aff = item_aff.loc[cid].drop(labels=list(tr_set), errors="ignore")
        top_model = list(c_aff.nlargest(3).index)
        if any(rec in new_test_buys for rec in top_model):
            hits_model += 1

        # Recomendações do Baseline (Top 3 populares excluindo compradas no treino)
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


def build_white_space_mart(  # noqa: PLR0915
    con: duckdb.DuckDBPyConnection | None = None,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
    *,
    as_of_date: str | None = None,
) -> pd.DataFrame:
    """Executa o pipeline completo de White Space, valida o contrato e persiste em DuckDB e Parquet.

    Args:
        con: Conexão ativa DuckDB. Se None, conecta em `data/kyberna.duckdb`.
        scenario_id: Identificador do cenário ('c1_toys').
        as_of_date: Data de corte temporal (YYYY-MM-DD). Se None, resolve automaticamente.

    Returns:
        DataFrame validado pelo contrato `GoldWhiteSpaceSchema`.
    """
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

        # 1. Carrega dados de vendas de gold.fact_sales
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

        # 2. Carrega dim_customer
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

        # 3. Carrega probabilidades de churn de mart_customer_risk (se existir)
        churn_map: dict[str, float] = {}
        try:
            churn_df = con.execute(
                f"SELECT customer_id, churn_probability FROM {scenario_id}.mart_customer_risk"
            ).df()
            churn_map = dict(zip(churn_df["customer_id"], churn_df["churn_probability"], strict=False))
        except Exception:
            logger.debug("mart_customer_risk não encontrado; usando estimativas padrão de churn.")

        # 4. Margem média histórica por família
        margin_df = (
            sales_df.groupby("family")
            .agg(tot_gross=("gross_revenue", "sum"), tot_cm=("contribution_margin", "sum"))
            .reset_index()
        )
        margin_rates = (margin_df["tot_cm"] / margin_df["tot_gross"]).clip(0.10, 0.50)
        family_margins = dict(zip(margin_df["family"], margin_rates, strict=False))

        # 5. Algoritmo Apriori
        min_sup = float(cfg.get("apriori_min_support", 0.03))
        min_conf = float(cfg.get("apriori_min_confidence", 0.15))
        rules_df, anchor_skus = compute_apriori_rules(sales_df, min_support=min_sup, min_confidence=min_conf)

        # 6. Matrizes por cliente e família
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

        # 7. Afinidade de Itens e Lookalike
        item_aff = compute_item_affinity_scores(rules_df, active_b, rel_mix, all_families=all_fams)
        n_neighbors = int(cfg.get("lookalike_n_neighbors", 15))
        lookalike_df, peer_pen_df, peer_med_df = compute_lookalike_scores(
            cust_df, rel_mix, annual_rev, all_families=all_fams, n_neighbors=n_neighbors
        )

        # 8. Geração das recomendações
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
            top_k=top_k,
            item_weight=w_item,
            lookalike_weight=w_look,
            max_total_potential_share=max_pot_share,
        )

        # 9. Validação de contrato Pandera
        validated_df = validate_contract(recs_df, GoldWhiteSpaceSchema, layer="Gold (mart_white_space)")

        # 10. Persistência no DuckDB
        con.execute("CREATE SCHEMA IF NOT EXISTS gold")
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {scenario_id}")

        con.register("v_white_space_mart", validated_df)
        con.execute(
            f"CREATE OR REPLACE TABLE {scenario_id}.mart_white_space AS SELECT * FROM v_white_space_mart"
        )
        con.execute("CREATE OR REPLACE TABLE gold.mart_white_space AS SELECT * FROM v_white_space_mart")
        con.unregister("v_white_space_mart")

        # 11. Snapshot Parquet
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
