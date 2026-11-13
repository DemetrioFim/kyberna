from __future__ import annotations

import duckdb
import typer

from src.core.logging import timed_step
from src.core.paths import get_duckdb_path
from src.ml.abc_xyz import build_abc_xyz_mart, compute_abc_xyz_matrix_summary
from src.ml.churn import build_customer_risk_mart, compute_customer_risk_summary
from src.ml.forecast import build_forecast_30d_mart, compute_forecast_summary
from src.ml.inventory import build_inventory_position_mart, compute_inventory_position_summary
from src.ml.rep_performance import build_rep_performance_mart, compute_rep_performance_summary
from src.ml.rfm import build_rfm_mart, compute_rfm_segment_summary
from src.ml.white_space import build_white_space_mart

ml_app = typer.Typer(
    name="ml",
    help="Treinamento e inferência dos modelos de ML e inteligência prescritiva",
    no_args_is_help=True,
)


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


@ml_app.command("forecast")
def ml_forecast(
    scenario: str = typer.Option("c1_toys", "--scenario", help="Identificador do cenário"),
    as_of: str | None = typer.Option(None, "--as-of", help="Data de corte analítica (YYYY-MM-DD)"),
    horizon: int = typer.Option(30, "--horizon", help="Horizonte de previsão em dias"),
) -> None:
    """Executa previsão de demanda 30d por SKU via StatsForecast e salva mart_forecast_30d."""
    con = duckdb.connect(str(get_duckdb_path()))
    try:
        with timed_step("ml_forecast"):
            df = build_forecast_30d_mart(
                con,
                as_of_date=as_of,
                scenario_id=scenario,  # type: ignore[arg-type]
                horizon_days=horizon,
            )
            summary = compute_forecast_summary(df)

        typer.echo(f"\nPrevisão de demanda {horizon}d concluída para '{scenario}' ({len(df):,} linhas):")
        if not summary.empty:
            typer.echo(summary.to_string(index=False))
    finally:
        con.close()


@ml_app.command("inventory")
def ml_inventory(
    scenario: str = typer.Option("c1_toys", "--scenario", help="Identificador do cenário"),
    as_of: str | None = typer.Option(None, "--as-of", help="Data de corte analítica (YYYY-MM-DD)"),
) -> None:
    """Consolida posição prescritiva de estoque (SS, ROP, ruptura e capital travado)."""
    con = duckdb.connect(str(get_duckdb_path()))
    try:
        with timed_step("ml_inventory"):
            df = build_inventory_position_mart(
                con,
                as_of_date=as_of,
                scenario_id=scenario,  # type: ignore[arg-type]
            )
            summary = compute_inventory_position_summary(df)

        locked_total = float(df["locked_capital_brl"].sum())
        protected_total = float(df["protected_revenue_brl"].sum())
        typer.echo(
            f"\nPosição Prescritiva de Estoque gerada para '{scenario}' ({len(df):,} SKUs | "
            f"Capital Travado >120d: R$ {locked_total:,.2f} | Receita Protegida: R$ {protected_total:,.2f}):"
        )
        if not summary.empty:
            typer.echo(summary.to_string(index=False))
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
