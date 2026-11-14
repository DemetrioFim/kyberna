from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.services.dto import TemperancePageDTO
from src.services.inventory_dto import InventoryPageDTO
from src.ui.components.kpi_card import render_kpi_card
from src.ui.components.prescription import render_prescription_box
from src.ui.formatting import (
    format_brl,
    format_int,
)
from src.ui.theme import get_theme_tokens


def _fmt_brl(x: object) -> str:
    return format_brl(float(str(x)))


def _fmt_pct(x: object) -> str:
    return f"{float(str(x)):.1f}%"


def _fmt_int(x: object) -> str:
    return format_int(int(float(str(x))))


def _fmt_days(x: object) -> str:
    return f"{float(str(x)):.1f}d"


def _fmt_days_full(x: object) -> str:
    return f"{float(str(x)):.1f} dias"


def _fmt_days_int(x: object) -> str:
    return f"{int(float(str(x)))}d"


def _fmt_boxes(x: object) -> str:
    return f"{float(str(x)):.1f}"


def render_temperance_kpi_cards(
    dto: TemperancePageDTO,
    inv_dto: InventoryPageDTO | None = None,
) -> None:
    """Renderiza os 5 KPI Cards estruturados com ícones de informação e semântica de alerta."""
    kpis = dto.kpis
    c1, c2, c3, c4, c5 = st.columns(5)

    with c1:
        render_kpi_card(
            title="Erosão Comercial Total",
            value=format_brl(kpis.total_commercial_erosion_brl, compact=True, decimals=1),
            subfooter_left=f"Sangria: {kpis.total_commercial_erosion_pct:.1f}% da receita",
            accent="alert_warn",
            help_text="Deduções entre faturamento bruto e lucro: descontos, comissões de RCAs e frete CIF.",
        )

    with c2:
        render_kpi_card(
            title="Descontos Fora de Tabela",
            value=format_brl(kpis.excess_discount_brl, compact=True, decimals=1),
            subfooter_left=f"{kpis.excess_discount_pct_of_discount:.1f}% dos descontos",
            accent="alert_neg",
            help_text="Concedido acima do teto estipulado por porte (P=3%, M=6.5%, G=10.5%).",
        )

    with c3:
        render_kpi_card(
            title="Custo de Prazo Esticado",
            value=format_brl(kpis.financial_term_leak_brl, compact=True, decimals=1),
            subfooter_left="Prazo > 30 dias (1,35% a.m.)",
            accent="brass",
            help_text="Custo de carregamento financeiro de boletos esticados além do padrão de 30 dias.",
        )

    with c4:
        render_kpi_card(
            title="Capital Travado (>120d)",
            value=format_brl(kpis.locked_capital_brl, compact=True, decimals=1),
            subfooter_left=f"{kpis.locked_skus_count} SKUs parados",
            accent="gold",
            help_text="Valor contábil a custo de SKUs com cobertura de vendas > 120 dias.",
        )

    with c5:
        rup_skus_a = kpis.stockout_risk_skus_count
        rup_rev = (
            inv_dto.kpis.protected_revenue_brl
            if inv_dto is not None and inv_dto.kpis.protected_revenue_brl > 0.0
            else kpis.stockout_risk_revenue_brl
        )
        render_kpi_card(
            title="Ruptura Iminente (Curva A)",
            value=f"{rup_skus_a} SKUs",
            subfooter_left=f"Risco: {format_brl(rup_rev, compact=True, decimals=1)}",
            accent="alert_neg",
            help_text="SKUs Curva A com cobertura abaixo do ponto de pedido (lead time + SS).",
        )


def render_violations_rep_chart(df: pd.DataFrame, theme_mode: str) -> go.Figure:
    """Gera gráfico de barras horizontais com o ranking de excesso de desconto por RCA."""
    tokens = get_theme_tokens(theme_mode)
    template_name = "kyberna_dark" if theme_mode == "dark" else "kyberna_light"

    if df.empty:
        fig = go.Figure()
        fig.update_layout(template=template_name, title="Sem dados de violação")
        return fig

    top_df = df.head(8).iloc[::-1]
    fig = go.Figure(
        go.Bar(
            x=top_df["excess_discount_brl"].tolist(),
            y=top_df["rep_name"].tolist(),
            orientation="h",
            marker_color=tokens["negative"],
            text=[format_brl(float(v), compact=True, decimals=1) for v in top_df["excess_discount_brl"]],
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>Excesso Fora do Teto: R$ %{x:,.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        template=template_name,
        title=None,
        xaxis_title=None,
        margin={"l": 20, "r": 40, "t": 10, "b": 15},
        height=280,
    )
    return fig


def render_policy_violations_tabs(dto: TemperancePageDTO) -> None:
    """Renderiza as abas de auditoria de política comercial e custos de prazo com scroll interno."""
    t_reps, t_fams, t_terms = st.tabs(
        [
            "Por Representante (RCA)",
            "Por Família de Produto",
            "Custo Financeiro de Prazo",
        ]
    )

    with t_reps:
        if not dto.policy_violations_by_rep_df.empty:
            cols_show = [
                "rep_name",
                "total_orders",
                "gross_revenue",
                "avg_discount_pct",
                "excess_discount_brl",
            ]
            df_rep_table = dto.policy_violations_by_rep_df[cols_show].copy()
            df_rep_table.columns = [
                "Representante",
                "Pedidos",
                "Faturamento (R$)",
                "Desc. Médio %",
                "Excesso Fora do Teto (R$)",
            ]
            st.dataframe(
                df_rep_table.head(10).style.format(
                    {
                        "Faturamento (R$)": _fmt_brl,
                        "Desc. Médio %": _fmt_pct,
                        "Excesso Fora do Teto (R$)": _fmt_brl,
                        "Pedidos": _fmt_int,
                    }
                ),
                use_container_width=True,
                hide_index=True,
                height=210,
            )
        else:
            st.info("Nenhuma violação de política identificada para a seleção atual.")

    with t_fams:
        if not dto.policy_violations_by_family_df.empty:
            cols_fam = [
                "family",
                "total_orders",
                "gross_revenue",
                "avg_discount_pct",
                "excess_discount_brl",
            ]
            df_fam_table = dto.policy_violations_by_family_df[cols_fam].copy()
            df_fam_table.columns = [
                "Família",
                "Pedidos",
                "Faturamento (R$)",
                "Desc. Médio %",
                "Excesso Fora do Teto (R$)",
            ]
            st.dataframe(
                df_fam_table.style.format(
                    {
                        "Faturamento (R$)": _fmt_brl,
                        "Desc. Médio %": _fmt_pct,
                        "Excesso Fora do Teto (R$)": _fmt_brl,
                        "Pedidos": _fmt_int,
                    }
                ),
                use_container_width=True,
                hide_index=True,
                height=210,
            )

    with t_terms:
        if not dto.term_leak_by_rep_df.empty:
            cols_term = ["rep_name", "avg_pmr_days", "term_leak_brl"]
            df_term_table = dto.term_leak_by_rep_df[cols_term].copy()
            df_term_table.columns = [
                "Representante",
                "Prazo Médio (dias)",
                "Custo Financeiro de Prazo (R$)",
            ]
            st.dataframe(
                df_term_table.head(10).style.format(
                    {
                        "Prazo Médio (dias)": _fmt_days_full,
                        "Custo Financeiro de Prazo (R$)": _fmt_brl,
                    }
                ),
                use_container_width=True,
                hide_index=True,
                height=210,
            )


def render_temperance_verdict_section(dto: TemperancePageDTO) -> None:
    """Renderiza a caixa estilizada do veredito executivo e impacto financeiro quantificado."""
    render_prescription_box(
        title=dto.prescription_title,
        recommendation_html=dto.prescription_html,
        impact_brl=dto.prescription_impact_brl,
        help_text=(
            "Impacto calculado como a soma da liberação de capital em estoque parado (>120d) "
            "e da estancagem de descontos acima da tabela."
        ),
    )
