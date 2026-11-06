from __future__ import annotations

import duckdb
import yaml
from typer.testing import CliRunner

from src.cli import app
from src.core.paths import config_path, get_duckdb_path, gold_snapshot_path
from src.etl.contracts import GoldRepPerformanceSchema, validate_contract
from src.ml.rep_performance import (
    build_rep_performance_mart,
    compute_rep_performance_summary,
    load_rep_performance_config,
)

runner = CliRunner()


def test_load_rep_performance_config() -> None:
    """Valida leitura das configurações de quadrantes do pipeline.yaml."""
    cfg = load_rep_performance_config()
    assert "quadrants" in cfg
    quads = cfg["quadrants"]
    assert "star" in quads
    assert "volume_no_margin" in quads
    assert "margin_no_volume" in quads
    assert "attention" in quads
    assert quads["star"]["name"] == "Estrela"
    assert "action" in quads["star"]


def test_rep_performance_mart_c1_build_and_contract() -> None:
    """Valida a geração do mart_rep_performance para o Cenário 1 e conformidade com o contrato Pandera."""
    db_path = get_duckdb_path()
    assert db_path.exists(), f"Banco DuckDB não encontrado em {db_path}."

    con = duckdb.connect(str(db_path))
    try:
        mart_df = build_rep_performance_mart(con, scenario_id="c1_toys")

        assert not mart_df.empty, "mart_rep_performance retornou vazio"
        assert len(mart_df) >= 20, f"Esperado >= 20 RCAs, encontrado {len(mart_df)}"

        # Validação de Contrato Pandera estrito
        validated_df = validate_contract(
            mart_df, GoldRepPerformanceSchema, layer="Gold (mart_rep_performance)"
        )
        assert len(validated_df) == len(mart_df)

        # Unicidade e não nulidade de sales_rep_id
        assert mart_df["sales_rep_id"].is_unique
        assert mart_df["sales_rep_id"].notna().all()

        # Snapshot Parquet gerado
        parquet_p = gold_snapshot_path("c1_toys", "mart_rep_performance")
        assert parquet_p.exists(), f"Arquivo Parquet não encontrado em {parquet_p}"
        assert parquet_p.stat().st_size > 0
    finally:
        con.close()


def test_rep_performance_gross_revenue_conservation() -> None:
    """Valida o DoD: soma de gross_revenue por RCA = SUM(gross_revenue) de fact_sales (tolerância 0.05)."""
    db_path = get_duckdb_path()
    con = duckdb.connect(str(db_path))
    try:
        mart_df = build_rep_performance_mart(con, scenario_id="c1_toys")
        rca_total_revenue = float(mart_df["gross_revenue"].sum())

        fact_row = con.execute(
            """
            SELECT SUM(gross_revenue)
            FROM gold.fact_sales
            WHERE scenario_id = 'c1_toys'
            """
        ).fetchone()
        assert fact_row is not None and fact_row[0] is not None
        fact_total_revenue = float(fact_row[0])

        diff = abs(rca_total_revenue - fact_total_revenue)
        assert diff <= 0.05, (
            f"Desvio de conservação de faturamento entre RCA (R$ {rca_total_revenue:,.2f}) e "
            f"fact_sales (R$ {fact_total_revenue:,.2f}) foi R$ {diff:.4f}, superior à tolerância de 0.05."
        )
    finally:
        con.close()


def test_high_discount_reps_fall_in_volume_no_margin_or_attention() -> None:
    """Valida o DoD: >= 80% dos RCAs com viés agressivo caem em 'Volume sem margem' ou 'Atenção'."""
    discounts_file = config_path("finance/discounts.yaml")
    assert discounts_file.exists(), f"Arquivo {discounts_file} não encontrado."
    with open(discounts_file, encoding="utf-8") as f:
        disc_cfg = yaml.safe_load(f)

    high_discount_reps = disc_cfg.get("rep_bias", {}).get("high_discount_reps", [])
    assert len(high_discount_reps) > 0, "Lista high_discount_reps vazia em discounts.yaml"

    db_path = get_duckdb_path()
    con = duckdb.connect(str(db_path))
    try:
        mart_df = build_rep_performance_mart(con, scenario_id="c1_toys")

        existing_reps = [r for r in high_discount_reps if r in mart_df["sales_rep_id"].values]
        assert len(existing_reps) >= 5, (
            f"Esperado >= 5 RCAs de alto desconto em mart_rep_performance, encontrados {len(existing_reps)}"
        )
        filtered = mart_df[mart_df["sales_rep_id"].isin(existing_reps)]

        in_target_quadrants = filtered["quadrant"].isin(["Volume sem margem", "Atenção"]).sum()
        pct_in_target = in_target_quadrants / len(filtered)

        obs_dict = filtered[["sales_rep_id", "quadrant"]].to_dict(orient="records")
        assert pct_in_target >= 0.80, (
            f"Apenas {pct_in_target:.1%} dos RCAs de alto desconto caíram em 'Volume sem margem' ou "
            f"'Atenção' (mínimo exigido: 80.0%). Quadrantes observados: {obs_dict}"
        )
    finally:
        con.close()


def test_quadrants_distribution_and_summary() -> None:
    """Valida a integridade da distribuição de quadrantes e a função de sumarização agregada."""
    db_path = get_duckdb_path()
    con = duckdb.connect(str(db_path))
    try:
        mart_df = build_rep_performance_mart(con, scenario_id="c1_toys")

        # Todos os RCAs devem possuir quadrante e prescrição válidos
        valid_quadrants = {"Estrela", "Volume sem margem", "Margem sem volume", "Atenção"}
        assert set(mart_df["quadrant"]).issubset(valid_quadrants)
        assert mart_df["action_prescription"].str.len().gt(10).all()

        # Sumarização agregada
        summary_df = compute_rep_performance_summary(mart_df)
        assert not summary_df.empty
        assert summary_df["reps_count"].sum() == len(mart_df)
        assert abs(summary_df["reps_pct"].sum() - 100.0) < 0.5
        assert summary_df["gross_revenue"].sum() > 0
    finally:
        con.close()


def test_cli_rep_performance() -> None:
    """Valida a execução do comando CLI 'kyberna ml rep-performance'."""
    result = runner.invoke(app, ["ml", "rep-performance", "--scenario", "c1_toys"])
    assert result.exit_code == 0, f"Comando CLI falhou com saída: {result.output}"
    assert "Quadrante de Representantes (RCAs) construído para 'c1_toys'" in result.output
    assert "Estrela" in result.output
    assert "Volume sem margem" in result.output
