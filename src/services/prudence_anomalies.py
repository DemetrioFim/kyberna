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
    """Detecta anomalias 100% operacionais e de Supply para o Radar de 1. Prudência."""
    del where_sql, params, joins
    anomalies: list[dict[str, Any]] = []

    try:
        sql_rup = """
        SELECT
            COUNT(*) AS cnt,
            ROUND(COALESCE(SUM(protected_revenue_brl), 0.0), 2) AS rev_brl,
            COALESCE(SUM(suggested_order_boxes), 0)::INTEGER AS boxes_cnt
        FROM gold.mart_inventory_position
        WHERE scenario_id = ? AND abc_class = 'A' AND stock_status = 'Ruptura Iminente'
        """
        df_rup = repo.query(sql_rup, params=[scenario_id])
        if not df_rup.empty and int(df_rup.iloc[0]["cnt"]) > 0:
            cnt = int(df_rup.iloc[0]["cnt"])
            rev_brl = float(df_rup.iloc[0]["rev_brl"])
            boxes = int(df_rup.iloc[0]["boxes_cnt"])
            anomalies.append(
                {
                    "severity": "Crítica",
                    "category": "Ruptura Curva A",
                    "title": f"{cnt} SKUs Curva A abaixo do Ponto de Pedido (ROP)",
                    "impact_brl": rev_brl,
                    "recommendation": (
                        f"Emitir ordem imediata de {boxes:,} caixas master para proteger "
                        "faturamento dos itens essenciais."
                    ).replace(",", "."),
                }
            )
    except Exception as exc:
        logger.debug("Falha ao calcular anomalia de ruptura Curva A: %s", exc)

    try:
        sql_lock = """
        SELECT
            COUNT(*) AS cnt,
            ROUND(COALESCE(SUM(locked_capital_brl), 0.0), 2) AS lock_brl
        FROM gold.mart_inventory_position
        WHERE scenario_id = ? AND stock_status = 'Capital Travado'
        """
        df_lock = repo.query(sql_lock, params=[scenario_id])
        if not df_lock.empty and int(df_lock.iloc[0]["cnt"]) > 0:
            cnt = int(df_lock.iloc[0]["cnt"])
            lock_brl = float(df_lock.iloc[0]["lock_brl"])
            anomalies.append(
                {
                    "severity": "Alta",
                    "category": "Capital Imobilizado",
                    "title": f"{cnt} SKUs acumulam cobertura superior a 120 dias",
                    "impact_brl": lock_brl,
                    "recommendation": (
                        "Executar campanha de giro e conversão da cauda CZ para venda sob encomenda."
                    ),
                }
            )
    except Exception as exc:
        logger.debug("Falha ao calcular anomalia de capital travado: %s", exc)

    try:
        sql_sop = """
        SELECT
            pos.family,
            ROUND(AVG(fc.family_wape_pct), 1) AS wape_pct,
            ROUND(COALESCE(SUM(pos.protected_revenue_brl), 0.0), 2) AS prot_brl
        FROM gold.mart_inventory_position pos
        JOIN (
            SELECT DISTINCT family, family_wape_pct
            FROM gold.mart_forecast_30d
            WHERE scenario_id = ?
        ) fc ON pos.family = fc.family
        WHERE pos.scenario_id = ?
        GROUP BY pos.family
        ORDER BY wape_pct DESC, prot_brl DESC
        LIMIT 1
        """
        df_sop = repo.query(sql_sop, params=[scenario_id, scenario_id])
        if not df_sop.empty:
            fam = str(df_sop.iloc[0]["family"])
            wape = float(df_sop.iloc[0]["wape_pct"])
            prot_brl = float(df_sop.iloc[0]["prot_brl"])
            anomalies.append(
                {
                    "severity": "Média",
                    "category": "Atenção S&OP / Forecast",
                    "title": f"Maior volatilidade preditiva em {fam} (WAPE {wape:.1f}%)",
                    "impact_brl": prot_brl,
                    "recommendation": (
                        f"Reforçar estoque de segurança e revisar lead time de reposição em {fam}."
                    ),
                }
            )
    except Exception as exc:
        logger.debug("Falha ao calcular anomalia de S&OP/WAPE: %s", exc)

    if not anomalies:
        anomalies.append(
            {
                "severity": "Baixa",
                "category": "Operações & Supply",
                "title": "Níveis de estoque e cobertura dentro dos parâmetros operacionais",
                "impact_brl": 0.0,
                "recommendation": "Manter rotina semanal de revisão de ROP e giro ABC/XYZ.",
            }
        )

    severity_order = {"Crítica": 0, "Alta": 1, "Média": 2, "Baixa": 3}
    anomalies.sort(
        key=lambda item: (
            severity_order.get(str(item.get("severity", "Baixa")), 9),
            -float(item.get("impact_brl", 0.0)),
        )
    )
    return pd.DataFrame(anomalies)
