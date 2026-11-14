from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from src.cli import app
from src.core.settings import get_settings
from src.etl.pipeline import PIPELINE_STEPS, resolve_steps_from, run_pipeline


def test_resolve_steps_from_order_and_validation() -> None:
    """Valida ordem completa, retomada por etapa e erro em etapa inválida."""
    assert resolve_steps_from(None) == PIPELINE_STEPS
    assert resolve_steps_from("gold_star") == (
        "gold_star",
        "inventory_snapshot",
        "gold_marts",
        "audit",
    )
    assert resolve_steps_from("audit") == ("audit",)

    with pytest.raises(ValueError, match="Etapa inválida"):
        resolve_steps_from("etapa_inexistente")


def test_run_pipeline_lake_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Falha rápido quando --lake é inválido ou remote sem KYBERNA_LAKE_URI."""
    with pytest.raises(ValueError, match="Modo de lake inválido"):
        run_pipeline(sample=True, lake="s3")  # type: ignore[arg-type]

    monkeypatch.delenv("KYBERNA_LAKE_URI", raising=False)
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="KYBERNA_LAKE_URI"):
            run_pipeline(sample=True, lake="remote")
    finally:
        get_settings.cache_clear()


def test_cli_pipeline_run_sample_and_resume_from_step(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Executa `kyberna pipeline run --sample` ponta a ponta e valida retomada com --from-step."""
    monkeypatch.setenv("KYBERNA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("KYBERNA_DUCKDB_PATH", raising=False)
    get_settings.cache_clear()

    runner = CliRunner()
    try:
        res = runner.invoke(app, ["pipeline", "run", "--sample"])
        assert res.exit_code == 0, res.output

        stamp = datetime.date.today().strftime("%Y%m%d")
        reports_dir = tmp_path / "data" / "reports"
        json_path = reports_dir / f"quality_{stamp}.json"
        md_path = reports_dir / f"quality_{stamp}.md"
        xlsx_path = reports_dir / "conciliacao_c1_toys.xlsx"

        assert json_path.exists()
        assert md_path.exists()
        assert xlsx_path.exists()

        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert payload["mode"] == "sample"
        assert payload["lake"] == "local"
        assert payload["executed_steps"] == list(PIPELINE_STEPS)
        assert payload["steps"]["ingest"]["status"] == "skipped"
        assert payload["steps"]["bronze"]["rows"] > 0
        assert payload["steps"]["silver"]["rows"] > 0
        assert payload["steps"]["price_events"]["affected_rows"] > 0

        c1 = payload["scenarios"]["c1_toys"]
        assert c1["star_schema"]["fact_sales"] > 0
        assert c1["inventory_snapshot_rows"] > 0
        assert c1["model_metrics"]["abc_xyz_skus"] > 0
        assert c1["model_metrics"]["rfm_customers"] > 0
        assert c1["model_metrics"]["forecast_skus"] > 0
        assert c1["model_metrics"]["elasticity_families"] > 0

        md_text = md_path.read_text(encoding="utf-8")
        assert "Execução por Etapa" in md_text
        assert "Métricas Analíticas e Modelos por Cenário" in md_text
        assert "WAPE Médio Forecast (%)" in md_text

        # Retomada a partir de 'audit' executa somente a última etapa
        res_resume = runner.invoke(app, ["pipeline", "run", "--sample", "--from-step", "audit"])
        assert res_resume.exit_code == 0, res_resume.output
        payload_resume = json.loads(json_path.read_text(encoding="utf-8"))
        assert payload_resume["executed_steps"] == ["audit"]

        # Passo inválido retorna erro de parâmetro na CLI
        res_bad = runner.invoke(app, ["pipeline", "run", "--sample", "--from-step", "invalido"])
        assert res_bad.exit_code != 0
    finally:
        get_settings.cache_clear()
