from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

import pandas as pd

from src.core.logging import get_logger
from src.core.types import ScenarioId
from src.db.repository import DataRepository
from src.ml.abc_xyz import compute_abc_xyz_matrix_summary
from src.services.dto import (
    ExecutivePageDTO,
)
from src.services.executive_kpis import compute_executive_kpis
from src.services.executive_queries import (
    build_filter_clauses,
    query_margin_recovery_potential,
    query_monthly_sales_table,
    query_monthly_trend,
    query_prudence_anomalies,
    query_top_drivers,
)
from src.services.simulator import simulate_quick_what_if
from src.services.waterfall_steps import build_waterfall_steps
from src.ui.formatting import format_brl

__all__ = [
    "build_executive_dashboard",
    "build_waterfall_steps",
    "compute_executive_kpis",
    "get_abc_xyz_overview",
    "get_filter_options",
    "get_monthly_margin_trend",
    "get_monthly_sales_table",
    "get_top_margin_drivers",
    "simulate_quick_what_if",
]

logger = get_logger(__name__)


def get_filter_options(repo: DataRepository, scenario_id: ScenarioId = "c1_toys") -> dict[str, list[str]]:
    """Obtém as opções únicas de filtro para o cenário selecionado."""
    regioes, ufs, families, reps = ["Centro-Oeste", "Nordeste", "Norte", "Sudeste", "Sul"], [], [], []
    try:
        c_df = repo.table("dim_customer", scenario_id, columns=["region", "state"])
        regioes = sorted([str(r) for r in c_df["region"].dropna().unique() if str(r).strip()]) or regioes
        ufs = sorted([str(u) for u in c_df["state"].dropna().unique() if str(u).strip()])
        p_df = repo.table("dim_product", scenario_id, columns=["family"])
        families = sorted([str(f) for f in p_df["family"].dropna().unique() if str(f).strip()])
        r_df = repo.table("dim_sales_rep", scenario_id, columns=["name"])
        reps = sorted([str(r) for r in r_df["name"].dropna().unique() if str(r).strip()])
    except Exception as exc:
        logger.debug("Falha ao obter opções de filtro: %s", exc)
    return {"regioes": regioes, "ufs": ufs, "families": families, "sales_reps": reps}


def get_monthly_margin_trend(
    repo: DataRepository,
    scenario_id: ScenarioId = "c1_toys",
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    families: Sequence[str] = (),
    sales_reps: Sequence[str] = (),
    start_date_key: int | None = None,
    end_date_key: int | None = None,
) -> pd.DataFrame:
    """Consulta a evolução mensal agregada de Faturamento Bruto e Margem Líquida %."""
    return query_monthly_trend(
        repo,
        scenario_id,
        regiao=regiao,
        uf=uf,
        families=families,
        sales_reps=sales_reps,
        start_date_key=start_date_key,
        end_date_key=end_date_key,
    )


def get_monthly_sales_table(
    repo: DataRepository,
    scenario_id: ScenarioId = "c1_toys",
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    families: Sequence[str] = (),
    sales_reps: Sequence[str] = (),
    start_date_key: int | None = None,
    end_date_key: int | None = None,
) -> pd.DataFrame:
    """Consulta o demonstrativo detalhado de vendas mês a mês para exibição em tabela analítica."""
    where_sql, params, joins = build_filter_clauses(
        scenario_id,
        regiao=regiao,
        uf=uf,
        families=families,
        sales_reps=sales_reps,
        start_date_key=start_date_key,
        end_date_key=end_date_key,
    )
    return query_monthly_sales_table(repo, where_sql=where_sql, params=params, joins=joins)


def get_abc_xyz_overview(
    repo: DataRepository,
    scenario_id: ScenarioId = "c1_toys",
    selected_cell: str | None = None,
    families: Sequence[str] = (),
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Retorna o resumo 3x3 da Matriz ABC/XYZ e a listagem de SKUs da célula selecionada."""
    try:
        mart_df = repo.table("mart_abc_xyz", scenario_id)
    except Exception as exc:
        logger.warning("Falha ao carregar mart_abc_xyz: %s", exc)
        return pd.DataFrame(), pd.DataFrame()

    if mart_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    if families:
        mart_df = mart_df[mart_df["family"].isin(families)]
        if mart_df.empty:
            return pd.DataFrame(), pd.DataFrame()

    matrix_summary = compute_abc_xyz_matrix_summary(mart_df)
    matrix_summary["abc_xyz_cell"] = matrix_summary["cell"]
    matrix_summary["margin_share_pct"] = matrix_summary["margin_pct"]
    matrix_summary["recommended_policy"] = matrix_summary["policy"]

    skus_df = mart_df.copy()
    if selected_cell and selected_cell != "Todas":
        skus_df = skus_df[skus_df["abc_xyz_class"] == selected_cell]

    cols_to_keep = [
        "product_id",
        "product_name",
        "family",
        "abc_class",
        "xyz_class",
        "abc_xyz_class",
        "gross_revenue",
        "contribution_margin",
        "margin_pct",
        "weekly_cv",
        "policy",
    ]
    existing_cols = [c for c in cols_to_keep if c in skus_df.columns]
    skus_df = skus_df[existing_cols].sort_values(by="contribution_margin", ascending=False)
    return matrix_summary, skus_df


def get_top_margin_drivers(
    repo: DataRepository,
    scenario_id: ScenarioId = "c1_toys",
    *,
    by: Literal["product", "customer", "family", "sales_rep"] = "product",
    regiao: str = "Todas",
    uf: str = "Todas",
    families: Sequence[str] = (),
    sales_reps: Sequence[str] = (),
    start_date_key: int | None = None,
    end_date_key: int | None = None,
    limit: int = 10,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Retorna os Top Geradores e Top Destruidores por Produto, Cliente, Família ou RCA."""
    where_sql, params, joins = build_filter_clauses(
        scenario_id,
        regiao=regiao,
        uf=uf,
        families=families,
        sales_reps=sales_reps,
        start_date_key=start_date_key,
        end_date_key=end_date_key,
    )
    return query_top_drivers(repo, by, where_sql=where_sql, params=params, joins=joins, limit=limit)


def build_executive_dashboard(
    repo: DataRepository,
    scenario_id: ScenarioId = "c1_toys",
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    families: Sequence[str] = (),
    sales_reps: Sequence[str] = (),
    selected_cell: str | None = None,
    start_date_key: int | None = None,
    end_date_key: int | None = None,
    comp_start_date_key: int | None = None,
    comp_end_date_key: int | None = None,
    comparison_mode: Literal["pop", "yoy"] = "pop",
    period_label: str = "01/01/2023 a 31/12/2024 (24 Meses)",
    comparison_label: str = "Histórico Global Consolidado",
    as_of_date_label: str = "31/12/2024",
) -> ExecutivePageDTO:
    """Monta o payload analítico completo da Visão Executiva pronto para a camada de UI."""
    kpis = compute_executive_kpis(
        repo,
        scenario_id,
        regiao=regiao,
        uf=uf,
        families=families,
        sales_reps=sales_reps,
        start_date_key=start_date_key,
        end_date_key=end_date_key,
        comp_start_date_key=comp_start_date_key,
        comp_end_date_key=comp_end_date_key,
        comparison_mode=comparison_mode,
    )
    waterfall_df = build_waterfall_steps(kpis)
    monthly_trend_df = get_monthly_margin_trend(
        repo,
        scenario_id,
        regiao=regiao,
        uf=uf,
        families=families,
        sales_reps=sales_reps,
        start_date_key=start_date_key,
        end_date_key=end_date_key,
    )
    monthly_sales_table_df = get_monthly_sales_table(
        repo,
        scenario_id,
        regiao=regiao,
        uf=uf,
        families=families,
        sales_reps=sales_reps,
        start_date_key=start_date_key,
        end_date_key=end_date_key,
    )
    abc_xyz_matrix_df, abc_xyz_skus_df = get_abc_xyz_overview(
        repo, scenario_id, selected_cell, families=families
    )

    # 4 Dimensões de Geradores vs Detratores
    dims: tuple[Literal["product", "customer", "family", "sales_rep"], ...] = (
        "product",
        "customer",
        "family",
        "sales_rep",
    )
    drvs = [
        get_top_margin_drivers(
            repo,
            scenario_id,
            by=d,
            regiao=regiao,
            uf=uf,
            families=families,
            sales_reps=sales_reps,
            start_date_key=start_date_key,
            end_date_key=end_date_key,
            limit=10,
        )
        for d in dims
    ]
    (top_gen_p, top_dest_p), (top_gen_c, top_dest_c) = drvs[0], drvs[1]
    (top_gen_f, top_dest_f), (top_gen_r, top_dest_r) = drvs[2], drvs[3]

    where_sql, params, joins = build_filter_clauses(
        scenario_id,
        regiao=regiao,
        uf=uf,
        families=families,
        sales_reps=sales_reps,
        start_date_key=start_date_key,
        end_date_key=end_date_key,
    )
    anomalies_df = query_prudence_anomalies(
        repo, where_sql=where_sql, params=params, joins=joins, scenario_id=scenario_id
    )
    low_margin_count, recovery_impact = query_margin_recovery_potential(
        repo, where_sql=where_sql, params=params, joins=joins, target_rate=0.22
    )

    headline_title = "Síntese Executiva: Ritmo de Metas & Margem Real"
    headline_text = (
        f"Faturamento de <strong>{format_brl(kpis.gross_revenue, compact=True)}</strong> gerou "
        f"<strong>{format_brl(kpis.contribution_margin, compact=True)}</strong> em Margem de Contribuição "
        f"(<strong>{kpis.contribution_margin_pct:.1f}%</strong>). "
        f"Ritmo atual atinge <strong>{kpis.revenue_pacing_pct:.1f}% da meta</strong> com ritmo trimestral de "
        f"<strong>{format_brl(kpis.projected_quarter_revenue_brl, compact=True)}</strong>."
    )

    prescription_title = "Diagnóstico Executivo: Proteção e Captura de Margem"
    prescription_html = (
        f"Foram identificados <strong>{low_margin_count} lojistas</strong> com margem inferior a 22,0% "
        f"(frente à média da carteira de {kpis.contribution_margin_pct:.1f}%). "
        f"A limitação do teto de desconto e a exigência de pedido mínimo por caixa master "
        f"podem recuperar até <strong>{format_brl(recovery_impact, compact=True)}</strong> "
        f"em margem adicional sem risco de ruptura comercial."
    )

    pacing_kpis = {
        "revenue_target": kpis.revenue_target_brl,
        "revenue_pacing_pct": kpis.revenue_pacing_pct,
        "margin_target_pct": kpis.margin_target_pct,
        "projected_revenue": kpis.projected_quarter_revenue_brl,
    }

    return ExecutivePageDTO(
        scenario_id=scenario_id,
        kpis=kpis,
        headline_title=headline_title,
        headline_text=headline_text,
        waterfall_df=waterfall_df,
        monthly_trend_df=monthly_trend_df,
        abc_xyz_matrix_df=abc_xyz_matrix_df,
        abc_xyz_skus_df=abc_xyz_skus_df,
        top_generators_df=top_gen_p,
        top_destroyers_df=top_dest_p,
        top_customer_generators_df=top_gen_c,
        top_customer_destroyers_df=top_dest_c,
        top_family_generators_df=top_gen_f,
        top_family_destroyers_df=top_dest_f,
        top_rep_generators_df=top_gen_r,
        top_rep_destroyers_df=top_dest_r,
        anomalies_df=anomalies_df,
        pacing_kpis=pacing_kpis,
        prescription_title=prescription_title,
        prescription_html=prescription_html,
        prescription_impact_brl=recovery_impact,
        period_label=period_label,
        comparison_label=comparison_label,
        as_of_date_label=as_of_date_label,
        monthly_sales_table_df=monthly_sales_table_df,
    )
