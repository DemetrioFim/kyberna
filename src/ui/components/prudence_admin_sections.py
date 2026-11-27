from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pandas as pd
import streamlit as st

from src.services.dto import ExecutivePageDTO, TemperancePageDTO
from src.services.inventory_dto import InventoryPageDTO
from src.ui.components.kpi_card import KpiAccent, render_kpi_card
from src.ui.formatting import fmt_brl_cell, fmt_int_cell, fmt_pct_cell, format_brl, format_int


def _cell_stats(matrix_df: pd.DataFrame, abc: str, xyz: str) -> tuple[int, float]:
    """Extrai quantidade de SKUs e % de MC de uma célula da Matriz ABC/XYZ."""
    if matrix_df.empty or "abc_class" not in matrix_df.columns or "xyz_class" not in matrix_df.columns:
        return 0, 0.0
    sub = matrix_df[(matrix_df["abc_class"] == abc) & (matrix_df["xyz_class"] == xyz)]
    if sub.empty:
        return 0, 0.0
    share_col = "margin_share_pct" if "margin_share_pct" in sub.columns else "margin_pct"
    return int(sub["sku_count"].iloc[0]), float(sub[share_col].iloc[0])


def render_admin_portfolio_kpis(exec_dto: ExecutivePageDTO, inv_dto: InventoryPageDTO) -> None:
    """Renderiza os 5 KPIs da Aba 1 (Portfólio & Curva ABC/XYZ) de Prudência Administrativa."""
    skus_df = exec_dto.abc_xyz_skus_df
    matrix_df = exec_dto.abc_xyz_matrix_df
    sku_total = (
        len(skus_df)
        if (not skus_df.empty or exec_dto.kpis.total_orders == 0)
        else len(inv_dto.sku_options_df)
    )
    fam_count = int(skus_df["family"].nunique()) if not skus_df.empty and "family" in skus_df.columns else 0

    if not skus_df.empty and "abc_class" in skus_df.columns:
        curva_a_df = skus_df[skus_df["abc_class"] == "A"]
    elif not skus_df.empty and "abc_xyz_class" in skus_df.columns:
        curva_a_df = skus_df[skus_df["abc_xyz_class"].astype(str).str.startswith("A")]
    else:
        curva_a_df = skus_df.iloc[0:0]

    curva_a_skus = len(curva_a_df)
    curva_a_mix_pct = (curva_a_skus / sku_total * 100.0) if sku_total > 0 else 0.0
    curva_a_gross = float(curva_a_df["gross_revenue"].sum()) if not curva_a_df.empty else 0.0
    curva_a_cm = float(curva_a_df["contribution_margin"].sum()) if not curva_a_df.empty else 0.0
    curva_a_mc_pct = (curva_a_cm / curva_a_gross * 100.0) if curva_a_gross > 0.0 else 0.0

    ax_skus, ax_share = _cell_stats(matrix_df, "A", "X")
    cz_skus, cz_share = _cell_stats(matrix_df, "C", "Z")
    net_rev_str = format_brl(exec_dto.kpis.net_revenue, compact=True, decimals=1)

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        render_kpi_card(
            title="SKUs Ativos no Portfólio",
            value=f"{format_int(sku_total)} SKUs",
            subfooter_left=f"{fam_count} famílias ativas",
            accent="teal",
            help_text="Total de SKUs ativos no catálogo que registraram movimentação no filtro atual.",
        )
    with c2:
        render_kpi_card(
            title="Margem de Contribuição Total",
            value=format_brl(exec_dto.kpis.contribution_margin, compact=True),
            subfooter_left=f"Receita Líq.: {net_rev_str} · MC {exec_dto.kpis.contribution_margin_pct:.1f}%",
            accent="green",
            help_text=("Denominador financeiro completo do portfólio após impostos, CPV, comissões e frete."),
        )
    with c3:
        render_kpi_card(
            title="SKUs na Curva A",
            value=f"{format_int(curva_a_skus)} SKUs",
            subfooter_left=f"{curva_a_mix_pct:.1f}% do mix · MC {curva_a_mc_pct:.1f}%",
            accent="teal",
            help_text=(
                "Quantidade de SKUs que compõem os 80% principais da Margem de Contribuição (Pareto ABC)."
            ),
        )
    with c4:
        render_kpi_card(
            title="SKUs Classe AX (Core)",
            value=f"{format_int(ax_skus)} SKUs",
            subfooter_left=f"{ax_share:.1f}% da MC Total",
            accent="teal",
            help_text="Produtos de alta margem (A) e demanda regular (X): política JIT / ruptura zero.",
        )
    with c5:
        render_kpi_card(
            title="SKUs Classe CZ (Cauda)",
            value=f"{format_int(cz_skus)} SKUs",
            subfooter_left=f"{cz_share:.1f}% da MC Total",
            accent="alert_warn" if cz_skus > 40 else "brass",
            help_text=(
                "Itens de baixa margem (C) e giro intermitente (Z): candidatos a venda sob encomenda."
            ),
        )


def render_admin_inventory_kpis(
    temp_dto: TemperancePageDTO,
    inv_dto: InventoryPageDTO,
    *,
    is_scoped: bool = False,
) -> None:
    """Renderiza os 5 KPIs da Aba 2 (Estoque, Ruptura & Capital Travado) de Prudência."""
    t_k = temp_dto.kpis
    i_k = inv_dto.kpis
    locked_cap = i_k.locked_capital_brl if i_k.locked_capital_brl > 0 else t_k.locked_capital_brl
    locked_cnt = i_k.locked_skus_count if i_k.locked_skus_count > 0 else t_k.locked_skus_count
    rup_a_skus = (
        i_k.stockout_curve_a_skus_count
        if i_k.stockout_curve_a_skus_count > 0
        else t_k.stockout_risk_skus_count
    )
    prot_rev = i_k.protected_revenue_brl if i_k.protected_revenue_brl > 0 else t_k.stockout_risk_revenue_brl
    stock_total_str = format_brl(i_k.total_stock_value_brl, compact=True, decimals=1)
    scope_suffix = " · Armazém global" if is_scoped else ""

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        render_kpi_card(
            title="Capital Travado (>120d)",
            value=format_brl(locked_cap, compact=True, decimals=1),
            subfooter_left=f"Estoque total: {stock_total_str}{scope_suffix}",
            accent="gold",
            help_text=(
                "Capital imobilizado a custo contábil no estoque excedente acima de 120 dias de cobertura "
                "(posição corporativa do armazém)."
            ),
        )
    with c2:
        render_kpi_card(
            title="SKUs Imobilizados (>120d)",
            value=f"{format_int(locked_cnt)} SKUs",
            subfooter_left=f"Saudáveis: {format_int(i_k.healthy_skus_count)} SKUs",
            accent="alert_warn" if locked_cnt > 0 else "green",
            help_text="Quantidade de SKUs com excesso crônico de cobertura, exigindo campanhas de saldo.",
        )
    with c3:
        render_kpi_card(
            title="Ruptura Iminente (Curva A)",
            value=f"{format_int(rup_a_skus)} SKUs",
            subfooter_left=f"Total abaixo ROP: {format_int(i_k.stockout_risk_skus_count)} SKUs",
            accent="alert_neg",
            help_text=(
                "SKUs de Curva A com estoque abaixo do Ponto de Pedido (Lead Time + Estoque de Segurança). "
                "O rodapé indica o total de todas as curvas (A/B/C) abaixo do ROP."
            ),
        )
    with c4:
        curva_a_rev = format_brl(i_k.stockout_curve_a_revenue_brl, compact=True, decimals=1)
        render_kpi_card(
            title="Receita Protegida (Ruptura)",
            value=format_brl(prot_rev, compact=True, decimals=1),
            subfooter_left=f"Curva A: {curva_a_rev}",
            accent="alert_neg",
            help_text=(
                "Faturamento potencial preservado nos próximos 30 dias ao executar o ressuprimento imediato "
                "de todos os itens abaixo do ROP."
            ),
        )
    with c5:
        render_kpi_card(
            title="Ordem Sugerida (Reposição)",
            value=f"{format_int(i_k.suggested_order_boxes_total)} cx",
            subfooter_left="Caixas master abaixo do ROP",
            accent="teal",
            help_text=(
                "Soma de caixas master recomendadas para normalizar todos os itens abaixo do Ponto de Pedido."
            ),
        )


def render_admin_pcp_kpis(inv_dto: InventoryPageDTO) -> None:
    """Renderiza os 5 KPIs S&OP/PCP da Aba 3 (Previsão de Demanda 30d & PCP)."""
    i_k = inv_dto.kpis
    wape_acc: KpiAccent = "green" if i_k.weighted_wape_pct <= 25.0 else "alert_warn"
    delta_acc: KpiAccent = "teal" if i_k.forecast_vs_30d_pct >= 0.0 else "brass"

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        render_kpi_card(
            title="Projeção de Demanda (30d)",
            value=format_brl(i_k.forecast_30d_revenue_brl, compact=True, decimals=2),
            subfooter_left=f"{format_int(i_k.forecast_30d_units_total)} un previstas (30d)",
            accent="teal",
            help_text=(
                "Soma da demanda prevista pelo StatsForecast nos próximos 30 dias valorizada a preço de "
                "lista para os SKUs filtrados."
            ),
        )
    with c2:
        render_kpi_card(
            title="Acurácia do Motor (WAPE)",
            value=f"{i_k.weighted_wape_pct:.1f}%",
            subfooter_left="Ponderado · AutoETS / Croston",
            accent=wape_acc,
            help_text=(
                "Erro percentual absoluto ponderado pelo volume previsto (WAPE) no holdout temporal "
                "sem vazamento de 28 dias."
            ),
        )
    with c3:
        render_kpi_card(
            title="Variação Projetada (vs. 30d)",
            value=f"{i_k.forecast_vs_30d_pct:+.1f}%",
            subfooter_left=f"Real últimos 30d: {format_int(i_k.last_30d_actual_units)} un",
            accent=delta_acc,
            help_text=(
                "Diferença percentual do volume previsto para os próximos 30 dias frente ao realizado "
                "nos últimos 30 dias históricos."
            ),
        )
    with c4:
        render_kpi_card(
            title="Necessidade de Compra",
            value=f"{format_int(i_k.suggested_order_boxes_total)} cx",
            subfooter_left=f"{format_int(i_k.stockout_risk_skus_count)} SKUs abaixo do ROP",
            accent="alert_neg" if i_k.suggested_order_boxes_total > 0 else "green",
            help_text="Volume total de reposição em caixas master requerido pelo planejamento PCP.",
        )
    with c5:
        render_kpi_card(
            title="SKUs com Pico Sazonal",
            value=f"{format_int(i_k.seasonal_peak_skus_count)} SKUs",
            subfooter_left="Classe Y com ordem ativa",
            accent="alert_warn" if i_k.seasonal_peak_skus_count > 0 else "teal",
            help_text=(
                "Itens de comportamento sazonal (Classe Y) que demandam reposição imediata para "
                "atender o próximo ciclo de demanda."
            ),
        )


def render_sku_portfolio_table(exec_dto: ExecutivePageDTO) -> None:
    """Renderiza a tabela operacional de Portfólio de SKUs sem corte horizontal."""
    if exec_dto.abc_xyz_skus_df.empty:
        st.info("Nenhum SKU disponível para a seleção atual.")
        return

    df_src = exec_dto.abc_xyz_skus_df.copy()
    if "policy" in df_src.columns:
        df_src["policy_short"] = df_src["policy"].astype(str).str.split("/", n=1).str[0].str.strip()
    cols_src = [
        c
        for c in (
            "product_name",
            "family",
            "abc_xyz_class",
            "gross_revenue",
            "contribution_margin",
            "margin_pct",
            "policy_short",
        )
        if c in df_src.columns
    ]
    sku_view = df_src[cols_src].rename(
        columns={
            "product_name": "Produto",
            "family": "Família",
            "abc_xyz_class": "Célula",
            "gross_revenue": "Fat. Bruto",
            "contribution_margin": "MC (R$)",
            "margin_pct": "MC %",
            "policy_short": "Política",
        }
    )
    fmt_map: dict[Any, str | Callable[[object], str] | None] = {
        k: fn
        for k, fn in (
            ("Fat. Bruto", fmt_brl_cell),
            ("MC (R$)", fmt_brl_cell),
            ("MC %", fmt_pct_cell),
        )
        if k in sku_view.columns
    }
    st.dataframe(
        sku_view.style.format(fmt_map),
        use_container_width=True,
        height=185,
        hide_index=True,
        column_config={
            "Célula": st.column_config.TextColumn("Célula", width="small"),
            "MC %": st.column_config.TextColumn("MC %", width="small"),
        },
    )


def render_pcp_plan_table(inv_dto: InventoryPageDTO) -> None:
    """Renderiza a tabela do Plano Mestre de Necessidade de Compra/Produção por SKU."""
    df = inv_dto.pcp_plan_df
    if df.empty:
        st.info("Nenhuma necessidade de compra/produção crítica nos filtros atuais.")
        return

    cols_src = [
        c
        for c in (
            "product_name",
            "family",
            "abc_xyz_class",
            "stock_units",
            "forecast_30d_units",
            "reorder_point_units",
            "suggested_order_boxes",
            "protected_revenue_brl",
        )
        if c in df.columns
    ]
    view = (
        df[cols_src]
        .head(30)
        .rename(
            columns={
                "product_name": "Produto",
                "family": "Família",
                "abc_xyz_class": "Célula",
                "stock_units": "Est. (un)",
                "forecast_30d_units": "Dem. 30d",
                "reorder_point_units": "ROP",
                "suggested_order_boxes": "Ordem (cx)",
                "protected_revenue_brl": "Receita Prot.",
            }
        )
    )
    fmt_map: dict[Any, str | Callable[[object], str] | None] = {
        k: fn
        for k, fn in (
            ("Est. (un)", fmt_int_cell),
            ("Dem. 30d", fmt_int_cell),
            ("ROP", fmt_int_cell),
            ("Ordem (cx)", fmt_int_cell),
            ("Receita Prot.", fmt_brl_cell),
        )
        if k in view.columns
    }
    st.dataframe(
        view.style.format(fmt_map),
        use_container_width=True,
        height=185,
        hide_index=True,
        column_config={
            "Produto": st.column_config.TextColumn("Produto", width="medium"),
            "Célula": st.column_config.TextColumn("Cél.", width="small"),
            "Est. (un)": st.column_config.TextColumn("Est.", width="small"),
            "Dem. 30d": st.column_config.TextColumn("Dem.30d", width="small"),
            "ROP": st.column_config.TextColumn("ROP", width="small"),
            "Ordem (cx)": st.column_config.TextColumn("Ordem", width="small"),
        },
    )
