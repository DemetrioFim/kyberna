from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from src.core.paths import get_project_root
from src.etl.gold.star_schema import build_gold_star_schema
from src.etl.scenarios.c1_toys import C1ToysScenarioBuilder
from src.ml.features import (
    compute_customer_family_features,
    compute_customer_features,
    compute_feature_store,
    compute_sku_features,
    resolve_as_of_date,
)


@pytest.fixture
def populated_c1_gold(tmp_path: Path) -> tuple[duckdb.DuckDBPyConnection, Path]:
    """Cria ambiente temporário com cenário C1 e Star Schema Gold completo."""
    db_path = tmp_path / "test_features.duckdb"
    con = duckdb.connect(str(db_path))

    # Garante fixture reduzida
    sample_path = get_project_root() / "tests" / "fixtures" / "iowa_sample.parquet"
    if not sample_path.exists():
        from src.etl.ingest.fixture import generate_fixture

        generate_fixture(output_path=sample_path)

    # 1. Builder C1
    builder = C1ToysScenarioBuilder(duckdb_path=db_path, global_seed=42)
    builder.build(con)

    # 2. Star Schema Gold
    build_gold_star_schema(con, scenario_id="c1_toys")
    return con, db_path


def test_resolve_as_of_date(populated_c1_gold: tuple[duckdb.DuckDBPyConnection, Path]) -> None:
    """Valida resolução da data de corte a partir de string, date ou inferência."""
    con, _ = populated_c1_gold

    # String ISO
    d1 = resolve_as_of_date(con, "2024-06-30")
    assert d1 == date(2024, 6, 30)

    # Objeto date
    d2 = resolve_as_of_date(con, date(2023, 12, 15))
    assert d2 == date(2023, 12, 15)

    # Inferência da data máxima da base
    d3 = resolve_as_of_date(con, None, scenario_id="c1_toys")
    assert d3 >= date(2024, 1, 1)


def test_temporal_leakage_absence(populated_c1_gold: tuple[duckdb.DuckDBPyConnection, Path]) -> None:
    """DoD: Prova matematicamente a ausência de vazamento temporal (data leakage).

    O cálculo com `as_of_date = T` na base completa deve ser 100% idêntico ao cálculo
    em uma base fisicamente truncada onde não existem dados com `date > T`.
    """
    con, _ = populated_c1_gold
    t_cutoff = "2024-06-30"

    # 1. Computa features na base completa com data de corte T
    cust_full = compute_customer_features(con, as_of_date=t_cutoff, scenario_id="c1_toys")
    sku_full = compute_sku_features(con, as_of_date=t_cutoff, scenario_id="c1_toys")
    cust_fam_full = compute_customer_family_features(con, as_of_date=t_cutoff, scenario_id="c1_toys")

    # 2. Cria banco em memória truncado onde NÃO existem dados posteriores a T
    con_trunc = duckdb.connect(":memory:")
    con_trunc.execute("CREATE SCHEMA gold")
    con_trunc.execute("CREATE SCHEMA c1_toys")

    dim_date_df = con.execute("SELECT * FROM gold.dim_date").df()
    dim_product_df = con.execute("SELECT * FROM gold.dim_product").df()
    dim_customer_df = con.execute("SELECT * FROM gold.dim_customer").df()
    dim_sales_rep_df = con.execute("SELECT * FROM gold.dim_sales_rep").df()
    fact_sales_trunc_df = con.execute(f"""
        SELECT f.*
        FROM gold.fact_sales f
        JOIN gold.dim_date d ON f.date_key = d.date_key
        WHERE d.full_date <= DATE '{t_cutoff}'
    """).df()

    # Clona dimensões e fatos truncados na nova conexão
    con_trunc.register("v_dim_date", dim_date_df)
    con_trunc.register("v_dim_product", dim_product_df)
    con_trunc.register("v_dim_customer", dim_customer_df)
    con_trunc.register("v_dim_sales_rep", dim_sales_rep_df)
    con_trunc.register("v_fact_sales", fact_sales_trunc_df)

    con_trunc.execute("CREATE TABLE gold.dim_date AS SELECT * FROM v_dim_date")
    con_trunc.execute("CREATE TABLE gold.dim_product AS SELECT * FROM v_dim_product")
    con_trunc.execute("CREATE TABLE gold.dim_customer AS SELECT * FROM v_dim_customer")
    con_trunc.execute("CREATE TABLE gold.dim_sales_rep AS SELECT * FROM v_dim_sales_rep")
    con_trunc.execute("CREATE TABLE gold.fact_sales AS SELECT * FROM v_fact_sales")

    # Computa features na base truncada
    cust_trunc = compute_customer_features(con_trunc, as_of_date=t_cutoff, scenario_id="c1_toys")
    sku_trunc = compute_sku_features(con_trunc, as_of_date=t_cutoff, scenario_id="c1_toys")
    cust_fam_trunc = compute_customer_family_features(con_trunc, as_of_date=t_cutoff, scenario_id="c1_toys")

    # 3. Comparações estritas de igualdade (zero vazamento!)
    pd.testing.assert_frame_equal(cust_full, cust_trunc, check_exact=False, rtol=1e-5)
    pd.testing.assert_frame_equal(sku_full, sku_trunc, check_exact=False, rtol=1e-5)
    pd.testing.assert_frame_equal(cust_fam_full, cust_fam_trunc, check_exact=False, rtol=1e-5)

    # 4. Invariantes temporais
    assert (pd.to_datetime(cust_full["last_order_date"]) <= pd.Timestamp(t_cutoff)).all()
    assert (cust_full["recency_days"] >= 0).all()
    assert (cust_fam_full["family_recency_days"] >= 0).all()


def test_customer_features_manual_verification(
    populated_c1_gold: tuple[duckdb.DuckDBPyConnection, Path],
) -> None:
    """DoD: Valida métricas de um cliente da fixture contra apuração manual via SQL."""
    con, _ = populated_c1_gold
    t_cutoff = "2024-12-31"

    cust_df = compute_customer_features(con, as_of_date=t_cutoff, scenario_id="c1_toys")
    assert len(cust_df) > 0

    # Seleciona o cliente com maior faturamento
    test_client_id = str(cust_df.iloc[0]["customer_id"])

    # Apuração manual direta via SQL isolado
    manual_sql = f"""
    SELECT
        COUNT(DISTINCT f.order_id) AS freq,
        ROUND(SUM(f.gross_revenue), 2) AS gross,
        ROUND(SUM(f.contribution_margin), 2) AS margin,
        COUNT(DISTINCT p.family) AS families,
        MAX(d.full_date) AS last_dt
    FROM gold.fact_sales f
    JOIN gold.dim_date d ON f.date_key = d.date_key
    JOIN gold.dim_product p ON f.product_id = p.product_id
    WHERE f.scenario_id = 'c1_toys'
      AND f.customer_id = '{test_client_id}'
      AND d.full_date <= DATE '{t_cutoff}'
    """
    manual_row = con.execute(manual_sql).fetchone()
    assert manual_row is not None

    client_row = cust_df[cust_df["customer_id"] == test_client_id].iloc[0]

    assert client_row["frequency"] == manual_row[0]
    assert abs(client_row["gross_revenue"] - manual_row[1]) < 0.05
    assert abs(client_row["contribution_margin"] - manual_row[2]) < 0.05
    assert client_row["n_families"] == manual_row[3]
    assert str(client_row["last_order_date"])[:10] == str(manual_row[4])[:10]
    assert client_row["avg_ticket"] == round(manual_row[1] / manual_row[0], 2)


def test_sku_features_weekly_cv_and_demand(
    populated_c1_gold: tuple[duckdb.DuckDBPyConnection, Path],
) -> None:
    """Valida cálculo de demanda diária/semanal e coeficiente de variação (XYZ)."""
    con, _ = populated_c1_gold

    sku_df = compute_sku_features(con, as_of_date="2024-12-31", scenario_id="c1_toys")

    # Todos os produtos da dimensão estão presentes
    dim_count = con.execute("SELECT COUNT(*) FROM gold.dim_product").fetchone()[0]
    assert len(sku_df) == dim_count

    # Invariantes estatísticos
    assert (sku_df["weekly_demand_mean"] >= 0.0).all()
    assert (sku_df["weekly_demand_std"] >= 0.0).all()
    assert (sku_df["weekly_cv"] >= 0.0).all()

    # Relação exata entre demanda diária e demanda semanal (/ 7.0)
    for _, row in sku_df.head(20).iterrows():
        expected_daily = round(float(row["weekly_demand_mean"]) / 7.0, 2)
        assert abs(float(row["daily_demand_mean"]) - expected_daily) < 0.02


def test_customer_family_features_share_sums(
    populated_c1_gold: tuple[duckdb.DuckDBPyConnection, Path],
) -> None:
    """Valida que a soma dos shares por família fecha em 100% por cliente."""
    con, _ = populated_c1_gold

    cf_df = compute_customer_family_features(con, as_of_date="2024-12-31", scenario_id="c1_toys")
    assert len(cf_df) > 0

    # Agrupa soma de shares por cliente
    shares_sum = cf_df.groupby("customer_id")["family_revenue_share"].sum()

    # Cada cliente com compras deve ter soma de share = 1.0 (tolerância de arredondamento 0.01)
    assert (
        (shares_sum - 1.0).abs() < 0.01
    ).all(), (
        f"Shares de famílias não fecham em 100% para alguns clientes: {shares_sum[shares_sum != 1.0].head()}"
    )


def test_compute_feature_store_wrapper(
    populated_c1_gold: tuple[duckdb.DuckDBPyConnection, Path],
) -> None:
    """Valida a função orquestradora `compute_feature_store`."""
    con, _ = populated_c1_gold

    fs = compute_feature_store(con, as_of_date="2024-12-31", scenario_id="c1_toys")

    assert "customer_features" in fs
    assert "sku_features" in fs
    assert "customer_family_features" in fs

    assert len(fs["customer_features"]) > 0
    assert len(fs["sku_features"]) > 0
    assert len(fs["customer_family_features"]) > 0
