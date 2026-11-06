from __future__ import annotations

import time

import pytest

from src.core.paths import get_duckdb_path
from src.db.duckdb_repo import DuckDBRepository
from src.services.executive_service import (
    build_executive_dashboard,
    build_waterfall_steps,
    compute_executive_kpis,
    get_abc_xyz_overview,
    get_filter_options,
    get_monthly_margin_trend,
    get_monthly_sales_table,
    get_top_margin_drivers,
)
from src.ui.state import resolve_period_bounds


@pytest.fixture
def repo() -> DuckDBRepository:
    """Fixture fornecendo o DuckDBRepository conectado ao banco principal data/kyberna.duckdb."""
    db_path = get_duckdb_path()
    if not db_path.exists():
        pytest.skip(f"Banco '{db_path}' não encontrado para teste de reconciliação contábil.")
    return DuckDBRepository(db_path=db_path)


def test_executive_kpis_exact_accounting_reconciliation(repo: DuckDBRepository) -> None:
    """Valida reconciliação de 100% dos KPIs com c1_toys.fact_sales e aba DRE do Excel audit."""
    kpis = compute_executive_kpis(repo, scenario_id="c1_toys")

    # Valores canônicos exatos de c1_toys.fact_sales e conciliacao_c1_toys.xlsx
    assert kpis.gross_revenue == pytest.approx(19703059.08, abs=0.02)
    assert kpis.discount_amount == pytest.approx(1493170.89, abs=0.02)
    assert kpis.net_price_revenue == pytest.approx(18209888.19, abs=0.02)
    assert kpis.tax_amount == pytest.approx(3176081.32, abs=0.02)
    assert kpis.net_revenue == pytest.approx(15033806.87, abs=0.02)
    assert kpis.cogs == pytest.approx(8537828.64, abs=0.02)
    assert kpis.commission_amount == pytest.approx(953518.01, abs=0.02)
    assert kpis.freight_amount == pytest.approx(216967.80, abs=0.02)
    assert kpis.contribution_margin == pytest.approx(5325492.42, abs=0.02)
    assert kpis.contribution_margin_pct == pytest.approx(27.03, abs=0.02)
    assert kpis.total_orders == 19578
    assert kpis.active_customers == 300

    # Identidade contábil canônica do Waterfall
    expected_cm = kpis.net_revenue - kpis.cogs - kpis.commission_amount - kpis.freight_amount
    assert abs(kpis.contribution_margin - expected_cm) < 1e-6


def test_waterfall_steps_structure_and_conservation(repo: DuckDBRepository) -> None:
    """Valida que o Waterfall possui 9 etapas e respeita a decomposição contábil."""
    kpis = compute_executive_kpis(repo, scenario_id="c1_toys")
    steps_df = build_waterfall_steps(kpis)

    assert len(steps_df) == 9
    assert set(steps_df.columns) == {"step_key", "label", "amount", "pct_of_gross", "measure"}

    # Primeira etapa deve ser Faturamento Bruto (absoluta)
    assert steps_df.iloc[0]["step_key"] == "gross_revenue"
    assert steps_df.iloc[0]["measure"] == "absolute"
    assert steps_df.iloc[0]["amount"] == kpis.gross_revenue

    # Última etapa deve ser Margem de Contribuição (total)
    assert steps_df.iloc[-1]["step_key"] == "contribution_margin"
    assert steps_df.iloc[-1]["measure"] == "total"
    assert steps_df.iloc[-1]["amount"] == kpis.contribution_margin


def test_monthly_margin_trend_conservation(repo: DuckDBRepository) -> None:
    """Valida a série temporal mensal e conservação de totais contra os KPIs consolidados."""
    monthly_df = get_monthly_margin_trend(repo, scenario_id="c1_toys")

    assert len(monthly_df) == 24  # 24 meses (2023-01 a 2024-12)
    assert "month_label" in monthly_df.columns
    assert "gross_revenue" in monthly_df.columns
    assert "contribution_margin" in monthly_df.columns
    assert "margin_pct" in monthly_df.columns

    # Soma de todos os meses deve conservar o faturamento bruto e a margem de contribuição
    total_gross = float(monthly_df["gross_revenue"].sum())
    total_cm = float(monthly_df["contribution_margin"].sum())

    assert total_gross == pytest.approx(19703059.08, abs=0.05)
    assert total_cm == pytest.approx(5325492.42, abs=0.05)


def test_abc_xyz_matrix_summary_and_filtering(repo: DuckDBRepository) -> None:
    """Valida a matriz 3x3 ABC/XYZ e o filtro de SKUs da célula selecionada."""
    matrix_df, skus_df = get_abc_xyz_overview(repo, scenario_id="c1_toys", selected_cell="AX")

    assert len(matrix_df) == 9
    assert "margin_share_pct" in matrix_df.columns
    assert "recommended_policy" in matrix_df.columns

    # A soma das participações na margem das 9 células deve somar ~100%
    total_margin_share = float(matrix_df["margin_share_pct"].sum())
    assert 99.0 <= total_margin_share <= 101.0

    # Todos os SKUs retornados devem pertencer à célula AX
    assert not skus_df.empty
    assert (skus_df["abc_xyz_class"] == "AX").all()


def test_top_margin_drivers_ranking(repo: DuckDBRepository) -> None:
    """Valida extração dos Top 10 geradores e destruidores por produto e cliente."""
    gen_p, dest_p = get_top_margin_drivers(repo, scenario_id="c1_toys", by="product", limit=10)
    assert len(gen_p) == 10
    assert len(dest_p) == 10

    # Gerador #1 deve ter maior margem que o #10
    assert gen_p.iloc[0]["contribution_margin"] >= gen_p.iloc[-1]["contribution_margin"]

    # Menor margem deve ter margem % menor que a média geral
    assert dest_p.iloc[0]["margin_pct"] < 25.0

    gen_c, dest_c = get_top_margin_drivers(repo, scenario_id="c1_toys", by="customer", limit=10)
    assert len(gen_c) == 10
    assert len(dest_c) == 10
    assert dest_c.iloc[0]["margin_pct"] < 15.0  # Lojistas com desconto elevado em SP


def test_filter_options_and_geographic_filtering(repo: DuckDBRepository) -> None:
    """Valida que opções de filtro são extraídas e filtros geográficos reduzem o volume."""
    options = get_filter_options(repo, scenario_id="c1_toys")
    assert "Sudeste" in options["regioes"]
    assert "SP" in options["ufs"]
    assert len(options["families"]) >= 5

    kpis_all = compute_executive_kpis(repo, scenario_id="c1_toys")
    kpis_sp = compute_executive_kpis(repo, scenario_id="c1_toys", regiao="Sudeste", uf="SP")

    assert kpis_sp.gross_revenue < kpis_all.gross_revenue
    assert kpis_sp.active_customers < kpis_all.active_customers
    assert kpis_sp.contribution_margin < kpis_all.contribution_margin


def test_executive_dashboard_build_latency_and_payload(repo: DuckDBRepository) -> None:
    """Valida latência de montagem do payload da Visão Executiva (< 1,5 s) e integridade do DTO."""
    t0 = time.perf_counter()
    dto = build_executive_dashboard(repo, scenario_id="c1_toys")
    latency_s = time.perf_counter() - t0

    assert latency_s < 1.5, f"Dashboard demorou {latency_s:.2f} s, acima do limite de 1.5 s."
    assert dto.scenario_id == "c1_toys"
    assert len(dto.waterfall_df) == 9
    assert len(dto.monthly_trend_df) == 24
    assert len(dto.abc_xyz_matrix_df) == 9
    assert len(dto.top_generators_df) == 10
    assert len(dto.top_destroyers_df) == 10
    assert len(dto.top_customer_generators_df) == 10
    assert len(dto.top_customer_destroyers_df) == 10
    assert dto.prescription_impact_brl is not None
    assert dto.prescription_impact_brl > 0
    assert not dto.monthly_sales_table_df.empty
    assert "gross_revenue" in dto.monthly_sales_table_df.columns
    assert "margin_pct" in dto.monthly_sales_table_df.columns
    assert "mom_gross_pct" in dto.monthly_sales_table_df.columns


def test_executive_dashboard_temporal_presets_and_monthly_table(repo: DuckDBRepository) -> None:
    """Valida filtros temporais (YTD 12M, Mês Específico) e a geração da tabela de demonstrativo mensal."""
    # Teste com filtro YTD (Ano 2024) resolvido
    bounds_ytd = resolve_period_bounds("ytd")
    dto_ytd = build_executive_dashboard(
        repo,
        scenario_id="c1_toys",
        start_date_key=bounds_ytd.start_date_key,
        end_date_key=bounds_ytd.end_date_key,
        comp_start_date_key=bounds_ytd.comparison_start_date_key,
        comp_end_date_key=bounds_ytd.comparison_end_date_key,
        period_label=bounds_ytd.period_label,
        comparison_label=bounds_ytd.comparison_label,
    )
    assert "2024" in dto_ytd.period_label
    assert dto_ytd.kpis.gross_revenue < 19703059.08  # Subconjunto do faturamento total de 24m
    assert dto_ytd.kpis.gross_revenue_delta_pct is not None
    assert dto_ytd.kpis.contribution_margin_delta_pct is not None
    assert len(dto_ytd.monthly_sales_table_df) == 12

    # Teste com filtro de Mês Específico (2024-12)
    bounds_month = resolve_period_bounds("custom_month", selected_month="2024-12")
    dto_month = build_executive_dashboard(
        repo,
        scenario_id="c1_toys",
        start_date_key=bounds_month.start_date_key,
        end_date_key=bounds_month.end_date_key,
        comp_start_date_key=bounds_month.comparison_start_date_key,
        comp_end_date_key=bounds_month.comparison_end_date_key,
        period_label=bounds_month.period_label,
        comparison_label=bounds_month.comparison_label,
    )
    assert "Dezembro" in dto_month.period_label
    assert dto_month.kpis.total_orders < dto_ytd.kpis.total_orders
    assert not dto_month.monthly_sales_table_df.empty

    # Teste de chamada direta à função de demonstrativo mensal
    table_direct = get_monthly_sales_table(repo, scenario_id="c1_toys")
    assert len(table_direct) == 24
