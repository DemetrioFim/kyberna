from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

import duckdb

from src.core.paths import get_data_dir
from src.core.types import ScenarioId


def collect_model_metrics(con: duckdb.DuckDBPyConnection, scenario_id: ScenarioId) -> dict[str, Any]:
    """Coleta contagens e métricas resumidas dos marts analíticos e modelos de ML no DuckDB."""
    metrics: dict[str, Any] = {}
    queries: dict[str, str] = {
        "abc_xyz_skus": f"SELECT COUNT(*) FROM gold.mart_abc_xyz WHERE scenario_id = '{scenario_id}'",
        "rfm_customers": f"SELECT COUNT(*) FROM gold.mart_rfm WHERE scenario_id = '{scenario_id}'",
        "churn_at_risk_customers": (
            "SELECT COUNT(*) FROM gold.mart_customer_risk "
            f"WHERE scenario_id = '{scenario_id}' AND risk_status != 'No Ciclo'"
        ),
        "forecast_skus": (
            "SELECT COUNT(DISTINCT product_id) FROM gold.mart_forecast_30d "
            f"WHERE scenario_id = '{scenario_id}'"
        ),
        "forecast_avg_wape_pct": (
            "SELECT ROUND(AVG(family_wape_pct), 2) FROM gold.mart_forecast_30d "
            f"WHERE scenario_id = '{scenario_id}' AND record_type = 'forecast'"
        ),
        "inventory_rupture_skus": (
            "SELECT COUNT(*) FROM gold.mart_inventory_position "
            f"WHERE scenario_id = '{scenario_id}' AND stock_status = 'Ruptura Iminente'"
        ),
        "elasticity_families": (
            f"SELECT COUNT(*) FROM gold.mart_price_elasticity WHERE scenario_id = '{scenario_id}'"
        ),
    }
    for key, sql in queries.items():
        try:
            row = con.execute(sql).fetchone()
            val = row[0] if row else None
            if key == "forecast_avg_wape_pct":
                metrics[key] = float(val) if val is not None else 0.0
            else:
                metrics[key] = int(val) if val is not None else 0
        except Exception:
            metrics[key] = 0.0 if key == "forecast_avg_wape_pct" else 0
    return metrics


def _summarize_step_details(step_name: str, info: dict[str, Any]) -> str:
    """Resume em uma linha as contagens de uma etapa para a tabela Markdown."""
    if info.get("status") == "skipped":
        return f"Pulado ({info.get('reason', 'configurado')})"
    summaries: dict[str, str] = {
        "ingest": f"{info.get('partitions', 0)} partições ({info.get('range', '-')})",
        "bronze": f"{info.get('rows', 0):,} linhas",
        "silver": f"{info.get('rows', 0):,} linhas (removidas: {info.get('removed', 0):,})",
        "price_events": (
            f"{info.get('affected_rows', 0):,}/{info.get('total_rows', 0):,} linhas "
            f"({info.get('affected_fraction', 0.0):.1%})"
        ),
    }
    if step_name in summaries:
        return summaries[step_name]
    if step_name in ("gold_star", "inventory_snapshot", "gold_marts", "audit"):
        return f"Cenários: {', '.join(info.get('scenarios', []))}"
    return "-"


def format_quality_markdown(report: dict[str, Any]) -> str:
    """Formata o relatório consolidado de qualidade do pipeline em Markdown."""
    lines: list[str] = [
        f"# Relatório de Qualidade do Pipeline — {report['report_date']}",
        "",
        f"- **Executado em:** `{report['executed_at']}`",
        (
            f"- **Modo:** `{report['mode']}` | **Lake:** `{report['lake']}` "
            f"| **Duração Total:** `{report['total_duration_s']:.2f} s`"
        ),
        f"- **Etapas Executadas:** `{', '.join(report['executed_steps'])}`",
        "",
        "## 1. Execução por Etapa",
        "",
        "| Etapa | Status | Duração (s) | Detalhes |",
        "| --- | --- | ---: | --- |",
    ]
    for step_name, info in report["steps"].items():
        details = _summarize_step_details(step_name, info)
        lines.append(f"| `{step_name}` | `{info['status']}` | {info['duration_s']:.2f} | {details} |")

    lines.extend(["", "## 2. Métricas Analíticas e Modelos por Cenário", ""])
    for scn, scn_data in report["scenarios"].items():
        lines.append(f"### Cenário `{scn}`")
        lines.append("")
        lines.append("| Indicador | Valor |")
        lines.append("| --- | ---: |")
        star = scn_data.get("star_schema", {})
        if star:
            lines.append(f"| `fact_sales` (linhas) | {star.get('fact_sales', 0):,} |")
            lines.append(f"| `dim_product` (SKUs) | {star.get('dim_product', 0):,} |")
            lines.append(f"| `dim_customer` (clientes) | {star.get('dim_customer', 0):,} |")
        if "inventory_snapshot_rows" in scn_data:
            lines.append(f"| `inventory_snapshot` (SKUs) | {scn_data['inventory_snapshot_rows']:,} |")
        model_m = scn_data.get("model_metrics", {})
        if model_m:
            lines.append(f"| SKUs ABC/XYZ | {model_m.get('abc_xyz_skus', 0):,} |")
            lines.append(f"| Clientes RFM | {model_m.get('rfm_customers', 0):,} |")
            lines.append(f"| Clientes em Risco (Churn) | {model_m.get('churn_at_risk_customers', 0):,} |")
            lines.append(f"| SKUs Forecast 30d | {model_m.get('forecast_skus', 0):,} |")
            lines.append(f"| WAPE Médio Forecast (%) | {model_m.get('forecast_avg_wape_pct', 0.0):.2f}% |")
            lines.append(f"| SKUs em Ruptura Iminente | {model_m.get('inventory_rupture_skus', 0):,} |")
            lines.append(f"| Famílias Elasticidade | {model_m.get('elasticity_families', 0):,} |")
        if "audit_excel_path" in scn_data:
            lines.append(f"| Planilha Auditoria | `{Path(scn_data['audit_excel_path']).name}` |")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def write_quality_reports(
    report: dict[str, Any],
    *,
    base_dir: Path | None = None,
    report_date: datetime.date | None = None,
) -> tuple[Path, Path]:
    """Persiste os relatórios `quality_<YYYYMMDD>.json` e `.md` em `data/reports/`."""
    eff_date = report_date or datetime.date.today()
    stamp = eff_date.strftime("%Y%m%d")
    reports_dir = get_data_dir(base_dir) / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    json_path = reports_dir / f"quality_{stamp}.json"
    md_path = reports_dir / f"quality_{stamp}.md"

    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    md_path.write_text(format_quality_markdown(report), encoding="utf-8")
    return json_path, md_path
