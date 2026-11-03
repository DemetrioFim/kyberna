from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import pytest

from src.core.paths import get_project_root
from src.etl.contracts import GoldFactSalesSchema
from src.etl.finance.margin_waterfall import (
    compute_margin_waterfall,
    load_commission_config,
    load_discounts_config,
    load_freight_config,
)
from src.etl.finance.taxes import (
    get_icms_rate,
    get_total_sales_tax_rate,
    load_tax_rules,
)
from src.etl.scenarios.c1_toys import C1ToysScenarioBuilder


def test_taxes_icms_rates_by_destination_uf() -> None:
    """DoD: Validação dos casos unitários de alíquotas de ICMS a partir de SP."""
    tax_cfg = load_tax_rules()

    # 1. Destino interno SP = 18.0%
    assert get_icms_rate("SP", tax_cfg) == 0.18

    # 2. Destinos Sul e Sudeste (exceto ES) = 12.0%
    for uf in ["RJ", "MG", "PR", "SC", "RS"]:
        assert get_icms_rate(uf, tax_cfg) == 0.12, f"UF {uf} deveria ter alíquota 12%"

    # 3. Destinos Norte, Nordeste, Centro-Oeste e ES = 7.0%
    n_ne_co_es_ufs = [
        "ES",
        "DF",
        "GO",
        "MT",
        "MS",
        "BA",
        "PE",
        "CE",
        "MA",
        "PB",
        "RN",
        "AL",
        "SE",
        "PI",
        "AM",
        "PA",
        "RO",
        "AC",
        "TO",
        "AP",
        "RR",
    ]
    for uf in n_ne_co_es_ufs:
        assert get_icms_rate(uf, tax_cfg) == 0.07, f"UF {uf} deveria ter alíquota 7%"


def test_taxes_total_sales_tax_rate_composition() -> None:
    """Valida a soma de ICMS + PIS (1,65%) + COFINS (7,60%)."""
    tax_cfg = load_tax_rules()

    # SP: 18% + 9,25% = 27,25%
    assert get_total_sales_tax_rate("SP", tax_cfg) == 0.2725

    # RJ: 12% + 9,25% = 21,25%
    assert get_total_sales_tax_rate("RJ", tax_cfg) == 0.2125

    # BA: 7% + 9,25% = 16,25%
    assert get_total_sales_tax_rate("BA", tax_cfg) == 0.1625


def test_freight_and_commission_configs_integrity() -> None:
    """Valida carregamento e integridade dos arquivos freight.yaml e commission.yaml."""
    freight_cfg = load_freight_config()
    assert freight_cfg.cost_per_box_by_region["Sudeste"] == 3.50
    assert freight_cfg.cost_per_box_by_region["Sul"] == 4.80
    assert freight_cfg.cost_per_box_by_region["Centro-Oeste"] == 6.20
    assert freight_cfg.cost_per_box_by_region["Nordeste"] == 8.50
    assert freight_cfg.cost_per_box_by_region["Norte"] == 11.00

    comm_cfg = load_commission_config()
    assert comm_cfg.min_rate == 0.035
    assert comm_cfg.max_rate == 0.065
    assert comm_cfg.basis == "net_price_revenue"


def test_discounts_config_structure() -> None:
    """Valida baseline de descontos por porte e existência de RCAs com viés."""
    disc_cfg = load_discounts_config()
    assert disc_cfg.size_baseline["P"] < disc_cfg.size_baseline["M"] < disc_cfg.size_baseline["G"]
    assert len(disc_cfg.rep_bias.high_discount_reps) >= 3
    assert len(disc_cfg.rep_bias.disciplined_reps) >= 3
    assert disc_cfg.rep_bias.extra_discount > 0.0
    assert disc_cfg.rep_bias.discount_reduction < 0.0


@pytest.fixture
def populated_c1_duckdb(tmp_path: Path) -> duckdb.DuckDBPyConnection:
    """Fixture que inicializa um banco DuckDB com a fixture reduzida e roda o builder C1."""
    db_file = tmp_path / "waterfall_test.duckdb"
    con = duckdb.connect(str(db_file))

    sample_path = get_project_root() / "tests" / "fixtures" / "iowa_sample.parquet"
    if not sample_path.exists():
        from src.etl.ingest.fixture import generate_fixture

        generate_fixture(output_path=sample_path)

    # Executa o builder C1 (popula c1_toys.sales_remapped, dim_product, dim_customer)
    builder = C1ToysScenarioBuilder(duckdb_path=db_file, global_seed=42)
    builder.build(con)

    return con


def test_accounting_identity_line_by_line(populated_c1_duckdb: duckdb.DuckDBPyConnection) -> None:
    """DoD: Teste de identidade contábil linha a linha com tolerância < 1e-6.

    Identidade canônica:
        contribution_margin == net_revenue - cogs - commission_amount - freight_amount
    """
    con = populated_c1_duckdb
    df_fact = compute_margin_waterfall(con, scenario_id="c1_toys")

    assert len(df_fact) > 0

    # 1. Teste de identidade contábil exata por linha
    expected_margin = (
        df_fact["net_revenue"] - df_fact["cogs"] - df_fact["commission_amount"] - df_fact["freight_amount"]
    )
    diff = (df_fact["contribution_margin"] - expected_margin).abs()

    max_diff = float(diff.max())
    assert max_diff < 1e-6, f"Identidade contábil violada! Maior diferença observada: {max_diff}"

    # 2. Validação estrita do contrato Pandera
    GoldFactSalesSchema.validate(df_fact)


def test_c1_average_margin_and_rca_dispersion(
    populated_c1_duckdb: duckdb.DuckDBPyConnection,
) -> None:
    """DoD: Margem média do C1 entre 18% e 35% com dispersão entre RCAs (DP >= 4 p.p.)."""
    con = populated_c1_duckdb
    df_fact = compute_margin_waterfall(con, scenario_id="c1_toys")

    # Calcula margem percentual global do C1
    total_gross = df_fact["gross_revenue"].sum()
    total_margin = df_fact["contribution_margin"].sum()
    avg_margin_pct = (total_margin / total_gross) * 100.0

    assert 18.0 <= avg_margin_pct <= 35.0, (
        f"Margem média do C1 foi {avg_margin_pct:.2f}%, fora do intervalo esperado [18%, 35%]"
    )

    # Agrupa por RCA para medir dispersão
    rca_margins = (
        df_fact.groupby("sales_rep_id")
        .agg(
            gross=("gross_revenue", "sum"),
            margin=("contribution_margin", "sum"),
        )
        .reset_index()
    )
    rca_margins["margin_pct"] = rca_margins["margin"] / rca_margins["gross"] * 100.0

    std_margin_pct = float(rca_margins["margin_pct"].std())

    assert std_margin_pct >= 4.0, (
        f"Dispersão de margem entre RCAs foi {std_margin_pct:.2f} p.p., inferior a 4.0 p.p."
    )


def test_margin_waterfall_determinism(tmp_path: Path) -> None:
    """Duas execuções do waterfall com a mesma base geram números idênticos."""
    con1 = duckdb.connect(str(tmp_path / "db1.duckdb"))
    con2 = duckdb.connect(str(tmp_path / "db2.duckdb"))

    builder1 = C1ToysScenarioBuilder(duckdb_path=tmp_path / "db1.duckdb", global_seed=42)
    builder2 = C1ToysScenarioBuilder(duckdb_path=tmp_path / "db2.duckdb", global_seed=42)
    builder1.build(con1)
    builder2.build(con2)

    df1 = compute_margin_waterfall(con1, scenario_id="c1_toys")
    df2 = compute_margin_waterfall(con2, scenario_id="c1_toys")

    pd.testing.assert_frame_equal(df1, df2)
