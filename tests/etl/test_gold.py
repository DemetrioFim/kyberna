from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import duckdb
import pytest
from typer.testing import CliRunner

from src.cli import app
from src.etl.audit import generate_audit_report
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
