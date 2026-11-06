from __future__ import annotations

import re
from pathlib import Path

import duckdb
import pandas as pd
from typer.testing import CliRunner

from src.cli import app
from src.etl.contracts import SilverCustomerSchema, SilverGeographySchema, SilverSalesRepSchema
from src.etl.silver.enrich import (
    UF_DDDS,
    compute_cnpj_dv,
    enrich_silver_dimensions,
    generate_customers,
    generate_geography,
    generate_sales_reps,
    generate_valid_cnpj,
    validate_cnpj,
)
from src.ui.theme import UF_REGIAO


def test_cnpj_dv_algorithm_and_validation() -> None:
    """Verifica exatidão do cálculo de DVs (Módulo 11) e validação de CNPJs válidos e inválidos."""
    # 1. Casos oficiais conhecidos
    # Banco do Brasil: 00.000.000/0001-91
    bb_first12 = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1]
    assert compute_cnpj_dv(bb_first12) == (9, 1)
    assert validate_cnpj("00.000.000/0001-91") is True
    assert validate_cnpj("00000000000191") is True

    # Petrobras: 33.000.167/0001-01
    petro_first12 = [3, 3, 0, 0, 0, 1, 6, 7, 0, 0, 0, 1]
    assert compute_cnpj_dv(petro_first12) == (0, 1)
    assert validate_cnpj("33.000.167/0001-01") is True

    # 2. Rejeição de CNPJs inválidos
    assert validate_cnpj("00.000.000/0001-92") is False  # DV errado
    assert validate_cnpj("11.111.111/1111-11") is False  # Todos iguais
    assert validate_cnpj("12345") is False  # Comprimento incorreto

    # 3. Geração determinística de 500 CNPJs válidos
    for seed in range(500):
        cnpj_fmt = generate_valid_cnpj(seed, formatted=True)
        assert validate_cnpj(cnpj_fmt) is True
        assert len(cnpj_fmt) == 18
        assert cnpj_fmt[11:15] == "0001"
        assert "/0001-" in cnpj_fmt

        cnpj_num = generate_valid_cnpj(seed, formatted=False)
        assert validate_cnpj(cnpj_num) is True
        assert len(cnpj_num) == 14


def test_generate_sales_reps_contract() -> None:
    """Verifica geração da dimensão de RCAs, unicidade de ID e conformidade com o contrato."""
    df_reps = generate_sales_reps(num_reps=30, global_seed=42)

    assert len(df_reps) == 30
    assert df_reps["sales_rep_id"].nunique() == 30

    # Todas as 5 regiões brasileiras atendidas
    expected_regions = {"Sudeste", "Sul", "Nordeste", "Centro-Oeste", "Norte"}
    assert set(df_reps["region"].unique()) == expected_regions

    # Taxa de comissão na faixa esperada (3,5% a 6,5%)
    assert (df_reps["commission_rate"] >= 0.03).all()
    assert (df_reps["commission_rate"] <= 0.07).all()

    # Validação via Pandera
    SilverSalesRepSchema.validate(df_reps)


def test_generate_geography_contract() -> None:
    """Verifica padronização da dimensão de geografia brasileira e contrato Pandera."""
    df_geo = generate_geography()

    assert len(df_geo) >= 150
    assert df_geo["state"].nunique() == 27
    assert (df_geo["populacao"] > 0).all()

    SilverGeographySchema.validate(df_geo)


def test_generate_customers_contract_and_whatsapp_ddd() -> None:
    """DoD: Valida contrato de clientes, CNPJs 100% válidos e WhatsApp com DDD compatível com a UF."""
    # Amostra de 50 lojas sintéticas
    stores_data = [
        {
            "store_number": f"{1000 + i}",
            "county": "Polk" if i % 2 == 0 else "Linn",
            "revenue": 5000.0 * (i + 1),
        }
        for i in range(50)
    ]
    stores_df = pd.DataFrame(stores_data)

    df_reps = generate_sales_reps(num_reps=30, global_seed=42)
    df_geo = generate_geography()

    df_cust = generate_customers(stores_df, df_geo, df_reps, global_seed=42)

    # 1. Total e unicidade
    assert len(df_cust) == 50
    assert df_cust["customer_id"].nunique() == 50
    assert df_cust["store_number"].nunique() == 50

    # 2. Todos os CNPJs são 100% válidos com DV
    for cnpj in df_cust["cnpj"]:
        assert validate_cnpj(cnpj) is True

    # 3. Distribuição de portes (P, M, G)
    assert set(df_cust["size"].unique()).issubset({"P", "M", "G"})
    assert (df_cust["size"] == "G").sum() > 0
    assert (df_cust["size"] == "P").sum() > 0

    # 4. WhatsApp no formato +55 DDD 9XXXX-XXXX coerente com a UF
    phone_pattern = re.compile(r"^\+55\s(\d{2})\s9\d{4}-\d{4}$")
    for _, row in df_cust.iterrows():
        uf = row["state"]
        phone = row["whatsapp"]
        match = phone_pattern.match(phone)
        assert match is not None, f"Telefone com formato inválido: {phone}"

        ddd = int(match.group(1))
        assert ddd in UF_DDDS[uf], f"DDD {ddd} incompatível com a UF {uf} (esperados: {UF_DDDS[uf]})"

    # 5. Validação formal do contrato Pandera
    SilverCustomerSchema.validate(df_cust)


def test_determinism_two_executions_identical() -> None:
    """DoD: Duas execuções com a mesma semente geram dimensões rigorosamente idênticas."""
    stores_df = pd.DataFrame(
        [{"store_number": f"{2000 + i}", "county": "Story", "revenue": 10000.0} for i in range(30)]
    )
    df_reps = generate_sales_reps(num_reps=30, global_seed=42)
    df_geo = generate_geography()

    df_cust1 = generate_customers(stores_df, df_geo, df_reps, global_seed=42)
    df_cust2 = generate_customers(stores_df, df_geo, df_reps, global_seed=42)

    pd.testing.assert_frame_equal(df_cust1, df_cust2)


def test_incremental_stability_new_store_does_not_alter_existing() -> None:
    """DoD: Adicionar loja nova não altera os atributos sintéticos das lojas existentes."""
    stores_initial = pd.DataFrame(
        [{"store_number": f"{3000 + i}", "county": "Polk", "revenue": 1000.0} for i in range(20)]
    )
    df_reps = generate_sales_reps(num_reps=30, global_seed=42)
    df_geo = generate_geography()

    df_cust_initial = generate_customers(stores_initial, df_geo, df_reps, global_seed=42)

    # Adiciona 5 novas lojas no final
    stores_extended = pd.DataFrame(
        [{"store_number": f"{3000 + i}", "county": "Polk", "revenue": 1000.0} for i in range(25)]
    )
    df_cust_extended = generate_customers(stores_extended, df_geo, df_reps, global_seed=42)

    # As 20 primeiras lojas devem manter exatamente o mesmo CNPJ, razão social, cidade e RCA
    cols_to_check = [
        "customer_id",
        "store_number",
        "cnpj",
        "company_name",
        "city",
        "state",
        "region",
        "sales_rep_id",
        "whatsapp",
    ]
    pd.testing.assert_frame_equal(
        df_cust_initial[cols_to_check],
        df_cust_extended[cols_to_check].head(20),
    )


def test_each_customer_has_exactly_one_rca_and_one_municipality() -> None:
    """DoD: Cada cliente tem exatamente 1 RCA e 1 município, e a região do RCA cobre a UF do cliente."""
    stores_df = pd.DataFrame(
        [
            {"store_number": f"{4000 + i}", "county": "Black Hawk", "revenue": 15000.0 * (i + 1)}
            for i in range(40)
        ]
    )
    df_reps = generate_sales_reps(num_reps=30, global_seed=42)
    df_geo = generate_geography()

    df_cust = generate_customers(stores_df, df_geo, df_reps, global_seed=42)

    # Sem nulos em município, UF e RCA
    assert df_cust["city"].isna().sum() == 0
    assert df_cust["state"].isna().sum() == 0
    assert df_cust["sales_rep_id"].isna().sum() == 0

    # O RCA atribuído atua na mesma região do estado do cliente
    rep_region_map = df_reps.set_index("sales_rep_id")["region"].to_dict()
    for _, row in df_cust.iterrows():
        uf = row["state"]
        rep_id = row["sales_rep_id"]
        customer_region = UF_REGIAO[uf]
        rep_region = rep_region_map[rep_id]
        assert customer_region == rep_region, (
            f"Cliente na UF {uf} (Região {customer_region}) recebeu RCA {rep_id} da Região {rep_region}"
        )


def test_full_enrich_pipeline_and_duckdb_persistence(tmp_path: Path) -> None:
    """Executa o pipeline completo de enriquecimento com escrita em Parquet e tabelas DuckDB."""
    tmp_dir = tmp_path / "silver_test"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_db = tmp_dir / "kyberna_test.duckdb"

    counts = enrich_silver_dimensions(duckdb_path=tmp_db, silver_dir=tmp_dir, global_seed=42)

    assert counts["sales_reps"] == 30
    assert counts["geography"] >= 150
    assert counts["customers"] > 0

    # Verifica persistência física dos arquivos Parquet
    assert (tmp_dir / "dim_sales_rep.parquet").exists()
    assert (tmp_dir / "dim_geography.parquet").exists()
    assert (tmp_dir / "dim_customer.parquet").exists()

    # Verifica registro das tabelas no catálogo DuckDB (schema silver)
    con = duckdb.connect(str(tmp_db))
    tables = [t[0] for t in con.execute("SHOW TABLES FROM silver").fetchall()]
    assert "dim_sales_rep" in tables
    assert "dim_geography" in tables
    assert "dim_customer" in tables

    # Query de integridade relacional no DuckDB
    joined_df = con.execute(
        """
        SELECT
            c.customer_id,
            c.cnpj,
            c.city,
            c.state,
            r.name AS rep_name,
            r.commission_rate
        FROM silver.dim_customer c
        JOIN silver.dim_sales_rep r ON c.sales_rep_id = r.sales_rep_id
        LIMIT 5
        """
    ).df()
    assert len(joined_df) == 5
    con.close()


def test_cli_silver_enrich() -> None:
    """Verifica invocação do subcomando CLI `kyberna silver enrich`."""
    runner = CliRunner()
    result = runner.invoke(app, ["silver", "enrich", "--seed", "42"])
    assert result.exit_code == 0
    assert "Dimensões Silver enriquecidas com sucesso" in result.stdout
