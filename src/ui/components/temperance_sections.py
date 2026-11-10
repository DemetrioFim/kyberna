from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.services.dto import TemperancePageDTO
from src.ui.components.charts import waterfall_margin
from src.ui.components.kpi_card import (
    info_tooltip_html,
    render_kpi_card,
)
from src.ui.components.prescription import (
    render_prescription_box,
    section_header,
)
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


def render_temperance_banner(dto: TemperancePageDTO) -> None:
    """Exibe barra informativa discreta sobre o escopo de Temperança e disciplina de margem."""
    st.markdown(
        """
        <div style="background-color: var(--kyb-card-bg); border-left: 4px solid var(--kyb-teal);
                    padding: 8px 14px; border-radius: 6px; margin-bottom: 0.85rem;
                    border: 1px solid var(--kyb-border);">
            <span style="font-weight: 600; font-size: 0.82rem; color: var(--kyb-text);">
                4. TEMPERANÇA & DISCIPLINA OPERACIONAL
            </span>
            <span style="color: var(--kyb-text-muted); font-size: 0.82rem;">
                — Auditoria de erosão comercial, descontos fora de tabela e destravamento de capital.
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_temperance_headline(dto: TemperancePageDTO) -> None:
    """Renderiza a manchete executiva dinâmica e contextualizada da Temperança."""
    info_html = info_tooltip_html(
        "Diagnóstico quantificado das perdas estancáveis: excesso de descontos acima da política de tabela "
        "e valor imobilizado em produtos com giro superior a 120 dias.",
        align="left",
    )
    h_box = (
        f'<div style="background: var(--kyb-card-bg); border-left: 4px solid var(--kyb-teal); '
        f"border: 1px solid var(--kyb-border); padding: 0.85rem 1.25rem; border-radius: 6px; "
        f'margin: 0.25rem 0 1.25rem 0;">'
        f'<div style="font-size: 0.82rem; font-weight: 700; text-transform: uppercase; '
        f"letter-spacing: 0.05em; color: var(--kyb-teal); margin-bottom: 0.35rem; display: flex; "
        f'justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem;">'
        f"<span>{dto.headline_title}{info_html}</span>"
        f'<span style="font-size: 0.78rem; font-weight: 500; text-transform: none; '
        f'color: var(--kyb-text-muted);">'
        f"<span>Data de Corte: <strong>{dto.as_of_date_label}</strong></span>"
        f"</span>"
        f"</div>"
        f'<div style="font-size: 0.90rem; color: var(--kyb-text); line-height: 1.45;">'
        f"{dto.headline_text}"
        f"</div>"
        f"</div>"
    )
    st.markdown(h_box, unsafe_allow_html=True)


def render_temperance_kpi_cards(dto: TemperancePageDTO) -> None:
    """Renderiza os 5 KPI Cards estruturados com ícones de informação e bordas temáticas."""
    kpis = dto.kpis
    c1, c2, c3, c4, c5 = st.columns(5)

    with c1:
        render_kpi_card(
            title="Erosão Comercial Total",
            value=format_brl(kpis.total_commercial_erosion_brl, compact=True, decimals=1),
            subfooter_left=f"Sangria: {kpis.total_commercial_erosion_pct:.1f}% da receita",
            accent="teal",
            help_text="Deduções entre faturamento bruto e lucro: descontos, comissões de RCAs e frete CIF.",
        )

    with c2:
        render_kpi_card(
            title="Descontos Fora de Tabela",
            value=format_brl(kpis.excess_discount_brl, compact=True, decimals=1),
            subfooter_left=f"{kpis.excess_discount_pct_of_discount:.1f}% dos descontos",
            accent="red",
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
        render_kpi_card(
            title="Ruptura Iminente (Curva A)",
            value=f"{kpis.stockout_risk_skus_count} SKUs",
            subfooter_left=f"Risco: {format_brl(kpis.stockout_risk_revenue_brl, compact=True, decimals=1)}",
            accent="neg",
            help_text="Produtos Curva A e B com estoque físico atual menor ou igual ao lead time de entrega.",
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


def render_commercial_erosion_and_policy_section(dto: TemperancePageDTO, theme_mode: str) -> None:
    """Renderiza a Seção 1 em 2 colunas: Waterfall da Margem Real e Auditoria de Descontos e Prazos."""
    col_wat, col_audit = st.columns([1, 1])

    with col_wat:
        section_header(
            "Decomposição da Margem Real",
            "Do faturamento bruto até o lucro líquido no bolso com % de perda em cada degrau",
            help_text="Deduções da receita bruta. As barras exibem o valor e a % do faturamento bruto.",
        )
        fig_wat = waterfall_margin(dto.waterfall_df, theme_mode=theme_mode)
        st.plotly_chart(fig_wat, use_container_width=True)

    with col_audit:
        section_header(
            "Auditoria de Política Comercial & Prazos",
            "Identificação de descontos fora de tabela e custos ocultos de prazo esticado",
            help_text="Auditoria com as regras de discounts.yaml e working_capital.yaml.",
        )
        if not dto.policy_violations_by_rep_df.empty:
            fig_rep = render_violations_rep_chart(dto.policy_violations_by_rep_df, theme_mode=theme_mode)
            st.plotly_chart(fig_rep, use_container_width=True)
        render_policy_violations_tabs(dto)


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
