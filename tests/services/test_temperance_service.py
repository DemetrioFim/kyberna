from __future__ import annotations

import pytest

from src.core.paths import get_duckdb_path
from src.db.duckdb_repo import DuckDBRepository
from src.services.dto import TemperancePageDTO
from src.services.executive_service import build_executive_dashboard
from src.services.temperance_queries import (
    query_commercial_erosion_waterfall,
    query_discount_policy_violations,
    query_temperance_inventory_details,
    query_temperance_kpis,
    query_term_leak_by_rep,
)
from src.services.temperance_service import build_temperance_dashboard
from src.ui.state import fetch_date_bounds, resolve_period_bounds


@pytest.fixture
def repo() -> DuckDBRepository:
    """Fixture fornecendo o DuckDBRepository conectado ao banco principal data/kyberna.duckdb."""
    db_path = get_duckdb_path()
    if not db_path.exists():
        pytest.skip(f"Banco '{db_path}' não encontrado para teste de serviços de temperança.")
    return DuckDBRepository(db_path=db_path)


def test_temperance_kpis_aggregation(repo: DuckDBRepository) -> None:
    """Valida cálculo consolidado dos KPIs de Temperança para o Cenário 1."""
    kpis = query_temperance_kpis(repo, scenario_id="c1_toys")

    assert kpis.gross_revenue > 0.0
    assert kpis.discount_amount > 0.0
    assert kpis.commission_erosion_brl > 0.0
    assert kpis.freight_erosion_brl > 0.0

    # Identidade contábil da erosão comercial
    expected_erosion = round(
        kpis.discount_amount + kpis.commission_erosion_brl + kpis.freight_erosion_brl,
        2,
    )
    assert abs(kpis.total_commercial_erosion_brl - expected_erosion) < 0.05
    assert 10.0 <= kpis.total_commercial_erosion_pct <= 20.0

    # Descontos fora da política
    assert kpis.excess_discount_brl > 300_000.0
    assert 20.0 <= kpis.excess_discount_pct_of_discount <= 35.0

    # Custo de prazo esticado (>30d)
    assert kpis.financial_term_leak_brl > 100_000.0

    # Estoque imobilizado e risco de ruptura
    assert kpis.total_stock_value_brl > 300_000.0
    assert kpis.locked_capital_brl > 45_000.0
    assert kpis.locked_skus_count == 59
    assert kpis.stockout_risk_skus_count > 0
    assert kpis.stockout_risk_revenue_brl > 0.0


def test_commercial_erosion_waterfall_structure(repo: DuckDBRepository) -> None:
    """Valida a tabela de 9 etapas do Waterfall de Margem Real."""
    df = query_commercial_erosion_waterfall(repo, scenario_id="c1_toys")

    assert not df.empty
    assert len(df) == 9

    expected_cols = {"step_key", "label", "amount", "pct_of_gross", "measure", "color"}
    assert expected_cols.issubset(df.columns)

    # Primeira etapa deve ser o Faturamento Bruto positivo
    assert df.iloc[0]["step_key"] == "gross_revenue"
    assert df.iloc[0]["amount"] > 0
    assert df.iloc[0]["pct_of_gross"] == 100.0

    # Última etapa deve ser a Margem de Contribuição Líquida
    assert df.iloc[-1]["step_key"] == "contribution_margin"
    assert df.iloc[-1]["amount"] > 0
    assert 20.0 <= df.iloc[-1]["pct_of_gross"] <= 35.0


def test_discount_policy_violations_ranking(repo: DuckDBRepository) -> None:
    """Valida auditoria de descontos acima do teto com identificação de RCAs agressivos."""
    df_reps, df_fams = query_discount_policy_violations(repo, scenario_id="c1_toys")

    assert not df_reps.empty
    assert not df_fams.empty

    # RCAs agressivos devem estar no topo de excess_discount_brl
    top_rep_ids = set(df_reps.head(5)["sales_rep_id"].tolist())
    aggressive_candidates = {"RCA-025", "RCA-028", "RCA-019", "RCA-012", "RCA-003"}
    assert len(top_rep_ids.intersection(aggressive_candidates)) >= 3

    # Famílias devem ter faturamento e descontos positivos
    assert len(df_fams) >= 5
    assert (df_fams["excess_discount_brl"] > 0).any()


def test_term_leak_by_rep_ranking(repo: DuckDBRepository) -> None:
    """Valida o cálculo do custo financeiro de prazos acima de 30 dias por representante."""
    df = query_term_leak_by_rep(repo, scenario_id="c1_toys")

    assert not df.empty
    assert "sales_rep_id" in df.columns
    assert "term_leak_brl" in df.columns
    assert "avg_pmr_days" in df.columns

    # O topo deve ter valor financeiro de prazo significativo
    assert df["term_leak_brl"].iloc[0] > df["term_leak_brl"].iloc[-1]
    assert df["avg_pmr_days"].max() >= 40.0


def test_temperance_inventory_details(repo: DuckDBRepository) -> None:
    """Valida as tabelas operacionais de estoque imobilizado e risco de ruptura."""
    df_locked, df_stockout, df_abc = query_temperance_inventory_details(repo, scenario_id="c1_toys")

    # Itens travados (>120d)
    assert len(df_locked) == 59
    assert (df_locked["coverage_days"] > 120.0).all()
    assert (df_locked["stock_value_brl"] > 0).all()
    assert "action_prescription" in df_locked.columns

    # Risco de ruptura na Curva A/B
    assert not df_stockout.empty
    assert (df_stockout["coverage_days"] <= df_stockout["lead_time_days"]).all()
    assert (df_stockout["suggested_order_boxes"] >= 1).all()
    assert (df_stockout["revenue_at_risk_brl"] > 0).all()

    # Matriz ABC/XYZ
    assert not df_abc.empty
    assert len(df_abc) <= 9


def test_temperance_dashboard_full_payload_and_prescriptions(repo: DuckDBRepository) -> None:
    """Valida geração do payload completo TemperancePageDTO consumido pela Tela 4."""
    dto = build_temperance_dashboard(repo, scenario_id="c1_toys")

    assert isinstance(dto, TemperancePageDTO)
    assert dto.scenario_id == "c1_toys"
    assert "Temperança Comercial" in dto.headline_title
    assert "descontos fora da política" in dto.headline_title
    assert "Veredito de Temperança" in dto.prescription_title
    assert dto.prescription_impact_brl is not None and dto.prescription_impact_brl > 0.0

    # DataFrames populados
    assert not dto.waterfall_df.empty
    assert not dto.policy_violations_by_rep_df.empty
    assert not dto.policy_violations_by_family_df.empty
    assert not dto.locked_inventory_df.empty
    assert not dto.stockout_risk_df.empty


def test_temperance_filtering_consistency(repo: DuckDBRepository) -> None:
    """Valida consistência dos filtros geográficos e de representantes."""
    dto_all = build_temperance_dashboard(repo, scenario_id="c1_toys")
    dto_se = build_temperance_dashboard(repo, scenario_id="c1_toys", regiao="Sudeste")
    dto_rep = build_temperance_dashboard(repo, scenario_id="c1_toys", sales_reps=["RCA-025"])

    # Filtro Sudeste deve ser um subconjunto estrito do global
    assert 0 < dto_se.kpis.gross_revenue < dto_all.kpis.gross_revenue
    assert 0 < dto_se.kpis.excess_discount_brl < dto_all.kpis.excess_discount_brl

    # Filtro de RCA único
    assert 0 < dto_rep.kpis.gross_revenue < dto_all.kpis.gross_revenue
    assert len(dto_rep.policy_violations_by_rep_df) == 1
    assert dto_rep.policy_violations_by_rep_df.iloc[0]["sales_rep_id"] == "RCA-025"


@pytest.mark.parametrize("preset", ["all", "ytd", "s2", "q4", "last_month", "custom_month"])
def test_prudencia_and_temperanca_waterfalls_match_across_period_presets(
    repo: DuckDBRepository,
    preset: str,
) -> None:
    """Valida reconciliação exata do Waterfall entre Prudência e Temperança em todos os presets."""
    min_d, max_d = fetch_date_bounds(repo, "c1_toys")
    bounds = resolve_period_bounds(preset, selected_month="2024-11", min_date=min_d, max_date=max_d)

    exec_dto = build_executive_dashboard(
        repo,
        scenario_id="c1_toys",
        start_date_key=bounds.start_date_key,
        end_date_key=bounds.end_date_key,
        comp_start_date_key=bounds.comparison_start_date_key,
        comp_end_date_key=bounds.comparison_end_date_key,
        period_label=bounds.period_label,
        comparison_label=bounds.comparison_label,
    )
    temp_dto = build_temperance_dashboard(
        repo,
        scenario_id="c1_toys",
        start_date_key=bounds.start_date_key,
        end_date_key=bounds.end_date_key,
    )

    assert len(exec_dto.waterfall_df) == 9
    assert len(temp_dto.waterfall_df) == 9

    assert exec_dto.kpis.gross_revenue == pytest.approx(
        float(temp_dto.waterfall_df.iloc[0]["amount"]),
        abs=1e-2,
    )
    assert exec_dto.kpis.contribution_margin == pytest.approx(
        float(temp_dto.waterfall_df.iloc[-1]["amount"]),
        abs=1e-2,
    )

    for idx in range(9):
        exec_amt = float(exec_dto.waterfall_df.iloc[idx]["amount"])
        temp_amt = float(temp_dto.waterfall_df.iloc[idx]["amount"])
        assert exec_amt == pytest.approx(temp_amt, abs=1e-2)
