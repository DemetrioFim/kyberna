from __future__ import annotations

from pathlib import Path

import typer

from src.core.logging import setup_logging, timed_step
from src.core.paths import get_project_root
from src.etl.ingest.fixture import generate_fixture
from src.etl.ingest.raw_to_bronze import convert_all_raw_to_bronze, populate_bronze_from_sample_fixture
from src.etl.ingest.socrata_client import SocrataClient

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
) -> None:
    """Aplica limpeza canônica, âncora temporal e dimensões sintéticas no DuckDB."""
    # TODO(M1-D5): Implementar pipeline Silver SQL no DuckDB + enriquecimento Faker
    raise NotImplementedError("Comando ainda não implementado. Tarefa responsável: M1-D5")


# ------------------------------------------------------------------------------
# Gold
# ------------------------------------------------------------------------------
@gold_app.command("build")
def gold_build(
    scenario: str = typer.Option("c1_toys", "--scenario", help="Identificador do cenário de negócio"),
    sample: bool = typer.Option(False, "--sample", help="Processar com base na amostra reduzida"),
) -> None:
    """Gera dimensões, fatos e marts analíticos da camada Gold no formato Parquet e DuckDB."""
    # TODO(M2-D1): Implementar star schema e marts de margem de contribuição
    raise NotImplementedError("Comando ainda não implementado. Tarefa responsável: M2-D1")


# ------------------------------------------------------------------------------
# ML
# ------------------------------------------------------------------------------
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
@audit_app.command("report")
def audit_report(
    scenario: str = typer.Option("c1_toys", "--scenario", help="Identificador do cenário a auditar"),
) -> None:
    """Gera planilha Excel aberta de conciliação financeira e memória de cálculo."""
    # TODO(M2-D4): Implementar gerador xlsxwriter com abas DRE, Memória e Curvas
    raise NotImplementedError("Comando ainda não implementado. Tarefa responsável: M2-D4")


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
