from __future__ import annotations

import streamlit as st


def render_page() -> None:
    """Renderiza a página 'Visão Executiva & Margem Real' com estado elegante."""
    st.title("📊 Visão Executiva & Margem Real")
    st.caption("Decomposição do faturamento bruto até a margem de contribuição líquida no bolso.")

    # Contexto e filtros selecionados
    scenario_id = st.session_state.get("scenario_id", "c1_toys")
    theme_mode = st.session_state.get("theme_mode", "light")
    regiao = st.session_state.get("regiao", "Todas")
    uf = st.session_state.get("uf", "Todas")

    # Layout de KPIs em colunas
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown(
            """
            <div class="kpi-card kpi-card-teal">
                <div class="kpi-title">Faturamento Bruto</div>
                <div class="kpi-value">R$ 4.280.000</div>
                <div class="kpi-subfooter">
                    <span>Meta: R$ 4,1 mi</span>
                    <span class="badge badge-positive">+4,4%</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            """
            <div class="kpi-card kpi-card-brass">
                <div class="kpi-title">Receita Líquida</div>
                <div class="kpi-value">R$ 3.338.400</div>
                <div class="kpi-subfooter">
                    <span>Impostos: 18,2%</span>
                    <span class="badge badge-warning">-22,0%</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col3:
        st.markdown(
            """
            <div class="kpi-card kpi-card-pos">
                <div class="kpi-title">Margem de Contribuição</div>
                <div class="kpi-value">R$ 1.155.600</div>
                <div class="kpi-subfooter">
                    <span>Margem %: 27,0%</span>
                    <span class="badge badge-positive">+1,8 p.p.</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col4:
        st.markdown(
            """
            <div class="kpi-card kpi-card-neg">
                <div class="kpi-title">Clientes Ativos</div>
                <div class="kpi-value">284</div>
                <div class="kpi-subfooter">
                    <span>Em risco: 38</span>
                    <span class="badge badge-negative">-12 lojas</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("---")

    st.info(
        f"**Cenário:** `{scenario_id}` | **Região:** `{regiao}` | **UF:** `{uf}` | "
        f"**Tema:** `{theme_mode.upper()}`. "
        "A camada analítica completa será conectada no Marco M2."
    )

    # Bloco Prescritivo Executivo
    st.markdown(
        """
        <div class="prescription-box">
            <div class="prescription-title">🎯 Diagnóstico Prescritivo Automático</div>
            <div class="prescription-content">
                O faturamento cresceu 4,4%, porém
                <strong>38 lojistas estão há mais de 60 dias sem recompra</strong>.
                Recomendação: Atuar no combate ao churn imediato para proteger
                <strong>R$ 312.000/ano em margem</strong>.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


render_page()
