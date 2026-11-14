from __future__ import annotations

import datetime
import time
from pathlib import Path
from typing import Any, Final, Literal

import duckdb
import yaml

from src.core.logging import get_logger, timed_step
from src.core.paths import config_path, get_data_dir, get_duckdb_path, get_project_root
from src.core.scenarios import list_scenario_configs, load_scenario_config
from src.core.settings import get_settings
from src.core.types import ScenarioId
from src.etl.audit import generate_audit_report
from src.etl.gold.inventory_snapshot import build_inventory_snapshot
from src.etl.gold.marts import build_gold_marts
from src.etl.gold.star_schema import build_gold_star_schema
from src.etl.ingest.fixture import generate_fixture
from src.etl.ingest.raw_to_bronze import convert_all_raw_to_bronze, populate_bronze_from_sample_fixture
from src.etl.ingest.socrata_client import SocrataClient
from src.etl.lake import get_duckdb_connection
from src.etl.pipeline_reports import collect_model_metrics, write_quality_reports
from src.etl.scenarios.c1_toys import C1ToysScenarioBuilder
from src.etl.silver.clean import build_silver_sales
from src.etl.silver.enrich import enrich_silver_dimensions
from src.etl.silver.price_events import apply_price_events
from src.etl.silver.time_anchor import apply_time_anchor

logger = get_logger(__name__)

PIPELINE_STEPS: Final[tuple[str, ...]] = (
    "ingest",
    "bronze",
    "silver",
    "price_events",
    "gold_star",
    "inventory_snapshot",
    "gold_marts",
    "audit",
)


def resolve_steps_from(from_step: str | None) -> tuple[str, ...]:
    """Valida e retorna a sequência de etapas a partir de `from_step`."""
    if from_step is None:
        return PIPELINE_STEPS
    if from_step not in PIPELINE_STEPS:
        valid = ", ".join(PIPELINE_STEPS)
        raise ValueError(f"Etapa inválida '{from_step}'. Etapas válidas: {valid}.")
    start_idx = PIPELINE_STEPS.index(from_step)
    return PIPELINE_STEPS[start_idx:]


def _load_ingestion_dates(pipeline_yaml: Path | None = None) -> tuple[str, str]:
    """Lê a janela padrão de datas (`start_date`, `end_date`) do `config/pipeline.yaml`."""
    yaml_path = pipeline_yaml or config_path("pipeline.yaml")
    if not yaml_path.exists():
        return ("2023-01-01", "2024-12-31")
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    ingest_cfg = raw.get("ingestion", {})
    return (
        str(ingest_cfg.get("start_date", "2023-01-01")),
        str(ingest_cfg.get("end_date", "2024-12-31")),
    )


def _resolve_target_scenarios(scenario: str) -> list[ScenarioId]:
    """Resolve e valida os cenários alvo suportados pelo pipeline atual."""
    if scenario in ("c1_toys", "c1", "all"):
        if scenario == "all":
            list_scenario_configs()
        load_scenario_config("c1_toys")
        return ["c1_toys"]
    load_scenario_config(scenario)
    msg = f"Builder para o cenário '{scenario}' será implementado nos próximos marcos (M6)."
    raise NotImplementedError(msg)


def _execute_ingest(
    *,
    sample: bool,
    skip_ingest: bool,
) -> dict[str, Any]:
    """Executa ou pula a etapa de ingestão bruta da API Socrata."""
    if sample or skip_ingest:
        reason = "modo --sample" if sample else "--skip-ingest"
        return {"status": "skipped", "reason": reason, "partitions": 0}
    start_date, end_date = _load_ingestion_dates()
    with SocrataClient() as client:
        downloaded = client.download_range(start_date=start_date, end_date=end_date)
    return {"status": "completed", "partitions": len(downloaded), "range": f"{start_date}..{end_date}"}


def _execute_bronze(*, sample: bool, base_dir: Path | None) -> dict[str, Any]:
    """Popula a camada Bronze Parquet e registra a view `bronze.sales_raw`."""
    duckdb_p = get_duckdb_path(base_dir)
    con = get_duckdb_connection(duckdb_p)
    try:
        if sample:
            fixture_p = get_project_root() / "tests" / "fixtures" / "iowa_sample.parquet"
            if not fixture_p.exists():
                generate_fixture(output_path=fixture_p)
            parquet_p = populate_bronze_from_sample_fixture(fixture_p, base_dir=base_dir, db_con=con)
            row = con.execute("SELECT COUNT(*) FROM bronze.sales_raw").fetchone()
            return {"status": "completed", "rows": int(row[0]) if row else 0, "files": [str(parquet_p)]}
        files = convert_all_raw_to_bronze(base_dir=base_dir, db_con=con)
        row = con.execute("SELECT COUNT(*) FROM bronze.sales_raw").fetchone()
        return {"status": "completed", "rows": int(row[0]) if row else 0, "partitions": len(files)}
    finally:
        con.close()


def _execute_silver(
    *,
    sample: bool,
    reference_date: str | None,
    base_dir: Path | None,
) -> dict[str, Any]:
    """Limpa Bronze -> Silver, aplica âncora temporal e enriquece dimensões sintéticas."""
    duckdb_p = get_duckdb_path(base_dir)
    con = get_duckdb_connection(duckdb_p)
    try:
        _, clean_report = build_silver_sales(db_con=con, base_dir=base_dir, sample=sample)
        _, anchor_meta = apply_time_anchor(db_con=con, reference_date=reference_date, base_dir=base_dir)
    finally:
        con.close()

    silver_dir = get_data_dir(base_dir) / "silver"
    dim_counts = enrich_silver_dimensions(duckdb_path=duckdb_p, silver_dir=silver_dir)
    return {
        "status": "completed",
        "rows": int(clean_report.get("final_silver", 0)),
        "removed": int(clean_report.get("total_removed", 0)),
        "time_shift_days": int(anchor_meta.get("time_shift_days", 0)),
        "dimensions": dim_counts,
    }


def _execute_price_events(*, base_dir: Path | None) -> dict[str, Any]:
    """Aplica eventos determinísticos de variação de preço na camada Silver."""
    duckdb_p = get_duckdb_path(base_dir)
    con = get_duckdb_connection(duckdb_p)
    try:
        _, pe_meta = apply_price_events(db_con=con, base_dir=base_dir)
    finally:
        con.close()
    return {
        "status": "completed",
        "total_rows": int(pe_meta.get("total_rows", 0)),
        "affected_rows": int(pe_meta.get("affected_rows", 0)),
        "affected_fraction": round(float(pe_meta.get("affected_fraction", 0.0)), 4),
    }


def run_pipeline(
    *,
    scenario: str = "c1_toys",
    sample: bool = False,
    lake: Literal["local", "remote"] = "local",
    skip_ingest: bool = False,
    from_step: str | None = None,
    reference_date: str | None = None,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    """Orquestra ponta a ponta o pipeline Kyberna e gera relatórios de qualidade."""
    if lake not in ("local", "remote"):
        raise ValueError(f"Modo de lake inválido: '{lake}'. Use 'local' ou 'remote'.")
    if lake == "remote" and not get_settings().lake_uri:
        raise RuntimeError(
            "Modo '--lake remote' requer KYBERNA_LAKE_URI configurado (ex: abfss://lake@...). "
            "Sincronização remota será expandida em M7-D1."
        )

    steps_to_run = resolve_steps_from(from_step)
    target_scenarios = _resolve_target_scenarios(scenario)
    t_total = time.perf_counter()

    steps_report: dict[str, dict[str, Any]] = {}
    scenarios_report: dict[str, dict[str, Any]] = {scn: {} for scn in target_scenarios}

    for step in steps_to_run:
        t_step = time.perf_counter()
        with timed_step(f"pipeline_{step}"):
            if step == "ingest":
                res = _execute_ingest(sample=sample, skip_ingest=skip_ingest)
            elif step == "bronze":
                res = _execute_bronze(sample=sample, base_dir=base_dir)
            elif step == "silver":
                res = _execute_silver(sample=sample, reference_date=reference_date, base_dir=base_dir)
            elif step == "price_events":
                res = _execute_price_events(base_dir=base_dir)
            elif step == "gold_star":
                res = _run_gold_star_step(target_scenarios, scenarios_report, base_dir=base_dir)
            elif step == "inventory_snapshot":
                res = _run_inventory_step(target_scenarios, scenarios_report, base_dir=base_dir)
            elif step == "gold_marts":
                res = _run_marts_step(target_scenarios, scenarios_report, base_dir=base_dir)
            else:
                res = _run_audit_step(target_scenarios, scenarios_report)

        res["duration_s"] = round(time.perf_counter() - t_step, 3)
        steps_report[step] = res

    now = datetime.datetime.now()
    payload: dict[str, Any] = {
        "report_date": now.date().isoformat(),
        "executed_at": now.isoformat(timespec="seconds"),
        "mode": "sample" if sample else "full",
        "lake": lake,
        "executed_steps": list(steps_to_run),
        "total_duration_s": round(time.perf_counter() - t_total, 3),
        "steps": steps_report,
        "scenarios": scenarios_report,
    }
    json_path, md_path = write_quality_reports(payload, base_dir=base_dir, report_date=now.date())
    payload["quality_json_path"] = str(json_path)
    payload["quality_md_path"] = str(md_path)
    logger.info("Pipeline concluído em %.2fs. Relatório salvo em %s", payload["total_duration_s"], md_path)
    return payload


def _run_gold_star_step(
    target_scenarios: list[ScenarioId],
    scenarios_report: dict[str, dict[str, Any]],
    *,
    base_dir: Path | None,
) -> dict[str, Any]:
    """Executa builder do cenário e Star Schema Gold para cada cenário alvo."""
    con = duckdb.connect(str(get_duckdb_path(base_dir)))
    try:
        for scn in target_scenarios:
            if scn == "c1_toys":
                C1ToysScenarioBuilder().build(con)
            star_counts = build_gold_star_schema(con, scenario_id=scn)
            scenarios_report[scn]["star_schema"] = star_counts
    finally:
        con.close()
    return {"status": "completed", "scenarios": [str(s) for s in target_scenarios]}


def _run_inventory_step(
    target_scenarios: list[ScenarioId],
    scenarios_report: dict[str, dict[str, Any]],
    *,
    base_dir: Path | None,
) -> dict[str, Any]:
    """Gera o snapshot determinístico de estoque na camada Gold."""
    con = duckdb.connect(str(get_duckdb_path(base_dir)))
    try:
        for scn in target_scenarios:
            inv_df = build_inventory_snapshot(con, scenario_id=scn)
            scenarios_report[scn]["inventory_snapshot_rows"] = len(inv_df)
    finally:
        con.close()
    return {"status": "completed", "scenarios": [str(s) for s in target_scenarios]}


def _run_marts_step(
    target_scenarios: list[ScenarioId],
    scenarios_report: dict[str, dict[str, Any]],
    *,
    base_dir: Path | None,
) -> dict[str, Any]:
    """Gera todos os marts analíticos e modelos ML da camada Gold e coleta métricas."""
    con = duckdb.connect(str(get_duckdb_path(base_dir)))
    try:
        for scn in target_scenarios:
            mart_counts = build_gold_marts(con, scenario_id=scn)
            scenarios_report[scn]["marts"] = mart_counts
            scenarios_report[scn]["model_metrics"] = collect_model_metrics(con, scn)
    finally:
        con.close()
    return {"status": "completed", "scenarios": [str(s) for s in target_scenarios]}


def _run_audit_step(
    target_scenarios: list[ScenarioId],
    scenarios_report: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Gera a planilha Excel de conciliação financeira para cada cenário."""
    for scn in target_scenarios:
        xlsx_path = generate_audit_report(scenario_id=scn)
        scenarios_report[scn]["audit_excel_path"] = str(xlsx_path)
    return {"status": "completed", "scenarios": [str(s) for s in target_scenarios]}
