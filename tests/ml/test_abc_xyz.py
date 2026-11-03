from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import pytest

from src.core.paths import get_project_root
from src.etl.gold.star_schema import build_gold_star_schema
from src.etl.scenarios.c1_toys import C1ToysScenarioBuilder
from src.ml.abc_xyz import (
    DEFAULT_POLICIES,
    build_abc_xyz_mart,
    classify_abc_xyz,
    compute_abc_xyz_matrix_summary,
    load_abc_xyz_config,
)
from src.ml.features import compute_sku_features


@pytest.fixture
def populated_c1_gold(tmp_path: Path) -> tuple[duckdb.DuckDBPyConnection, Path]:
    """Cria ambiente temporário com cenário C1 e Star Schema Gold completo."""
    db_path = tmp_path / "test_abc_xyz.duckdb"
    con = duckdb.connect(str(db_path))

    sample_path = get_project_root() / "tests" / "fixtures" / "iowa_sample.parquet"
    if not sample_path.exists():
        from src.etl.ingest.fixture import generate_fixture

        generate_fixture(output_path=sample_path)

    builder = C1ToysScenarioBuilder(duckdb_path=db_path, global_seed=42)
    builder.build(con)

    build_gold_star_schema(con, scenario_id="c1_toys")
    return con, db_path


def test_abc_xyz_config_loading() -> None:
    """Verifica carregamento das configurações e políticas padrão do pipeline.yaml."""
    cfg = load_abc_xyz_config()
    assert "abc_metric" in cfg
    assert 0.5 <= cfg["abc_a_cutoff"] <= 0.9
    assert 0.8 <= cfg["abc_b_cutoff"] <= 0.99
    assert cfg["xyz_x_cutoff"] > 0
    assert cfg["xyz_y_cutoff"] > cfg["xyz_x_cutoff"]

    policies = cfg["abc_xyz_policies"]
    assert len(policies) == 9
    expected_cells = {"AX", "AY", "AZ", "BX", "BY", "BZ", "CX", "CY", "CZ"}
    assert set(policies.keys()) == expected_cells
    for cell, policy in policies.items():
        assert len(policy.strip()) > 10, f"Política para '{cell}' vazia ou curta demais."


def test_abc_xyz_cumulative_shares_sum_100(
    populated_c1_gold: tuple[duckdb.DuckDBPyConnection, Path],
) -> None:
    """DoD: Verifica que as participações acumuladas fecham em 100% (soma = 1.0)."""
    con, _ = populated_c1_gold
    sku_features = compute_sku_features(con, as_of_date="2024-06-30", scenario_id="c1_toys")

    df = classify_abc_xyz(
        sku_features,
        metric="contribution_margin",
        scenario_id="c1_toys",
        as_of_date="2024-06-30",
    )

    # 1. Soma das fatias individuais fecha em 1.0 (tolerância de arredondamento)
    assert abs(df["revenue_share"].sum() - 1.0) < 0.05
    assert abs(df["margin_share"].sum() - 1.0) < 0.05

    # 2. Curva acumulada atinge 1.0 no final
    assert df["cum_revenue_share"].max() >= 0.99
    assert df["cum_margin_share"].max() >= 0.99

    # 3. Monotonicidade das somas acumuladas (ordenado por margem)
    # A margem acumulada para itens positivos deve ser não-decrescente
    pos_items = df[df["contribution_margin"] > 0]
    assert pos_items["cum_margin_share"].is_monotonic_increasing


def test_all_skus_classified(
    populated_c1_gold: tuple[duckdb.DuckDBPyConnection, Path],
) -> None:
    """DoD: Todos os SKUs ativos devem ser classificados sem nenhum valor nulo."""
    con, _ = populated_c1_gold
    sku_features = compute_sku_features(con, scenario_id="c1_toys")

    df = classify_abc_xyz(sku_features, scenario_id="c1_toys")

    assert len(df) == len(sku_features)
    assert len(df) > 0

    # Nenhuma classificação nula
    assert df["abc_class"].isna().sum() == 0
    assert df["xyz_class"].isna().sum() == 0
    assert df["abc_xyz_class"].isna().sum() == 0

    # Classes estritamente válidas
    assert set(df["abc_class"].unique()).issubset({"A", "B", "C"})
    assert set(df["xyz_class"].unique()).issubset({"X", "Y", "Z"})
    expected_cells = {"AX", "AY", "AZ", "BX", "BY", "BZ", "CX", "CY", "CZ"}
    assert set(df["abc_xyz_class"].unique()).issubset(expected_cells)


def test_policies_present_in_all_nine_cells() -> None:
    """DoD: Política prescritiva presente e não-vazia nas 9 células da matriz."""
    expected_cells = {"AX", "AY", "AZ", "BX", "BY", "BZ", "CX", "CY", "CZ"}
    assert set(DEFAULT_POLICIES.keys()) == expected_cells

    for cell in expected_cells:
        policy = DEFAULT_POLICIES[cell]
        assert isinstance(policy, str)
        assert len(policy.strip()) > 5


def test_matrix_summary_contains_all_nine_cells(
    populated_c1_gold: tuple[duckdb.DuckDBPyConnection, Path],
) -> None:
    """Garante que o resumo executivo 3x3 contenha exatamente as 9 células."""
    con, _ = populated_c1_gold
    sku_features = compute_sku_features(con, scenario_id="c1_toys")
    df = classify_abc_xyz(sku_features, scenario_id="c1_toys")

    summary = compute_abc_xyz_matrix_summary(df)

    # Exatamente 9 linhas
    assert len(summary) == 9
    expected_cells = {"AX", "AY", "AZ", "BX", "BY", "BZ", "CX", "CY", "CZ"}
    assert set(summary["cell"]) == expected_cells

    # Total de SKUs bate
    assert summary["sku_count"].sum() == len(df)
    assert abs(summary["sku_pct"].sum() - 100.0) < 0.2

    # Totais financeiros batem
    assert abs(summary["gross_revenue"].sum() - df["gross_revenue"].sum()) < 1.0
    assert abs(summary["contribution_margin"].sum() - df["contribution_margin"].sum()) < 1.0

    # Toda célula tem política prescritiva
    assert (summary["policy"].str.len() > 10).all()


def test_abc_xyz_mart_build_and_persistence(
    populated_c1_gold: tuple[duckdb.DuckDBPyConnection, Path],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Valida execução completa de `build_abc_xyz_mart` com DuckDB e snapshot Parquet."""
    con, _ = populated_c1_gold

    # Redireciona data_dir para tmp_path para não sobrescrever arquivos reais
    monkeypatch.setattr("src.core.paths.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        "src.ml.abc_xyz.gold_snapshot_path",
        lambda scenario, table: tmp_path / "data" / "gold" / "snapshot" / scenario / f"{table}.parquet",
    )

    df = build_abc_xyz_mart(con, scenario_id="c1_toys")

    assert len(df) > 0

    # 1. Verifica tabela no DuckDB
    res = con.execute("SELECT COUNT(*) FROM gold.mart_abc_xyz").fetchone()
    assert res is not None
    assert res[0] == len(df)

    res_c1 = con.execute("SELECT COUNT(*) FROM c1_toys.mart_abc_xyz").fetchone()
    assert res_c1 is not None
    assert res_c1[0] == len(df)

    # 2. Verifica snapshot Parquet gerado
    parquet_path = tmp_path / "data" / "gold" / "snapshot" / "c1_toys" / "mart_abc_xyz.parquet"
    assert parquet_path.exists()
    parquet_df = pd.read_parquet(parquet_path)
    assert len(parquet_df) == len(df)


def test_abc_metric_toggle(
    populated_c1_gold: tuple[duckdb.DuckDBPyConnection, Path],
) -> None:
    """Testa alternância de métrica do corte ABC entre margem de contribuição e receita bruta."""
    con, _ = populated_c1_gold
    sku_features = compute_sku_features(con, scenario_id="c1_toys")

    df_margin = classify_abc_xyz(sku_features, metric="contribution_margin", scenario_id="c1_toys")
    df_revenue = classify_abc_xyz(sku_features, metric="gross_revenue", scenario_id="c1_toys")

    assert len(df_margin) == len(df_revenue)
    # A e B devem ter SKUs em ambos os modos
    assert (df_margin["abc_class"] == "A").sum() > 0
    assert (df_revenue["abc_class"] == "A").sum() > 0
    assert (df_margin["abc_class"] == "C").sum() > 0
    assert (df_revenue["abc_class"] == "C").sum() > 0
