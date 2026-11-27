from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pandas as pd
import streamlit as st

from src.services.export_service import attach_whatsapp_links
from src.ui.formatting import fmt_brl_cell, fmt_pct_cell


def render_margin_drivers_table(
    df: pd.DataFrame,
    is_generator: bool = True,
    *,
    height: int | None = None,
) -> None:
    """Renderiza a tabela de Top Geradores ou Destruidores de Margem de Contribuição."""
    del is_generator
    if df.empty:
        st.info("Nenhum registro encontrado para os filtros selecionados.")
        return

    cols_src = [
        c
        for c in (
            "name",
            "secondary_label",
            "gross_revenue",
            "discount_pct",
            "contribution_margin",
            "margin_pct",
        )
        if c in df.columns
    ]
    display_df = df[cols_src].rename(
        columns={
            "name": "Item / Parceiro",
            "secondary_label": "Família / Região",
            "gross_revenue": "Fat. Bruto",
            "discount_pct": "Desc. %",
            "contribution_margin": "MC (R$)",
            "margin_pct": "MC %",
        }
    )

    fmt_map: dict[str, Any] = {}
    if "Fat. Bruto" in display_df.columns:
        fmt_map["Fat. Bruto"] = fmt_brl_cell
    if "Desc. %" in display_df.columns:
        fmt_map["Desc. %"] = fmt_pct_cell
    if "MC (R$)" in display_df.columns:
        fmt_map["MC (R$)"] = fmt_brl_cell

    column_config: dict[str, Any] = {
        "MC %": st.column_config.ProgressColumn(
            "MC %",
            format="%.1f%%",
            min_value=0.0,
            max_value=100.0,
            help="Margem de contribuição percentual sobre o faturamento bruto",
        ),
    }

    styled = display_df.style.format(fmt_map) if fmt_map else display_df
    df_kwargs: dict[str, Any] = {
        "use_container_width": True,
        "hide_index": True,
        "column_config": column_config,
    }
    if height is not None:
        df_kwargs["height"] = height
    st.dataframe(styled, **df_kwargs)


def render_vampire_customers_expander(vampires_df: pd.DataFrame, customer_label: str) -> None:
    """Renderiza acesso rápido às contas Vampiro (<15% MC) na Aba 2 de 2. Fortaleza."""
    if vampires_df.empty:
        return
    with st.expander(
        f"Detalhamento: Clientes Vampiros (<15% MC · {len(vampires_df)} contas)", expanded=False
    ):
        cols = [
            c
            for c in (
                "customer_name",
                "state",
                "sales_rep_name",
                "gross_revenue",
                "avg_discount_pct",
                "contribution_margin",
                "margin_pct",
            )
            if c in vampires_df.columns
        ]
        view = vampires_df[cols].rename(
            columns={
                "customer_name": customer_label,
                "state": "UF",
                "sales_rep_name": "RCA",
                "gross_revenue": "Fat. Bruto",
                "avg_discount_pct": "Desc. %",
                "contribution_margin": "MC (R$)",
                "margin_pct": "MC %",
            }
        )
        fmt_map: dict[Any, str | Callable[[object], str] | None] = {
            k: fn
            for k, fn in (
                ("Fat. Bruto", fmt_brl_cell),
                ("Desc. %", fmt_pct_cell),
                ("MC (R$)", fmt_brl_cell),
                ("MC %", fmt_pct_cell),
            )
            if k in view.columns
        }
        st.dataframe(view.style.format(fmt_map), use_container_width=True, hide_index=True, height=160)


def render_silent_churn_expander(silent_churn_df: pd.DataFrame, customer_label: str) -> None:
    """Renderiza contas em Churn Silencioso (ciclo ativo mas queda >35% em 90d ou perda de mix)."""
    if silent_churn_df.empty:
        return
    with st.expander(
        f"Churn Silencioso: Queda de Volume/Mix ({len(silent_churn_df)} contas ativas no ciclo)",
        expanded=False,
    ):
        work = silent_churn_df.copy()
        work["_pitch"] = (
            "Notamos redução recente no seu volume de compras e separamos uma condição especial de reposição."
        )
        work = attach_whatsapp_links(
            work,
            pitch_col="_pitch",
            fallback_pitch="Condição especial de retomada de mix",
        )
        if "fams_prev" in work.columns and "fams_curr" in work.columns:
            work["mix_shift"] = [
                f"{int(p)} → {int(c)}" for p, c in zip(work["fams_prev"], work["fams_curr"], strict=False)
            ]
        cols = [
            c
            for c in (
                "customer_name",
                "state",
                "sales_rep_name",
                "rev_prev_90d",
                "rev_curr_90d",
                "drop_pct",
                "mix_shift",
                "whatsapp_link",
            )
            if c in work.columns
        ]
        view = work[cols].rename(
            columns={
                "customer_name": customer_label,
                "state": "UF",
                "sales_rep_name": "RCA",
                "rev_prev_90d": "90d Ant.",
                "rev_curr_90d": "90d Atual",
                "drop_pct": "Queda %",
                "mix_shift": "Famílias",
                "whatsapp_link": "WhatsApp",
            }
        )
        fmt_map: dict[Any, str | Callable[[object], str] | None] = {
            k: fn
            for k, fn in (
                ("90d Ant.", lambda v: fmt_brl_cell(v, decimals=0)),
                ("90d Atual", lambda v: fmt_brl_cell(v, decimals=0)),
                ("Queda %", fmt_pct_cell),
            )
            if k in view.columns
        }
        st.dataframe(
            view.style.format(fmt_map),
            use_container_width=True,
            hide_index=True,
            height=165,
            column_config={
                "UF": st.column_config.TextColumn("UF", width="small"),
                "WhatsApp": st.column_config.LinkColumn("WhatsApp", display_text="Chamar", width="small"),
            },
        )


def render_risk_expanders(
    vampires_df: pd.DataFrame,
    silent_churn_df: pd.DataFrame,
    customer_label: str,
) -> None:
    """Agrupa os expanders de Vampiros e Churn Silencioso na Aba 2 de 2. Fortaleza."""
    render_vampire_customers_expander(vampires_df, customer_label)
    render_silent_churn_expander(silent_churn_df, customer_label)
