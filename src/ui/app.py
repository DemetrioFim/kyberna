from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.ui.theme import REGIOES_BR, get_theme_tokens, get_ufs_for_regiao

# ==============================================================================
# Configuração da Aplicação (Deve ser a primeira chamada Streamlit)
# ==============================================================================

st.set_page_config(
    page_title="Kyberna · Decision Intelligence",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ==============================================================================
# Inicialização do Estado Global de Sessão (st.session_state)
# ==============================================================================

if "theme_mode" not in st.session_state:
    st.session_state.theme_mode = "light"

if "scenario_id" not in st.session_state:
    st.session_state.scenario_id = "c1_toys"

if "regiao" not in st.session_state:
    st.session_state.regiao = "Todas"

if "uf" not in st.session_state:
    st.session_state.uf = "Todas"


# ==============================================================================
# Injeção de CSS Dinâmico (Light & Dark Theme)
# ==============================================================================


def inject_custom_css(theme_mode: str) -> None:
    """Carrega o stylesheet e injeta variáveis CSS de acordo com o tema selecionado."""
    css_path = Path(__file__).parent / "assets" / "styles.css"
    if css_path.exists():
        css_content = css_path.read_text(encoding="utf-8")
        tokens = get_theme_tokens(theme_mode)

        # Força aplicação dos tokens do tema ativo no root
        dynamic_vars = f"""
        :root {{
            --kyb-bg: {tokens["bg_primary"]};
            --kyb-sidebar-bg: {tokens["sidebar_bg"]};
            --kyb-card-bg: {tokens["surface_card"]};
            --kyb-input-bg: {tokens["input_bg"]};
            --kyb-border: {tokens["border_subtle"]};
            --kyb-text: {tokens["text_primary"]};
            --kyb-text-muted: {tokens["text_muted"]};
            --kyb-teal: {tokens["teal_500"]};
            --kyb-brass: {tokens["brass_500"]};
            --kyb-pos: {tokens["positive"]};
            --kyb-neg: {tokens["negative"]};
            --kyb-warn: {tokens["warning"]};
        }}
        """
        st.markdown(f"<style>{css_content}\n{dynamic_vars}</style>", unsafe_allow_html=True)


inject_custom_css(st.session_state.theme_mode)

# ==============================================================================
# Sidebar Global (Branding, Cenários, Tema e Cascata Geográfica)
# ==============================================================================

with st.sidebar:
    # 1. Branding / Logo (Adaptação para o tema ativo)
    logo_filename = "logo_dark.svg" if st.session_state.theme_mode == "dark" else "logo.svg"
    logo_path = Path(__file__).parent / "assets" / logo_filename
    if not logo_path.exists():
        logo_path = Path(__file__).parent / "assets" / "logo.svg"

    if logo_path.exists():
        st.image(str(logo_path), width=260)
    else:
        st.markdown("### 🧭 **KYBERNA**")

    st.markdown("---")

    # 2. Seletor de Tema via Toggle Switch
    def _on_theme_toggle() -> None:
        is_dark = bool(st.session_state.get("_theme_toggle", False))
        st.session_state.theme_mode = "dark" if is_dark else "light"

    st.toggle(
        "Modo Escuro 🌙",
        value=(st.session_state.theme_mode == "dark"),
        key="_theme_toggle",
        on_change=_on_theme_toggle,
        help="Alterna dinamicamente entre o visual executivo claro e o cockpit escuro de alto contraste.",
    )

    st.markdown("---")

    # 3. Seletor de Cenário
    scenario_options = {
        "c1_toys": "C1 — Indústria de Brinquedos",
        "c2_beverages": "C2 — Distribuidora Bebidas",
        "c3_retail_chain": "C3 — Rede de Varejo",
        "c4_single_store": "C4 — Varejo Loja Única",
    }

    def _on_scenario_change() -> None:
        val = st.session_state.get("_scenario_select")
        if val:
            st.session_state.scenario_id = val

    st.selectbox(
        "Cenário de Negócio",
        options=list(scenario_options.keys()),
        format_func=lambda s: scenario_options[s],
        index=list(scenario_options.keys()).index(st.session_state.scenario_id),
        key="_scenario_select",
        on_change=_on_scenario_change,
        help="Altera o vocabulário, lógica de margem e matrizes analíticas da demonstração.",
    )

    st.markdown("---")

    # 4. Cascata Geográfica (Região -> UF)
    st.markdown("##### 📍 Filtros Geográficos")

    def _on_regiao_change() -> None:
        val = st.session_state.get("_regiao_select", "Todas")
        st.session_state.regiao = val
        st.session_state.uf = "Todas"
        if "_uf_select" in st.session_state:
            st.session_state._uf_select = "Todas"

    regioes = ["Todas", *REGIOES_BR]
    st.selectbox(
        "Região",
        options=regioes,
        index=regioes.index(st.session_state.regiao) if st.session_state.regiao in regioes else 0,
        key="_regiao_select",
        on_change=_on_regiao_change,
    )

    def _on_uf_change() -> None:
        val = st.session_state.get("_uf_select", "Todas")
        st.session_state.uf = val

    ufs_disponiveis = ["Todas", *get_ufs_for_regiao(st.session_state.regiao)]
    current_uf_index = (
        ufs_disponiveis.index(st.session_state.uf) if st.session_state.uf in ufs_disponiveis else 0
    )
    st.selectbox(
        "Estado (UF)",
        options=ufs_disponiveis,
        index=current_uf_index,
        key="_uf_select",
        on_change=_on_uf_change,
    )

    st.markdown("---")

    # 5. Fonte de Dados (Badge)
    st.markdown(
        """
        <div style="text-align: center; margin-top: 1rem;">
            <span class="badge badge-source">Fonte: Snapshot Local (DuckDB)</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ==============================================================================
# Navegação Multipage (st.navigation)
# ==============================================================================

app_dir = Path(__file__).parent

pages = [
    st.Page(
        str(app_dir / "pages" / "1_executive.py"),
        title="Visão Executiva",
        icon="📊",
        default=True,
    ),
    st.Page(
        str(app_dir / "pages" / "2_commercial_radar.py"),
        title="Radar Comercial",
        icon="🎯",
    ),
    st.Page(
        str(app_dir / "pages" / "3_inventory_demand.py"),
        title="Estoque & Demanda",
        icon="📦",
    ),
    st.Page(
        str(app_dir / "pages" / "4_simulator.py"),
        title="Simulador What-If",
        icon="⚡",
    ),
]

nav = st.navigation(pages)
nav.run()
