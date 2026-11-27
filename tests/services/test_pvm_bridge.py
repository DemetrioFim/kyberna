from __future__ import annotations

import pandas as pd
import pytest

from src.core.paths import get_duckdb_path
from src.db.duckdb_repo import DuckDBRepository
from src.services.executive_service import build_executive_dashboard
from src.services.pvm_bridge import build_pvm_bridge, compute_pvm_bridge_steps


@pytest.fixture
def repo() -> DuckDBRepository:
    """Fornece o DuckDBRepository conectado ao banco principal data/kyberna.duckdb."""
    db_path = get_duckdb_path()
    if not db_path.exists():
        pytest.skip(f"Banco '{db_path}' nao encontrado para testes de PVM Bridge.")
    return DuckDBRepository(db_path=db_path)


def test_compute_pvm_bridge_steps_exact_reconciliation() -> None:
    """Valida fechamento contabil exato do Bridge PVM com dados sinteticos conhecidos."""
    prev_df = pd.DataFrame(
        [
            {
                "product_id": "SKU1",
                "units": 100.0,
                "gross_revenue": 1000.0,
                "net_keep_revenue": 800.0,
                "contribution_margin": 300.0,
            },
            {
                "product_id": "SKU2",
                "units": 100.0,
                "gross_revenue": 2000.0,
                "net_keep_revenue": 1600.0,
                "contribution_margin": 500.0,
            },
        ]
    )
    # Volume +10%, Preco SKU1 +10%, Mix deslocado para SKU2 (maior margem unitaria)
    cur_df = pd.DataFrame(
        [
            {
                "product_id": "SKU1",
                "units": 90.0,
                "gross_revenue": 990.0,
                "net_keep_revenue": 780.0,
                "contribution_margin": 295.0,
            },
            {
                "product_id": "SKU2",
                "units": 130.0,
                "gross_revenue": 2600.0,
                "net_keep_revenue": 2050.0,
                "contribution_margin": 640.0,
            },
        ]
    )
    bridge = compute_pvm_bridge_steps(prev_df, cur_df)
    assert list(bridge["step_key"]) == ["mc_base", "volume", "price", "mix", "disc_cost", "mc_final"]

    mc0 = float(bridge.loc[bridge["step_key"] == "mc_base", "amount"].iloc[0])
    mc1 = float(bridge.loc[bridge["step_key"] == "mc_final", "amount"].iloc[0])
    effects_sum = float(bridge.loc[bridge["measure"] == "relative", "amount"].sum())
    assert mc0 == pytest.approx(800.0, abs=1e-2)
    assert mc1 == pytest.approx(935.0, abs=1e-2)
    assert (mc0 + effects_sum) == pytest.approx(mc1, abs=1e-2)

    # Efeito Volume positivo (+20 un * 4.00 = +80.00) e Efeito Mix positivo (mais SKU2 de 5.00/un)
    vol = float(bridge.loc[bridge["step_key"] == "volume", "amount"].iloc[0])
    mix = float(bridge.loc[bridge["step_key"] == "mix", "amount"].iloc[0])
    price = float(bridge.loc[bridge["step_key"] == "price", "amount"].iloc[0])
    assert vol == pytest.approx(80.0, abs=1e-2)
    assert mix > 0.0
    assert price > 0.0


def test_build_pvm_bridge_duckdb_yoy_pop_and_empty_all_pop(repo: DuckDBRepository) -> None:
    """Valida Bridge PVM real em all+yoy, mes explicito e DataFrame vazio em all+pop."""
    assert build_pvm_bridge(repo, "c1_toys", comparison_mode="pop").empty

    exec_yoy = build_executive_dashboard(repo, "c1_toys", comparison_mode="yoy")
    bridge = exec_yoy.pvm_bridge_df
    assert len(bridge) == 6
    mc0 = float(bridge.loc[bridge["step_key"] == "mc_base", "amount"].iloc[0])
    mc1 = float(bridge.loc[bridge["step_key"] == "mc_final", "amount"].iloc[0])
    effects = float(bridge.loc[bridge["measure"] == "relative", "amount"].sum())
    assert abs((mc0 + effects) - mc1) < 1e-2

    # Janela explicita (Dez/2024 vs Nov/2024)
    m_bridge = build_pvm_bridge(
        repo,
        "c1_toys",
        start_date_key=20241201,
        end_date_key=20241231,
        comp_start_date_key=20241101,
        comp_end_date_key=20241130,
        comparison_mode="pop",
    )
    assert len(m_bridge) == 6
    m0 = float(m_bridge.loc[m_bridge["step_key"] == "mc_base", "amount"].iloc[0])
    m1 = float(m_bridge.loc[m_bridge["step_key"] == "mc_final", "amount"].iloc[0])
    m_eff = float(m_bridge.loc[m_bridge["measure"] == "relative", "amount"].sum())
    assert abs((m0 + m_eff) - m1) < 1e-2
