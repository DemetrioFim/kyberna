from __future__ import annotations

import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from src.cli import app
from src.etl.contracts import SilverSalesSchema, validate_contract
from src.etl.lake import get_duckdb_connection, read_parquet
from src.etl.silver.time_anchor import apply_time_anchor, compute_weekly_time_shift

runner = CliRunner()


@pytest.mark.parametrize(
    ("max_date", "ref_date"),
    [
        (datetime.date(2024, 12, 31), datetime.date(2026, 10, 29)),
        (datetime.date(2024, 12, 31), datetime.date(2024, 12, 31)),
        (datetime.date(2024, 12, 31), datetime.date(2025, 1, 1)),
        (datetime.date(2024, 12, 31), datetime.date(2025, 1, 6)),
        (datetime.date(2024, 12, 31), datetime.date(2025, 1, 7)),
        (datetime.date(2024, 12, 31), datetime.date(2025, 1, 14)),
        (datetime.date(2024, 12, 31), datetime.date(2024, 12, 25)),
    ],
)
def test_compute_weekly_time_shift_invariants(max_date: datetime.date, ref_date: datetime.date) -> None:
    """DoD: Testa matematicamente que o offset é múltiplo de 7 e max(shifted) ∈ [ref - 6, ref]."""
    shift_days = compute_weekly_time_shift(max_date, ref_date)

    # 1. Invariante: múltiplo exato de 7 dias (semanas cheias)
    assert shift_days % 7 == 0, f"Offset não é múltiplo de 7: {shift_days}"

    # 2. Invariante: max_date deslocada cai na mesma semana da data de referência
    shifted_max = max_date + datetime.timedelta(days=shift_days)
    lower_bound = ref_date - datetime.timedelta(days=6)
    upper_bound = ref_date

    assert lower_bound <= shifted_max <= upper_bound, (
        f"Data deslocada {shifted_max} fora do intervalo [{lower_bound}, {upper_bound}]"
    )

    # 3. Invariante: dia da semana preservado
    assert shifted_max.weekday() == max_date.weekday()


def test_apply_time_anchor_preserves_dayofweek_distribution(tmp_path: Path) -> None:
    """DoD: Verifica que a distribuição por dia da semana é 100% idêntica antes e depois do shift."""
    db_path = tmp_path / "test_anchor.duckdb"
    con = get_duckdb_connection(db_path=db_path)

    try:
        # Prepara base Silver sintética reduzida com várias datas
        con.execute("""
            CREATE OR REPLACE TABLE silver.sales AS
            SELECT
                'INV-' || id AS invoice_line_id,
                (DATE '2024-01-01' + INTERVAL (id * 3) DAY)::DATE AS date,
                (DATE '2024-01-01' + INTERVAL (id * 3) DAY)::DATE AS original_date,
                0 AS time_shift_days,
                '100' AS store_number,
                'Store #1' AS store_name,
                'Des Moines' AS city,
                'Polk' AS county,
                '50309' AS zip_code,
                'Hy-Vee' AS chain_name,
                'Vodka' AS category_name,
                '260' AS vendor_number,
                'Diageo' AS vendor_name,
                'ITEM-1' AS item_number,
                'Vodka 750ml' AS item_description,
                12 AS pack,
                750.0 AS bottle_volume_ml,
                10.0 AS unit_cost,
                15.0 AS unit_price,
                5 AS units,
                75.0 AS sale_amount
            FROM range(1, 150) tbl(id);
        """)

        # Distribuição antes do shift
        dist_before = con.execute("""
            SELECT dayofweek(date) AS dow, COUNT(*) AS cnt
            FROM silver.sales
            GROUP BY dow
            ORDER BY dow;
        """).fetchall()

        # Aplica a âncora temporal para uma data recente
        ref_date = datetime.date(2026, 10, 28)
        parquet_p, meta = apply_time_anchor(
            db_con=con,
            reference_date=ref_date,
            base_dir=tmp_path,
        )

        assert parquet_p.exists()
        assert meta["time_shift_days"] % 7 == 0
        assert meta["time_shift_days"] > 0

        # Distribuição após o shift
        dist_after = con.execute("""
            SELECT dayofweek(date) AS dow, COUNT(*) AS cnt
            FROM silver.sales
            GROUP BY dow
            ORDER BY dow;
        """).fetchall()

        # DoD: Distribuição por dia da semana deve ser rigorosamente a mesma
        assert dist_before == dist_after, "Distribuição por dia da semana foi alterada!"

        # Validação do Contrato Pandera
        df_shifted = read_parquet(parquet_p)
        validated = validate_contract(df_shifted, SilverSalesSchema, layer="silver")
        assert len(validated) == 149
        assert "original_date" in df_shifted.columns
        assert "time_shift_days" in df_shifted.columns

        # Verifica limite de data
        max_date_actual = datetime.date.fromisoformat(meta["max_shifted_date"])
        assert (ref_date - datetime.timedelta(days=6)) <= max_date_actual <= ref_date
    finally:
        con.close()


def test_apply_time_anchor_no_shift(tmp_path: Path) -> None:
    """Verifica comportamento com --no-shift (mantém datas originais com shift_days=0)."""
    db_path = tmp_path / "test_no_shift.duckdb"
    con = get_duckdb_connection(db_path=db_path)

    try:
        con.execute("""
            CREATE OR REPLACE TABLE silver.sales AS
            SELECT
                'INV-1' AS invoice_line_id,
                DATE '2024-05-10' AS date,
                DATE '2024-05-10' AS original_date,
                0 AS time_shift_days,
                '100' AS store_number,
                'Store' AS store_name,
                'City' AS city,
                'County' AS county,
                '50000' AS zip_code,
                'Fareway' AS chain_name,
                'Whiskey' AS category_name,
                '1' AS vendor_number,
                'Vendor' AS vendor_name,
                'IT-1' AS item_number,
                'Item' AS item_description,
                12 AS pack,
                750.0 AS bottle_volume_ml,
                10.0 AS unit_cost,
                15.0 AS unit_price,
                2 AS units,
                30.0 AS sale_amount;
        """)

        parquet_p, meta = apply_time_anchor(
            db_con=con,
            no_shift=True,
            base_dir=tmp_path,
        )

        assert meta["time_shift_days"] == 0
        assert meta["no_shift"] is True
        assert meta["min_shifted_date"] == "2024-05-10"
        assert meta["max_shifted_date"] == "2024-05-10"

        df = read_parquet(parquet_p)
        assert df["date"].iloc[0].strftime("%Y-%m-%d") == "2024-05-10"
    finally:
        con.close()


def test_time_anchor_idempotency_and_reversibility(tmp_path: Path) -> None:
    """Verifica que reaplicar a âncora com novas datas não acumula shifts indevidos."""
    db_path = tmp_path / "test_idemp.duckdb"
    con = get_duckdb_connection(db_path=db_path)

    try:
        con.execute("""
            CREATE OR REPLACE TABLE silver.sales AS
            SELECT
                'INV-10' AS invoice_line_id,
                DATE '2024-12-31' AS date,
                DATE '2024-12-31' AS original_date,
                0 AS time_shift_days,
                '100' AS store_number,
                'Store' AS store_name,
                'City' AS city,
                'County' AS county,
                '50000' AS zip_code,
                'Independente' AS chain_name,
                'Rum' AS category_name,
                '1' AS vendor_number,
                'Vendor' AS vendor_name,
                'IT-1' AS item_number,
                'Item' AS item_description,
                12 AS pack,
                750.0 AS bottle_volume_ml,
                10.0 AS unit_cost,
                15.0 AS unit_price,
                1 AS units,
                15.0 AS sale_amount;
        """)

        # Primeiro shift para outubro de 2026
        _, meta1 = apply_time_anchor(
            db_con=con,
            reference_date="2026-10-25",
            base_dir=tmp_path,
        )
        assert meta1["time_shift_days"] > 0

        # Segundo shift para novembro de 2026 (não deve somar shift1 + shift2)
        _, meta2 = apply_time_anchor(
            db_con=con,
            reference_date="2026-11-15",
            base_dir=tmp_path,
        )

        # O shift deve ser calculado em relação à original_date (2024-12-31), não à data já deslocada
        expected_shift = compute_weekly_time_shift(
            datetime.date(2024, 12, 31),
            datetime.date(2026, 11, 15),
        )
        assert meta2["time_shift_days"] == expected_shift

        # Reversão com no_shift: retorna à data original
        _, meta3 = apply_time_anchor(
            db_con=con,
            no_shift=True,
            base_dir=tmp_path,
        )
        assert meta3["time_shift_days"] == 0
        assert meta3["max_shifted_date"] == "2024-12-31"
    finally:
        con.close()


def test_cli_silver_build_with_time_anchor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Testa integração ponta a ponta do comando CLI kyberna silver build com âncora temporal."""
    monkeypatch.setenv("KYBERNA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("KYBERNA_DUCKDB_PATH", str(tmp_path / "data" / "kyberna.duckdb"))

    # Constrói silver a partir da fixture com âncora para data fixa
    result = runner.invoke(
        app,
        ["silver", "build", "--sample", "--reference-date", "2026-10-28"],
    )
    assert result.exit_code == 0
    assert "Silver construída com sucesso" in result.output
    assert "Âncora temporal aplicada" in result.output

    # Testa também o subcomando silver anchor isolado com --no-shift
    result_anchor = runner.invoke(app, ["silver", "anchor", "--no-shift"])
    assert result_anchor.exit_code == 0
    assert "shift=0 dias" in result_anchor.output
