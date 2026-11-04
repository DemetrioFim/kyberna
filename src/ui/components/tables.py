from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st


def render_margin_drivers_table(
    df: pd.DataFrame,
    is_generator: bool = True,
) -> None:
    """Renderiza a tabela de Top Geradores ou Destruidores de Margem de Contribuição.

    Espera DataFrame com colunas:
        - `name`: Nome do produto ou razão social do lojista.
        - `secondary_label`: Família do produto ou UF/Segmento do cliente.
        - `gross_revenue`: Faturamento bruto (R$).
        - `discount_pct`: Desconto médio praticado (%).
        - `contribution_margin`: Margem de contribuição líquida (R$).
        - `margin_pct`: Margem de contribuição líquida (%).
    """
    if df.empty:
        st.info("Nenhum registro encontrado para os filtros selecionados.")
        return

    display_df = df.copy()

    # Renomeia colunas para cabeçalhos executivos em português
    col_mapping = {
        "name": "Item / Parceiro",
        "secondary_label": "Família / Região",
        "gross_revenue": "Fat. Bruto (R$)",
        "discount_pct": "Desconto (%)",
        "contribution_margin": "Margem Líquida (R$)",
        "margin_pct": "Margem Líquida (%)",
    }
    display_df = display_df.rename(columns=col_mapping)

    # Configuração de exibição tipada para o st.dataframe
    column_config: dict[str, Any] = {
        "Fat. Bruto (R$)": st.column_config.NumberColumn(
            "Fat. Bruto",
            format="R$ %.2f",
            help="Faturamento bruto tabelado faturado no período",
        ),
        "Desconto (%)": st.column_config.NumberColumn(
            "Desconto Médio",
            format="%.1f%%",
            help="Percentual médio de desconto comercial concedido",
        ),
        "Margem Líquida (R$)": st.column_config.NumberColumn(
            "Margem Líq. (R$)",
            format="R$ %.2f",
            help="Margem de contribuição líquida que sobrou no bolso da empresa",
        ),
        "Margem Líquida (%)": st.column_config.ProgressColumn(
            "Margem Líq. (%)",
            format="%.1f%%",
            min_value=0.0,
            max_value=100.0,
            help="Margem de contribuição percentual sobre a receita líquida",
        ),
    }

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config=column_config,
    )
