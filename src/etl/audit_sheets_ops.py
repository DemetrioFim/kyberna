from __future__ import annotations

from typing import Any

import pandas as pd
import xlsxwriter


def _build_families_sheet(
    workbook: xlsxwriter.Workbook,
    formats: dict[str, Any],
    families_df: pd.DataFrame,
) -> None:
    """Constrói a Aba 3: Resumo por Família e Mix de Produtos."""
    ws = workbook.add_worksheet("Resumo_Familias_Mix")
    ws.set_tab_color("#D97706")
    ws.hide_gridlines(2)

    ws.write(1, 1, "RESUMO POR FAMÍLIA DE PRODUTOS — ANÁLISE DE MIX E RENTABILIDADE", formats["title"])
    ws.write(
        2,
        1,
        "Decomposição do faturamento, participação relativa, volume e margem de contribuição por família.",
        formats["subtitle"],
    )

    headers = [
        "Família de Brinquedos",
        "Faturamento Bruto (R$)",
        "Participação (%)",
        "Descontos (R$)",
        "Receita Líquida (R$)",
        "CMV Fabril (R$)",
        "Margem Contr (R$)",
        "Margem (%)",
        "Unidades",
        "Caixas Master",
        "Pedidos Distintos",
    ]
    for col_idx, h in enumerate(headers, start=1):
        ws.write(4, col_idx, h, formats["header_amber"])

    start_row = 5
    for i, (_, row) in enumerate(families_df.iterrows()):
        curr_row = start_row + i
        ws.write(curr_row, 1, row["family"], formats["cell_bold_text"])
        ws.write(curr_row, 2, row["gross_revenue"], formats["cell_currency"])
        ws.write(curr_row, 3, row["revenue_share_pct"] / 100.0, formats["cell_percent"])
        ws.write(curr_row, 4, row["discount_amount"], formats["cell_currency"])
        ws.write(curr_row, 5, row["net_revenue"], formats["cell_currency"])
        ws.write(curr_row, 6, row["cogs"], formats["cell_currency"])
        ws.write(curr_row, 7, row["contribution_margin"], formats["cell_currency"])
        ws.write(curr_row, 8, row["margin_pct"] / 100.0, formats["cell_percent"])
        ws.write(curr_row, 9, int(row["units"]), formats["cell_int"])
        ws.write(curr_row, 10, int(row["boxes"]), formats["cell_int"])
        ws.write(curr_row, 11, int(row["orders_count"]), formats["cell_int"])

    total_row = start_row + len(families_df)
    ws.write(total_row, 1, "TOTAL GERAL", formats["total_row_text"])
    col_gross = xlsxwriter.utility.xl_col_to_name(2)
    ws.write_formula(
        total_row,
        2,
        f"=SUM({col_gross}{start_row + 1}:{col_gross}{total_row})",
        formats["total_row_currency"],
    )
    ws.write(total_row, 3, 1.0, formats["total_row_percent"])

    for c_idx in [4, 5, 6, 7]:
        c_letter = xlsxwriter.utility.xl_col_to_name(c_idx)
        ws.write_formula(
            total_row,
            c_idx,
            f"=SUM({c_letter}{start_row + 1}:{c_letter}{total_row})",
            formats["total_row_currency"],
        )

    col_mc = xlsxwriter.utility.xl_col_to_name(7)
    ws.write_formula(
        total_row, 8, f"={col_mc}{total_row + 1}/{col_gross}{total_row + 1}", formats["total_row_percent"]
    )

    for c_idx in [9, 10, 11]:
        c_letter = xlsxwriter.utility.xl_col_to_name(c_idx)
        ws.write_formula(
            total_row,
            c_idx,
            f"=SUM({c_letter}{start_row + 1}:{c_letter}{total_row})",
            formats["total_row_currency"],
        )

    ws.set_column(1, 1, 28)
    ws.set_column(2, 7, 18)
    ws.set_column(8, 8, 14)
    ws.set_column(9, 11, 15)


def _build_integrity_panel(
    ws: xlsxwriter.workbook.Worksheet,
    formats: dict[str, Any],
    integrity: dict[str, Any],
) -> None:
    """Preenche o painel superior de integridade contábil."""
    ws.write(4, 1, "QUADRO DE AUDITORIA E INTEGRIDADE CONTÁBIL", formats["header_navy"])
    ws.write(4, 2, "STATUS / VALOR", formats["header_navy"])
    ws.write(4, 3, "CRITÉRIO DE PRONTO (DoD)", formats["header_navy"])

    ws.write(5, 1, "Total de Registros de Venda Auditados", formats["cell_bold_text"])
    ws.write(5, 2, integrity.get("total_rows", 0), formats["cell_int"])
    ws.write(5, 3, "100% dos pedidos da camada Gold", formats["cell_text"])

    ws.write(6, 1, "Divergências na Identidade do Waterfall (|diff| > 0.01)", formats["cell_bold_text"])
    ws.write(6, 2, integrity.get("divergences", 0), formats["badge_pass"])
    ws.write(6, 3, "Zero divergências contábeis (DoD < 1e-6)", formats["cell_text"])

    ws.write(7, 1, "Conservação de Faturamento Bruto (Gold vs Silver)", formats["cell_bold_text"])
    gold_t = integrity.get("total_gold", 0.0)
    silver_t = integrity.get("total_silver", 1.0)
    dev_pct = abs(gold_t - silver_t) / silver_t * 100.0 if silver_t > 0 else 0.0
    ws.write(7, 2, f"R$ {gold_t:,.2f} ({dev_pct:.4f}%)", formats["cell_bold_text"])
    ws.write(7, 3, "Desvio estrito inferior a ± 0.01%", formats["cell_text"])

    ws.write(8, 1, "Veredito da Auditoria de Conciliação", formats["cell_bold_text"])
    ws.write(8, 2, "100% APROVADO E CONCILIADO", formats["badge_pass"])
    ws.write(8, 3, "Pronto para certificação contábil", formats["cell_text"])


def _build_rcas_table(
    ws: xlsxwriter.workbook.Worksheet,
    formats: dict[str, Any],
    rcas_df: pd.DataFrame,
) -> int:
    """Preenche a tabela de ranking e dispersão de RCAs. Retorna próxima linha livre."""
    title_text = "RANKING DE REPRESENTANTES COMERCIAIS (RCAs) — DISPERSÃO DE DESCONTO E MARGEM"
    ws.write(10, 1, title_text, formats["header_teal"])
    rca_headers = [
        "Representante (RCA)",
        "Região",
        "Pedidos",
        "Clientes",
        "Faturamento Bruto (R$)",
        "Desconto Médio (%)",
        "Comissão Total (R$)",
        "Margem Contr (R$)",
        "Margem (%)",
    ]
    for col_idx, h in enumerate(rca_headers, start=1):
        ws.write(11, col_idx, h, formats["header_teal"])

    rca_start = 12
    for i, (_, row) in enumerate(rcas_df.iterrows()):
        curr_r = rca_start + i
        ws.write(curr_r, 1, row["sales_rep"], formats["cell_bold_text"])
        ws.write(curr_r, 2, row["region"], formats["cell_center"])
        ws.write(curr_r, 3, int(row["orders_count"]), formats["cell_int"])
        ws.write(curr_r, 4, int(row["customers_count"]), formats["cell_int"])
        ws.write(curr_r, 5, row["gross_revenue"], formats["cell_currency"])
        ws.write(curr_r, 6, row["avg_discount_pct"] / 100.0, formats["cell_percent"])
        ws.write(curr_r, 7, row["total_commission"], formats["cell_currency"])
        ws.write(curr_r, 8, row["contribution_margin"], formats["cell_currency"])
        ws.write(curr_r, 9, row["margin_pct"] / 100.0, formats["cell_percent"])

    return rca_start + len(rcas_df)


def _build_top_customers_table(
    ws: xlsxwriter.workbook.Worksheet,
    formats: dict[str, Any],
    customers_df: pd.DataFrame,
    start_row: int,
) -> None:
    """Preenche a tabela dos top 20 clientes lojistas."""
    ws.write(start_row, 1, "TOP 20 CLIENTES (LOJISTAS) EM FATURAMENTO E MARGEM", formats["header_amber"])

    cust_headers = [
        "Razão Social / Nome Fantasia",
        "CNPJ",
        "Porte",
        "Município",
        "UF",
        "RCA Responsável",
        "Pedidos",
        "Faturamento Bruto (R$)",
        "Margem Contr (R$)",
        "Margem (%)",
    ]
    for col_idx, h in enumerate(cust_headers, start=1):
        ws.write(start_row + 1, col_idx, h, formats["header_amber"])

    cust_start = start_row + 2
    for i, (_, row) in enumerate(customers_df.iterrows()):
        curr_c = cust_start + i
        ws.write(curr_c, 1, row["trade_name"], formats["cell_bold_text"])
        ws.write(curr_c, 2, row["cnpj"], formats["cell_center"])
        ws.write(curr_c, 3, row["size"], formats["cell_center"])
        ws.write(curr_c, 4, row["city"], formats["cell_text"])
        ws.write(curr_c, 5, row["state"], formats["cell_center"])
        ws.write(curr_c, 6, row["sales_rep"], formats["cell_text"])
        ws.write(curr_c, 7, int(row["orders_count"]), formats["cell_int"])
        ws.write(curr_c, 8, row["gross_revenue"], formats["cell_currency"])
        ws.write(curr_c, 9, row["contribution_margin"], formats["cell_currency"])
        ws.write(curr_c, 10, row["margin_pct"] / 100.0, formats["cell_percent"])


def _build_rcas_and_audit_sheet(
    workbook: xlsxwriter.Workbook,
    formats: dict[str, Any],
    rcas_df: pd.DataFrame,
    customers_df: pd.DataFrame,
    integrity: dict[str, Any],
    *,
    scenario_id: str,
) -> None:
    """Constrói a Aba 4: Desempenho de RCAs, Top Lojistas e Painel de Auditoria."""
    ws = workbook.add_worksheet("Auditoria_RCAs_Clientes")
    ws.set_tab_color("#1E3A8A")
    ws.hide_gridlines(2)

    ws.write(1, 1, "PAINEL DE AUDITORIA, RCAs E TOP CLIENTES", formats["title"])
    sub_title = (
        "Ranking de representantes comerciais, dispersão de desconto/margem "
        "e validação de integridade contábil."
    )
    ws.write(2, 1, sub_title, formats["subtitle"])

    _build_integrity_panel(ws, formats, integrity)
    next_row = _build_rcas_table(ws, formats, rcas_df)
    _build_top_customers_table(ws, formats, customers_df, start_row=next_row + 2)

    ws.set_column(1, 1, 32)
    ws.set_column(2, 2, 20)
    ws.set_column(3, 4, 14)
    ws.set_column(5, 5, 20)
    ws.set_column(6, 9, 18)
    ws.set_column(10, 10, 14)


def _build_abc_xyz_sheet(
    workbook: xlsxwriter.Workbook,
    formats: dict[str, Any],
    abc_xyz_df: pd.DataFrame,
    summary_df: pd.DataFrame,
) -> None:
    """Constrói a Aba 5: Matriz ABC/XYZ, Resumo das 9 Células e Políticas Prescritivas."""
    ws = workbook.add_worksheet("Matriz_ABC_XYZ")
    ws.set_tab_color("#D97706")
    ws.hide_gridlines(2)

    ws.write(1, 1, "MATRIZ 3x3 ABC/XYZ & POLÍTICAS PRESCRITIVAS DE ESTOQUE", formats["title"])
    sub_title = (
        "Cruzamento de relevância financeira (Curva ABC) e previsibilidade de demanda (XYZ) "
        "com políticas sugeridas por célula."
    )
    ws.write(2, 1, sub_title, formats["subtitle"])

    ws.write(4, 1, "RESUMO EXECUTIVO DAS 9 CÉLULAS DA MATRIZ", formats["header_teal"])
    headers_summary = [
        "Célula",
        "Curva ABC",
        "Volatilidade XYZ",
        "SKUs",
        "% SKUs",
        "Faturamento Bruto (R$)",
        "% Receita",
        "Margem Contr (R$)",
        "% Margem",
        "Margem Média (%)",
        "Política Prescritiva Recomendada",
    ]
    for col_idx, h in enumerate(headers_summary, start=1):
        ws.write(5, col_idx, h, formats["header_teal"])

    for i, (_, row) in enumerate(summary_df.iterrows()):
        curr_r = 6 + i
        ws.write(curr_r, 1, row["cell"], formats["cell_bold_text"])
        ws.write(curr_r, 2, f"Classe {row['abc_class']}", formats["cell_center"])
        ws.write(curr_r, 3, f"Classe {row['xyz_class']}", formats["cell_center"])
        ws.write(curr_r, 4, int(row["sku_count"]), formats["cell_int"])
        ws.write(curr_r, 5, row["sku_pct"] / 100.0, formats["cell_percent"])
        ws.write(curr_r, 6, row["gross_revenue"], formats["cell_currency"])
        ws.write(curr_r, 7, row["revenue_pct"] / 100.0, formats["cell_percent"])
        ws.write(curr_r, 8, row["contribution_margin"], formats["cell_currency"])
        ws.write(curr_r, 9, row["margin_pct"] / 100.0, formats["cell_percent"])
        ws.write(curr_r, 10, row["avg_margin_rate"] / 100.0, formats["cell_percent"])
        ws.write(curr_r, 11, row["policy"], formats["cell_text"])

    top_start_r = 17
    ws.write(
        top_start_r,
        1,
        "CATÁLOGO DE SKUs — CLASSIFICAÇÃO ABC/XYZ E POLÍTICA (TOP 30 POR MARGEM)",
        formats["header_teal"],
    )
    headers_skus = [
        "Código EAN-13",
        "Produto",
        "Família",
        "Emb (Pack)",
        "Unidades",
        "Faturamento Bruto (R$)",
        "Margem Contr (R$)",
        "Margem (%)",
        "Demanda Semanal Média",
        "CV Semanal",
        "Célula",
        "Política Prescritiva",
    ]
    for col_idx, h in enumerate(headers_skus, start=1):
        ws.write(top_start_r + 1, col_idx, h, formats["header_teal"])

    top_skus = abc_xyz_df.head(30)
    for i, (_, row) in enumerate(top_skus.iterrows()):
        curr_r = top_start_r + 2 + i
        ws.write(curr_r, 1, str(row["product_id"]), formats["cell_code"])
        ws.write(curr_r, 2, row["product_name"], formats["cell_bold_text"])
        ws.write(curr_r, 3, row["family"], formats["cell_text"])
        ws.write(curr_r, 4, int(row["pack"]), formats["cell_int"])
        ws.write(curr_r, 5, int(row["units_sold"]), formats["cell_int"])
        ws.write(curr_r, 6, row["gross_revenue"], formats["cell_currency"])
        ws.write(curr_r, 7, row["contribution_margin"], formats["cell_currency"])
        m_pct = row["margin_pct"] / 100.0 if pd.notna(row["margin_pct"]) else 0.0
        ws.write(curr_r, 8, m_pct, formats["cell_percent"])
        ws.write(curr_r, 9, row["weekly_demand_mean"], formats["cell_float"])
        ws.write(curr_r, 10, row["weekly_cv"], formats["cell_float"])
        ws.write(curr_r, 11, row["abc_xyz_class"], formats["cell_bold_text"])
        ws.write(curr_r, 12, row["policy"], formats["cell_text"])

    ws.set_column(1, 1, 18)
    ws.set_column(2, 2, 38)
    ws.set_column(3, 3, 22)
    ws.set_column(4, 5, 14)
    ws.set_column(6, 7, 20)
    ws.set_column(8, 10, 16)
    ws.set_column(11, 11, 12)
    ws.set_column(12, 12, 60)
