from __future__ import annotations

import streamlit as st

from src.core.types import ScenarioId
from src.services.dto import TemperancePageDTO
from src.services.inventory_dto import InventoryPageDTO
from src.ui.cache import cached_sku_forecast
from src.ui.components.inventory_charts import (
    forecast_band_chart,
    locked_capital_treemap,
)
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
        '<div style="font-size:0.82rem; color:var(--kyb-text-muted); margin-bottom:0.25rem;">'
        f"Imobilização: <strong>{format_brl(dto.kpis.locked_capital_brl)}</strong> em "
        f"{dto.kpis.locked_skus_count} SKUs · Liquidação de 25% libera "
        f"<strong>{format_brl(dto.kpis.locked_capital_brl * 0.25)}</strong> no caixa."
        "</div>",
        unsafe_allow_html=True,
    )
    if not dto.locked_inventory_df.empty:
        val_col = (
            "locked_capital_brl"
            if "locked_capital_brl" in dto.locked_inventory_df.columns
            else "stock_value_brl"
        )
        val_label = "Excesso (R$)" if val_col == "locked_capital_brl" else "Valor (R$)"
        cols_locked = [
            "product_name",
            "family",
            "stock_units",
            "stock_boxes",
            val_col,
            "coverage_days",
            "cell",
            "action_prescription",
        ]
        df_l_show = dto.locked_inventory_df[cols_locked].copy()
        df_l_show.columns = [
            "Produto",
            "Família",
            "Unidades",
            "Cx Master",
            val_label,
            "Cobertura",
            "Célula",
            "Prescrição",
        ]
        st.dataframe(
            df_l_show.head(15).style.format(
                {
                    "Unidades": _fmt_int,
                    "Cx Master": _fmt_boxes,
                    val_label: _fmt_brl,
                    "Cobertura": _fmt_days,
                }
            ),
            use_container_width=True,
            hide_index=True,
            height=185,
        )


def render_stockout_risk_table(
    dto: TemperancePageDTO,
    inv_dto: InventoryPageDTO | None = None,
) -> None:
    """Renderiza a tabela de semáforo de ruptura com SS/ROP/ordens em caixas master."""
    if inv_dto is not None and not inv_dto.stockout_df.empty:
        total_boxes = inv_dto.kpis.suggested_order_boxes_total
        prot_rev = format_brl(inv_dto.kpis.protected_revenue_brl)
        count_skus = inv_dto.kpis.stockout_risk_skus_count
        st.caption(
            f"Reposição: {count_skus} SKUs abaixo do ROP · Receita protegida: {prot_rev} · "
            f"Ordem sugerida: {format_int(total_boxes)} cx master"
        )
        cols_pos = [
            "product_name",
            "family",
            "stock_boxes",
            "safety_stock_units",
            "reorder_point_units",
            "coverage_days",
            "suggested_order_boxes",
            "protected_revenue_brl",
            "abc_xyz_class",
        ]
        df_show = inv_dto.stockout_df[cols_pos].copy()
        df_show.columns = [
            "Produto",
            "Família",
            "Est. (cx)",
            "SS",
            "ROP",
            "Cobertura",
            "Ordem (cx)",
            "Receita Prot.",
            "Célula",
        ]
        st.dataframe(
            df_show.head(15).style.format(
                {
                    "Est. (cx)": _fmt_boxes,
                    "SS": _fmt_int,
                    "ROP": _fmt_int,
                    "Cobertura": _fmt_days,
                    "Ordem (cx)": _fmt_int,
                    "Receita Prot.": _fmt_brl,
                }
            ),
            use_container_width=True,
            hide_index=True,
            height=185,
        )
        return

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
            "Produto",
            "Família",
            "Est. (cx)",
            "Cobertura",
            "Lead Time",
            "Ordem (cx)",
            "Receita Risco",
            "Célula",
        ]
        st.dataframe(
            df_r_show.head(15).style.format(
                {
                    "Est. (cx)": _fmt_boxes,
                    "Cobertura": _fmt_days,
                    "Lead Time": _fmt_days_int,
                    "Ordem (cx)": _fmt_int,
                    "Receita Risco": _fmt_brl,
                }
            ),
            use_container_width=True,
            hide_index=True,
            height=185,
        )


@st.fragment
def render_sku_forecast_fragment(
    scenario_id: ScenarioId,
    inv_dto: InventoryPageDTO,
    *,
    theme_mode: str = "light",
) -> None:
    """Fragmento reativo para seleção de SKU e exibição do Forecast 30d com bandas 80%/95%."""
    opts_df = inv_dto.sku_options_df
    if opts_df.empty:
        st.info("Previsão 30d ainda não disponível para os filtros selecionados.")
        return

    sku_ids = opts_df["product_id"].astype(str).tolist()
    labels_map = {
        str(row["product_id"]): f"{row['product_name']} ({row['family']} · {row['abc_xyz_class']})"
        for _, row in opts_df.iterrows()
    }
    selected_sku = st.selectbox(
        "SKU para Forecast 30d",
        options=sku_ids,
        format_func=lambda pid: labels_map.get(str(pid), str(pid)),
        key="temperance_forecast_sku",
        label_visibility="collapsed",
    )
    fc_dto = cached_sku_forecast(scenario_id, str(selected_sku))
    st.caption(
        f"Modelo: **{fc_dto.selected_model}** | WAPE Família: **{fc_dto.family_wape_pct:.1f}%** | "
        f"MAE SKU: **{fc_dto.sku_mae:.2f}** | Demanda 30d Prevista: "
        f"**{format_int(round(fc_dto.forecast_30d_total_units))} un**"
    )
    fig = forecast_band_chart(fc_dto.series_df, theme_mode=theme_mode)
    st.plotly_chart(fig, use_container_width=True, theme=None)


def render_locked_capital_treemap_tab(
    inv_dto: InventoryPageDTO,
    *,
    theme_mode: str = "light",
) -> None:
    """Renderiza o Treemap de capital travado (>120d) reconciliado com o KPI de excesso."""
    st.caption(
        f"Capital Travado Excedente (>120d): **{format_brl(inv_dto.kpis.locked_capital_brl)}** "
        f"distribuído em **{inv_dto.kpis.locked_skus_count} SKUs**."
    )
    fig = locked_capital_treemap(inv_dto.treemap_df, theme_mode=theme_mode)
    st.plotly_chart(fig, use_container_width=True, theme=None)
