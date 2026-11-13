from __future__ import annotations

import io
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile

import pandas as pd

from src.services.export_service import (
    attach_whatsapp_links,
    build_whatsapp_link,
    dataframe_to_csv_bom,
    generate_commercial_action_excel,
    normalize_phone_e164_digits,
    sanitize_excel_sheet_name,
)


def _make_mock_risk_df(n_rows: int = 4) -> pd.DataFrame:
    """Gera DataFrame sintético realista de clientes em risco para testes de exportação."""
    reps = ["Carlos Eduardo Silva", "Mariana Oliveira [Norte/Nordeste] Ultra Long Name"]
    rows: list[dict[str, object]] = []
    for idx in range(n_rows):
        rows.append(
            {
                "customer_id": f"CLI-{idx + 1:04d}",
                "customer_name": f"Brinquedos São Paulo #{idx + 1}",
                "city": "São Paulo",
                "state": "SP",
                "region": "Sudeste",
                "sales_rep_name": reps[idx % len(reps)],
                "rfm_segment": "Em Risco",
                "risk_status": "Em Risco Imediato",
                "delay_ratio": 1.85,
                "recency_days": 54,
                "expected_cycle_days": 29.0,
                "annual_revenue_at_risk": 48_500.75 + idx,
                "annual_margin_at_risk": 12_900.40 + idx,
                "top_opportunity_family": "Jogos Educativos",
                "top_opportunity_brl": 9_200.00,
                "top_opportunity_pitch": "Condição especial no Kit Robótica com ação de giro imediato.",
                "whatsapp": "(11) 98765-4321" if idx % 2 == 0 else "+55 21 99123-4567",
            }
        )
    return pd.DataFrame(rows)


def _make_mock_ws_df(n_rows: int = 3) -> pd.DataFrame:
    """Gera DataFrame sintético realista de oportunidades White Space."""
    rows: list[dict[str, object]] = []
    for idx in range(n_rows):
        rows.append(
            {
                "customer_id": f"CLI-{idx + 1:04d}",
                "customer_name": f"Mundo Lúdico Ltda #{idx + 1}",
                "state": "MG",
                "city": "Belo Horizonte",
                "sales_rep_name": "Carlos Eduardo Silva",
                "rfm_segment": "Campeões",
                "recommended_family": "Brinquedos de Madeira",
                "recommended_top_sku": "Brinquedos de Madeira - Sortimento A",
                "anchor_sku_name": "Lojista Especializado (Perfil G)",
                "affinity_lift": 2.35,
                "potential_revenue_brl": 15_400.00,
                "potential_margin_brl": 4_620.00,
                "action_pitch": "Ação promocional em blocos pedagógicos com entrega programada.",
                "whatsapp": "31988887777",
            }
        )
    return pd.DataFrame(rows)


def test_normalize_phone_e164_digits() -> None:
    """Valida normalização para E.164 brasileiro sem '+'."""
    assert normalize_phone_e164_digits("(11) 98765-4321") == "5511987654321"
    assert normalize_phone_e164_digits("+55 (21) 3344-5566") == "552133445566"
    assert normalize_phone_e164_digits("011987654321") == "5511987654321"
    assert normalize_phone_e164_digits("123") == ""
    assert normalize_phone_e164_digits(None) == ""


def test_build_whatsapp_link_valid_format_and_accent_encoding() -> None:
    """Valida formato wa.me/55... e encoding UTF-8 seguro de acentos em português."""
    pitch = "Ação especial em Quebra-Cabeças com condição São Paulo!"
    url = build_whatsapp_link(
        "(11) 98765-4321",
        "Loja Coração Infantil",
        "João Gonçalves",
        pitch,
    )

    assert re.match(r"^https://wa\.me/55\d{10,11}\?text=.+$", url)
    decoded = urllib.parse.unquote(url.split("?text=", maxsplit=1)[1])
    assert "Loja Coração Infantil" in decoded
    assert "João Gonçalves" in decoded
    assert "Quebra-Cabeças" in decoded
    assert "São Paulo" in decoded

    assert build_whatsapp_link("", "Loja X", "RCA Y", "Pitch") == ""


def test_dataframe_to_csv_bom_preserves_accents_and_semicolon() -> None:
    """Valida prefixo BOM UTF-8 e separador ';' para abertura direta no Excel BR."""
    df = _make_mock_risk_df(2)
    csv_bytes = dataframe_to_csv_bom(df)

    assert csv_bytes.startswith(b"\xef\xbb\xbf")
    text = csv_bytes.decode("utf-8-sig")
    assert ";" in text
    assert "Brinquedos São Paulo #1" in text


def test_sanitize_excel_sheet_name_limits_and_deduplicates() -> None:
    """Garante remoção de caracteres proibidos, limite de 31 chars e unicidade."""
    used: set[str] = set()
    s1 = sanitize_excel_sheet_name("João [SP/RJ]: Vendas * Norte/Nordeste Muito Longo", used)
    s2 = sanitize_excel_sheet_name("João [SP/RJ]: Vendas * Norte/Nordeste Muito Longo", used)

    assert len(s1) <= 31
    assert len(s2) <= 31
    assert s1 != s2
    assert not any(ch in s1 for ch in "[]:*?/\\")


def test_generate_commercial_action_excel_readable_with_per_rep_tabs() -> None:
    """Valida que o Excel gerado em memória possui OOXML íntegro, abas por RCA, autofiltro e freeze panes."""
    risk_df = _make_mock_risk_df(4)
    ws_df = _make_mock_ws_df(3)

    excel_bytes = generate_commercial_action_excel(risk_df, ws_df, "Indústria de Brinquedos")
    assert len(excel_bytes) > 5_000

    with zipfile.ZipFile(io.BytesIO(excel_bytes), "r") as zf:
        wb_root = ET.fromstring(zf.read("xl/workbook.xml"))
        sheet_names = [
            s.attrib["name"]
            for s in wb_root.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet")
        ]
        shared_strings = zf.read("xl/sharedStrings.xml").decode("utf-8")
        sheet1_xml = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")

    assert "Resumo_Priorizado" in sheet_names
    assert "Oportunidades_WhiteSpace" in sheet_names
    assert "Carlos Eduardo Silva" in sheet_names
    assert len(sheet_names) == 4
    assert all(len(name) <= 31 for name in sheet_names)

    assert "Link WhatsApp" in shared_strings
    assert "https://wa.me/55" in shared_strings
    assert "autoFilter" in sheet1_xml
    assert "ySplit" in sheet1_xml


def test_generate_commercial_action_excel_empty_inputs_stays_valid() -> None:
    """Garante que entradas vazias geram workbook válido sem exceção de planilha sem abas."""
    excel_bytes = generate_commercial_action_excel(pd.DataFrame(), pd.DataFrame(), "Vazio")
    with zipfile.ZipFile(io.BytesIO(excel_bytes), "r") as zf:
        wb_root = ET.fromstring(zf.read("xl/workbook.xml"))
        sheet_names = [
            s.attrib["name"]
            for s in wb_root.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet")
        ]
    assert sheet_names == ["Resumo_Priorizado"]


def test_attach_whatsapp_links_and_export_1000_rows_under_1s() -> None:
    """DoD: exportação Excel de 1.000 linhas executa em menos de 1 segundo."""
    risk_1k = _make_mock_risk_df(1_000)
    ws_200 = _make_mock_ws_df(200)

    t0 = time.perf_counter()
    linked = attach_whatsapp_links(risk_1k)
    excel_bytes = generate_commercial_action_excel(risk_1k, ws_200, "Benchmark 1k")
    elapsed = time.perf_counter() - t0

    assert len(linked) == 1_000
    assert (linked["whatsapp_link"].str.startswith("https://wa.me/55")).all()
    assert len(excel_bytes) > 10_000
    assert elapsed < 1.0, f"Exportação de 1.000 linhas demorou {elapsed:.3f}s (limite < 1.0s)"
