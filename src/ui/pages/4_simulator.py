from __future__ import annotations

import streamlit as st


def render_page() -> None:
    """Renderiza a página 'Simulador Prescritivo What-If'."""
    st.title("⚡ Simulador Prescritivo What-If")
    st.caption(
        "Simulação dinâmica de preço, desconto comercial e comissão com volume de equilíbrio (breakeven)."
    )

    # Controles interativos básicos para validação do esqueleto
    st.subheader("Parâmetros da Simulação")
    col_s1, col_s2, col_s3 = st.columns(3)

    with col_s1:
        preco_var = st.slider(
            "Variação de Preço de Tabela (%)", min_value=-15.0, max_value=20.0, value=0.0, step=0.5
        )
    with col_s2:
        desc_var = st.slider(
            "Desconto Comercial Adicional (%)", min_value=0.0, max_value=15.0, value=5.0, step=0.5
        )
    with col_s3:
        comissao_var = st.slider(
            "Ajuste de Comissão RCA (%)", min_value=-2.0, max_value=2.0, value=0.0, step=0.25
        )

    # Cálculo preliminar de breakeven ilustrativo
    # Breakeven % = desc / (margem_atual - desc)
    margem_base = 0.27
    desc_frac = desc_var / 100.0
    breakeven_vol = (desc_frac / (margem_base - desc_frac)) * 100.0 if margem_base > desc_frac else 999.0

    st.markdown("---")
    st.subheader("Impacto Estimado no Resultado")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(
            f"""
            <div class="kpi-card kpi-card-teal">
                <div class="kpi-title">Volume Necessário (Breakeven)</div>
                <div class="kpi-value">+{breakeven_vol:.1f}%</div>
                <div class="kpi-subfooter">
                    <span>Para empatar o lucro</span>
                    <span class="badge badge-warning">Mínimo necessário</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        # Elasticidade estimada
        volume_estimado = -1.4 * preco_var + 1.2 * desc_var
        badge_cls = "badge-positive" if volume_estimado >= breakeven_vol else "badge-negative"
        badge_txt = "Gera Lucro" if volume_estimado >= breakeven_vol else "Erosão de Lucro"

        st.markdown(
            f"""
            <div class="kpi-card kpi-card-brass">
                <div class="kpi-title">Volume Estimado pela Elasticidade</div>
                <div class="kpi-value">{volume_estimado:+.1f}%</div>
                <div class="kpi-subfooter">
                    <span>Sensibilidade: -1.4</span>
                    <span class="badge {badge_cls}">{badge_txt}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col3:
        st.markdown(
            f"""
            <div class="kpi-card kpi-card-pos">
                <div class="kpi-title">Margem Residual Estimada</div>
                <div class="kpi-value">{(margem_base - desc_frac) * 100:.1f}%</div>
                <div class="kpi-subfooter">
                    <span>Comissão: {5.0 + comissao_var:.2f}%</span>
                    <span class="badge badge-positive">Margem positiva</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Bloco Prescritivo do Simulador
    if volume_estimado < breakeven_vol:
        veredito = (
            f"⚠️ <strong>Atenção:</strong> O desconto de {desc_var:.1f}% exige um aumento de volume "
            f"de <strong>+{breakeven_vol:.1f}%</strong> para empatar o lucro, mas a demanda prevista "
            f"entregará apenas <strong>{volume_estimado:+.1f}%</strong>. "
            f"Recomendação: Reduzir desconto para no máximo 3%."
        )
    else:
        veredito = (
            f"✅ <strong>Oportunidade:</strong> O volume estimado de "
            f"<strong>{volume_estimado:+.1f}%</strong> supera o breakeven de "
            f"<strong>+{breakeven_vol:.1f}%</strong>, gerando ganho de margem líquida."
        )

    st.markdown(
        f"""
        <div class="prescription-box">
            <div class="prescription-title">⚡ Veredito Automático do Simulador</div>
            <div class="prescription-content">{veredito}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


render_page()
