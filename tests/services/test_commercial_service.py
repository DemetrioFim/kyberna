from __future__ import annotations

import pytest

from src.core.paths import get_duckdb_path
from src.db.duckdb_repo import DuckDBRepository
from src.services.commercial_queries import (
    query_commercial_kpis_data,
    query_priority_risk_customers,
    query_rep_performance_data,
    query_rfm_summary_data,
    query_white_space_matrix_data,
)
from src.services.commercial_service import (
    build_commercial_dashboard,
    build_commercial_headline,
    build_commercial_prescription,
)
from src.services.dto import CommercialKpisDTO


@pytest.fixture
def repo() -> DuckDBRepository:
    """Fixture fornecendo o DuckDBRepository conectado ao banco principal data/kyberna.duckdb."""
    db_path = get_duckdb_path()
    if not db_path.exists():
        pytest.skip(f"Banco '{db_path}' não encontrado para teste de serviços comerciais.")
    return DuckDBRepository(db_path=db_path)


def test_commercial_kpis_data(repo: DuckDBRepository) -> None:
    """Valida a consulta dos KPIs comerciais consolidados para o Cenário 1."""
    kpis_raw = query_commercial_kpis_data(repo, scenario_id="c1_toys")
    kpis = CommercialKpisDTO(**kpis_raw)

    assert kpis.total_customers == 300
    assert kpis.at_risk_customers > 0
    assert kpis.at_risk_customers_pct > 0.0
    assert kpis.annual_revenue_at_risk_brl > 0.0
    assert kpis.annual_margin_at_risk_brl > 0.0
    assert kpis.white_space_potential_revenue_brl > 0.0
    assert kpis.avg_positivation_pct > 0.0


def test_priority_risk_customers_data(repo: DuckDBRepository) -> None:
    """Valida a lista priorizada de clientes com ordenação por valor exposto e atributos enriquecidos."""
    df = query_priority_risk_customers(repo, scenario_id="c1_toys", limit=50)

    assert not df.empty
    assert len(df) <= 50

    expected_cols = {
        "customer_id",
        "customer_name",
        "state",
        "sales_rep_name",
        "rfm_segment",
        "risk_status",
        "delay_ratio",
        "recency_days",
        "expected_cycle_days",
        "annual_revenue_at_risk",
        "top_opportunity_family",
        "top_opportunity_brl",
    }
    assert expected_cols.issubset(set(df.columns))

    # Verifica ordenação decrescente por valor anual em risco
    rev_risk = df["annual_revenue_at_risk"].tolist()
    assert rev_risk == sorted(rev_risk, reverse=True)


def test_rfm_summary_data(repo: DuckDBRepository) -> None:
    """Valida o agrupamento dos 9 segmentos RFM sob o repositório."""
    df = query_rfm_summary_data(repo, scenario_id="c1_toys")

    assert not df.empty
    assert len(df) == 9
    assert "rfm_segment" in df.columns
    assert "customer_count" in df.columns
    assert "gross_revenue" in df.columns
    assert "customer_share_pct" in df.columns
    assert df["customer_count"].sum() == 300


def test_white_space_matrix_data(repo: DuckDBRepository) -> None:
    """Valida a matriz de oportunidades White Space por família recomendada e segmento."""
    df = query_white_space_matrix_data(repo, scenario_id="c1_toys")

    assert not df.empty
    assert "recommended_family" in df.columns
    assert "rfm_segment" in df.columns
    assert "potential_revenue_brl" in df.columns
    assert df["potential_revenue_brl"].sum() > 0


def test_rep_performance_data(repo: DuckDBRepository) -> None:
    """Valida a consulta dos representantes para exibição no gráfico cartesiano."""
    df = query_rep_performance_data(repo, scenario_id="c1_toys")

    assert not df.empty
    assert len(df) == 30
    assert "sales_rep_name" in df.columns
    assert "quadrant" in df.columns
    assert "gross_revenue" in df.columns
    assert "margin_pct" in df.columns
    assert "revenue_at_risk_brl" in df.columns


def test_commercial_headline_and_prescription() -> None:
    """Valida a formatação de manchete e prescrição comercial para diferentes estados."""
    kpis = CommercialKpisDTO(
        total_customers=300,
        active_customers=250,
        at_risk_customers=40,
        at_risk_customers_pct=13.3,
        annual_revenue_at_risk_brl=850000.0,
        annual_margin_at_risk_brl=230000.0,
        white_space_potential_revenue_brl=450000.0,
        white_space_potential_margin_brl=120000.0,
        avg_positivation_pct=83.3,
    )

    title, text = build_commercial_headline(kpis)
    assert "Radar de Churn: 40 clientes" in title
    assert "13.3%" in text

    # Prescrição com lista
    import pandas as pd

    sample_df = pd.DataFrame(
        {
            "annual_revenue_at_risk": [10000.0, 5000.0],
            "annual_margin_at_risk": [2700.0, 1350.0],
            "top_opportunity_brl": [4000.0, 2000.0],
        }
    )
    p_title, p_html, impact = build_commercial_prescription(kpis, sample_df)
    assert "Plano Tático" in p_title
    assert "R$ 15.000,00" in p_html
    assert impact == pytest.approx(4050.0)


def test_build_commercial_dashboard_full(repo: DuckDBRepository) -> None:
    """Valida a construção completa do CommercialPageDTO e latência de consulta."""
    import time

    start = time.perf_counter()
    dto = build_commercial_dashboard(repo, scenario_id="c1_toys")
    elapsed = time.perf_counter() - start

    assert elapsed < 1.5, f"Dashboard demorou {elapsed:.3f}s (esperado < 1.5s)"
    assert dto.scenario_id == "c1_toys"
    assert dto.kpis.total_customers == 300
    assert not dto.priority_risk_df.empty
    assert not dto.rfm_summary_df.empty
    assert not dto.white_space_matrix_df.empty
    assert not dto.rep_performance_df.empty
    assert len(dto.headline_title) > 5
    assert len(dto.prescription_title) > 5


def test_commercial_dashboard_filters(repo: DuckDBRepository) -> None:
    """Valida aplicação de filtros de região e UF no CommercialPageDTO."""
    dto_sudeste = build_commercial_dashboard(repo, scenario_id="c1_toys", regiao="Sudeste")
    assert dto_sudeste.kpis.total_customers < 300
    assert dto_sudeste.kpis.total_customers > 0

    dto_sp = build_commercial_dashboard(repo, scenario_id="c1_toys", regiao="Sudeste", uf="SP")
    assert dto_sp.kpis.total_customers <= dto_sudeste.kpis.total_customers
    assert (dto_sp.priority_risk_df["state"] == "SP").all()
