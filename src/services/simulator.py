from __future__ import annotations

from typing import Final

import numpy as np
import pandas as pd

from src.core.logging import get_logger
from src.core.types import ScenarioId
from src.db.repository import DataRepository
from src.services.dto import (
    ExecutiveKpisDTO,
    SimulationBaseline,
    SimulationLevers,
    SimulationResult,
)

logger = get_logger(__name__)

PROFIT_CURVE_DELTAS: Final[np.ndarray] = np.round(np.linspace(-0.25, 0.25, 41), 4)


def _evaluate_waterfall_arrays(
    baseline: SimulationBaseline,
    *,
    delta_price_pct: np.ndarray,
    delta_discount_pp: np.ndarray,
    delta_commission_pp: np.ndarray,
    delta_cogs_pct: np.ndarray,
    apply_elasticity: bool,
    beta: float,
    volume_override: np.ndarray | None = None,
) -> dict[str, np.ndarray]:
    """Avalia vetorizadamente o Waterfall completo de margem para arrays de alavancas."""
    r_p = np.maximum(1.0 + delta_price_pct, 0.05)
    d_1 = np.clip(baseline.discount_rate_0 + delta_discount_pp, 0.0, 0.50)
    c_1 = np.clip(baseline.commission_rate_0 + delta_commission_pp, 0.0, 0.25)

    denom = max(1.0 - baseline.discount_rate_0, 0.01)
    net_price_ratio = np.maximum(r_p * (1.0 - d_1) / denom, 0.05)

    if volume_override is not None:
        q_ratio = np.maximum(volume_override, 0.01)
    elif apply_elasticity:
        q_ratio = np.maximum(np.power(net_price_ratio, beta), 0.01)
    else:
        q_ratio = np.ones_like(r_p, dtype=np.float64)

    gross_1 = baseline.gross_revenue_0 * q_ratio * r_p
    disc_1 = gross_1 * d_1
    net_price_rev_1 = gross_1 - disc_1
    tax_1 = net_price_rev_1 * baseline.tax_rate_eff
    net_rev_1 = net_price_rev_1 - tax_1
    cogs_1 = baseline.cogs_0 * q_ratio * (1.0 + delta_cogs_pct)
    comm_1 = net_price_rev_1 * c_1
    freight_1 = baseline.freight_0 * q_ratio
    margin_1 = net_rev_1 - cogs_1 - comm_1 - freight_1

    return {
        "q_ratio": q_ratio,
        "net_price_ratio": net_price_ratio,
        "d_1": d_1,
        "c_1": c_1,
        "gross_1": gross_1,
        "disc_1": disc_1,
        "net_price_rev_1": net_price_rev_1,
        "tax_1": tax_1,
        "net_rev_1": net_rev_1,
        "cogs_1": cogs_1,
        "comm_1": comm_1,
        "freight_1": freight_1,
        "margin_1": margin_1,
    }


def _compute_profit_curve(
    baseline: SimulationBaseline,
    levers: SimulationLevers,
    *,
    beta: float,
) -> tuple[pd.DataFrame, float, float]:
    """Avalia a curva Lucro x Preço em 41 pontos [-25%, +25%] e identifica o ótimo."""
    n_pts = len(PROFIT_CURVE_DELTAS)
    res = _evaluate_waterfall_arrays(
        baseline,
        delta_price_pct=PROFIT_CURVE_DELTAS,
        delta_discount_pp=np.full(n_pts, levers.delta_discount_pp, dtype=np.float64),
        delta_commission_pp=np.full(n_pts, levers.delta_commission_pp, dtype=np.float64),
        delta_cogs_pct=np.full(n_pts, levers.delta_cogs_pct, dtype=np.float64),
        apply_elasticity=levers.apply_elasticity,
        beta=beta,
    )
    gross = res["gross_1"]
    margin = res["margin_1"]
    margin_pct = np.where(gross > 0.0, (margin / gross) * 100.0, 0.0)

    curve_df = pd.DataFrame(
        {
            "delta_price_pct": PROFIT_CURVE_DELTAS,
            "price_change_label_pct": np.round(PROFIT_CURVE_DELTAS * 100.0, 2),
            "volume_ratio": np.round(res["q_ratio"], 4),
            "gross_revenue": np.round(gross, 2),
            "contribution_margin": np.round(margin, 2),
            "margin_pct": np.round(margin_pct, 2),
        }
    )
    best_idx = int(np.argmax(margin))
    return (
        curve_df,
        float(PROFIT_CURVE_DELTAS[best_idx]),
        round(float(margin[best_idx]), 2),
    )


def _compute_tornado_sensitivity(
    baseline: SimulationBaseline,
    *,
    margin_0: float,
    apply_elasticity: bool,
    beta: float,
) -> pd.DataFrame:
    """Calcula impacto individual (±) na margem de contribuição para os 5 drivers do Tornado."""
    dp = np.array([-0.05, 0.05, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float64)
    dd = np.array([0.0, 0.0, -0.02, 0.02, 0.0, 0.0, 0.0, 0.0], dtype=np.float64)
    dcogs = np.array([0.0, 0.0, 0.0, 0.0, -0.05, 0.05, 0.0, 0.0], dtype=np.float64)
    dcomm = np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -0.01, 0.01], dtype=np.float64)

    res = _evaluate_waterfall_arrays(
        baseline,
        delta_price_pct=dp,
        delta_discount_pp=dd,
        delta_commission_pp=dcomm,
        delta_cogs_pct=dcogs,
        apply_elasticity=apply_elasticity,
        beta=beta,
    )
    deltas = res["margin_1"] - margin_0

    vol_res = _evaluate_waterfall_arrays(
        baseline,
        delta_price_pct=np.zeros(2, dtype=np.float64),
        delta_discount_pp=np.zeros(2, dtype=np.float64),
        delta_commission_pp=np.zeros(2, dtype=np.float64),
        delta_cogs_pct=np.zeros(2, dtype=np.float64),
        apply_elasticity=False,
        beta=beta,
        volume_override=np.array([0.95, 1.05], dtype=np.float64),
    )
    vol_deltas = vol_res["margin_1"] - margin_0

    rows = [
        {"driver": "Preço (±5%)", "low_delta_brl": float(deltas[0]), "high_delta_brl": float(deltas[1])},
        {
            "driver": "Desconto (±2 p.p.)",
            "low_delta_brl": float(deltas[2]),
            "high_delta_brl": float(deltas[3]),
        },
        {
            "driver": "Custo / CMV (±5%)",
            "low_delta_brl": float(deltas[4]),
            "high_delta_brl": float(deltas[5]),
        },
        {
            "driver": "Comissão (±1 p.p.)",
            "low_delta_brl": float(deltas[6]),
            "high_delta_brl": float(deltas[7]),
        },
        {
            "driver": "Volume (±5%)",
            "low_delta_brl": float(vol_deltas[0]),
            "high_delta_brl": float(vol_deltas[1]),
        },
    ]
    tornado_df = pd.DataFrame(rows)
    tornado_df["low_delta_brl"] = tornado_df["low_delta_brl"].round(2)
    tornado_df["high_delta_brl"] = tornado_df["high_delta_brl"].round(2)
    tornado_df["swing_brl"] = (tornado_df["high_delta_brl"] - tornado_df["low_delta_brl"]).abs().round(2)
    return tornado_df.sort_values("swing_brl", ascending=False).reset_index(drop=True)


def simulate(
    baseline: SimulationBaseline,
    levers: SimulationLevers,
) -> SimulationResult:
    """Executa simulação What-If pura com Waterfall, Breakeven, Curva Lucro x Preço e Tornado."""
    beta = (
        float(levers.beta_override) if levers.beta_override is not None else float(baseline.beta_elasticity)
    )

    base_arr = _evaluate_waterfall_arrays(
        baseline,
        delta_price_pct=np.array([0.0]),
        delta_discount_pp=np.array([0.0]),
        delta_commission_pp=np.array([0.0]),
        delta_cogs_pct=np.array([0.0]),
        apply_elasticity=False,
        beta=beta,
    )
    sim_arr = _evaluate_waterfall_arrays(
        baseline,
        delta_price_pct=np.array([levers.delta_price_pct]),
        delta_discount_pp=np.array([levers.delta_discount_pp]),
        delta_commission_pp=np.array([levers.delta_commission_pp]),
        delta_cogs_pct=np.array([levers.delta_cogs_pct]),
        apply_elasticity=levers.apply_elasticity,
        beta=beta,
    )

    gross_0 = float(base_arr["gross_1"][0])
    gross_1 = float(sim_arr["gross_1"][0])
    margin_0 = float(base_arr["margin_1"][0])
    margin_1 = float(sim_arr["margin_1"][0])
    q_ratio = float(sim_arr["q_ratio"][0])
    units_1 = float(baseline.units_0 * q_ratio)
    unit_margin_1 = margin_1 / units_1 if units_1 > 0.0 else 0.0
    margin_delta = margin_1 - margin_0

    if gross_0 <= 0.0:
        breakeven_pct: float | None = None
        verdict = "Sem Receita Baseline"
    elif unit_margin_1 <= 0.0:
        breakeven_pct = None
        verdict = "Destruição de Margem Unitária Negativa"
    else:
        breakeven_pct = round(((margin_0 / (unit_margin_1 * baseline.units_0)) - 1.0) * 100.0, 2)
        if abs(margin_delta) < 1e-4:
            verdict = "Neutro (Baseline)"
        elif margin_delta > 0.0:
            verdict = "Ganho de Margem Projetado"
        else:
            verdict = "Erosão de Margem Projetada"

    curve_df, opt_dp, opt_margin = _compute_profit_curve(baseline, levers, beta=beta)
    tornado_df = _compute_tornado_sensitivity(
        baseline,
        margin_0=margin_0,
        apply_elasticity=levers.apply_elasticity,
        beta=beta,
    )

    return SimulationResult(
        units_0=baseline.units_0,
        units_1=round(units_1, 2),
        volume_ratio=round(q_ratio, 6),
        projected_volume_change_pct=round((q_ratio - 1.0) * 100.0, 2),
        net_price_ratio=round(float(sim_arr["net_price_ratio"][0]), 6),
        effective_discount_rate=round(float(sim_arr["d_1"][0]), 6),
        effective_commission_rate=round(float(sim_arr["c_1"][0]), 6),
        gross_revenue_0=round(gross_0, 2),
        gross_revenue_1=round(gross_1, 2),
        discount_amount_0=round(float(base_arr["disc_1"][0]), 2),
        discount_amount_1=round(float(sim_arr["disc_1"][0]), 2),
        net_price_revenue_0=round(float(base_arr["net_price_rev_1"][0]), 2),
        net_price_revenue_1=round(float(sim_arr["net_price_rev_1"][0]), 2),
        tax_amount_0=round(float(base_arr["tax_1"][0]), 2),
        tax_amount_1=round(float(sim_arr["tax_1"][0]), 2),
        net_revenue_0=round(float(base_arr["net_rev_1"][0]), 2),
        net_revenue_1=round(float(sim_arr["net_rev_1"][0]), 2),
        cogs_0=round(float(base_arr["cogs_1"][0]), 2),
        cogs_1=round(float(sim_arr["cogs_1"][0]), 2),
        commission_amount_0=round(float(base_arr["comm_1"][0]), 2),
        commission_amount_1=round(float(sim_arr["comm_1"][0]), 2),
        freight_0=round(float(base_arr["freight_1"][0]), 2),
        freight_1=round(float(sim_arr["freight_1"][0]), 2),
        contribution_margin_0=round(margin_0, 2),
        contribution_margin_1=round(margin_1, 2),
        margin_pct_0=round((margin_0 / gross_0 * 100.0), 2) if gross_0 > 0.0 else 0.0,
        margin_pct_1=round((margin_1 / gross_1 * 100.0), 2) if gross_1 > 0.0 else 0.0,
        margin_delta_brl=round(margin_delta, 2),
        revenue_delta_brl=round(gross_1 - gross_0, 2),
        unit_margin_1=round(unit_margin_1, 4),
        breakeven_volume_change_pct=breakeven_pct,
        verdict=verdict,
        optimal_price_change_pct=opt_dp,
        optimal_margin_brl=opt_margin,
        profit_curve_df=curve_df,
        tornado_df=tornado_df,
    )


def simulate_quick_what_if(
    kpis: ExecutiveKpisDTO,
    *,
    price_change_pct: float = 0.0,
    discount_change_pp: float = 0.0,
    commission_or_cost_change_pct: float = 0.0,
    elasticity: float = -1.2,
) -> dict[str, float]:
    """Simula rapidamente o impacto de 3 alavancas no lucro líquido e calcula breakeven.

    Alavancas:
      - price_change_pct: variação percentual na tabela de preços (% delta).
      - discount_change_pp: variação em pontos percentuais no desconto médio.
      - commission_or_cost_change_pct: variação percentual no custo da mercadoria (COGS).
    """
    gross_0 = kpis.gross_revenue
    if gross_0 <= 0 or (
        price_change_pct == 0.0 and discount_change_pp == 0.0 and commission_or_cost_change_pct == 0.0
    ):
        return {
            "simulated_revenue_brl": round(gross_0, 2),
            "simulated_margin_brl": round(kpis.contribution_margin, 2),
            "simulated_margin_pct": round(kpis.contribution_margin / gross_0 * 100.0, 2)
            if gross_0 > 0
            else 0.0,
            "margin_delta_brl": 0.0,
            "breakeven_volume_pct": 0.0,
            "estimated_volume_pct": 0.0,
        }

    disc_0 = kpis.discount_amount / gross_0 if gross_0 > 0 else 0.0
    disc_1 = min(max(disc_0 + discount_change_pp / 100.0, 0.0), 0.50)
    price_factor = 1.0 + price_change_pct / 100.0
    net_price_ratio = max(price_factor * (1.0 - disc_1) / max(1.0 - disc_0, 0.01), 0.05)

    vol_factor = max(net_price_ratio**elasticity, 0.05)
    estimated_vol_pct = round((vol_factor - 1.0) * 100.0, 1)

    gross_1 = gross_0 * vol_factor * price_factor
    net_price_rev_1 = gross_1 * (1.0 - disc_1)
    tax_rate = kpis.tax_amount / kpis.net_price_revenue if kpis.net_price_revenue > 0 else 0.174
    net_rev_1 = net_price_rev_1 * (1.0 - tax_rate)

    cogs_factor = 1.0 + commission_or_cost_change_pct / 100.0
    cogs_1 = kpis.cogs * vol_factor * cogs_factor
    comm_rate = kpis.commission_amount / kpis.net_price_revenue if kpis.net_price_revenue > 0 else 0.05
    comm_1 = net_price_rev_1 * comm_rate
    freight_1 = kpis.freight_amount * vol_factor

    margin_1 = net_rev_1 - cogs_1 - comm_1 - freight_1
    margin_pct_1 = round(margin_1 / gross_1 * 100.0, 2) if gross_1 > 0 else 0.0
    margin_delta = round(margin_1 - kpis.contribution_margin, 2)

    margin_at_base_vol = margin_1 / vol_factor
    breakeven_vol = (
        round(((kpis.contribution_margin / margin_at_base_vol) - 1.0) * 100.0, 1)
        if (margin_at_base_vol > 0 and kpis.contribution_margin > 0)
        else 999.0
    )

    return {
        "simulated_revenue_brl": round(gross_1, 2),
        "simulated_margin_brl": round(margin_1, 2),
        "simulated_margin_pct": margin_pct_1,
        "margin_delta_brl": margin_delta,
        "breakeven_volume_pct": breakeven_vol,
        "estimated_volume_pct": estimated_vol_pct,
    }


def query_family_elasticity(repo: DataRepository, scenario_id: ScenarioId) -> pd.DataFrame:
    """Consulta elasticidade-preço real por família em `gold.mart_price_elasticity`."""
    sql = """
    SELECT
        family,
        beta_hat,
        ci_95_low,
        ci_95_high,
        optimal_price_change_pct,
        elasticity_classification,
        prescription_text
    FROM gold.mart_price_elasticity
    WHERE scenario_id = ?
    ORDER BY family ASC
    """
    try:
        return repo.query(sql, params=[scenario_id])
    except Exception as exc:
        logger.warning("mart_price_elasticity indisponível para %s: %s", scenario_id, exc)
        return pd.DataFrame()
