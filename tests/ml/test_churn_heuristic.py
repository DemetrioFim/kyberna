from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from src.core.paths import get_duckdb_path
from src.ml.churn import (
    build_customer_risk_mart,
    classify_churn_risk_status,
    compute_churn_risk,
    compute_customer_risk_summary,
    compute_individual_cycle,
    load_churn_config,
)


def test_classify_churn_risk_status_cutoffs() -> None:
    """Valida a precisão dos cortes nos limiares exatos de delay_ratio."""
    # Faixa 1: No Ciclo (<= 1.1)
    assert classify_churn_risk_status(0.0) == "No Ciclo"
    assert classify_churn_risk_status(0.5) == "No Ciclo"
    assert classify_churn_risk_status(1.1) == "No Ciclo"

    # Faixa 2: Atenção (1.1 < r <= 1.5)
    assert classify_churn_risk_status(1.101) == "Atenção"
    assert classify_churn_risk_status(1.3) == "Atenção"
    assert classify_churn_risk_status(1.5) == "Atenção"

    # Faixa 3: Em Risco Imediato (1.5 < r <= 2.5)
    assert classify_churn_risk_status(1.501) == "Em Risco Imediato"
    assert classify_churn_risk_status(2.0) == "Em Risco Imediato"
    assert classify_churn_risk_status(2.5) == "Em Risco Imediato"

    # Faixa 4: Adormecido / Perdido (> 2.5)
    assert classify_churn_risk_status(2.501) == "Adormecido / Perdido"
    assert classify_churn_risk_status(5.0) == "Adormecido / Perdido"
    assert classify_churn_risk_status(10.0) == "Adormecido / Perdido"


def test_compute_individual_cycle_shrinkage() -> None:
    """Valida o amortecimento empírico bayesiano (Empirical Bayes Shrinkage)."""
    # 3 clientes no mesmo segmento 'Loja de Conveniência'
    # C1: Compra única (n=0) -> deve receber 100% da prior do segmento
    # C2: Poucas compras (n=2) -> recebe peso parcial w = 2 / (2 + 3) = 0.4
    # C3: Muitas compras (n=27) -> recebe peso dominante w = 27 / (27 + 3) = 0.9
    data = {
        "customer_id": ["C1", "C2", "C3"],
        "customer_segment": ["Varejo", "Varejo", "Varejo"],
        "frequency": [1, 3, 28],
        "n_intervals": [0, 2, 27],
        "median_interval_days": [np.nan, 20.0, 10.0],
        "std_interval_days": [np.nan, 8.0, 4.0],
    }
    df = pd.DataFrame(data)

    res = compute_individual_cycle(df, prior_shrinkage_k=3, min_cycle_days=7.0, min_std_days=5.0)

    # Mediana do segmento para o ciclo: média/mediana entre 20 e 10 = 15.0 dias
    seg_cycle = 15.0
    seg_std = 6.0

    # C1 (compra única): cycle_expected deve coincidir exatamente com a prior do segmento
    assert res.loc[res["customer_id"] == "C1", "expected_cycle_days"].iloc[0] == seg_cycle
    assert res.loc[res["customer_id"] == "C1", "cycle_std_days"].iloc[0] == seg_std

    # C3 (muitas compras): cycle_expected deve estar muito próximo do histórico individual (10.0 dias)
    c3_cycle = res.loc[res["customer_id"] == "C3", "expected_cycle_days"].iloc[0]
    # w = 27/30 = 0.9 -> 0.9 * 10 + 0.1 * 15 = 10.5
    assert abs(c3_cycle - 10.5) < 0.1

    # Piso inferior (min_cycle_days = 7.0, min_std_days = 5.0)
    low_data = pd.DataFrame(
        {
            "customer_id": ["C_LOW"],
            "frequency": [20],
            "n_intervals": [19],
            "median_interval_days": [2.0],  # Abaixo do piso de 7.0
            "std_interval_days": [1.0],  # Abaixo do piso de 5.0
        }
    )
    res_low = compute_individual_cycle(low_data, min_cycle_days=7.0, min_std_days=5.0)
    assert res_low["expected_cycle_days"].iloc[0] >= 7.0
    assert res_low["cycle_std_days"].iloc[0] >= 5.0


def test_churn_probability_monotonicity_and_bounds() -> None:
    """Valida monotonicidade estrita de P(churn) e limites [0, 1] conforme a recência cresce."""
    recencies = list(range(0, 150, 5))
    data = {
        "customer_id": [f"C{r}" for r in recencies],
        "recency_days": recencies,
        "frequency": [10] * len(recencies),
        "n_intervals": [9] * len(recencies),
        "median_interval_days": [30.0] * len(recencies),
        "std_interval_days": [10.0] * len(recencies),
        "gross_revenue": [10000.0] * len(recencies),
        "contribution_margin": [3000.0] * len(recencies),
    }
    df = pd.DataFrame(data)

    res = compute_churn_risk(df)

    # 1. Limites estritos: P(churn) in [0, 1]
    assert (res["churn_probability"] >= 0.0).all()
    assert (res["churn_probability"] <= 1.0).all()

    # 2. Monotonicidade não-decrescente em recency_days
    probs = res["churn_probability"].tolist()
    for i in range(len(probs) - 1):
        assert probs[i] <= probs[i + 1], f"P(churn) violou monotonicidade: {probs[i]} > {probs[i + 1]}"

    # 3. Transição progressiva de status
    statuses = res["risk_status"].tolist()
    assert "No Ciclo" in statuses
    assert "Atenção" in statuses
    assert "Em Risco Imediato" in statuses
    assert "Adormecido / Perdido" in statuses


def test_load_churn_config_structure() -> None:
    """Valida leitura estruturada do bloco churn de config/pipeline.yaml."""
    cfg = load_churn_config()
    assert cfg.get("healthy_ratio_cutoff") == 1.1
    assert cfg.get("attention_ratio_cutoff") == 1.5
    assert cfg.get("at_risk_ratio_cutoff") == 2.5
    assert cfg.get("prior_shrinkage_k") == 3
    assert cfg.get("min_cycle_days") == 7.0
    assert cfg.get("min_std_days") == 5.0
    assert "statuses" in cfg


def test_customer_risk_on_c1_fixture() -> None:
    """Valida a análise heurística de Churn e ciclo de recompra na base C1 Toys contra o DoD de M3-S2."""
    db_path = get_duckdb_path()
    assert db_path.exists(), f"Banco DuckDB não encontrado em {db_path}."

    con = duckdb.connect(str(db_path))
    try:
        mart_df = build_customer_risk_mart(con, scenario_id="c1_toys")

        # Critério 1 do DoD: 100% dos clientes classificados em exatamente 1 dos 4 status
        assert len(mart_df) == 300
        assert mart_df["risk_status"].notna().all()
        assert (mart_df["risk_status"] != "").all()
        valid_statuses = {"No Ciclo", "Atenção", "Em Risco Imediato", "Adormecido / Perdido"}
        assert set(mart_df["risk_status"].unique()).issubset(valid_statuses)

        # Critério 2 do DoD: detecção de lojas adormecidas/adormecendo da fixture (is_sleeping)
        # Na fixture C1, ~15% das lojas (43 lojas) pararam de comprar em 2024-09-01 (recency >= 120 dias)
        sleeping_mask = mart_df["recency_days"] >= 120
        sleeping_customers = mart_df[sleeping_mask]
        assert len(sleeping_customers) >= 40, (
            f"Esperado >= 40 clientes inativos na fixture, encontrado {len(sleeping_customers)}"
        )

        # DoD exige >= 90% das lojas adormecidas classificadas como Em Risco Imediato ou Adormecido / Perdido
        high_risk_sleeping = sleeping_customers[
            sleeping_customers["risk_status"].isin(["Em Risco Imediato", "Adormecido / Perdido"])
        ]
        detection_rate = len(high_risk_sleeping) / len(sleeping_customers)
        assert detection_rate >= 0.90, (
            f"Taxa de detecção de clientes inativos ({detection_rate:.1%}) abaixo do requisito de 90% do DoD."
        )

        # Critério 3 do DoD: financeiro em risco coerente
        # No Ciclo deve ter 0.0 de receita e margem em risco
        no_ciclo_df = mart_df[mart_df["risk_status"] == "No Ciclo"]
        assert (no_ciclo_df["annual_revenue_at_risk"] == 0.0).all()
        assert (no_ciclo_df["annual_margin_at_risk"] == 0.0).all()

        # Clientes em risco imediato e adormecidos devem ter valores financeiros positivos
        at_risk_df = mart_df[mart_df["risk_status"].isin(["Em Risco Imediato", "Adormecido / Perdido"])]
        assert (at_risk_df["annual_revenue_at_risk"] > 0).all()
        assert at_risk_df["annual_revenue_at_risk"].sum() > 1_000_000.0  # R$ > 1 milhão em risco

        # Resumo executivo da carteira
        summary = compute_customer_risk_summary(mart_df)
        assert len(summary) == 4
        assert summary["customer_count"].sum() == 300
        assert abs(summary["customer_share_pct"].sum() - 100.0) < 0.5
    finally:
        con.close()


def test_churn_determinism() -> None:
    """Valida que duas execuções sucessivas com os mesmos dados produzem resultados idênticos."""
    data = {
        "customer_id": [f"C{i:03d}" for i in range(1, 31)],
        "recency_days": [(i * 9) % 200 for i in range(1, 31)],
        "frequency": [(i % 7) + 1 for i in range(1, 31)],
        "n_intervals": [(i % 7) for i in range(1, 31)],
        "median_interval_days": [float((i % 5 + 1) * 15) for i in range(1, 31)],
        "std_interval_days": [float((i % 4 + 1) * 5) for i in range(1, 31)],
        "gross_revenue": [float(i * 2500.0) for i in range(1, 31)],
        "contribution_margin": [float(i * 750.0) for i in range(1, 31)],
    }
    df = pd.DataFrame(data)

    res1 = compute_churn_risk(df, scenario_id="c1_toys", as_of_date="2024-12-31")
    res2 = compute_churn_risk(df, scenario_id="c1_toys", as_of_date="2024-12-31")

    assert_frame_equal(res1, res2)
