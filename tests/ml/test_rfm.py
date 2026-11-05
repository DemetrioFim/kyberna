from __future__ import annotations

from itertools import product

import duckdb
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from src.core.paths import get_duckdb_path
from src.ml.rfm import (
    VALID_RFM_SEGMENTS,
    assign_rfm_quintiles,
    build_rfm_mart,
    classify_rfm_cell,
    compute_rfm_scores,
    compute_rfm_segment_summary,
    load_rfm_config,
)


def test_classify_rfm_cell_exhaustiveness_and_validity() -> None:
    """Valida que todas as 125 células possíveis (5x5x5) são mapeadas para os 9 segmentos válidos."""
    covered_segments: set[str] = set()

    for r, f, m in product(range(1, 6), range(1, 6), range(1, 6)):
        seg = classify_rfm_cell(r, f, m)
        assert seg in VALID_RFM_SEGMENTS, f"Célula ({r},{f},{m}) mapeou para segmento inválido: '{seg}'"
        covered_segments.add(seg)

    # Garante que nenhum dos 9 segmentos fica órfão (todos possuem pelo menos 1 célula)
    assert len(covered_segments) == 9
    assert covered_segments == set(VALID_RFM_SEGMENTS)


def test_assign_rfm_quintiles_logic_and_inversion() -> None:
    """Valida o cálculo dos quintis e a inversão estrita da métrica de Recência (R)."""
    # 5 clientes com perfis crescentes de recência, frequência e margem
    data = {
        "customer_id": [f"C{i}" for i in range(1, 6)],
        "recency_days": [5, 20, 50, 90, 180],  # C1 mais recente (deve ter maior R), C5 mais antigo (menor R)
        "frequency": [1, 2, 4, 8, 15],  # C1 menor frequência, C5 maior
        "contribution_margin": [100.0, 500.0, 1500.0, 5000.0, 20000.0],  # C1 menor margem, C5 maior
    }
    df = pd.DataFrame(data)
    result = assign_rfm_quintiles(df, quantiles=5)

    # Recência inversa: C1 comprou há 5 dias -> R=5; C5 comprou há 180 dias -> R=1
    assert list(result["r_score"]) == [5, 4, 3, 2, 1]

    # Frequência direta: C1 menor freq -> F=1; C5 maior freq -> F=5
    assert list(result["f_score"]) == [1, 2, 3, 4, 5]

    # Margem direta: C1 menor margem -> M=1; C5 maior margem -> M=5
    assert list(result["m_score"]) == [1, 2, 3, 4, 5]

    # Células compostas
    assert list(result["rfm_cell"]) == ["511", "422", "333", "244", "155"]
    assert list(result["rfm_score"]) == [2.33, 2.67, 3.0, 3.33, 3.67]


def test_compute_rfm_scores_missing_columns() -> None:
    """Valida que compute_rfm_scores levanta ValueError se colunas obrigatórias faltarem."""
    invalid_df = pd.DataFrame({"customer_id": ["C1"], "recency_days": [10]})
    with pytest.raises(ValueError, match="Coluna obrigatória"):
        compute_rfm_scores(invalid_df)


def test_load_rfm_config_structure() -> None:
    """Valida carregamento de configurações com métricas corretas e dicionário de segmentos."""
    cfg = load_rfm_config()
    assert cfg["recency_metric"] == "recency_days"
    assert cfg["frequency_metric"] == "frequency"
    assert cfg["monetary_metric"] == "contribution_margin"
    assert cfg["quantiles"] == 5
    assert len(cfg["segments"]) == 9


def test_rfm_distribution_on_c1_fixture() -> None:
    """Valida a segmentação RFM real no banco DuckDB contra os critérios de pronto do Marco M3-S1."""
    db_path = get_duckdb_path()
    assert db_path.exists(), f"Banco DuckDB não encontrado em {db_path}."

    con = duckdb.connect(str(db_path))
    try:
        mart_df = build_rfm_mart(con, scenario_id="c1_toys")

        # Critério 1 do DoD: 100% dos clientes recebem exatamente 1 segmento (zero nulos)
        assert len(mart_df) > 0
        assert mart_df["rfm_segment"].notna().all()
        assert (mart_df["rfm_segment"] != "").all()

        # Critério 2 do DoD: scores R, F, M pertencem estritamente a {1, 2, 3, 4, 5}
        for col in ("r_score", "f_score", "m_score"):
            assert mart_df[col].isin([1, 2, 3, 4, 5]).all(), f"Scores inválidos na coluna '{col}'"

        # Critério 3 do DoD: nenhum segmento concentra mais de 40% dos clientes
        share_series = mart_df["rfm_segment"].value_counts(normalize=True)
        max_share = float(share_series.max())
        assert max_share <= 0.40, (
            f"Segmento '{share_series.idxmax()}' concentrou {max_share:.1%}, "
            "excedendo o limite de 40% do DoD."
        )

        # Garante que todos os 9 segmentos foram contemplados na base C1
        unique_segments = set(mart_df["rfm_segment"].unique())
        assert len(unique_segments) == 9

        # Verifica se metadados de dim_customer foram enriquecidos
        assert "customer_name" in mart_df.columns
        assert "customer_segment" in mart_df.columns
        assert "state" in mart_df.columns
        assert "sales_rep_id" in mart_df.columns

        # Tabela resumo agregada
        summary_df = compute_rfm_segment_summary(mart_df)
        assert len(summary_df) == 9
        assert summary_df["customer_count"].sum() == len(mart_df)
        assert abs(summary_df["customer_share_pct"].sum() - 100.0) < 0.5
    finally:
        con.close()


def test_rfm_determinism() -> None:
    """Valida determinismo estrito: duas execuções sucessivas geram resultados idênticos byte a byte."""
    data = {
        "customer_id": [f"C{i:03d}" for i in range(1, 21)],
        "recency_days": [(i * 7) % 150 for i in range(1, 21)],
        "frequency": [(i % 6) + 1 for i in range(1, 21)],
        "contribution_margin": [float(i * 1234.50) for i in range(1, 21)],
    }
    df = pd.DataFrame(data)

    res1 = compute_rfm_scores(df)
    res2 = compute_rfm_scores(df)

    assert_frame_equal(res1, res2)
