from __future__ import annotations

import pandas as pd
import streamlit as st

from src.services.export_service import (
    attach_whatsapp_links,
    dataframe_to_csv_bom,
    generate_commercial_action_excel,
)


def render_commercial_export_bar(
    risk_df: pd.DataFrame,
    white_space_df: pd.DataFrame,
    *,
    scenario_id: str,
    scenario_name: str,
) -> None:
    """Renderiza barra compacta de ação em 1 clique para download Excel (por RCA) e CSV BR."""
    has_data = not risk_df.empty or not white_space_df.empty

    if has_data:
        excel_bytes = generate_commercial_action_excel(risk_df, white_space_df, scenario_name)
        risk_export = attach_whatsapp_links(
            risk_df,
            pitch_col="top_opportunity_pitch",
            fallback_pitch="Condição especial de reativação de pedido",
        )
        csv_bytes = dataframe_to_csv_bom(risk_export)
    else:
        excel_bytes = b""
        csv_bytes = b""

    c_xlsx, c_csv = st.columns(2)
    with c_xlsx:
        st.download_button(
            label="Exportar Plano por RCA (.xlsx)",
            data=excel_bytes,
            file_name=f"plano_acao_{scenario_id}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            disabled=not has_data,
            help=(
                "Gera planilha Excel formatada com aba geral priorizada, oportunidades White Space, "
                "1 aba individual por RCA e links clicáveis de WhatsApp."
            ),
        )
    with c_csv:
        st.download_button(
            label="Exportar Lista Priorizada (.csv)",
            data=csv_bytes,
            file_name=f"clientes_risco_{scenario_id}.csv",
            mime="text/csv",
            use_container_width=True,
            disabled=not has_data,
            help="Exporta CSV com separador ';' e BOM UTF-8 para abertura imediata no Excel BR.",
        )

