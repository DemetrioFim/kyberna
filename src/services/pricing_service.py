from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from src.core.types import ScenarioId
from src.db.repository import DataRepository
from src.services.pricing_dto import PricingKpisDTO, PricingPageDTO, PricingShapDTO
from src.services.pricing_queries import (
    query_family_pricing_bands,
    query_filtered_pricing_kpis,
    query_pricing_boxplot_data,
    query_pricing_deviations,
)
from src.services.pricing_shap_queries import (
    query_pricing_shap_drivers,
    query_pricing_shap_options,
)
from src.ui.formatting import format_brl


def build_pricing_prescription(
    kpis: PricingKpisDTO,
    deviations_df: pd.DataFrame,
) -> tuple[str, str, float | None]:
    """Elabora o Veredito de Política de Preços com foco em vazamento e inelásticos."""
    recoverable = kpis.subpricing_leakage_brl * 0.70 + kpis.inelastic_reprice_upside_brl
    if kpis.subpricing_leakage_brl <= 0.0 and kpis.inelastic_reprice_upside_brl <= 0.0:
        return (
            "Veredito de Política de Preços: Dispersão Sob Controle",
            "<p>As vendas faturadas estão operando dentro da banda contextual esperada pelos drivers "
            "de porte, volume e frete.</p>",
            0.0,
        )

    top_fam = str(deviations_df.iloc[0]["family"]) if not deviations_df.empty else "Portfólio"
    top_rep = (
        str(deviations_df.iloc[0]["primary_offender_rep"]) if not deviations_df.empty else "equipe comercial"
    )
    leak_str = format_brl(kpis.subpricing_leakage_brl, compact=True, decimals=1)
    upside_str = format_brl(kpis.inelastic_reprice_upside_brl, compact=True, decimals=1)
    total_str = format_brl(recoverable, compact=True, decimals=1)

    title = f"Veredito de Política de Preços: {total_str} em Recuperação de Preço"
    html = (
        f"<p>A modelagem quantílica identificou <b>{kpis.below_band_sales_pct:.1f}%</b> dos pedidos "
        f"faturados abaixo da banda justa (P25), concentrando <b>{leak_str}</b> de vazamento sem "
        f"contrapartida de volume ou porte — com destaque na linha <b>{top_fam}</b> ({top_rep}).</p>"
        f"<p>Nas famílias inelásticas, há espaço adicional de <b>{upside_str}</b> para recomposição "
        f"gradual de tabela sem erosão de giro.</p>"
    )
    return title, html, round(recoverable, 2)


def build_pricing_dashboard(
    repo: DataRepository,
    scenario_id: ScenarioId = "c1_toys",
    *,
    regiao: str = "Todas",
    uf: str = "Todas",
    families: Sequence[str] = (),
    sales_reps: Sequence[str] = (),
    start_date_key: int | None = None,
    end_date_key: int | None = None,
) -> PricingPageDTO:
    """Consolida o payload completo da Aba 3 de 3. Justiça (Precificação, Banda & SHAP)."""
    raw_kpis = query_filtered_pricing_kpis(
        repo,
        scenario_id,
        regiao=regiao,
        uf=uf,
        families=families,
        sales_reps=sales_reps,
        start_date_key=start_date_key,
        end_date_key=end_date_key,
    )
    kpis = PricingKpisDTO(**raw_kpis)
    boxplot_df = query_pricing_boxplot_data(
        repo,
        scenario_id,
        regiao=regiao,
        uf=uf,
        families=families,
        sales_reps=sales_reps,
        start_date_key=start_date_key,
        end_date_key=end_date_key,
    )
    deviations_df = query_pricing_deviations(
        repo,
        scenario_id,
        regiao=regiao,
        uf=uf,
        families=families,
        sales_reps=sales_reps,
        start_date_key=start_date_key,
        end_date_key=end_date_key,
    )
    shap_options_df = query_pricing_shap_options(repo, scenario_id, families=families)
    family_bands_df = query_family_pricing_bands(repo, scenario_id)
    title, html, impact = build_pricing_prescription(kpis, deviations_df)

    return PricingPageDTO(
        scenario_id=scenario_id,
        kpis=kpis,
        boxplot_df=boxplot_df,
        deviations_df=deviations_df,
        shap_options_df=shap_options_df,
        family_bands_df=family_bands_df,
        prescription_title=title,
        prescription_html=html,
        prescription_impact_brl=impact,
    )


def get_pricing_shap_waterfall(
    repo: DataRepository,
    scenario_id: ScenarioId = "c1_toys",
    *,
    scope_type: str,
    scope_id: str,
    regiao: str = "Todas",
    uf: str = "Todas",
    families: Sequence[str] = (),
    sales_reps: Sequence[str] = (),
    start_date_key: int | None = None,
    end_date_key: int | None = None,
) -> PricingShapDTO:
    """Retorna os 5 drivers Linear SHAP (% e R$) para o Waterfall de Formação de Preço."""
    df, fin_stats = query_pricing_shap_drivers(
        repo,
        scenario_id,
        scope_type=scope_type,
        scope_id=scope_id,
        regiao=regiao,
        uf=uf,
        families=families,
        sales_reps=sales_reps,
        start_date_key=start_date_key,
        end_date_key=end_date_key,
    )
    if df.empty:
        return PricingShapDTO(
            scope_type=scope_type,
            scope_id=scope_id,
            scope_label=scope_id,
            family="—",
            base_idx=100.0,
            expected_idx=100.0,
            realized_idx=100.0,
            unjustified_gap_pp=0.0,
            drivers_df=df,
        )

    r0 = df.iloc[0]
    base_idx = float(r0["base_idx"])
    expected_idx = float(r0["expected_idx"])
    table_gross = float(fin_stats.get("table_gross_brl", 0.0))
    realized_net = float(fin_stats.get("realized_net_brl", 0.0))

    if table_gross > 0.0:
        realized_idx = round((realized_net / table_gross) * 100.0, 2)
        unjustified_gap_pp = round(realized_idx - expected_idx, 2)
        expected_net = round(table_gross * (expected_idx / 100.0), 2)
        unjustified_gap_brl = round(realized_net - expected_net, 2)
        work_df = df.copy()
        work_df["shap_impact_brl"] = (work_df["shap_impact_pp"].astype(float) / 100.0 * table_gross).round(2)
    else:
        realized_idx = float(r0["realized_idx"])
        unjustified_gap_pp = float(r0["unjustified_gap_pp"])
        expected_net = 0.0
        unjustified_gap_brl = 0.0
        work_df = df.copy()
        work_df["shap_impact_brl"] = 0.0

    return PricingShapDTO(
        scope_type=str(r0["scope_type"]),
        scope_id=str(r0["scope_id"]),
        scope_label=str(r0["scope_label"]),
        family=str(r0["family"]),
        base_idx=base_idx,
        expected_idx=expected_idx,
        realized_idx=realized_idx,
        unjustified_gap_pp=unjustified_gap_pp,
        table_gross_brl=table_gross,
        expected_net_brl=expected_net,
        realized_net_brl=realized_net,
        unjustified_gap_brl=unjustified_gap_brl,
        avg_base_unit_brl=float(fin_stats.get("avg_base_unit_brl", 0.0)),
        units_sold=int(fin_stats.get("units_sold", 0)),
        drivers_df=work_df,
    )
