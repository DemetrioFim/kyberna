from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import get_args

import duckdb
import pandas as pd
import pytest
from typer.testing import CliRunner

from src.cli import app
from src.core.types import GoldTable
from src.etl.audit import generate_audit_report
from src.etl.contracts import (
    DataContractError,
    GoldPriceRealizationSchema,
    GoldPricingDriversSchema,
    validate_contract,
)
from src.etl.gold.marts import build_gold_marts
from src.etl.gold.star_schema import (
    build_dim_branch,
    build_dim_date,
    build_gold_star_schema,
    validate_star_schema_integrity,
)
from src.etl.scenarios.c1_toys import C1ToysScenarioBuilder

runner = CliRunner()


@pytest.fixture
def populated_c1_lake(tmp_path: Path) -> tuple[duckdb.DuckDBPyConnection, Path]:
    """Cria ambiente temporário com cenário C1 pronto."""
    db_path = tmp_path / "test_kyberna.duckdb"
    con = duckdb.connect(str(db_path))
    builder = C1ToysScenarioBuilder(duckdb_path=db_path, global_seed=42)
    builder.build(con)
    return con, db_path


def test_build_dim_date_and_dim_branch(populated_c1_lake: tuple[duckdb.DuckDBPyConnection, Path]) -> None:
    """Valida geração das dimensões estruturais de calendário e filial."""
    con, _ = populated_c1_lake

    n_dates = build_dim_date(con, scenario_id="c1_toys", start_date="2023-01-01", end_date="2024-12-31")
    assert n_dates == 731  # 2023 (365) + 2024 bissexto (366) = 731 dias

    date_sample = con.execute("SELECT * FROM gold.dim_date WHERE date_key = 20240101").df()
    assert len(date_sample) == 1
    assert date_sample["year"].iloc[0] == 2024
    assert date_sample["month_name"].iloc[0] == "Janeiro"
    assert date_sample["day_name"].iloc[0] == "Segunda-feira"
    assert not bool(date_sample["is_weekend"].iloc[0])

    n_branches = build_dim_branch(con, scenario_id="c1_toys")
    assert n_branches >= 1
    branch_df = con.execute("SELECT * FROM gold.dim_branch WHERE branch_id = 'FAB-SP01'").df()
    assert len(branch_df) == 1
    assert branch_df["city"].iloc[0] == "São Paulo"
    assert branch_df["state"].iloc[0] == "SP"


def test_build_gold_star_schema_integrity_and_revenue_conservation(
    populated_c1_lake: tuple[duckdb.DuckDBPyConnection, Path],
) -> None:
    """DoD: Valida construção completa do Star Schema e integridade referencial 100%."""
    con, _ = populated_c1_lake

    counts = build_gold_star_schema(con, scenario_id="c1_toys")

    assert counts["dim_date"] > 0
    assert counts["dim_branch"] >= 1
    assert counts["dim_customer"] > 0
    assert counts["dim_sales_rep"] > 0
    assert counts["dim_geography"] > 0
    assert counts["dim_product"] > 0
    assert counts["fact_sales"] > 0

    # Valida auditoria de integridade (deve passar sem assertion errors)
    audit = validate_star_schema_integrity(con, scenario_id="c1_toys")
    assert audit["orphan_products"] == 0
    assert audit["orphan_customers"] == 0
    assert audit["orphan_reps"] == 0
    assert audit["orphan_branches"] == 0
    assert audit["orphan_dates"] == 0
    assert float(audit["revenue_diff_pct"]) < 0.01


def test_build_gold_marts_monthly_aggregation(
    populated_c1_lake: tuple[duckdb.DuckDBPyConnection, Path],
) -> None:
    """Valida agregação analítica do mart mensal `mart_margin_monthly`."""
    con, _ = populated_c1_lake

    build_gold_star_schema(con, scenario_id="c1_toys")
    mart_counts = build_gold_marts(con, scenario_id="c1_toys")

    assert mart_counts["mart_margin_monthly"] > 0

    # Verifica conservação de receita entre fact_sales e o mart agregado
    fact_rev = con.execute("SELECT ROUND(SUM(gross_revenue), 2) FROM gold.fact_sales").fetchone()
    mart_rev = con.execute("SELECT ROUND(SUM(gross_revenue), 2) FROM gold.mart_margin_monthly").fetchone()

    assert fact_rev is not None and mart_rev is not None
    assert abs(float(fact_rev[0]) - float(mart_rev[0])) < 0.05

    # Verifica que não existem nulos nas chaves de agrupamento
    nulls = con.execute("""
        SELECT
            COUNT(CASE WHEN year_month IS NULL THEN 1 END) AS null_month,
            COUNT(CASE WHEN family IS NULL THEN 1 END) AS null_family,
            COUNT(CASE WHEN state IS NULL THEN 1 END) AS null_state,
            COUNT(CASE WHEN sales_rep_id IS NULL THEN 1 END) AS null_rep
        FROM gold.mart_margin_monthly
    """).df()

    assert nulls["null_month"].iloc[0] == 0
    assert nulls["null_family"].iloc[0] == 0
    assert nulls["null_state"].iloc[0] == 0
    assert nulls["null_rep"].iloc[0] == 0


def test_generate_audit_report_excel_structure(
    populated_c1_lake: tuple[duckdb.DuckDBPyConnection, Path],
    tmp_path: Path,
) -> None:
    """DoD: Valida que `kyberna audit` gera o relatório Excel com as 4 abas estruturadas."""
    con, _ = populated_c1_lake

    build_gold_star_schema(con, scenario_id="c1_toys")
    build_gold_marts(con, scenario_id="c1_toys")

    output_file = tmp_path / "conciliacao_c1_toys_test.xlsx"
    res_path = generate_audit_report(con, scenario_id="c1_toys", output_path=output_file)

    assert res_path.exists()
    assert res_path.stat().st_size > 5000  # Tamanho > 5 KB

    # Inspeção da estrutura interna do arquivo XLSX (XML em ZIP)
    with zipfile.ZipFile(res_path, "r") as z:
        wb_xml = z.read("xl/workbook.xml")
        root = ET.fromstring(wb_xml)
        sheet_names = [
            s.attrib["name"]
            for s in root.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet")
        ]

    expected_sheets = [
        "DRE_Waterfall",
        "Memoria_Calculo",
        "Resumo_Familias_Mix",
        "Auditoria_RCAs_Clientes",
        "Matriz_ABC_XYZ",
    ]
    for expected in expected_sheets:
        assert expected in sheet_names, f"Aba '{expected}' ausente no arquivo Excel gerado"


def test_cli_gold_build_and_audit() -> None:
    """Valida execução dos comandos CLI `kyberna gold build` e `kyberna audit`."""
    # 1. gold build
    res_gold = runner.invoke(app, ["gold", "build", "--scenario", "c1_toys"])
    assert res_gold.exit_code == 0, f"gold build falhou: {res_gold.output}"
    assert "Cenário C1 (Brinquedos) construído com sucesso" in res_gold.output

    # 2. audit report (subcomando explícito)
    res_audit_cmd = runner.invoke(app, ["audit", "report", "--scenario", "c1_toys"])
    assert res_audit_cmd.exit_code == 0, f"audit report falhou: {res_audit_cmd.output}"
    assert "Planilha de conciliação gerada com sucesso" in res_audit_cmd.output

    # 3. audit (grupo direto)
    res_audit = runner.invoke(app, ["audit", "--scenario", "c1_toys"])
    assert res_audit.exit_code == 0, f"audit falhou: {res_audit.output}"
    assert "Planilha de conciliação gerada com sucesso" in res_audit.output


def _valid_price_realization_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "scenario_id": "c1_toys",
                "product_id": "7891234567890",
                "product_name": "Quebra-Cabeça 500 Peças",
                "family": "Quebra-Cabeças",
                "abc_class": "A",
                "units_sold": 1200,
                "orders_count": 45,
                "base_unit_price": 50.0,
                "avg_list_price": 49.5,
                "avg_net_price": 45.0,
                "realized_idx_mean": 90.0,
                "realized_idx_p05": 82.0,
                "realized_idx_p25": 87.5,
                "realized_idx_p50": 90.5,
                "realized_idx_p75": 94.0,
                "realized_idx_p95": 99.0,
                "contextual_band_low_idx": 88.0,
                "contextual_band_expected_idx": 91.5,
                "contextual_band_high_idx": 95.0,
                "min_healthy_idx": 85.0,
                "price_cv_pct": 5.4,
                "below_band_orders_pct": 18.5,
                "price_leakage_brl": 1850.0,
                "inelastic_upside_brl": 0.0,
                "primary_offender_rep": "RCA-003",
                "snapshot_date": "2024-12-31",
            }
        ]
    )


def _valid_pricing_drivers_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "scenario_id": "c1_toys",
                "scope_type": "family",
                "scope_id": "Quebra-Cabeças",
                "scope_label": "Quebra-Cabeças",
                "family": "Quebra-Cabeças",
                "base_idx": 100.0,
                "expected_idx": 92.5,
                "realized_idx": 90.0,
                "unjustified_gap_pp": -2.5,
                "driver_order": 1,
                "driver_name": "Porte do Cliente",
                "shap_impact_pp": -3.2,
                "snapshot_date": "2024-12-31",
            }
        ]
    )


def test_pricing_contracts_valid_payloads() -> None:
    """Valida schemas Gold de Precificação Contextual e presença em GoldTable."""
    gold_tables = get_args(GoldTable)
    assert "mart_price_realization" in gold_tables
    assert "mart_pricing_drivers" in gold_tables

    df_real = validate_contract(
        _valid_price_realization_df(),
        GoldPriceRealizationSchema,
        layer="Gold (mart_price_realization)",
    )
    df_drv = validate_contract(
        _valid_pricing_drivers_df(),
        GoldPricingDriversSchema,
        layer="Gold (mart_pricing_drivers)",
    )
    assert len(df_real) == 1
    assert len(df_drv) == 1


def test_price_realization_contract_rejects_inverted_quantiles() -> None:
    """Rejeita inversão de quantis na banda contextual ou vazamento negativo."""
    bad_quantiles = _valid_price_realization_df()
    bad_quantiles.loc[0, "contextual_band_low_idx"] = 96.0
    with pytest.raises(DataContractError):
        validate_contract(bad_quantiles, GoldPriceRealizationSchema, layer="Gold")

    bad_leakage = _valid_price_realization_df()
    bad_leakage.loc[0, "price_leakage_brl"] = -10.0
    with pytest.raises(DataContractError):
        validate_contract(bad_leakage, GoldPriceRealizationSchema, layer="Gold")


def test_pricing_drivers_contract_rejects_invalid_scope_or_driver() -> None:
    """Rejeita scope_type ou driver_name fora do domínio canônico."""
    bad_scope = _valid_pricing_drivers_df()
    bad_scope.loc[0, "scope_type"] = "region"
    with pytest.raises(DataContractError):
        validate_contract(bad_scope, GoldPricingDriversSchema, layer="Gold")

    bad_driver = _valid_pricing_drivers_df()
    bad_driver.loc[0, "driver_name"] = "RCA Desconhecido"
    with pytest.raises(DataContractError):
        validate_contract(bad_driver, GoldPricingDriversSchema, layer="Gold")
