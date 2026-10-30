from __future__ import annotations

import streamlit as st


def render_page() -> None:
    """Renderiza a página 'Inteligência de Estoque & Demanda'."""
    st.title("📦 Inteligência de Estoque & Demanda")
    st.caption("Forecast 30 dias via StatsForecast, semáforo de ruptura e destravamento de capital parado.")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(
            """
            <div class="kpi-card kpi-card-neg">
                <div class="kpi-title">Ruptura Iminente (&lt; 15 dias)</div>
                <div class="kpi-value">14 SKUs</div>
                <div class="kpi-subfooter">
                    <span>Receita em risco</span>
                    <span class="badge badge-negative">R$ 215.000</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            """
            <div class="kpi-card kpi-card-brass">
                <div class="kpi-title">Capital Travado (&gt; 120 dias)</div>
                <div class="kpi-value">R$ 680.000</div>
                <div class="kpi-subfooter">
                    <span>29 SKUs parados</span>
                    <span class="badge badge-warning">Ação de giro</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col3:
        st.markdown(
            """
            <div class="kpi-card kpi-card-teal">
                <div class="kpi-title">Acurácia do Forecast (WMAPE)</div>
                <div class="kpi-value">88,4%</div>
                <div class="kpi-subfooter">
                    <span>Horizonte: 30 dias</span>
                    <span class="badge badge-positive">AutoETS / Croston</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("---")

    st.info(
        "Módulo de projeção estatística e dimensionamento de estoque de segurança com ligação no Marco M4."
    )

    # Bloco Prescritivo Estoque
    st.markdown(
        """
        <div class="prescription-box">
            <div class="prescription-title">📦 Prescrição de Reposição e Desova</div>
            <div class="prescription-content">
                Emitir ordem de produção urgente para <strong>5.200 unidades da Linha Educativa</strong>
                e aplicar <strong>kit promocional com bonificação de 5%</strong>
                nos 8 itens com cobertura superior a 150 dias.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


render_page()
