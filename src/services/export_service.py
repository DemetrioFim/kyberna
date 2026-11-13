from __future__ import annotations

import io
import re
import urllib.parse
from typing import Any, Final

import pandas as pd

INVALID_EXCEL_SHEET_CHARS_RE: Final[re.Pattern[str]] = re.compile(r"[\[\]:*?/\\]")
EXCEL_MAX_SHEET_LEN: Final[int] = 31

_RISK_EXPORT_LABELS: Final[dict[str, str]] = {
    "customer_id": "ID Cliente",
    "customer_name": "Cliente / Lojista",
    "city": "Município",
    "state": "UF",
    "region": "Região",
    "sales_rep_name": "RCA Responsável",
    "rfm_segment": "Segmento RFM",
    "risk_status": "Status Ciclo",
    "delay_ratio": "Razão Atraso (x)",
    "recency_days": "Recência (Dias)",
    "expected_cycle_days": "Ciclo Esperado (Dias)",
    "annual_revenue_at_risk": "Receita em Risco (R$)",
    "annual_margin_at_risk": "Margem em Risco (R$)",
    "top_opportunity_family": "Família White Space",
    "top_opportunity_brl": "Potencial Cross-Sell (R$)",
    "top_opportunity_pitch": "Argumento Comercial (Pitch)",
    "whatsapp": "WhatsApp",
    "whatsapp_link": "Link WhatsApp",
}

_WS_EXPORT_LABELS: Final[dict[str, str]] = {
    "customer_id": "ID Cliente",
    "customer_name": "Cliente / Lojista",
    "state": "UF",
    "city": "Município",
    "sales_rep_name": "RCA Responsável",
    "rfm_segment": "Segmento RFM",
    "recommended_family": "Família Ausente",
    "recommended_top_sku": "SKU Recomendado",
    "anchor_sku_name": "Perfil / Âncora",
    "affinity_lift": "Lift Afinidade (x)",
    "potential_revenue_brl": "Potencial Receita (R$)",
    "potential_margin_brl": "Potencial Margem (R$)",
    "action_pitch": "Argumento Comercial (Pitch)",
    "whatsapp": "WhatsApp",
    "whatsapp_link": "Link WhatsApp",
}

_CURRENCY_EXPORT_COLS: Final[frozenset[str]] = frozenset(
    {
        "annual_revenue_at_risk",
        "annual_margin_at_risk",
        "top_opportunity_brl",
        "potential_revenue_brl",
        "potential_margin_brl",
    }
)
_DECIMAL_EXPORT_COLS: Final[frozenset[str]] = frozenset(
    {"delay_ratio", "expected_cycle_days", "affinity_lift"}
)


def normalize_phone_e164_digits(raw_phone: Any) -> str:
    """Extrai dígitos e normaliza telefone brasileiro para E.164 sem '+' (55DD9XXXXXXXX)."""
    if raw_phone is None or (isinstance(raw_phone, float) and pd.isna(raw_phone)):
        return ""
    digits = re.sub(r"\D", "", str(raw_phone))
    if not digits:
        return ""
    if digits.startswith("0") and len(digits) in (11, 12):
        digits = digits.lstrip("0")
    if len(digits) in (10, 11):
        digits = f"55{digits}"
    if not digits.startswith("55") or len(digits) not in (12, 13):
        return ""
    return digits


def build_whatsapp_link(
    phone: Any,
    customer_name: str,
    rep_name: str,
    context_pitch: str,
) -> str:
    """Gera URL clicável https://wa.me/<E164>?text=<mensagem> com encoding pt-BR seguro."""
    digits = normalize_phone_e164_digits(phone)
    if not digits:
        return ""

    cust_clean = str(customer_name or "Parceiro").strip()
    rep_clean = str(rep_name or "Consultor Comercial").strip()
    pitch_clean = str(context_pitch or "").strip()

    if pitch_clean:
        message = (
            f"Olá, equipe {cust_clean}! Aqui é {rep_clean}. "
            f"Preparamos uma oportunidade comercial para vocês: {pitch_clean}"
        )
    else:
        message = (
            f"Olá, equipe {cust_clean}! Aqui é {rep_clean}. "
            "Podemos alinhar a reposição de pedidos e condições desta semana?"
        )

    encoded = urllib.parse.quote(message, safe="")
    return f"https://wa.me/{digits}?text={encoded}"


def attach_whatsapp_links(
    df: pd.DataFrame,
    *,
    phone_col: str = "whatsapp",
    customer_col: str = "customer_name",
    rep_col: str = "sales_rep_name",
    pitch_col: str = "top_opportunity_pitch",
    fallback_pitch: str = "",
) -> pd.DataFrame:
    """Retorna cópia do DataFrame com a coluna `whatsapp_link` preenchida sem usar iterrows()."""
    out = df.copy()
    if out.empty:
        out["whatsapp_link"] = pd.Series(dtype="object")
        return out

    phones = out[phone_col].tolist() if phone_col in out.columns else [""] * len(out)
    customers = out[customer_col].tolist() if customer_col in out.columns else ["Cliente"] * len(out)
    reps = out[rep_col].tolist() if rep_col in out.columns else ["Consultor"] * len(out)
    pitches = out[pitch_col].tolist() if pitch_col in out.columns else [fallback_pitch] * len(out)

    out["whatsapp_link"] = [
        build_whatsapp_link(
            ph,
            str(cust or ""),
            str(rep or ""),
            str(pitch or fallback_pitch),
        )
        for ph, cust, rep, pitch in zip(phones, customers, reps, pitches, strict=False)
    ]
    return out


def dataframe_to_csv_bom(df: pd.DataFrame) -> bytes:
    """Serializa DataFrame para CSV com separador ';' e BOM UTF-8 compatível com Excel BR."""
    return df.to_csv(index=False, sep=";").encode("utf-8-sig")


def sanitize_excel_sheet_name(raw_name: str, used_names: set[str] | None = None) -> str:
    """Sanitiza nome de aba Excel removendo caracteres inválidos e truncando em 31 chars."""
    cleaned = INVALID_EXCEL_SHEET_CHARS_RE.sub("", str(raw_name or "")).strip()
    cleaned = re.sub(r"\s+", " ", cleaned) or "Geral"
    base = cleaned[:EXCEL_MAX_SHEET_LEN].rstrip() or "Geral"

    if used_names is None:
        return base

    candidate = base
    suffix_idx = 2
    while candidate.lower() in {u.lower() for u in used_names}:
        suffix = f"_{suffix_idx}"
        candidate = f"{base[: EXCEL_MAX_SHEET_LEN - len(suffix)].rstrip()}{suffix}"
        suffix_idx += 1
    used_names.add(candidate)
    return candidate


def _write_styled_sheet(
    writer: pd.ExcelWriter,
    df: pd.DataFrame,
    sheet_name: str,
    labels_map: dict[str, str],
    formats: dict[str, Any],
) -> None:
    """Grava uma aba formatada no ExcelWriter com congelamento de painel e autofiltro."""
    export_cols = [c for c in labels_map if c in df.columns]
    if not export_cols:
        export_cols = list(df.columns)
    export_df = df[export_cols].copy()

    export_df.to_excel(writer, sheet_name=sheet_name, startrow=1, header=False, index=False)
    ws = writer.sheets[sheet_name]
    ws.freeze_panes(1, 0)

    n_rows = len(export_df)
    n_cols = len(export_cols)
    if n_cols > 0:
        ws.autofilter(0, 0, max(n_rows, 1), n_cols - 1)

    for col_idx, col_name in enumerate(export_cols):
        header_label = labels_map.get(col_name, col_name)
        ws.write(0, col_idx, header_label, formats["header"])

        if col_name in _CURRENCY_EXPORT_COLS:
            col_fmt = formats["currency"]
            min_w = 18
        elif col_name in _DECIMAL_EXPORT_COLS:
            col_fmt = formats["decimal"]
            min_w = 14
        elif col_name == "whatsapp_link":
            col_fmt = formats["link"]
            min_w = 34
        else:
            col_fmt = formats["text"]
            min_w = 14

        max_cell_len = int(export_df[col_name].astype(str).str.len().max()) if not export_df.empty else 0
        width = min(max(len(header_label) + 4, min_w, min(max_cell_len + 2, 46)), 48)
        ws.set_column(col_idx, col_idx, width, col_fmt)


def generate_commercial_action_excel(
    risk_df: pd.DataFrame,
    white_space_df: pd.DataFrame,
    scenario_name: str,
) -> bytes:
    """Gera workbook Excel em memória com Resumo Priorizado, White Space e 1 aba por RCA."""
    risk_ready = attach_whatsapp_links(
        risk_df,
        pitch_col="top_opportunity_pitch",
        fallback_pitch="Condição especial de reativação de pedido",
    )
    ws_ready = attach_whatsapp_links(
        white_space_df,
        pitch_col="action_pitch",
        fallback_pitch="Sugestão de ampliação de mix",
    )

    bio = io.BytesIO()
    with pd.ExcelWriter(
        bio,
        engine="xlsxwriter",
        engine_kwargs={"options": {"nan_inf_to_errors": True}},
    ) as writer:
        workbook = writer.book
        formats = {
            "header": workbook.add_format(
                {
                    "font_name": "Calibri",
                    "font_size": 10,
                    "bold": True,
                    "bg_color": "#0A192F",
                    "font_color": "#FFFFFF",
                    "border": 1,
                    "align": "center",
                    "valign": "vcenter",
                }
            ),
            "currency": workbook.add_format(
                {"font_name": "Calibri", "font_size": 10, "num_format": "R$ #,##0.00"}
            ),
            "decimal": workbook.add_format({"font_name": "Calibri", "font_size": 10, "num_format": "0.00"}),
            "text": workbook.add_format({"font_name": "Calibri", "font_size": 10}),
            "link": workbook.add_format(
                {"font_name": "Calibri", "font_size": 9, "font_color": "#0D9488", "underline": True}
            ),
        }

        used_names: set[str] = set()
        summary_sheet = sanitize_excel_sheet_name("Resumo_Priorizado", used_names)
        _write_styled_sheet(writer, risk_ready, summary_sheet, _RISK_EXPORT_LABELS, formats)

        if not ws_ready.empty:
            ws_sheet = sanitize_excel_sheet_name("Oportunidades_WhiteSpace", used_names)
            _write_styled_sheet(writer, ws_ready, ws_sheet, _WS_EXPORT_LABELS, formats)

        if not risk_ready.empty and "sales_rep_name" in risk_ready.columns:
            rep_names = sorted(
                {
                    str(rep).strip()
                    for rep in risk_ready["sales_rep_name"].dropna().tolist()
                    if str(rep).strip()
                }
            )
            for rep_name in rep_names:
                rep_df = risk_ready[risk_ready["sales_rep_name"].astype(str).str.strip() == rep_name]
                if rep_df.empty:
                    continue
                rep_sheet = sanitize_excel_sheet_name(rep_name, used_names)
                _write_styled_sheet(writer, rep_df, rep_sheet, _RISK_EXPORT_LABELS, formats)

        workbook.set_properties({"title": f"Plano de Ação Comercial — {scenario_name}", "company": "Kyberna"})

    return bio.getvalue()
