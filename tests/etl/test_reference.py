from __future__ import annotations

import re

import duckdb
import pandas as pd
import pytest

from src.core.paths import get_project_root
from src.etl.silver.reference import (
    EXPECTED_UF_COUNT,
    MunicipioReference,
    UfReference,
    apply_category_mapping,
    build_category_case_when_sql,
    compile_category_rules,
    load_category_map,
    load_municipios,
    load_ufs,
    match_category,
)
from src.ui.theme import UF_REGIAO


def test_load_ufs_integrity() -> None:
    """Verifica se ufs_br.csv contém exatamente as 27 UFs brasileiras válidas e tipadas."""
    df_ufs = load_ufs()

    # 1. Quantidade exata de UFs
    assert len(df_ufs) == EXPECTED_UF_COUNT
    assert df_ufs["uf"].nunique() == EXPECTED_UF_COUNT

    # 2. Todas as 27 UFs mapeadas em UF_REGIAO devem constar na tabela
    assert set(df_ufs["uf"].unique()) == set(UF_REGIAO.keys())

    # 3. Alíquotas internas de ICMS dentro da faixa constitucional brasileira (16% a 25%)
    assert (df_ufs["aliquota_icms_interna"] >= 0.16).all()
    assert (df_ufs["aliquota_icms_interna"] <= 0.25).all()

    # 4. Validação Pydantic de cada registro
    for record in df_ufs.to_dict(orient="records"):
        uf_ref = UfReference(**record)
        assert uf_ref.uf in UF_REGIAO
        assert uf_ref.regiao == UF_REGIAO[uf_ref.uf]


def test_load_municipios_integrity() -> None:
    """Verifica integridade de municipios_br.csv: coordenadas, IBGE e cobertura das 27 UFs."""
    df_mun = load_municipios()

    # 1. Total mínimo de municípios conforme especificação (~150)
    assert len(df_mun) >= 150

    # 2. Cobertura completa de todas as 27 UFs
    assert df_mun["uf"].nunique() == EXPECTED_UF_COUNT
    assert set(df_mun["uf"].unique()) == set(UF_REGIAO.keys())

    # 3. Todas as 27 capitais devem estar identificadas
    capitais = df_mun[df_mun["capital"]]
    assert len(capitais) == 27
    assert capitais["uf"].nunique() == 27

    # 4. Código IBGE: 7 dígitos numéricos cujo prefixo de 2 dígitos bate com a UF
    df_ufs = load_ufs().set_index("uf")["codigo_ibge"].to_dict()
    for _, row in df_mun.iterrows():
        ibge_str = str(row["codigo_ibge"])
        assert len(ibge_str) == 7
        uf_prefix = int(ibge_str[:2])
        assert uf_prefix == df_ufs[row["uf"]]

    # 5. Coordenadas geográficas estritamente dentro do território brasileiro
    assert (df_mun["latitude"] >= -34.0).all()
    assert (df_mun["latitude"] <= 5.5).all()
    assert (df_mun["longitude"] >= -74.0).all()
    assert (df_mun["longitude"] <= -34.5).all()

    # 6. Populações estritamente positivas
    assert (df_mun["populacao"] > 0).all()

    # 7. Validação Pydantic por amostragem
    for record in df_mun.head(30).to_dict(orient="records"):
        MunicipioReference(**record)


def test_category_map_loading_and_compilation() -> None:
    """Verifica o carregamento e compilação das regras taxonômicas para brinquedos e bebidas."""
    for scenario in ["toys", "c1_toys", "beverages", "c2_beverages"]:
        df_map = load_category_map(scenario)
        assert len(df_map) >= 8
        assert "pattern" in df_map.columns
        assert "family" in df_map.columns
        assert "priority" in df_map.columns

        # Prioridades não decrescentes
        assert (df_map["priority"].diff().dropna() >= 0).all()

        # Compilação sem exceções
        rules = compile_category_rules(df_map)
        assert len(rules) == len(df_map)
        for pattern, family in rules:
            assert isinstance(pattern, re.Pattern)
            assert len(family) > 0


def test_fixture_category_coverage_toys() -> None:
    """DoD: Garante 100% de cobertura das categorias da fixture para o Cenário 1 (Brinquedos).

    Nenhum item da fixture de teste deve cair na categoria 'Outros'.
    """
    fixture_path = get_project_root() / "tests" / "fixtures" / "iowa_sample.parquet"
    assert fixture_path.exists(), "Fixture sintética iowa_sample.parquet deve existir"

    df_sample = pd.read_parquet(fixture_path)
    assert len(df_sample) > 0

    df_map = load_category_map("toys")
    rules = compile_category_rules(df_map)

    mapped_df = apply_category_mapping(df_sample, rules, source_col="category_name", target_col="family")

    # 1. Nenhuma linha cai em 'Outros'
    outros_count = (mapped_df["family"] == "Outros").sum()
    assert outros_count == 0, f"{outros_count} linhas caíram em 'Outros'"

    # 2. Todas as 7 famílias de brinquedos devem estar presentes
    expected_families = {
        "Jogos Educativos",
        "Quebra-Cabeças",
        "Primeira Infância",
        "Brinquedos de Madeira",
        "Linha Escolar",
        "Jogos de Tabuleiro",
        "Pelúcias",
    }
    actual_families = set(mapped_df["family"].unique())
    assert expected_families == actual_families

    # 3. Distribuição de faturamento saudável (nenhuma família com 0%)
    revenue_by_family = mapped_df.groupby("family")["sale_dollars"].apply(lambda s: s.astype(float).sum())
    total_rev = revenue_by_family.sum()
    share_by_family = revenue_by_family / total_rev
    for fam in expected_families:
        assert share_by_family[fam] > 0.03, f"Família {fam} com fatia muito baixa: {share_by_family[fam]:.2%}"


def test_fixture_category_coverage_beverages() -> None:
    """DoD: Garante 100% de cobertura das categorias da fixture para o Cenário 2 (Bebidas)."""
    fixture_path = get_project_root() / "tests" / "fixtures" / "iowa_sample.parquet"
    df_sample = pd.read_parquet(fixture_path)

    df_map = load_category_map("beverages")
    rules = compile_category_rules(df_map)

    mapped_df = apply_category_mapping(df_sample, rules, source_col="category_name", target_col="family")

    # 1. Nenhuma linha cai em 'Outros'
    outros_count = (mapped_df["family"] == "Outros").sum()
    assert outros_count == 0

    # 2. Famílias de bebidas esperadas
    expected_beverage_families = {
        "Vodka",
        "Whisky",
        "Rum",
        "Tequila",
        "Licores",
        "Gin",
        "Cachaças e Destilados",
    }
    actual_families = set(mapped_df["family"].unique())
    assert expected_beverage_families == actual_families


def test_duckdb_sql_case_when_equivalence() -> None:
    """Verifica se a cláusula SQL gerada para DuckDB produz resultado idêntico ao motor Pandas."""
    fixture_path = get_project_root() / "tests" / "fixtures" / "iowa_sample.parquet"
    df_map = load_category_map("toys")
    rules = compile_category_rules(df_map)

    # 1. Gera expressão CASE WHEN SQL
    sql_case_when = build_category_case_when_sql(rules, source_col="category_name", default="Outros")

    # 2. Executa no DuckDB sobre o Parquet
    con = duckdb.connect()
    parquet_path_sql = str(fixture_path).replace("\\", "/")
    query = f"""
    SELECT
        category_name,
        {sql_case_when} AS family_sql
    FROM read_parquet('{parquet_path_sql}')
    """
    df_duckdb = con.execute(query).df()

    # 3. Executa no Pandas
    df_pandas = pd.read_parquet(fixture_path)
    df_pandas_mapped = apply_category_mapping(
        df_pandas, rules, source_col="category_name", target_col="family_pandas"
    )

    # 4. Compara equivalência exata linha a linha
    assert (df_duckdb["family_sql"] == df_pandas_mapped["family_pandas"]).all()


def test_reference_loaders_error_handling(tmp_path: pytest.TempPathFactory) -> None:
    """Verifica lançamento adequado de exceções para arquivos inexistentes ou corrompidos."""
    # 1. Arquivo inexistente
    non_existent = get_project_root() / "data" / "reference" / "nao_existe.csv"
    with pytest.raises(FileNotFoundError):
        load_ufs(non_existent)

    with pytest.raises(FileNotFoundError):
        load_municipios(non_existent)

    with pytest.raises(FileNotFoundError):
        load_category_map("cenario_fantasma")

    # 2. Arquivo com colunas faltantes
    bad_csv = get_project_root() / "tests" / "fixtures" / "bad_ufs.csv"
    bad_csv.write_text("uf,nome\nSP,São Paulo\n", encoding="utf-8")
    try:
        with pytest.raises(ValueError, match="Colunas obrigatórias ausentes"):
            load_ufs(bad_csv)
    finally:
        if bad_csv.exists():
            bad_csv.unlink()


def test_match_category_single_values() -> None:
    """Testa matching unitário para categorias isoladas e valores nulos."""
    df_map = load_category_map("toys")
    rules = compile_category_rules(df_map)

    assert match_category("VODKA 80 PROOF", rules) == "Jogos Educativos"
    assert match_category("CANADIAN WHISKIES", rules) == "Quebra-Cabeças"
    assert match_category("SPICED RUM", rules) == "Primeira Infância"
    assert match_category("100% AGAVE TEQUILA", rules) == "Brinquedos de Madeira"
    assert match_category("AMERICAN DRY GINS", rules) == "Jogos de Tabuleiro"
    assert match_category("AMERICAN BRANDIES", rules) == "Pelúcias"
    assert match_category("COFFEE LIQUEURS", rules) == "Linha Escolar"
    assert match_category("SOMETHING UNKNOWN 123", rules) == "Outros"
    assert match_category(None, rules) == "Outros"
    assert match_category("", rules) == "Outros"
