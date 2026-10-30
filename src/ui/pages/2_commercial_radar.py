from __future__ import annotations

import streamlit as st


def render_page() -> None:
    """Renderiza a página 'Radar Comercial, RFM & Antecipação de Churn'."""
    st.title("🎯 Radar Comercial & Antecipação de Churn")
    st.caption("Visão individualizada de ciclo de compra, matriz White Space e gestão de RCAs.")

    regiao = st.session_state.get("regiao", "Todas")
    uf = st.session_state.get("uf", "Todas")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(
            """
            <div class="kpi-card kpi-card-neg">
                <div class="kpi-title">Clientes em Risco Imediato</div>
                <div class="kpi-value">38 lojistas</div>
                <div class="kpi-subfooter">
                    <span>Delay Ratio &gt; 1.5</span>
                    <span class="badge badge-negative">R$ 840 mil em risco</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            """
            <div class="kpi-card kpi-card-brass">
                <div class="kpi-title">Oportunidade White Space</div>
                <div class="kpi-value">R$ 490.000</div>
                <div class="kpi-subfooter">
                    <span>Cross-sell prioritário</span>
                    <span class="badge badge-warning">64 carteiras</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col3:
        st.markdown(
            """
            <div class="kpi-card kpi-card-teal">
                <div class="kpi-title">RCAs Sob Gestão</div>
                <div class="kpi-value">28 representantes</div>
                <div class="kpi-subfooter">
                    <span>Top performance: 4</span>
                    <span class="badge badge-positive">Média 27% margem</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("---")

    st.info(
        f"Filtro ativo: Região `{regiao}` | UF `{uf}`. "
        "A esteira de Machine Learning (RFM, Churn e White Space) será integrada no Marco M3."
    )

    # Bloco Prescritivo Comercial
    st.markdown(
        """
        <div class="prescription-box">
            <div class="prescription-title">⚡ Ação Comercial Recomendada (Prioridade 1)</div>
            <div class="prescription-content">
                Disparar plano de recuperação para os <strong>top 10 lojistas em atraso no Sudeste</strong>
                via WhatsApp do RCA responsável. Potencial de recuperação imediata:
                <strong>R$ 180.000</strong> neste mês.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


render_page()
