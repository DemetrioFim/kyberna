from __future__ import annotations

import pandas as pd

from src.services.dto import ExecutiveKpisDTO


def _calc_pct(val: float, total: float) -> float:
    """Calcula percentual arredondado com guarda contra divisão por zero."""
    return round(val / total * 100.0, 1) if total > 0 else 0.0


def build_waterfall_steps(kpis: ExecutiveKpisDTO) -> pd.DataFrame:
    """Gera o DataFrame de etapas contábeis para alimentação do gráfico Waterfall."""
    gross = kpis.gross_revenue
    steps: list[dict[str, object]] = [
        {
            "step_key": "gross_revenue",
            "label": "Faturamento Bruto",
            "amount": gross,
            "pct_of_gross": 100.0 if gross > 0 else 0.0,
            "measure": "absolute",
        },
        {
            "step_key": "discount",
            "label": "(-) Descontos Concedidos",
            "amount": -kpis.discount_amount,
            "pct_of_gross": _calc_pct(kpis.discount_amount, gross),
            "measure": "relative",
        },
        {
            "step_key": "net_price_revenue",
            "label": "(=) Receita Faturada",
            "amount": kpis.net_price_revenue,
            "pct_of_gross": _calc_pct(kpis.net_price_revenue, gross),
            "measure": "total",
        },
        {
            "step_key": "taxes",
            "label": "(-) Impostos (ICMS/PIS/COFINS)",
            "amount": -kpis.tax_amount,
            "pct_of_gross": _calc_pct(kpis.tax_amount, gross),
            "measure": "relative",
        },
        {
            "step_key": "net_revenue",
            "label": "(=) Receita Líquida",
            "amount": kpis.net_revenue,
            "pct_of_gross": _calc_pct(kpis.net_revenue, gross),
            "measure": "total",
        },
        {
            "step_key": "cogs",
            "label": "(-) Custo Mercadoria (CPV)",
            "amount": -kpis.cogs,
            "pct_of_gross": _calc_pct(kpis.cogs, gross),
            "measure": "relative",
        },
        {
            "step_key": "commission",
            "label": "(-) Comissões Comerciais",
            "amount": -kpis.commission_amount,
            "pct_of_gross": _calc_pct(kpis.commission_amount, gross),
            "measure": "relative",
        },
        {
            "step_key": "freight",
            "label": "(-) Frete de Entrega CIF",
            "amount": -kpis.freight_amount,
            "pct_of_gross": _calc_pct(kpis.freight_amount, gross),
            "measure": "relative",
        },
        {
            "step_key": "contribution_margin",
            "label": "(=) Margem de Contribuição",
            "amount": kpis.contribution_margin,
            "pct_of_gross": _calc_pct(kpis.contribution_margin, gross),
            "measure": "total",
        },
    ]
    return pd.DataFrame(steps)
