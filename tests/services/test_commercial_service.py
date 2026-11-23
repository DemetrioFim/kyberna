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


def test_justice_service_innovations(repo: DuckDBRepository) -> None:
    """Valida inovações da Página 3 - Justiça: Funil do Ciclo, White Space com Pitch e Campeões/Vampiros."""
    from src.services.commercial_queries import (
        query_cycle_health_funnel,
        query_top_white_space_deals,
    )

    # 1. Funil do Ciclo em 4 estágios somando 100% dos clientes
    funnel_df = query_cycle_health_funnel(repo, scenario_id="c1_toys")
    assert not funnel_df.empty
    assert len(funnel_df) <= 4
    assert funnel_df["customer_count"].sum() == 300
    assert pytest.approx(funnel_df["customer_share_pct"].sum(), abs=0.5) == 100.0

    # 2. Top White Space Deals com SKU Âncora e Pitch
    ws_deals_df = query_top_white_space_deals(repo, scenario_id="c1_toys", limit=20)
    assert not ws_deals_df.empty
    assert "anchor_sku_name" in ws_deals_df.columns
    assert "action_pitch" in ws_deals_df.columns
    assert "recommended_top_sku" in ws_deals_df.columns
    assert len(ws_deals_df.iloc[0]["action_pitch"]) > 10

    # 3. Payload completo de Justiça
    dto = build_commercial_dashboard(repo, scenario_id="c1_toys")
    assert not dto.cycle_funnel_df.empty
    assert not dto.top_white_space_deals_df.empty
    assert not dto.champions_df.empty
    assert not dto.vampires_df.empty
    assert not dto.top_family_generators_df.empty
    assert not dto.top_product_generators_df.empty
    assert dto.kpis.attention_customers > 0
    assert dto.kpis.avg_ltv_brl > 0
    assert "estimated_ltv_brl" in dto.rfm_summary_df.columns


def test_apriori_real_metrics_coverage_and_excel_export(repo: DuckDBRepository) -> None:
    """Valida V5-S1: regras Apriori reais, cobertura sem LIMIT 50, RFM e aba Regras_Apriori no Excel."""
    import io
    import zipfile

    from src.services.export_service import generate_commercial_action_excel
    from src.services.white_space_queries import (
        query_apriori_rules_data,
        query_white_space_coverage_kpis,
    )

    rules_df = query_apriori_rules_data(repo, scenario_id="c1_toys")
    assert not rules_df.empty
    assert {"rule_level", "support_pct", "confidence_pct", "lift", "rule_label"}.issubset(
        set(rules_df.columns)
    )
    assert {"family", "sku"}.issubset(set(rules_df["rule_level"].unique()))

    cov = query_white_space_coverage_kpis(repo, scenario_id="c1_toys")
    assert int(cov["white_space_eligible_customers"]) > 50
    assert int(cov["white_space_total_offers"]) >= int(cov["white_space_eligible_customers"])

    dto = build_commercial_dashboard(repo, scenario_id="c1_toys")
    assert not dto.apriori_rules_df.empty
    assert dto.kpis.white_space_eligible_customers == int(cov["white_space_eligible_customers"])
    assert dto.kpis.apriori_rules_count == len(dto.apriori_rules_df)
    assert dto.kpis.apriori_max_lift >= 1.0
    assert dto.kpis.apriori_avg_confidence_pct > 0.0
    assert dto.kpis.apriori_avg_support_pct > 0.0

    deals = dto.top_white_space_deals_df
    assert {
        "rfm_segment",
        "best_rule_antecedent",
        "apriori_support_pct",
        "apriori_confidence_pct",
        "apriori_lift",
    }.issubset(set(deals.columns))
    assert not deals["recommended_top_sku"].astype(str).str.contains("Sortimento A").any()

    excel_bytes = generate_commercial_action_excel(
        dto.priority_risk_df.head(10),
        deals.head(10),
        "Brinquedos",
        apriori_rules_df=dto.apriori_rules_df,
    )
    with zipfile.ZipFile(io.BytesIO(excel_bytes)) as zf:
        workbook_xml = zf.read("xl/workbook.xml").decode("utf-8")
    assert "Regras_Apriori" in workbook_xml


def test_white_space_deals_reconcile_kpi_and_prefer_positive_lift(repo: DuckDBRepository) -> None:
    """Garante reconciliação integral da Diretriz Cross-Sell (>200 ofertas) com KPIs e Lift > 1.0."""
    dto = build_commercial_dashboard(repo, scenario_id="c1_toys")
    deals = dto.top_white_space_deals_df

    assert len(deals) > 200
    assert deals["potential_revenue_brl"].sum() == pytest.approx(
        dto.kpis.white_space_potential_revenue_brl, abs=1.0
    )
    assert deals["potential_margin_brl"].sum() == pytest.approx(
        dto.kpis.white_space_potential_margin_brl, abs=1.0
    )
    # Verifica que não há ofertas recomendadas com Lift < 1.0 quando há alternativa sinérgica no mart
    rules_family = dto.apriori_rules_df[dto.apriori_rules_df["rule_level"] == "family"]
    fams_with_pos_lift = set(rules_family.loc[rules_family["lift"] > 1.0, "consequent_name"].astype(str))
    deals_in_pos_fams = deals[deals["recommended_family"].astype(str).isin(fams_with_pos_lift)]
    if not deals_in_pos_fams.empty:
        assert (deals_in_pos_fams["apriori_lift"] > 1.0).all()
