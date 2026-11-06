from __future__ import annotations

import html
from pathlib import Path
from typing import Final

import streamlit as st

from src.core.logging import get_logger
from src.core.scenarios import load_scenario_config
from src.core.types import ScenarioId
from src.db.repository import DataRepository
from src.ui.cache import get_cached_repository
from src.ui.state import (
    MONTH_LABELS,
    PERIOD_PRESETS,
    AppState,
    get_app_state,
    on_families_change,
    on_period_preset_change,
    on_regiao_change,
    on_sales_reps_change,
    on_scenario_change,
    on_selected_month_change,
    on_theme_toggle,
    on_uf_change,
    resolve_period_bounds,
)
from src.ui.theme import REGIOES_BR, get_ufs_for_regiao

logger = get_logger(__name__)

SCENARIO_OPTIONS: Final[dict[ScenarioId, str]] = {
    "c1_toys": "C1 — Indústria de Brinquedos",
    "c2_beverages": "C2 — Distribuidora Bebidas",
    "c3_retail_chain": "C3 — Rede de Varejo",
    "c4_single_store": "C4 — Varejo Loja Única",
}


def _get_available_families(repo: DataRepository | None, scenario_id: ScenarioId) -> list[str]:
    """Retorna lista ordenada das famílias de produtos para o cenário ativo."""
    if repo is not None:
        try:
            df = repo.table("dim_product", scenario_id=scenario_id, columns=["family"])
            if not df.empty and "family" in df.columns:
                return sorted([str(f) for f in df["family"].dropna().unique()])
        except Exception as exc:
            logger.debug("Não foi possível carregar famílias de dim_product: %s", exc)

    fallbacks: dict[str, list[str]] = {
        "c1_toys": [
            "Brinquedos de Madeira",
            "Jogos Educativos",
            "Linha Escolar",
            "Pelúcias",
            "Primeira Infância",
            "Quebra-Cabeças",
        ],
        "c2_beverages": [
            "Cachaças e Destilados",
            "Gin",
            "Licores",
            "Quebra-Cabeças",
            "Rum",
            "Tequila",
            "Vodka",
            "Whisky",
        ],
        "c3_retail_chain": ["Bebidas", "Brinquedos e Jogos", "Conveniência", "Mercearia"],
        "c4_single_store": ["Balcão", "Frios", "Gôndola A", "Gôndola B"],
    }
    return fallbacks.get(scenario_id, [])


def _get_available_sales_reps(repo: DataRepository | None, scenario_id: ScenarioId) -> list[str]:
    """Retorna lista ordenada dos responsáveis comerciais para o cenário ativo."""
    if repo is not None:
        try:
            df = repo.table("dim_sales_rep", scenario_id=scenario_id, columns=["name"])
            if not df.empty and "name" in df.columns:
                return sorted([str(r) for r in df["name"].dropna().unique()])
        except Exception as exc:
            logger.debug("Não foi possível carregar representantes de dim_sales_rep: %s", exc)
    return []


def _render_data_source_badge(repo: DataRepository | None) -> str:
    """Gera o HTML do badge visual indicativo da fonte de dados conectada."""
    if repo is None:
        return (
            '<div style="text-align: center; margin-top: 1rem;">'
            '<span class="badge badge-source" title="Repositório não inicializado">'
            "Fonte: Snapshot Local (DuckDB)"
            "</span>"
            "</div>"
        )

    if repo.backend == "azure_sql":
        return (
            '<div style="text-align: center; margin-top: 1rem;">'
            '<span class="badge badge-positive" '
            'title="Conexão direta com Azure SQL Database (Serverless Gen5)">'
            "🟢 Fonte: Azure SQL"
            "</span>"
            "</div>"
        )

    if repo.fallback_reason:
        escaped_reason = html.escape(repo.fallback_reason)
        return (
            '<div style="text-align: center; margin-top: 1rem;">'
            f'<span class="badge badge-warning" title="{escaped_reason}">'
            "🟡 Fonte: Snapshot Local (Fallback)"
            "</span>"
            "</div>"
        )

    return (
        '<div style="text-align: center; margin-top: 1rem;">'
        '<span class="badge badge-source" title="Operação local sobre snapshot DuckDB e Parquet">'
        "⚡ Fonte: Snapshot Local (DuckDB)"
        "</span>"
        "</div>"
    )


def render_sidebar(repo: DataRepository | None = None) -> AppState:  # noqa: PLR0915
    """Renderiza a barra lateral unificada da aplicação Kyberna.

    Apresenta:
        1. Branding e logo adaptável ao tema ativo.
        2. Toggle switch para alternância Light Mode ☀️ / Dark Mode 🌙.
        3. Seletor de Cenário com vocabulário de negócio e perfil executivo.
        4. Filtros em cascata adaptativos (Região -> UF, Famílias de Produtos e Representantes).
        5. Badge de status e resiliência da fonte de dados (Azure SQL vs. Fallback DuckDB).

    Retorna:
        AppState: Estado atualizado e tipado da sessão.
    """
    if repo is None:
        try:
            repo = get_cached_repository()
        except Exception as exc:
            logger.debug("Falha ao obter repositório em cache: %s", exc)
            repo = None

    state = get_app_state()
    scenario = load_scenario_config(state.scenario_id)

    with st.sidebar:
        # 1. Branding / Logotipo adaptativo
        logo_filename = "logo_dark.svg" if state.theme_mode == "dark" else "logo.svg"
        logo_path = Path(__file__).parent.parent / "assets" / logo_filename
        if not logo_path.exists():
            logo_path = Path(__file__).parent.parent / "assets" / "logo.svg"

        if logo_path.exists():
            st.image(str(logo_path), width=260)
        else:
            st.markdown("### 🧭 **KYBERNA**")

        st.markdown("---")

        # 2. Alternador de Tema (Toggle Switch)
        st.toggle(
            "Modo Escuro 🌙",
            value=(state.theme_mode == "dark"),
            key="_theme_toggle",
            on_change=on_theme_toggle,
            help="Alterna dinamicamente entre o visual executivo claro e o cockpit escuro de alto contraste.",
        )

        st.markdown("---")

        # 3. Seletor Global de Cenário
        scenario_keys = list(SCENARIO_OPTIONS.keys())
        current_scenario_index = (
            scenario_keys.index(state.scenario_id) if state.scenario_id in scenario_keys else 0
        )
        st.selectbox(
            "Cenário de Negócio",
            options=scenario_keys,
            format_func=lambda s: SCENARIO_OPTIONS[s],
            index=current_scenario_index,
            key="_scenario_select",
            on_change=on_scenario_change,
            help="Altera o vocabulário, lógica de margem e matrizes analíticas da demonstração.",
        )
        st.caption(f"🏢 *{scenario.company_profile}*")

        st.markdown("---")

        # 4. Filtro de Período de Análise
        st.markdown("##### 📅 Período de Análise")
        preset_keys = list(PERIOD_PRESETS.keys())
        current_preset_idx = (
            preset_keys.index(state.period_preset) if state.period_preset in preset_keys else 0
        )
        st.selectbox(
            "Janela Temporal",
            options=preset_keys,
            format_func=lambda p: PERIOD_PRESETS[p],
            index=current_preset_idx,
            key="_period_preset_select",
            on_change=on_period_preset_change,
            help="Define o recorte temporal das vendas e o comparativo de período anterior (YoY/PoP/MoM).",
        )

        if state.period_preset == "custom_month":
            month_keys = list(MONTH_LABELS.keys())
            current_month_idx = (
                month_keys.index(state.selected_month) if state.selected_month in month_keys else 0
            )
            st.selectbox(
                "Mês Específico",
                options=month_keys,
                format_func=lambda m: MONTH_LABELS[m],
                index=current_month_idx,
                key="_selected_month_select",
                on_change=on_selected_month_change,
            )

        bounds = resolve_period_bounds(state.period_preset, state.selected_month)
        st.caption(f"🗓️ *{bounds.period_label}*")

        st.markdown("---")

        # 5. Cascata Geográfica (Região -> UF)
        if scenario.filters.has_geographic_filter:
            st.markdown("##### 📍 Filtros Geográficos")

            regioes = ["Todas", *REGIOES_BR]
            current_regiao_index = regioes.index(state.regiao) if state.regiao in regioes else 0
            st.selectbox(
                "Região",
                options=regioes,
                index=current_regiao_index,
                key="_regiao_select",
                on_change=on_regiao_change,
            )

            ufs_disponiveis = ["Todas", *get_ufs_for_regiao(state.regiao)]
            current_uf_index = ufs_disponiveis.index(state.uf) if state.uf in ufs_disponiveis else 0
            st.selectbox(
                "Estado (UF)",
                options=ufs_disponiveis,
                index=current_uf_index,
                key="_uf_select",
                on_change=on_uf_change,
            )

        # 5. Filtro de Famílias / Categorias de Produto
        if scenario.filters.has_family_filter:
            st.markdown("---")
            st.markdown(f"##### 📦 {scenario.labels.product_family}")
            available_families = _get_available_families(repo, state.scenario_id)
            default_families = [f for f in state.families if f in available_families]
            st.multiselect(
                f"Filtrar {scenario.labels.product_family}",
                options=available_families,
                default=default_families,
                key="_families_select",
                on_change=on_families_change,
                placeholder="Todas as famílias",
            )

        # 6. Filtro de Responsável Comercial (RCA / Vendedor / Gerente)
        if scenario.filters.has_rep_filter and scenario.capabilities.rep_efficiency:
            st.markdown("---")
            st.markdown(f"##### 👤 {scenario.labels.sales_rep}")
            available_reps = _get_available_sales_reps(repo, state.scenario_id)
            default_reps = [r for r in state.sales_reps if r in available_reps]
            st.multiselect(
                f"Filtrar {scenario.labels.sales_rep}",
                options=available_reps,
                default=default_reps,
                key="_sales_reps_select",
                on_change=on_sales_reps_change,
                placeholder="Todos os representantes",
            )

        st.markdown("---")

        # 7. Badge de Status da Fonte de Dados
        badge_html = _render_data_source_badge(repo)
        st.markdown(badge_html, unsafe_allow_html=True)

    return get_app_state()
