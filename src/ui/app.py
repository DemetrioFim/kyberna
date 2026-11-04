from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.db.repository import DataRepository
from src.ui.cache import get_cached_repository
from src.ui.components.sidebar import render_sidebar
from src.ui.state import init_app_state
from src.ui.theme import get_theme_tokens

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

state = init_app_state()

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


inject_custom_css(state.theme_mode)

# ==============================================================================
# Sidebar Global (Branding, Cenários, Tema, Cascata e Fonte de Dados)
# ==============================================================================

repo: DataRepository | None = None
try:
    repo = get_cached_repository()
except Exception:
    repo = None

render_sidebar(repo)

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
