from __future__ import annotations

from pathlib import Path

import duckdb
import typer

from src.core.logging import setup_logging, timed_step
from src.core.paths import get_duckdb_path, get_project_root
from src.core.scenarios import list_scenario_configs, load_scenario_config
from src.etl.audit import generate_audit_report
from src.etl.gold.marts import build_gold_marts
from src.etl.gold.star_schema import build_gold_star_schema
from src.etl.ingest.fixture import generate_fixture
from src.etl.ingest.raw_to_bronze import convert_all_raw_to_bronze, populate_bronze_from_sample_fixture
from src.etl.ingest.socrata_client import SocrataClient
from src.etl.scenarios.c1_toys import C1ToysScenarioBuilder
from src.etl.silver.clean import build_silver_sales
from src.etl.silver.enrich import enrich_silver_dimensions
from src.etl.silver.time_anchor import apply_time_anchor
from src.ml.abc_xyz import build_abc_xyz_mart, compute_abc_xyz_matrix_summary
from src.ml.churn import build_customer_risk_mart, compute_customer_risk_summary
from src.ml.rep_performance import build_rep_performance_mart, compute_rep_performance_summary
from src.ml.rfm import build_rfm_mart, compute_rfm_segment_summary
from src.ml.white_space import build_white_space_mart

app = typer.Typer(
    name="kyberna",
    help="Kyberna — Decision Intelligence & Prescriptive Analytics CLI",
    no_args_is_help=True,
    add_completion=False,
)

# ------------------------------------------------------------------------------
# Sub-aplicações (Grupos de Comandos)
# ------------------------------------------------------------------------------
ingest_app = typer.Typer(
    name="ingest",
    help="Ingestão de dados brutos da API pública Socrata (Iowa Liquor Sales)",
    no_args_is_help=True,
)
fixture_app = typer.Typer(
    name="fixture",
    help="Geração e gestão de fixtures sintéticas para testes e modo offline",
    no_args_is_help=True,
)
bronze_app = typer.Typer(
    name="bronze",
    help="Conversão de dados brutos para a camada Bronze Parquet",
    no_args_is_help=True,
)
silver_app = typer.Typer(
    name="silver",
    help="Construção da camada Silver canônica limpa e enriquecida",
    no_args_is_help=True,
)
gold_app = typer.Typer(
    name="gold",
    help="Geração de star schemas e marts analíticos por cenário",
    no_args_is_help=True,
)
ml_app = typer.Typer(
    name="ml",
    help="Treinamento e inferência dos modelos de ML e inteligência prescritiva",
    no_args_is_help=True,
)
audit_app = typer.Typer(
    name="audit",
    help="Geração de planilhas Excel de conciliação financeira e conferência",
    no_args_is_help=True,
)
load_app = typer.Typer(
    name="load",
    help="Carga atômica da camada Gold para o Azure SQL Database",
    no_args_is_help=True,
)
pipeline_app = typer.Typer(
    name="pipeline",
    help="Execução orquestrada ponta a ponta do pipeline de dados Kyberna",
    no_args_is_help=True,
)

app.add_typer(ingest_app)
app.add_typer(fixture_app)
app.add_typer(bronze_app)
app.add_typer(silver_app)
app.add_typer(gold_app)
app.add_typer(ml_app)
app.add_typer(audit_app)
app.add_typer(load_app)
app.add_typer(pipeline_app)


# ------------------------------------------------------------------------------
# Ingest
# ------------------------------------------------------------------------------
@ingest_app.command("run")
def ingest_run(
    start: str = typer.Option("2023-01-01", "--start", help="Data inicial no formato YYYY-MM-DD"),
    end: str = typer.Option("2024-12-31", "--end", help="Data final no formato YYYY-MM-DD"),
    sample_frac: float | None = typer.Option(
        None, "--sample-frac", help="Fração de amostragem estratificada por loja (ex: 0.3)"
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Força novo download mesmo se raw já existir"),
    app_token: str | None = typer.Option(None, "--app-token", help="App Token da API Socrata (opcional)"),
) -> None:
    """Executa a ingestão paginada da API Socrata para data/raw/ e converte para Bronze."""
    with timed_step("ingestao_socrata"):
        client = SocrataClient(app_token=app_token)
        downloaded = client.download_range(start_date=start, end_date=end, force=force)
        typer.echo(f"Ingestão concluída: {len(downloaded)} partições mensais em data/raw/sales/.")

    with timed_step("conversao_raw_to_bronze"):
        bronze_files = convert_all_raw_to_bronze(sample_frac=sample_frac)
        typer.echo(
            f"Camada Bronze atualizada: {len(bronze_files)} partições Parquet "
            "e view bronze.sales_raw registrada no DuckDB."
        )


@ingest_app.callback(invoke_without_command=True)
def ingest_callback(
    ctx: typer.Context,
    *,
    start: str = typer.Option("2023-01-01", "--start", help="Data inicial no formato YYYY-MM-DD"),
    end: str = typer.Option("2024-12-31", "--end", help="Data final no formato YYYY-MM-DD"),
    sample_frac: float | None = typer.Option(
        None, "--sample-frac", help="Fração de amostragem estratificada por loja (ex: 0.3)"
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Força novo download mesmo se raw já existir"),
    app_token: str | None = typer.Option(None, "--app-token", help="App Token da API Socrata (opcional)"),
) -> None:
    """Ingestão de dados brutos da API pública Socrata (Iowa Liquor Sales)."""
    if ctx.invoked_subcommand is None:
        ingest_run(start=start, end=end, sample_frac=sample_frac, force=force, app_token=app_token)


# ------------------------------------------------------------------------------
# Fixture
# ------------------------------------------------------------------------------
@fixture_app.command("generate")
def fixture_generate(
    rows: int = typer.Option(20000, "--rows", "-r", help="Quantidade de linhas sintéticas a gerar"),
    seed: int = typer.Option(42, "--seed", "-s", help="Semente pseudo-aleatória determinística"),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Caminho opcional do arquivo Parquet de saída"
    ),
) -> None:
    """Gera fixture mínima de vendas sintéticas em tests/fixtures/iowa_sample.parquet."""
    df = generate_fixture(num_rows=rows, seed=seed, output_path=output)
    typer.echo(f"Fixture gerada com sucesso: {len(df):,} linhas.")


# ------------------------------------------------------------------------------
# Bronze
# ------------------------------------------------------------------------------
@bronze_app.command("build")
def bronze_build(
    sample: bool = typer.Option(False, "--sample", help="Construir Bronze a partir da amostra fixture"),
    sample_frac: float | None = typer.Option(
        None, "--sample-frac", help="Fração de amostragem estratificada por loja"
    ),
) -> None:
    """Converte dados brutos (raw) para Bronze Parquet com metadados."""
    with timed_step("construcao_bronze"):
        if sample:
            fixture_p = get_project_root() / "tests" / "fixtures" / "iowa_sample.parquet"
            if not fixture_p.exists():
                generate_fixture(output_path=fixture_p)
            populate_bronze_from_sample_fixture(fixture_p)
            typer.echo("Bronze construída a partir da amostra fixture com sucesso.")
        else:
            files = convert_all_raw_to_bronze(sample_frac=sample_frac)
            typer.echo(f"Bronze construída a partir de {len(files)} arquivos raw.")


# ------------------------------------------------------------------------------
# Silver
# ------------------------------------------------------------------------------
@silver_app.command("build")
def silver_build(
    sample: bool = typer.Option(False, "--sample", help="Construir Silver a partir da Bronze sample"),
    reference_date: str | None = typer.Option(
        None, "--reference-date", help="Data de referência para a âncora temporal (YYYY-MM-DD)"
    ),
    no_shift: bool = typer.Option(
        False, "--no-shift", help="Não aplica o time-shift de semanas (mantém datas originais)"
    ),
) -> None:
    """Aplica limpeza canônica, tipagem, deduplicação e âncora temporal no DuckDB."""
    with timed_step("construcao_silver"):
        parquet_p, report = build_silver_sales(sample=sample)
        typer.echo(
            f"Silver construída com sucesso em {parquet_p}: "
            f"{report['final_silver']:,} linhas (descartadas {report['total_removed']:,})."
        )
        _, anchor_meta = apply_time_anchor(reference_date=reference_date, no_shift=no_shift)
        typer.echo(
            f"Âncora temporal aplicada: shift={anchor_meta['time_shift_days']} dias "
            f"({anchor_meta['min_shifted_date']} a {anchor_meta['max_shifted_date']})."
        )
        counts = enrich_silver_dimensions()
        typer.echo(
            f"Dimensões Silver enriquecidas: {counts['customers']:,} clientes, "
            f"{counts['sales_reps']:,} RCAs, {counts['geography']:,} municípios."
        )


@silver_app.command("anchor")
def silver_anchor(
    reference_date: str | None = typer.Option(
        None, "--reference-date", help="Data de referência para a âncora temporal (YYYY-MM-DD)"
    ),
    no_shift: bool = typer.Option(
        False, "--no-shift", help="Não aplica o time-shift de semanas (mantém datas originais)"
    ),
) -> None:
    """Ajusta a âncora temporal sobre a tabela Silver existente no DuckDB."""
    with timed_step("ajuste_ancora_temporal"):
        parquet_p, anchor_meta = apply_time_anchor(reference_date=reference_date, no_shift=no_shift)
        typer.echo(
            f"Âncora temporal atualizada em {parquet_p}: "
            f"shift={anchor_meta['time_shift_days']} dias "
            f"({anchor_meta['min_shifted_date']} a {anchor_meta['max_shifted_date']})."
        )


@silver_app.command("enrich")
def silver_enrich(
    seed: int = typer.Option(42, "--seed", "-s", help="Semente pseudo-aleatória determinística"),
) -> None:
    """Gera dimensões sintéticas brasileiras (clientes, RCAs e geografia) no DuckDB e Parquet."""
    with timed_step("enriquecimento_silver"):
        counts = enrich_silver_dimensions(global_seed=seed)
        typer.echo(
            f"Dimensões Silver enriquecidas com sucesso: "
            f"{counts['customers']:,} clientes, {counts['sales_reps']:,} RCAs, "
            f"{counts['geography']:,} municípios."
        )


# ------------------------------------------------------------------------------
# Gold
# ------------------------------------------------------------------------------
@gold_app.command("build")
def gold_build(
    scenario: str = typer.Option(
        "c1_toys", "--scenario", help="Identificador do cenário de negócio (ou 'all')"
    ),
    sample: bool = typer.Option(False, "--sample", help="Processar com base na amostra reduzida"),
) -> None:
    """Gera dimensões, fatos e marts analíticos da camada Gold no formato Parquet e DuckDB."""
    target_scenarios = ["c1_toys"] if scenario in ("c1_toys", "c1", "all") else [scenario]

    if scenario == "all":
        list_scenario_configs()

    for scn in target_scenarios:
        # Valida cenário existente
        load_scenario_config(scn)

        if scn in ("c1_toys", "c1"):
            with timed_step("build_cenario_c1_toys"):
                con = duckdb.connect(str(get_duckdb_path()))
                try:
                    # 1. Builder semântico do cenário
                    builder = C1ToysScenarioBuilder()
                    builder.build(con)

                    # 2. Star Schema Gold
                    star_counts = build_gold_star_schema(con, scenario_id="c1_toys")

                    # 3. Marts analíticos Gold
                    mart_counts = build_gold_marts(con, scenario_id="c1_toys")

                    typer.echo(
                        f"Cenário C1 (Brinquedos) construído com sucesso:\n"
                        f"  - Star Schema: {star_counts['dim_product']:,} produtos, "
                        f"{star_counts['dim_customer']:,} clientes, "
                        f"{star_counts['fact_sales']:,} vendas faturadas.\n"
                        f"  - Marts: {mart_counts['mart_margin_monthly']:,} registros mensais agregados, "
                        f"{mart_counts.get('mart_abc_xyz', 0):,} SKUs classificados em ABC/XYZ."
                    )
                finally:
                    con.close()
        else:
            # TODO(M6-D1 / M6-D2 / M6-D3): Builders para os demais cenários (C2, C3, C4)
            msg = f"Builder para o cenário '{scn}' será implementado nos próximos marcos."
            raise NotImplementedError(msg)


# ------------------------------------------------------------------------------
# ML
# ------------------------------------------------------------------------------
@ml_app.command("abc-xyz")
def ml_abc_xyz(
    scenario: str = typer.Option("c1_toys", "--scenario", help="Identificador do cenário"),
    as_of: str | None = typer.Option(None, "--as-of", help="Data de corte analítica (YYYY-MM-DD)"),
    metric: str = typer.Option(
        "contribution_margin",
        "--metric",
        help="Métrica do corte ABC ('contribution_margin' ou 'gross_revenue')",
    ),
) -> None:
    """Classifica produtos na Matriz ABC/XYZ e salva mart_abc_xyz."""
    con = duckdb.connect(str(get_duckdb_path()))
    try:
        with timed_step("ml_abc_xyz"):
            df = build_abc_xyz_mart(
                con,
                as_of_date=as_of,
                scenario_id=scenario,  # type: ignore[arg-type]
                metric=metric,  # type: ignore[arg-type]
            )
            summary = compute_abc_xyz_matrix_summary(df)

        typer.echo(f"\nMatriz 3x3 ABC/XYZ gerada com sucesso para '{scenario}' ({len(df):,} SKUs):")
        typer.echo(
            summary[
                [
                    "cell",
                    "sku_count",
                    "sku_pct",
                    "gross_revenue",
                    "revenue_pct",
                    "contribution_margin",
                    "margin_pct",
                ]
            ].to_string(index=False)
        )
    finally:
        con.close()


@ml_app.command("rfm")
def ml_rfm(
    scenario: str = typer.Option("c1_toys", "--scenario", help="Identificador do cenário"),
    as_of: str | None = typer.Option(None, "--as-of", help="Data de corte analítica (YYYY-MM-DD)"),
) -> None:
    """Calcula a segmentação RFM baseada em Margem de Contribuição e salva mart_rfm."""
    con = duckdb.connect(str(get_duckdb_path()))
    try:
        with timed_step("ml_rfm"):
            df = build_rfm_mart(
                con,
                as_of_date=as_of,
                scenario_id=scenario,  # type: ignore[arg-type]
            )
            summary = compute_rfm_segment_summary(df)

        typer.echo(f"\nSegmentação RFM B2B concluída para '{scenario}' ({len(df):,} clientes):")
        typer.echo(
            summary[
                [
                    "rfm_segment",
                    "customer_count",
                    "customer_share_pct",
                    "gross_revenue",
                    "contribution_margin",
                    "margin_share_pct",
                    "avg_ticket",
                ]
            ].to_string(index=False)
        )
    finally:
        con.close()


@ml_app.command("churn")
def ml_churn(
    scenario: str = typer.Option("c1_toys", "--scenario", help="Identificador do cenário"),
    as_of: str | None = typer.Option(None, "--as-of", help="Data de corte analítica (YYYY-MM-DD)"),
) -> None:
    """Calcula ciclo de recompra e risco heurístico de Churn e salva mart_customer_risk."""
    con = duckdb.connect(str(get_duckdb_path()))
    try:
        with timed_step("ml_churn"):
            df = build_customer_risk_mart(
                con,
                as_of_date=as_of,
                scenario_id=scenario,  # type: ignore[arg-type]
            )
            summary = compute_customer_risk_summary(df)

        typer.echo(f"\nAnálise de Risco de Churn concluída para '{scenario}' ({len(df):,} clientes):")
        typer.echo(
            summary[
                [
                    "risk_status",
                    "customer_count",
                    "customer_share_pct",
                    "annual_revenue_at_risk",
                    "annual_margin_at_risk",
                    "revenue_share_pct",
                    "margin_share_pct",
                    "avg_delay_ratio",
                    "avg_churn_prob",
                ]
            ].to_string(index=False)
        )
    finally:
        con.close()


@ml_app.command("white-space")
def ml_white_space(
    scenario: str = typer.Option("c1_toys", "--scenario", help="Identificador do cenário"),
    as_of: str | None = typer.Option(None, "--as-of", help="Data de corte analítica (YYYY-MM-DD)"),
) -> None:
    """Calcula matriz White Space e recomendações de Cross-Sell via Apriori e Lookalike."""
    con = duckdb.connect(str(get_duckdb_path()))
    try:
        with timed_step("ml_white_space"):
            df = build_white_space_mart(
                con,
                as_of_date=as_of,
                scenario_id=scenario,  # type: ignore[arg-type]
            )

        typer.echo(f"\nMatriz White Space construída para '{scenario}' ({len(df):,} recomendações geradas):")
        top_sample = df.head(10)[
            [
                "customer_id",
                "recommended_family",
                "rank_order",
                "opportunity_score",
                "item_affinity_score",
                "lookalike_score",
                "potential_revenue_brl",
                "potential_margin_brl",
            ]
        ]
        typer.echo(top_sample.to_string(index=False))
    finally:
        con.close()


@ml_app.command("rep-performance")
def ml_rep_performance(
    scenario: str = typer.Option("c1_toys", "--scenario", help="Identificador do cenário"),
    as_of: str | None = typer.Option(None, "--as-of", help="Data de corte analítica (YYYY-MM-DD)"),
) -> None:
    """Analisa a eficiência comercial de RCAs e classifica no Quadrante de Performance."""
    con = duckdb.connect(str(get_duckdb_path()))
    try:
        with timed_step("ml_rep_performance"):
            df = build_rep_performance_mart(
                con,
                as_of_date=as_of,
                scenario_id=scenario,  # type: ignore[arg-type]
            )
            summary = compute_rep_performance_summary(df)

        typer.echo(
            f"\nQuadrante de Representantes (RCAs) construído para '{scenario}' ({len(df):,} representantes):"
        )
        typer.echo(
            summary[
                [
                    "quadrant",
                    "reps_count",
                    "reps_pct",
                    "gross_revenue",
                    "revenue_pct",
                    "contribution_margin",
                    "margin_pct",
                    "avg_discount_pct",
                    "revenue_at_risk_brl",
                    "white_space_potential_brl",
                ]
            ].to_string(index=False)
        )
    finally:
        con.close()


@ml_app.command("train")
def ml_train(
    scenario: str = typer.Option("c1_toys", "--scenario", help="Identificador do cenário"),
) -> None:
    """Treina modelos preditivos e algoritmos prescritivos."""
    # TODO(M3-S1): Implementar algoritmos RFM, Churn e White Space
    raise NotImplementedError("Comando ainda não implementado. Tarefa responsável: M3-S1")


@ml_app.command("infer")
def ml_infer(
    scenario: str = typer.Option("c1_toys", "--scenario", help="Identificador do cenário"),
) -> None:
    """Executa inferência em lote e salva predições na camada Gold."""
    # TODO(M3-S1): Implementar inferência em lote
    raise NotImplementedError("Comando ainda não implementado. Tarefa responsável: M3-S1")


# ------------------------------------------------------------------------------
# Audit
# ------------------------------------------------------------------------------
@audit_app.callback(invoke_without_command=True)
def audit_main(
    ctx: typer.Context,
    scenario: str = typer.Option("c1_toys", "--scenario", help="Identificador do cenário a auditar"),
) -> None:
    """Gera planilha Excel aberta de conciliação financeira e memória de cálculo."""
    if ctx.invoked_subcommand is None:
        audit_report(scenario=scenario)


@audit_app.command("report")
def audit_report(
    scenario: str = typer.Option("c1_toys", "--scenario", help="Identificador do cenário a auditar"),
) -> None:
    """Gera planilha Excel aberta de conciliação financeira e memória de cálculo."""
    cfg = load_scenario_config(scenario)
    with timed_step("audit_report"):
        output_path = generate_audit_report(scenario_id=cfg.id)
        typer.echo(f"Planilha de conciliação gerada com sucesso: {output_path}")


# ------------------------------------------------------------------------------
# Load
# ------------------------------------------------------------------------------
@load_app.command("sync")
def load_sync(
    scenario: str = typer.Option("c1_toys", "--scenario", help="Identificador do cenário"),
) -> None:
    """Carrega dados Gold no Azure SQL Database com swap transacional staging."""
    # TODO(M7-D1): Implementar loader atômico pyodbc staging + swap
    raise NotImplementedError("Comando ainda não implementado. Tarefa responsável: M7-D1")


# ------------------------------------------------------------------------------
# Pipeline
# ------------------------------------------------------------------------------
@pipeline_app.command("run")
def pipeline_run(
    scenario: str = typer.Option("c1_toys", "--scenario", help="Identificador do cenário"),
    sample: bool = typer.Option(False, "--sample", help="Executar pipeline em modo amostra"),
) -> None:
    """Executa o pipeline completo ponta a ponta."""
    # TODO(M5-D1): Implementar orquestração ponta a ponta
    raise NotImplementedError("Comando ainda não implementado. Tarefa responsável: M5-D1")


# ------------------------------------------------------------------------------
# Root Callback & Versão
# ------------------------------------------------------------------------------
def version_callback(value: bool) -> None:
    if value:
        typer.echo("Kyberna CLI v0.1.0")
        raise typer.Exit()


@app.callback()
def main(
    version: bool | None = typer.Option(
        None,
        "--version",
        "-v",
        help="Exibe a versão atual da CLI Kyberna",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """Plataforma Kyberna de Decision Intelligence & Prescriptive Analytics."""
    setup_logging()


if __name__ == "__main__":
    app()
