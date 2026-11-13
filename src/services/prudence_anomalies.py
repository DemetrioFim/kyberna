from __future__ import annotations

from typing import Any

import pandas as pd

from src.core.logging import get_logger
from src.core.types import ScenarioId
from src.db.repository import DataRepository

logger = get_logger(__name__)


def query_prudence_anomalies(
    repo: DataRepository,
    *,
    where_sql: str,
    params: list[Any],
    joins: list[str],
    scenario_id: ScenarioId = "c1_toys",
) -> pd.DataFrame:
    """Detecta anomalias críticas e desvios operacionais para o Radar de Prudência."""
    anomalies: list[dict[str, Any]] = []

    joins_f = list(joins)
    if "JOIN gold.dim_product p ON f.product_id = p.product_id" not in joins_f:
        joins_f.append("JOIN gold.dim_product p ON f.product_id = p.product_id")
    sql_fam = f"""
    SELECT p.family, SUM(f.gross_revenue) AS gross,
           ROUND(SUM(f.discount_amount) / NULLIF(SUM(f.gross_revenue), 0) * 100.0, 1) AS disc_pct
    FROM gold.fact_sales f
    {" ".join(joins_f)}
    {where_sql}
    GROUP BY p.family HAVING SUM(f.gross_revenue) > 20000 ORDER BY disc_pct DESC LIMIT 1
    """
    try:
        df_fam = repo.query(sql_fam, params)
        if not df_fam.empty:
            row_f = df_fam.iloc[0]
            fam_name, disc, gross = str(row_f["family"]), float(row_f["disc_pct"]), float(row_f["gross"])
            anomalies.append(
                {
                    "severity": "Alta" if disc > 8.0 else "Média",
                    "category": "Erosão de Margem",
                    "title": f"Desconto médio de {disc:.1f}% na linha {fam_name}",
                    "impact_brl": round(gross * max(disc - 5.0, 1.0) / 100.0, 2),
                    "recommendation": (
                        f"Revisar política comercial da família {fam_name} para estancar sangria."
                    ),
                }
            )
    except Exception as exc:
        logger.debug("Falha ao calcular anomalia de família: %s", exc)

    joins_r = list(joins)
    if "JOIN gold.dim_sales_rep r ON f.sales_rep_id = r.sales_rep_id" not in joins_r:
        joins_r.append("JOIN gold.dim_sales_rep r ON f.sales_rep_id = r.sales_rep_id")
    sql_rep = f"""
    SELECT r.name, SUM(f.gross_revenue) AS gross,
           ROUND(SUM(f.discount_amount) / NULLIF(SUM(f.gross_revenue), 0) * 100.0, 1) AS disc_pct
    FROM gold.fact_sales f
    {" ".join(joins_r)}
    {where_sql}
    GROUP BY r.name HAVING SUM(f.gross_revenue) > 10000 ORDER BY disc_pct DESC LIMIT 1
    """
    try:
        df_rep = repo.query(sql_rep, params)
        if not df_rep.empty:
            row_r = df_rep.iloc[0]
            rep_name, disc_r, gross_r = str(row_r["name"]), float(row_r["disc_pct"]), float(row_r["gross"])
            anomalies.append(
                {
                    "severity": "Média",
                    "category": "Política de Desconto",
                    "title": f"RCA {rep_name} operando com {disc_r:.1f}% de desconto médio",
                    "impact_brl": round(gross_r * max(disc_r - 6.0, 1.0) / 100.0, 2),
                    "recommendation": (
                        f"Auditar pedidos concedidos por {rep_name} e aplicar teto de tabela."
                    ),
                }
            )
    except Exception as exc:
        logger.debug("Falha ao calcular anomalia de RCA: %s", exc)

    try:
        sql_risk = """
        SELECT COUNT(*) AS cnt, ROUND(COALESCE(SUM(annual_revenue_at_risk), 0), 2) AS at_risk_brl
        FROM gold.mart_customer_risk
        WHERE scenario_id = ? AND risk_status IN ('Em Risco Imediato', 'Adormecido / Perdido')
        """
        df_risk = repo.query(sql_risk, params=[scenario_id])
        if not df_risk.empty and int(df_risk.iloc[0]["cnt"]) > 0:
            cnt, risk_brl = int(df_risk.iloc[0]["cnt"]), float(df_risk.iloc[0]["at_risk_brl"])
            anomalies.append(
                {
                    "severity": "Crítica",
                    "category": "Retenção / Churn",
                    "title": f"{cnt} lojistas ultrapassaram a janela ideal de recompra",
                    "impact_brl": risk_brl,
                    "recommendation": "Disparar plano de abordagem no WhatsApp antes do encerramento do mês.",
                }
            )
    except Exception as exc:
        logger.debug("Falha ao calcular anomalia de churn: %s", exc)

    if not anomalies:
        anomalies.append(
            {
                "severity": "Baixa",
                "category": "Direção Operacional",
                "title": "Nenhum desvio crítico detectado no período selecionado",
                "impact_brl": 0.0,
                "recommendation": "Manter monitoramento semanal de margem e volume de recompra.",
            }
        )

    return pd.DataFrame(anomalies)
