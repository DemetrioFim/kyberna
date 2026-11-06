from __future__ import annotations

import re
from pathlib import Path

import duckdb
import pandas as pd
from typer.testing import CliRunner

from src.cli import app
from src.core.paths import get_project_root
from src.etl.contracts import GoldDimProductSchema
from src.etl.scenarios.c1_toys import (
    DEFAULT_BRANCH_ID,
    FORBIDDEN_BEVERAGE_TERMS,
    TOY_BRANDS,
    C1ToysScenarioBuilder,
    build_c1_dim_product,
    compute_ean13_dv,
    generate_toy_name_and_description,
    generate_valid_ean13,
    validate_ean13,
)
from src.etl.silver.reference import load_category_map


def test_ean13_algorithm_gs1_compliance() -> None:
    """Valida o cálculo do dígito verificador módulo 10 padrão GS1 e geração de EAN-13."""
    # Caso canônico conhecido
    assert compute_ean13_dv("789100010010") == 3
    assert validate_ean13("7891000100103") is True
    assert validate_ean13("7891000100104") is False  # DV errado

    # Validação de formato e tamanho
    assert validate_ean13("123") is False
    assert validate_ean13("789100010010A") is False

    # 50 códigos determinísticos gerados
    for seed in range(50):
        barcode = generate_valid_ean13(seed)
        assert len(barcode) == 13
        assert barcode.startswith("789")
        assert validate_ean13(barcode) is True


def test_generate_toy_name_and_description_zero_forbidden_terms() -> None:
    """DoD: Nomes e descrições de brinquedos não podem conter termos de bebidas."""
    families = [
        "Jogos Educativos",
        "Quebra-Cabeças",
        "Primeira Infância",
        "Brinquedos de Madeira",
        "Linha Escolar",
        "Jogos de Tabuleiro",
        "Pelúcias",
        "Outros",
    ]

    for family in families:
        for item_idx in range(25):
            item_num = f"{10000 + item_idx}"
            name, desc = generate_toy_name_and_description(item_num, family, global_seed=42)

            assert len(name) > 0
            assert len(desc) > len(name)

            text_to_check = f"{name} {desc}".lower()
            for term in FORBIDDEN_BEVERAGE_TERMS:
                assert not re.search(rf"\b{re.escape(term)}\b", text_to_check), (
                    f"Termo proibido '{term}' encontrado em produto: '{name}'"
                )


def test_build_c1_dim_product_contract_and_properties() -> None:
    """Valida a construção da dimensão de produtos, contrato Gold, preços e EANs."""
    sample_path = get_project_root() / "tests" / "fixtures" / "iowa_sample.parquet"
    if not sample_path.exists():
        from src.etl.ingest.fixture import generate_fixture

        generate_fixture(output_path=sample_path)

    con = duckdb.connect()
    silver_df = con.execute(
        f"""
        SELECT
            item_number,
            category_name,
            vendor_name,
            pack::INTEGER AS pack,
            state_bottle_cost::DOUBLE AS unit_cost,
            state_bottle_retail::DOUBLE AS unit_price
        FROM read_parquet('{sample_path.as_posix()}')
        """
    ).df()

    cat_map_df = load_category_map("toys")
    dim_product = build_c1_dim_product(silver_df, cat_map_df, global_seed=42)

    # 1. Contrato Pandera validado
    GoldDimProductSchema.validate(dim_product)

    # 2. Unicidade de EAN-13 e item_number
    assert dim_product["product_id"].nunique() == len(dim_product)
    assert dim_product["item_number"].nunique() == len(dim_product)

    # 3. Todos os EAN-13s são válidos
    for ean in dim_product["product_id"]:
        assert validate_ean13(ean) is True

    # 4. Faixa de preço realista de brinquedos (R$ 15 a R$ 350)
    assert (dim_product["base_unit_price"] >= 15.0).all()
    assert (dim_product["base_unit_price"] <= 350.0).all()

    # 5. Custo unitário base inferior ao preço de tabela
    assert (dim_product["base_unit_cost"] < dim_product["base_unit_price"]).all()

    # 6. Marcas pertencem ao rol de marcas fictícias de brinquedos
    assert set(dim_product["brand_name"].unique()).issubset(set(TOY_BRANDS))


def test_c1_builder_execution_and_top_families_revenue_share(tmp_path: Path) -> None:
    """DoD: Gold c1_toys contém as 5 famílias obrigatórias com ≥ 85% do faturamento."""
    con = duckdb.connect(str(tmp_path / "test_kyberna.duckdb"))

    # Cria tabelas Silver a partir da fixture
    sample_path = get_project_root() / "tests" / "fixtures" / "iowa_sample.parquet"
    if not sample_path.exists():
        from src.etl.ingest.fixture import generate_fixture

        generate_fixture(output_path=sample_path)

    con.execute("CREATE SCHEMA IF NOT EXISTS silver")
    con.execute(
        f"""
        CREATE TABLE silver.sales AS
        SELECT
            invoice_and_item_number AS invoice_line_id,
            date::DATE AS date,
            store_number,
            store_name,
            city,
            county,
            zip_code,
            category_name,
            vendor_name,
            item_number,
            item_description,
            pack::INTEGER AS pack,
            state_bottle_cost::DOUBLE AS unit_cost,
            state_bottle_retail::DOUBLE AS unit_price,
            bottles_sold::INTEGER AS units,
            sale_dollars::DOUBLE AS sale_amount
        FROM read_parquet('{sample_path.as_posix()}')
        """
    )

    # Executa o builder
    builder = C1ToysScenarioBuilder(duckdb_path=tmp_path / "test_kyberna.duckdb", global_seed=42)
    counts = builder.build(con)

    assert counts["dim_product"] > 0
    assert counts["sales_remapped"] > 0

    # Validação do DoD de faturamento por família: Top 5 famílias ≥ 85%
    family_revenue = con.execute(
        """
        SELECT
            family,
            SUM(gross_revenue) AS total_gross
        FROM c1_toys.sales_remapped
        GROUP BY family
        ORDER BY total_gross DESC
        """
    ).df()

    total_rev = family_revenue["total_gross"].sum()
    top5_rev = family_revenue.head(5)["total_gross"].sum()
    share_top5 = top5_rev / total_rev

    assert len(family_revenue) >= 5
    assert share_top5 >= 0.85, (
        f"Top 5 famílias somam {share_top5:.1%}, que é inferior a 85% do faturamento total."
    )


def test_c1_zero_forbidden_beverage_terms_in_database(tmp_path: Path) -> None:
    """DoD: Nenhum termo de bebida remanescente em nenhuma coluna de dim_product ou sales_remapped."""
    con = duckdb.connect(str(tmp_path / "test_beverage_check.duckdb"))
    builder = C1ToysScenarioBuilder(duckdb_path=tmp_path / "test_beverage_check.duckdb", global_seed=42)
    builder.build(con)

    # Coleta todos os textos de dim_product
    products_df = con.execute("SELECT product_name, brand_name, description FROM c1_toys.dim_product").df()

    for col in ["product_name", "brand_name", "description"]:
        for text in products_df[col]:
            low = str(text).lower()
            for term in FORBIDDEN_BEVERAGE_TERMS:
                assert not re.search(rf"\b{re.escape(term)}\b", low), (
                    f"Termo proibido '{term}' encontrado em dim_product.{col}: '{text}'"
                )

    # Coleta textos de sales_remapped
    sales_df = con.execute(
        "SELECT DISTINCT product_name, brand_name, family FROM c1_toys.sales_remapped"
    ).df()
    for col in ["product_name", "brand_name", "family"]:
        for text in sales_df[col]:
            low = str(text).lower()
            for term in FORBIDDEN_BEVERAGE_TERMS:
                assert not re.search(rf"\b{re.escape(term)}\b", low), (
                    f"Termo proibido '{term}' encontrado em sales_remapped.{col}: '{text}'"
                )


def test_c1_boxes_pack_and_branch_invariants(tmp_path: Path) -> None:
    """Garante que boxes = units / pack, branch_id = 'FAB-SP01' e date_key é inteiro YYYYMMDD."""
    con = duckdb.connect(str(tmp_path / "test_invariants.duckdb"))
    builder = C1ToysScenarioBuilder(duckdb_path=tmp_path / "test_invariants.duckdb", global_seed=42)
    builder.build(con)

    invariants = con.execute(
        f"""
        SELECT
            COUNT(*) AS total_rows,
            COUNT(
                CASE WHEN ABS(boxes - ROUND(CAST(units AS DOUBLE)/CAST(pack AS DOUBLE), 2)) > 0.01 THEN 1 END
            ) AS bad_boxes,
            COUNT(CASE WHEN branch_id != '{DEFAULT_BRANCH_ID}' THEN 1 END) AS bad_branch,
            COUNT(CASE WHEN date_key < 20200101 OR date_key > 20301231 THEN 1 END) AS bad_date_key,
            COUNT(CASE WHEN gross_revenue < cogs THEN 1 END) AS bad_margin
        FROM c1_toys.sales_remapped
        """
    ).df()

    assert invariants["bad_boxes"].iloc[0] == 0
    assert invariants["bad_branch"].iloc[0] == 0
    assert invariants["bad_date_key"].iloc[0] == 0
    assert invariants["bad_margin"].iloc[0] == 0


def test_c1_builder_determinism_byte_for_byte(tmp_path: Path) -> None:
    """Duas execuções consecutivas com a mesma seed geram DataFrames idênticos."""
    con1 = duckdb.connect(str(tmp_path / "run1.duckdb"))
    con2 = duckdb.connect(str(tmp_path / "run2.duckdb"))

    builder1 = C1ToysScenarioBuilder(duckdb_path=tmp_path / "run1.duckdb", global_seed=42)
    builder2 = C1ToysScenarioBuilder(duckdb_path=tmp_path / "run2.duckdb", global_seed=42)

    builder1.build(con1)
    builder2.build(con2)

    df1 = con1.execute("SELECT * FROM c1_toys.dim_product ORDER BY item_number").df()
    df2 = con2.execute("SELECT * FROM c1_toys.dim_product ORDER BY item_number").df()

    pd.testing.assert_frame_equal(df1, df2)


def test_cli_gold_build_c1_toys() -> None:
    """Verifica se o comando CLI 'kyberna gold build --scenario c1_toys' executa com sucesso."""
    runner = CliRunner()
    result = runner.invoke(app, ["gold", "build", "--scenario", "c1_toys"])
    assert result.exit_code == 0
    assert "Cenário C1 (Brinquedos) construído com sucesso" in result.output
