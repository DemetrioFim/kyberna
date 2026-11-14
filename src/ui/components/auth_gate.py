from __future__ import annotations

import hmac
from typing import Final

import streamlit as st

from src.core.settings import Settings, get_settings

MAX_AUTH_ATTEMPTS: Final[int] = 5


def _hide_sidebar_css() -> None:
    """Oculta a barra lateral e o botão de expansão enquanto a sessão não está autenticada."""
    st.markdown(
        """
        <style>
            [data-testid="stSidebar"],
            [data-testid="collapsedControl"],
            [data-testid="stSidebarCollapsedControl"] {
                display: none !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_auth_card_header(title: str, subtitle: str) -> None:
    """Renderiza o cabeçalho institucional do card de acesso usando tokens var(--kyb-*)."""
    st.markdown(
        f"""
        <div style="
            background: var(--kyb-card-bg);
            border: 1px solid var(--kyb-border);
            border-top: 4px solid var(--kyb-teal);
            border-radius: 10px;
            padding: 1.35rem 1.5rem 1rem 1.5rem;
            margin-top: 2.5rem;
            margin-bottom: 0.75rem;
            box-shadow: var(--kyb-shadow);
        ">
            <div style="
                font-size: 0.72rem;
                font-weight: 700;
                letter-spacing: 0.08em;
                text-transform: uppercase;
                color: var(--kyb-teal);
                margin-bottom: 0.35rem;
            ">VIRTUS · BY KYBERNA</div>
            <div style="
                font-size: 1.35rem;
                font-weight: 700;
                color: var(--kyb-text);
                line-height: 1.2;
                margin-bottom: 0.35rem;
            ">{title}</div>
            <div style="
                font-size: 0.88rem;
                color: var(--kyb-text-muted);
                line-height: 1.4;
            ">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _verify_password(typed_password: str, expected_password: str) -> bool:
    """Compara senhas em tempo constante para mitigar ataques de temporização."""
    return hmac.compare_digest(
        typed_password.encode("utf-8"),
        expected_password.encode("utf-8"),
    )


def _handle_demo_password(settings: Settings) -> bool:
    """Exibe o gate por senha para links externos com bloqueio após 5 falhas."""
    if bool(st.session_state.get("auth_authenticated", False)):
        return True

    _hide_sidebar_css()
    attempts = int(st.session_state.get("auth_failed_attempts", 0))

    _, col_center, _ = st.columns([1.0, 1.35, 1.0])
    with col_center:
        _render_auth_card_header(
            title="Acesso Restrito à Demonstração",
            subtitle="Informe a senha fornecida pela equipe Kyberna para liberar o cockpit executivo.",
        )

        if attempts >= MAX_AUTH_ATTEMPTS:
            st.error(
                f"Acesso bloqueado nesta sessão após {MAX_AUTH_ATTEMPTS} tentativas inválidas. "
                "Recarregue a página ou contate o administrador."
            )
            return False

        with st.form("kyberna_auth_form", clear_on_submit=False):
            typed_password = st.text_input(
                "Senha de Acesso",
                type="password",
                key="auth_password_input",
                placeholder="Digite a senha da sessão...",
            )
            submitted = st.form_submit_button(
                "Entrar no Virtus",
                use_container_width=True,
            )

        if submitted:
            if _verify_password(typed_password, settings.app_password):
                st.session_state["auth_authenticated"] = True
                st.session_state["auth_failed_attempts"] = 0
                st.rerun()
            else:
                attempts += 1
                st.session_state["auth_failed_attempts"] = attempts
                remaining = MAX_AUTH_ATTEMPTS - attempts
                if remaining <= 0:
                    st.rerun()
                else:
                    st.error(f"Senha inválida. Restam {remaining} tentativa(s) antes do bloqueio.")
        elif attempts > 0:
            remaining = MAX_AUTH_ATTEMPTS - attempts
            st.warning(f"Tentativas falhas registradas: {attempts}/{MAX_AUTH_ATTEMPTS} (restam {remaining}).")

    return False


def _handle_entra_id() -> bool:
    """Valida identidade corporativa injetada pelo Easy Auth / Azure Container Apps."""
    ctx = getattr(st, "context", None)
    raw_headers = getattr(ctx, "headers", None) if ctx is not None else None
    headers_lower: dict[str, str] = {}
    if raw_headers is not None:
        headers_lower = {str(k).lower(): str(v) for k, v in dict(raw_headers).items()}

    principal_name = headers_lower.get("x-ms-client-principal-name", "").strip()
    principal_id = headers_lower.get("x-ms-client-principal-id", "").strip()
    if principal_name or principal_id:
        st.session_state["auth_authenticated"] = True
        st.session_state["auth_user"] = principal_name or principal_id
        return True

    _hide_sidebar_css()
    _, col_center, _ = st.columns([1.0, 1.35, 1.0])
    with col_center:
        _render_auth_card_header(
            title="Autenticação Corporativa Necessária",
            subtitle=(
                "Este ambiente exige login via Microsoft Entra ID (Azure Easy Auth). "
                "Acesse pela URL corporativa autenticada."
            ),
        )
        st.error("Cabeçalhos de identidade Entra ID não detectados na requisição atual.")
    return False


def require_authentication(settings: Settings | None = None) -> bool:
    """Aplica o gate de acesso conforme `KYBERNA_AUTH_MODE` (`none`, `demo_password`, `entra_id`)."""
    cfg = settings or get_settings()
    if cfg.auth_mode == "none":
        return True
    if cfg.auth_mode == "demo_password":
        return _handle_demo_password(cfg)
    if cfg.auth_mode == "entra_id":
        return _handle_entra_id()
    return False
