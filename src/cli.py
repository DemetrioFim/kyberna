from __future__ import annotations

import typer

from src.core.logging import setup_logging

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
    sample: bool = typer.Option(False, "--sample", help="Ingerir apenas amostra reduzida para validação"),
    year: int | None = typer.Option(None, "--year", help="Filtrar ano específico para ingestão"),
) -> None:
    """Executa a ingestão paginada da API Socrata para data/raw/."""
    # TODO(M1-D1): Implementar cliente httpx com tenacity e paginação
    raise NotImplementedError("Comando ainda não implementado. Tarefa responsável: M1-D1")


# ------------------------------------------------------------------------------
# Fixture
# ------------------------------------------------------------------------------
@fixture_app.command("generate")
def fixture_generate(
    rows: int = typer.Option(1000, "--rows", help="Quantidade de linhas sintéticas a gerar"),
) -> None:
    """Gera fixture mínima de vendas sintéticas em tests/fixtures/iowa_sample.parquet."""
    # TODO(M1-D2): Implementar gerador determinístico com Faker pt_BR
    raise NotImplementedError("Comando ainda não implementado. Tarefa responsável: M1-D2")


# ------------------------------------------------------------------------------
# Bronze
# ------------------------------------------------------------------------------
@bronze_app.command("build")
def bronze_build(
    sample: bool = typer.Option(False, "--sample", help="Construir Bronze a partir da amostra fixture"),
) -> None:
    """Converte dados brutos (raw) para Bronze Parquet com metadados."""
    # TODO(M1-D3): Implementar conversão raw -> bronze com DuckDB e Pandera
    raise NotImplementedError("Comando ainda não implementado. Tarefa responsável: M1-D3")


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
