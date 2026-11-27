from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from src.core.logging import get_logger
from src.core.types import ScenarioId
from src.db.repository import DataRepository
from src.services.dto import (
    TemperanceKpisDTO,
    TemperancePageDTO,
)
from src.services.temperance_queries import (
    query_commercial_erosion_waterfall,
    query_discount_policy_violations,
    query_temperance_inventory_details,
    query_temperance_kpis,
    query_term_leak_by_rep,
)
from src.ui.formatting import format_brl

logger = get_logger(__name__)


def build_temperance_headline(
    kpis: TemperanceKpisDTO,
    *,
    is_scoped: bool = False,
) -> tuple[str, str]:
    """Gera a manchete executiva dinâmica e contextualizada para a Tela de Temperança."""
    erosion_str = format_brl(kpis.total_commercial_erosion_brl, compact=True, decimals=1)
    excess_str = format_brl(kpis.excess_discount_brl, compact=True, decimals=1)
    locked_str = format_brl(kpis.locked_capital_brl, compact=True, decimals=1)
    wh_prefix = "No armazém corporativo (escopo global)" if is_scoped else "No armazém"

    if kpis.excess_discount_brl > 0 or kpis.locked_capital_brl > 0:
        title = (
            f"Temperança Comercial: {excess_str} em descontos fora da política e "
            f"{locked_str} em estoque imobilizado"
        )
        text = (
            f"A sangria comercial totaliza <b>{erosion_str}</b> "
            f"({kpis.total_commercial_erosion_pct:.1f}% da receita bruta), "
            f"sendo <b>{excess_str}</b> concedidos acima do teto estipulado para o porte dos lojistas. "
            f"{wh_prefix}, <b>{kpis.locked_skus_count} SKUs</b> acumulam mais de 120 dias de cobertura "
            f"({locked_str} travados), enquanto <b>{kpis.stockout_risk_skus_count} SKUs da Curva A</b> "
            f"enfrentam risco iminente de desabastecimento."
        )
    else:
        title = "Temperança Comercial: Operação em Conformidade com a Política de Margem"
        text = (
            f"Descontos concedidos dentro dos limites de tabela e estoque operando em níveis saudáveis. "
            f"Erosão comercial controlada em <b>{erosion_str}</b>."
        )

    return title, text


def build_temperance_prescription(
    kpis: TemperanceKpisDTO,
    violations_df: pd.DataFrame,
    locked_df: pd.DataFrame,
    *,
    is_scoped: bool = False,
) -> tuple[str, str, float | None]:
    """Elabora a recomendação prescritiva acionável quantificada em R$ de estancamento de sangrias."""
    recoverable_discount = kpis.excess_discount_brl * 0.70
    recoverable_inventory = kpis.locked_capital_brl * 0.25
    total_impact = recoverable_discount if is_scoped else recoverable_discount + recoverable_inventory

    impact_str = format_brl(total_impact, compact=True, decimals=1)
    disc_impact_str = format_brl(recoverable_discount, compact=True, decimals=1)
    inv_impact_str = format_brl(recoverable_inventory, compact=True, decimals=1)

    top_reps = ""
    if not violations_df.empty:
        top_names = violations_df.head(3)["rep_name"].tolist()
        top_reps = f"com foco imediato nas carteiras de <b>{', '.join(top_names)}</b>"

    inv_item_title = (
        f"Desmobilização de Estoque — Armazém Global "
        f"({inv_impact_str} destraváveis adicionais fora do recorte)"
        if is_scoped
        else f"Desmobilização de Estoque ({inv_impact_str} destraváveis)"
    )

    title = f"Veredito de Temperança: Recuperação Estimada de {impact_str} no Caixa Operacional"
    html = (
        f"<p>A auditoria analítica identificou duas alavancas prioritárias para estancar sangrias:</p>"
        f"<ol>"
        f"<li><b>Corte de Descontos Fora de Tabela ({disc_impact_str} recuperáveis)</b>: "
        f"Impor trava sistêmica para concessões acima do teto de porte (P=3%, M=6.5%, G=10.5%), "
        f"{top_reps}.</li>"
        f"<li><b>{inv_item_title}</b>: "
        f"Campanha de liquidação em lotes fechados para os <b>{kpis.locked_skus_count} SKUs >120d</b>, "
        f"revertendo caixa para ressuprimento dos <b>{kpis.stockout_risk_skus_count} SKUs Curva A</b>.</li>"
        f"</ol>"
    )

    return title, html, round(total_impact, 2)


def build_temperance_dashboard(
    repo: DataRepository,
    scenario_id: ScenarioId = "c1_toys",
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    families: Sequence[str] = (),
    sales_reps: Sequence[str] = (),
    start_date_key: int | None = None,
    end_date_key: int | None = None,
    as_of_date_label: str = "31/12/2024",
) -> TemperancePageDTO:
    """Orquestra as consultas e consolida o payload completo consumido pela Página 4 (Temperança)."""
    logger.info("Construindo payload da Página de Temperança para cenário '%s'...", scenario_id)

    # 1. KPIs Consolidados
    kpis = query_temperance_kpis(
        repo,
        scenario_id,
        regiao=regiao,
        uf=uf,
        sales_reps=sales_reps,
        families=families,
        start_date_key=start_date_key,
        end_date_key=end_date_key,
    )

    # 2. Waterfall de Erosão Comercial
    waterfall_df = query_commercial_erosion_waterfall(
        repo,
        scenario_id,
        regiao=regiao,
        uf=uf,
        sales_reps=sales_reps,
        families=families,
        start_date_key=start_date_key,
        end_date_key=end_date_key,
    )

    # 3. Violações de Política Comercial
    violations_reps_df, violations_fams_df = query_discount_policy_violations(
        repo,
        scenario_id,
        regiao=regiao,
        uf=uf,
        sales_reps=sales_reps,
        families=families,
        start_date_key=start_date_key,
        end_date_key=end_date_key,
    )

    # 4. Vazamento Financeiro de Prazo por RCA
    term_leak_df = query_term_leak_by_rep(
        repo,
        scenario_id,
        regiao=regiao,
        uf=uf,
        sales_reps=sales_reps,
        families=families,
        start_date_key=start_date_key,
        end_date_key=end_date_key,
    )

    # 5. Temperança de Estoque (Capital Travado, Ruptura e Matriz ABC/XYZ)
    locked_inv_df, stockout_risk_df, abc_xyz_df = query_temperance_inventory_details(
        repo,
        scenario_id,
        families=families,
        regiao=regiao,
        uf=uf,
        sales_reps=sales_reps,
        start_date_key=start_date_key,
        end_date_key=end_date_key,
    )

    # 6. Manchete e Prescrição (sinalizando escopo global do armazém se houver filtro)
    is_scoped = (
        regiao != "Todas"
        or uf != "Todas"
        or bool(sales_reps)
        or start_date_key is not None
        or end_date_key is not None
    )
    headline_title, headline_text = build_temperance_headline(kpis, is_scoped=is_scoped)
    presc_title, presc_html, presc_impact = build_temperance_prescription(
        kpis,
        violations_reps_df,
        locked_inv_df,
        is_scoped=is_scoped,
    )

    return TemperancePageDTO(
        scenario_id=scenario_id,
        kpis=kpis,
        headline_title=headline_title,
        headline_text=headline_text,
        waterfall_df=waterfall_df,
        policy_violations_by_rep_df=violations_reps_df,
        policy_violations_by_family_df=violations_fams_df,
        term_leak_by_rep_df=term_leak_df,
        locked_inventory_df=locked_inv_df,
        stockout_risk_df=stockout_risk_df,
        abc_xyz_summary_df=abc_xyz_df,
        prescription_title=presc_title,
        prescription_html=presc_html,
        prescription_impact_brl=presc_impact,
        as_of_date_label=as_of_date_label,
    )
