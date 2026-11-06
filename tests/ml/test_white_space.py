from __future__ import annotations

from datetime import date

import duckdb
import pandas as pd
import pytest

from src.core.paths import get_duckdb_path, gold_snapshot_path
from src.etl.contracts import GoldWhiteSpaceSchema, validate_contract
from src.ml.white_space import (
    build_customer_family_matrices,
    build_white_space_mart,
    compute_apriori_rules,
    compute_white_space_recommendations,
    evaluate_white_space_backtest,
    load_white_space_config,
)


def test_load_white_space_config() -> None:
    """Valida leitura dos parâmetros do bloco white_space em config/pipeline.yaml."""
    cfg = load_white_space_config()
    assert "top_n_recommendations" in cfg
    assert cfg["top_n_recommendations"] == 3
    assert cfg["apriori_min_support"] == 0.03
    assert cfg["apriori_min_confidence"] == 0.15
    assert cfg["active_window_days"] == 180
    assert cfg["max_total_potential_share"] == 0.30


def test_compute_apriori_rules_metrics() -> None:
    """Valida mineração das regras Apriori (Suporte, Confiança, Lift) e SKU Âncora."""
    # 10 cestas simuladas
    # Cestas 1 a 6: Família A e Família B juntas
    # Cestas 7 a 8: Apenas Família A
    # Cestas 9 a 10: Apenas Família B
    # Total de cestas = 10
    # Support(A) = 8/10 = 0.8
    # Support(B) = 8/10 = 0.8
    # Support(A and B) = 6/10 = 0.6
    # Confidence(A => B) = 0.6 / 0.8 = 0.75
    # Lift(A => B) = 0.75 / 0.8 = 0.9375
    data: list[dict[str, object]] = []
    for basket_id in range(1, 11):
        if basket_id <= 6:
            data.append(
                {
                    "basket_id": f"B_{basket_id}",
                    "order_id": f"ORD_{basket_id}_1",
                    "family": "Brinquedos de Madeira",
                    "product_id": "SKU-MAD-1",
                    "product_name": "Blocos de Madeira 100 Peças",
                    "gross_revenue": 100.0,
                }
            )
            data.append(
                {
                    "basket_id": f"B_{basket_id}",
                    "order_id": f"ORD_{basket_id}_2",
                    "family": "Jogos Educativos",
                    "product_id": "SKU-EDU-TOP",
                    "product_name": "Quebra-Cabeça Alfabeto",
                    "gross_revenue": 150.0,
                }
            )
            data.append(
                {
                    "basket_id": f"B_{basket_id}",
                    "order_id": f"ORD_{basket_id}_3",
                    "family": "Jogos Educativos",
                    "product_id": "SKU-EDU-2",
                    "product_name": "Jogo da Memória",
                    "gross_revenue": 50.0,
                }
            )
        elif basket_id <= 8:
            data.append(
                {
                    "basket_id": f"B_{basket_id}",
                    "order_id": f"ORD_{basket_id}_1",
                    "family": "Brinquedos de Madeira",
                    "product_id": "SKU-MAD-1",
                    "product_name": "Blocos de Madeira 100 Peças",
                    "gross_revenue": 100.0,
                }
            )
        else:
            data.append(
                {
                    "basket_id": f"B_{basket_id}",
                    "order_id": f"ORD_{basket_id}_1",
                    "family": "Jogos Educativos",
                    "product_id": "SKU-EDU-TOP",
                    "product_name": "Quebra-Cabeça Alfabeto",
                    "gross_revenue": 150.0,
                }
            )

    df_baskets = pd.DataFrame(data)
    rules_df, anchor_skus = compute_apriori_rules(df_baskets, min_support=0.10, min_confidence=0.50)

    assert not rules_df.empty
    # SKU âncora de Jogos Educativos deve ser SKU-EDU-TOP (R$ 150 vs R$ 50)
    assert anchor_skus["Jogos Educativos"][0] == "SKU-EDU-TOP"
    assert anchor_skus["Brinquedos de Madeira"][0] == "SKU-MAD-1"

    rule_ab = rules_df[
        (rules_df["antecedent_family"] == "Brinquedos de Madeira")
        & (rules_df["consequent_family"] == "Jogos Educativos")
    ].iloc[0]

    assert rule_ab["support"] == pytest.approx(0.60, abs=0.01)
    assert rule_ab["confidence"] == pytest.approx(0.75, abs=0.01)


def test_active_bought_exclusion_rule() -> None:
    """Garante que famílias compradas na janela ativa (180 dias, share >= 5%) NUNCA são recomendadas."""
    ref_date = date(2024, 12, 31)

    # Cliente C1 comprou ativamente 'Brinquedos de Madeira' e 'Pelúcias' recentemente (2024-11)
    # E comprou 'Linha Escolar' no passado distante (2023-02, há quase 2 anos)
    sales_data = [
        {
            "customer_id": "C1",
            "family": "Brinquedos de Madeira",
            "date": "2024-11-15",
            "gross_revenue": 5000.0,
            "contribution_margin": 1500.0,
        },
        {
            "customer_id": "C1",
            "family": "Pelúcias",
            "date": "2024-10-20",
            "gross_revenue": 4000.0,
            "contribution_margin": 1200.0,
        },
        {
            "customer_id": "C1",
            "family": "Linha Escolar",
            "date": "2023-02-10",
            "gross_revenue": 1000.0,
            "contribution_margin": 300.0,
        },
    ]
    sales_df = pd.DataFrame(sales_data)

    matrices = build_customer_family_matrices(
        sales_df, active_window_days=180, min_active_share=0.05, reference_date=ref_date
    )
    active_b = matrices["active_bought"]

    # 'Brinquedos de Madeira' e 'Pelúcias' devem estar marcadas como ativas (1)
    assert active_b.loc["C1", "Brinquedos de Madeira"] == 1
    assert active_b.loc["C1", "Pelúcias"] == 1

    # 'Linha Escolar' é compra antiga (> 180 dias): deve estar como 0 (elegível a cross-sell)
    assert active_b.loc["C1", "Linha Escolar"] == 0

    # Gera recomendações
    all_fams = ["Brinquedos de Madeira", "Pelúcias", "Linha Escolar", "Jogos Educativos"]
    item_aff = pd.DataFrame(0.8, index=["C1"], columns=all_fams)
    lookalike = pd.DataFrame(0.9, index=["C1"], columns=all_fams)
    peer_pen = pd.DataFrame(80.0, index=["C1"], columns=all_fams)
    peer_med = pd.DataFrame(2000.0, index=["C1"], columns=all_fams)
    cust_df = pd.DataFrame([{"customer_id": "C1", "size": "Médio", "region": "Sudeste"}])
    anchors = {
        "Linha Escolar": ("SKU-1", "Kit Escolar"),
        "Jogos Educativos": ("SKU-2", "Quebra-Cabeça"),
    }

    recs = compute_white_space_recommendations(
        scenario_id="c1_toys",
        as_of_date="2024-12-31",
        active_bought_matrix=active_b,
        item_affinity_df=item_aff,
        lookalike_df=lookalike,
        peer_penetration_df=peer_pen,
        peer_median_rev_df=peer_med,
        customer_totals_df=matrices["customer_totals"],
        customers_df=cust_df,
        anchor_skus=anchors,
        family_margins={"Linha Escolar": 0.3, "Jogos Educativos": 0.28},
        rules_df=pd.DataFrame(),
        churn_probs={"C1": 0.1},
        all_families=all_fams,
        top_k=2,
    )

    recs_for_c1 = list(recs["recommended_family"].unique())
    # Brinquedos de Madeira e Pelúcias NÃO devem aparecer nas recomendações
    assert "Brinquedos de Madeira" not in recs_for_c1
    assert "Pelúcias" not in recs_for_c1
    # Linha Escolar e Jogos Educativos DEVEM ser recomendadas
    assert "Linha Escolar" in recs_for_c1
    assert "Jogos Educativos" in recs_for_c1


def test_potential_financial_sanity_cap() -> None:
    """Valida a trava conservadora: a soma do potencial das Top 3 recomendações <= 30% da receita anual."""
    annual_rev = 10000.0
    active_b = pd.DataFrame(0, index=["C1"], columns=["F1", "F2", "F3", "F4"])
    aff = pd.DataFrame(1.0, index=["C1"], columns=["F1", "F2", "F3", "F4"])
    lk = pd.DataFrame(1.0, index=["C1"], columns=["F1", "F2", "F3", "F4"])
    pen = pd.DataFrame(90.0, index=["C1"], columns=["F1", "F2", "F3", "F4"])
    # Mediana dos pares exorbitante (R$ 8.000 por família)
    med = pd.DataFrame(8000.0, index=["C1"], columns=["F1", "F2", "F3", "F4"])

    totals = pd.DataFrame(
        [
            {
                "customer_id": "C1",
                "annual_gross_revenue": annual_rev,
                "annual_contribution_margin": 3000.0,
                "last_order_date": date(2024, 12, 1),
            }
        ]
    )
    cust_df = pd.DataFrame([{"customer_id": "C1", "size": "Médio", "region": "Sudeste"}])

    recs = compute_white_space_recommendations(
        scenario_id="c1_toys",
        as_of_date="2024-12-31",
        active_bought_matrix=active_b,
        item_affinity_df=aff,
        lookalike_df=lk,
        peer_penetration_df=pen,
        peer_median_rev_df=med,
        customer_totals_df=totals,
        customers_df=cust_df,
        anchor_skus={},
        family_margins={},
        rules_df=pd.DataFrame(),
        churn_probs={"C1": 0.0},
        top_k=3,
        max_total_potential_share=0.30,
    )

    total_potential = float(recs["potential_revenue_brl"].sum())
    # O teto de 30% de 10.000 é 3.000,00
    assert total_potential <= 3000.01


def test_churn_probability_discounting() -> None:
    """Valida que clientes com maior probabilidade de Churn têm potencial financeiro penalizado."""
    active_b = pd.DataFrame(0, index=["C_HEALTHY", "C_CHURN"], columns=["F1", "F2"])
    aff = pd.DataFrame(0.8, index=["C_HEALTHY", "C_CHURN"], columns=["F1", "F2"])
    lk = pd.DataFrame(0.8, index=["C_HEALTHY", "C_CHURN"], columns=["F1", "F2"])
    pen = pd.DataFrame(80.0, index=["C_HEALTHY", "C_CHURN"], columns=["F1", "F2"])
    med = pd.DataFrame(5000.0, index=["C_HEALTHY", "C_CHURN"], columns=["F1", "F2"])

    totals = pd.DataFrame(
        [
            {
                "customer_id": "C_HEALTHY",
                "annual_gross_revenue": 100000.0,
                "annual_contribution_margin": 30000.0,
            },
            {
                "customer_id": "C_CHURN",
                "annual_gross_revenue": 100000.0,
                "annual_contribution_margin": 30000.0,
            },
        ]
    )

    cust_df = pd.DataFrame(
        [
            {"customer_id": "C_HEALTHY", "size": "Grande", "region": "Sul"},
            {"customer_id": "C_CHURN", "size": "Grande", "region": "Sul"},
        ]
    )

    recs = compute_white_space_recommendations(
        scenario_id="c1_toys",
        as_of_date="2024-12-31",
        active_bought_matrix=active_b,
        item_affinity_df=aff,
        lookalike_df=lk,
        peer_penetration_df=pen,
        peer_median_rev_df=med,
        customer_totals_df=totals,
        customers_df=cust_df,
        anchor_skus={},
        family_margins={},
        rules_df=pd.DataFrame(),
        churn_probs={"C_HEALTHY": 0.05, "C_CHURN": 0.90},  # 5% vs 90% churn
        top_k=1,
    )

    pot_healthy = recs[recs["customer_id"] == "C_HEALTHY"].iloc[0]["potential_revenue_brl"]
    pot_churn = recs[recs["customer_id"] == "C_CHURN"].iloc[0]["potential_revenue_brl"]

    # Potencial do cliente em risco de churn deve ser substancialmente menor
    assert pot_healthy > pot_churn * 5


def test_white_space_mart_contract_and_persistence() -> None:
    """Valida a construção ponta a ponta de mart_white_space sobre DuckDB, contrato Pandera e Parquet."""
    db_path = get_duckdb_path()
    if not db_path.exists():
        pytest.skip(f"Banco '{db_path}' não encontrado para teste de integração.")

    con = duckdb.connect(str(db_path))
    try:
        df = build_white_space_mart(con, scenario_id="c1_toys", as_of_date="2024-12-31")

        # 1. Contrato Pandera
        validated = validate_contract(df, GoldWhiteSpaceSchema, layer="Gold (mart_white_space)")
        assert len(validated) > 0

        # 2. Ranks devem ser 1, 2 ou 3
        assert set(df["rank_order"].unique()).issubset({1, 2, 3})

        # 3. Snapshot Parquet deve existir
        parquet_path = gold_snapshot_path(scenario="c1_toys", table="mart_white_space")
        assert parquet_path.exists()
        assert parquet_path.stat().st_size > 0

        # 4. Tabela deve existir no DuckDB
        row_cnt = con.execute("SELECT COUNT(*) FROM gold.mart_white_space").fetchone()
        assert row_cnt is not None and row_cnt[0] == len(df)
    finally:
        con.close()


def test_evaluate_white_space_backtest_lift() -> None:
    """Valida critério de aceite (DoD): hit rate @ 3 do modelo >= 2.0x baseline de popularidade."""
    db_path = get_duckdb_path()
    if not db_path.exists():
        pytest.skip(f"Banco '{db_path}' não encontrado para teste de backtest.")

    con = duckdb.connect(str(db_path))
    try:
        sales_query = """
        SELECT
            f.order_id,
            f.customer_id,
            p.family,
            d.full_date AS date,
            f.gross_revenue,
            f.contribution_margin,
            f.product_id,
            p.product_name
        FROM c1_toys.fact_sales f
        JOIN c1_toys.dim_product p ON f.product_id = p.product_id
        JOIN c1_toys.dim_date d ON f.date_key = d.date_key
        """
        sales_df = con.execute(sales_query).df()
        res = evaluate_white_space_backtest(sales_df, train_split_ratio=0.75)

        assert "model_hit_rate_at_3" in res
        assert "baseline_hit_rate_at_3" in res
        assert "lift_over_baseline" in res
        # Lift deve ser >= 2.0x conforme especificado no DoD do Marco 3
        assert res["lift_over_baseline"] >= 2.0
    finally:
        con.close()
