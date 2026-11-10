from __future__ import annotations

import streamlit as st

from src.services.dto import TemperancePageDTO
from src.ui.components.charts import abc_xyz_heatmap
from src.ui.components.prescription import section_header
from src.ui.formatting import (
    format_brl,
    format_int,
)


def _fmt_brl(x: object) -> str:
    return format_brl(float(str(x)))


def _fmt_int(x: object) -> str:
    return format_int(int(float(str(x))))


def _fmt_days(x: object) -> str:
    return f"{float(str(x)):.1f}d"


def _fmt_days_int(x: object) -> str:
    return f"{int(float(str(x)))}d"


def _fmt_boxes(x: object) -> str:
    return f"{float(str(x)):.1f}"


def render_locked_inventory_table(dto: TemperancePageDTO) -> None:
    """Renderiza a tabela de SKUs com capital imobilizado com scroll interno."""
    st.markdown(
        f"**Diagnóstico de Imobilização:** Total de **{format_brl(dto.kpis.locked_capital_brl)}** "
        f"travados em {dto.kpis.locked_skus_count} produtos. Uma liquidação de 25% pode liberar "
        f"**{format_brl(dto.kpis.locked_capital_brl * 0.25)}** imediatos para o caixa operacional."
    )
    if not dto.locked_inventory_df.empty:
        cols_locked = [
            "product_id",
            "product_name",
            "family",
            "stock_units",
            "stock_boxes",
            "stock_value_brl",
            "coverage_days",
            "cell",
            "action_prescription",
        ]
        df_l_show = dto.locked_inventory_df[cols_locked].copy()
        df_l_show.columns = [
            "Código",
            "Produto",
            "Família",
            "Unidades",
            "Caixas Master",
            "Valor em Estoque (R$)",
            "Cobertura (dias)",
            "Célula",
            "Prescrição Operacional",
        ]
        st.dataframe(
            df_l_show.head(15).style.format(
                {
                    "Unidades": _fmt_int,
                    "Caixas Master": _fmt_boxes,
                    "Valor em Estoque (R$)": _fmt_brl,
                    "Cobertura (dias)": _fmt_days,
                }
            ),
            use_container_width=True,
            hide_index=True,
            height=210,
        )


def render_stockout_risk_table(dto: TemperancePageDTO) -> None:
    """Renderiza a tabela de semáforo de ruptura com ordens em caixas master e scroll interno."""
    total_boxes = (
        int(dto.stockout_risk_df["suggested_order_boxes"].sum()) if not dto.stockout_risk_df.empty else 0
    )
    risk_rev = format_brl(dto.kpis.stockout_risk_revenue_brl)
    count_skus = dto.kpis.stockout_risk_skus_count
    st.markdown(
        f"**Alerta de Desabastecimento:** {count_skus} SKUs essenciais possuem estoque "
        f"inferior ao lead time de entrega, colocando **{risk_rev}** em risco de ruptura. "
        f"Sugestão de reposição imediata: **{format_int(total_boxes)} Caixas Master**."
    )
    if not dto.stockout_risk_df.empty:
        cols_rup = [
            "product_id",
            "product_name",
            "family",
            "stock_boxes",
            "coverage_days",
            "lead_time_days",
            "suggested_order_boxes",
            "revenue_at_risk_brl",
            "cell",
        ]
        df_r_show = dto.stockout_risk_df[cols_rup].copy()
        df_r_show.columns = [
            "Código",
            "Produto",
            "Família",
            "Estoque Atual (cx)",
            "Cobertura (dias)",
            "Lead Time (dias)",
            "Ordem Sugerida (cx)",
            "Receita em Risco (R$)",
            "Célula",
        ]
        st.dataframe(
            df_r_show.head(15).style.format(
                {
                    "Estoque Atual (cx)": _fmt_boxes,
                    "Cobertura (dias)": _fmt_days,
                    "Lead Time (dias)": _fmt_days_int,
                    "Ordem Sugerida (cx)": _fmt_int,
                    "Receita em Risco (R$)": _fmt_brl,
                }
            ),
            use_container_width=True,
            hide_index=True,
            height=210,
        )


@st.fragment
def render_temperance_inventory_section(dto: TemperancePageDTO, theme_mode: str) -> None:
    """Fragmento isolado para exploração de estoque imobilizado e semáforo de ruptura em caixas master."""
    section_header(
        "Gestão Prescritiva de Estoque & Capital de Giro",
        "Matriz 3x3 ABC/XYZ cruzada com controle de capital travado (> 120d) e ruptura na Curva A",
        help_text="Cruza a contribuição na margem (ABC) com a volatilidade semanal da demanda (XYZ).",
    )

    matrix_df = dto.abc_xyz_summary_df.copy()
    if not matrix_df.empty and "recommended_policy" not in matrix_df.columns:
        matrix_df["recommended_policy"] = matrix_df["policy"]

    fig_abc = abc_xyz_heatmap(matrix_df, theme_mode=theme_mode)
    st.plotly_chart(fig_abc, use_container_width=True)

    tab_locked, tab_rupture = st.tabs(
        [
            f"🛑 Capital Imobilizado ({dto.kpis.locked_skus_count} SKUs com > 120 dias)",
            f"🚨 Semáforo de Ruptura ({dto.kpis.stockout_risk_skus_count} SKUs Curva A/B)",
        ]
    )

    with tab_locked:
        render_locked_inventory_table(dto)

    with tab_rupture:
        render_stockout_risk_table(dto)
