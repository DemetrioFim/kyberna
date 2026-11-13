from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import xlsxwriter


def _build_dre_sheet(
    workbook: xlsxwriter.Workbook,
    formats: dict[str, Any],
    dre: dict[str, float],
    scenario_id: str,
) -> None:
    """Constrói a Aba 1: DRE Waterfall Executiva."""
    ws = workbook.add_worksheet("DRE_Waterfall")
    ws.set_tab_color("#0A192F")
    ws.hide_gridlines(2)  # Mostra gridlines ativas

    ws.write(
        1,
        1,
        "KYBERNA DECISION INTELLIGENCE — DEMONSTRAÇÃO DO RESULTADO (WATERFALL)",
        formats["title"],
    )
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    subtitle_text = (
        f"Cenário: {scenario_id} (Caso Âncora — Indústria de Brinquedos) | "
        f"Snapshot: {now_str} | Base Auditada: DuckDB Gold Fact Sales"
    )
    ws.write(2, 1, subtitle_text, formats["subtitle"])

    ws.write(4, 1, "Volume de Linhas Auditadas", formats["header_navy"])
    ws.write(5, 1, int(dre.get("total_lines", 0)), formats["cell_int"])

    ws.write(4, 2, "Pedidos Distintos", formats["header_navy"])
    ws.write(5, 2, int(dre.get("total_orders", 0)), formats["cell_int"])

    ws.write(4, 3, "Lojistas Ativos", formats["header_navy"])
    ws.write(5, 3, int(dre.get("total_customers", 0)), formats["cell_int"])

    ws.write(4, 4, "SKUs Faturados", formats["header_navy"])
    ws.write(5, 4, int(dre.get("total_products", 0)), formats["cell_int"])

    headers = [
        "Linha do Waterfall",
        "Descrição Canônica",
        "Valor Total (R$)",
        "% Faturamento Bruto",
        "% Receita Líquida",
        "Regra de Negócio & Base de Cálculo",
    ]
    for col_idx, h in enumerate(headers, start=1):
        ws.write(7, col_idx, h, formats["header_teal"])

    gross = dre.get("gross_revenue", 1.0)
    net_rev = dre.get("net_revenue", 1.0)

    rows = [
        (
            "(+) Faturamento Bruto (Preço de Tabela)",
            "gross_revenue = units * unit_list_price",
            dre.get("gross_revenue", 0.0),
            dre.get("gross_revenue", 0.0) / gross,
            dre.get("gross_revenue", 0.0) / net_rev,
            "Preço de tabela de fábrica sugerido para lojistas (R$ 15 a R$ 350)",
            True,
        ),
        (
            "(-) Desconto Comercial Concedido",
            "discount_amount = gross_revenue * discount_rate",
            dre.get("discount_amount", 0.0),
            dre.get("discount_amount", 0.0) / gross,
            dre.get("discount_amount", 0.0) / net_rev,
            "Baseline por porte (P 3%, M 6.5%, G 10.5%) + viés comportamental de RCA (-4% a +8%)",
            False,
        ),
        (
            "(=) Receita Faturada (Líquida de Desconto)",
            "net_price_revenue = gross_revenue - discount_amount",
            dre.get("net_price_revenue", 0.0),
            dre.get("net_price_revenue", 0.0) / gross,
            dre.get("net_price_revenue", 0.0) / net_rev,
            "Receita na Nota Fiscal (base de incidência de ICMS, PIS, COFINS e Comissão)",
            True,
        ),
        (
            "(-) Impostos sobre Venda",
            "tax_amount = ICMS + PIS (1.65%) + COFINS (7.60%)",
            dre.get("tax_amount", 0.0),
            dre.get("tax_amount", 0.0) / gross,
            dre.get("tax_amount", 0.0) / net_rev,
            "ICMS interestadual com origem SP (18% SP, 12% Sul/Sudeste, 7% N/NE/CO/ES) + PIS/COFINS (9.25%)",
            False,
        ),
        (
            "(=) Receita Líquida Real",
            "net_revenue = net_price_revenue - tax_amount",
            dre.get("net_revenue", 0.0),
            dre.get("net_revenue", 0.0) / gross,
            1.0,
            "Receita líquida que ingressa no cofre da indústria",
            True,
        ),
        (
            "(-) Custo dos Produtos Vendidos (CMV)",
            "cogs = units * unit_cost",
            dre.get("cogs", 0.0),
            dre.get("cogs", 0.0) / gross,
            dre.get("cogs", 0.0) / net_rev,
            "Custo fabril industrial de fabricação de brinquedos (~43% do preço de tabela)",
            False,
        ),
        (
            "(=) Margem Bruta Industrial",
            "gross_margin = net_revenue - cogs",
            dre.get("gross_margin", 0.0),
            dre.get("gross_margin", 0.0) / gross,
            dre.get("gross_margin", 0.0) / net_rev,
            "Margem fabril antes dos custos comerciais e logísticos de entrega",
            True,
        ),
        (
            "(-) Comissões de RCAs",
            "commission_amount = net_price_revenue * commission_rate",
            dre.get("commission_amount", 0.0),
            dre.get("commission_amount", 0.0) / gross,
            dre.get("commission_amount", 0.0) / net_rev,
            "Remuneração da equipe de representantes comerciais (alíquotas de 3.5% a 6.5%)",
            False,
        ),
        (
            "(-) Frete CIF de Expedição",
            "freight_amount = boxes * freight_per_box",
            dre.get("freight_amount", 0.0),
            dre.get("freight_amount", 0.0) / gross,
            dre.get("freight_amount", 0.0) / net_rev,
            "Frete pago pela indústria por caixa master expedida (R$ 3.50 Sudeste a R$ 11.00 Norte)",
            False,
        ),
        (
            "(=) Margem de Contribuição Líquida",
            "contribution_margin = net_revenue - cogs - commission - freight",
            dre.get("contribution_margin", 0.0),
            dre.get("contribution_margin", 0.0) / gross,
            dre.get("contribution_margin", 0.0) / net_rev,
            "Resultado líquido no bolso da empresa para cobrir despesas fixas e gerar lucro",
            True,
        ),
    ]

    for idx, (label, canon, val, p_gross, p_net, rule, is_bold) in enumerate(rows, start=8):
        fmt_text = formats["cell_bold_text"] if is_bold else formats["cell_text"]
        fmt_curr = formats["cell_currency_bold"] if is_bold else formats["cell_currency"]
        fmt_pct = formats["cell_percent_bold"] if is_bold else formats["cell_percent"]

        ws.write(idx, 1, label, fmt_text)
        ws.write(idx, 2, canon, fmt_text)
        ws.write(idx, 3, val, fmt_curr)
        ws.write(idx, 4, p_gross, fmt_pct)
        ws.write(idx, 5, p_net, fmt_pct)
        ws.write(idx, 6, rule, fmt_text)

    ws.set_column(1, 1, 40)
    ws.set_column(2, 2, 45)
    ws.set_column(3, 3, 20)
    ws.set_column(4, 5, 20)
    ws.set_column(6, 6, 65)


def _build_calc_memory_sheet(
    workbook: xlsxwriter.Workbook,
    formats: dict[str, Any],
    sample_df: pd.DataFrame,
) -> None:
    """Constrói a Aba 2: Memória de Cálculo Aberta (100 pedidos)."""
    ws = workbook.add_worksheet("Memoria_Calculo")
    ws.set_tab_color("#0D9488")
    ws.hide_gridlines(2)

    ws.write(1, 1, "MEMÓRIA DE CÁLCULO ABERTA — AMOSTRA DE 100 PEDIDOS DE VENDA", formats["title"])
    ws.write(
        2,
        1,
        "Amostra balanceada por lojista, região, família e RCA com todas as colunas intermediárias abertas.",
        formats["subtitle"],
    )

    columns_config = [
        ("Nº Pedido", "order_id", formats["cell_center"], 14),
        ("Data", "order_date", formats["cell_center"], 12),
        ("Lojista (Cliente)", "customer_name", formats["cell_text"], 28),
        ("Porte", "customer_size", formats["cell_center"], 8),
        ("UF", "state", formats["cell_center"], 6),
        ("Região", "region", formats["cell_center"], 14),
        ("RCA", "sales_rep", formats["cell_text"], 22),
        ("Produto", "product_name", formats["cell_text"], 32),
        ("Família", "family", formats["cell_text"], 22),
        ("Unidades", "units", formats["cell_int"], 10),
        ("Cx Master", "boxes", formats["cell_int"], 10),
        ("Preço Lista", "unit_list_price", formats["cell_currency"], 13),
        ("Faturamento Bruto", "gross_revenue", formats["cell_currency"], 18),
        ("Desc (%)", "discount_rate", formats["cell_percent"], 10),
        ("Desc (R$)", "discount_amount", formats["cell_currency"], 13),
        ("Receita Faturada", "net_price_revenue", formats["cell_currency"], 18),
        ("Impostos (%)", "tax_rate", formats["cell_percent"], 12),
        ("Impostos (R$)", "tax_amount", formats["cell_currency"], 14),
        ("Receita Líquida", "net_revenue", formats["cell_currency"], 18),
        ("Custo Unit (R$)", "unit_cost", formats["cell_currency"], 13),
        ("CMV Fabril (R$)", "cogs", formats["cell_currency"], 16),
        ("Comissão (%)", "commission_rate", formats["cell_percent"], 12),
        ("Comissão (R$)", "commission_amount", formats["cell_currency"], 14),
        ("Frete CIF (R$)", "freight_amount", formats["cell_currency"], 13),
        ("Margem Contr (R$)", "contribution_margin", formats["cell_currency"], 18),
        ("Margem (%)", "margin_pct", formats["cell_percent"], 12),
    ]

    for col_idx, (col_title, _, _, col_w) in enumerate(columns_config, start=1):
        ws.write(4, col_idx, col_title, formats["header_navy"])
        ws.set_column(col_idx, col_idx, col_w)

    start_row = 5
    for i, (_, row) in enumerate(sample_df.iterrows()):
        current_row = start_row + i
        for col_idx, (_, field_name, cell_fmt, _) in enumerate(columns_config, start=1):
            val = row[field_name]
            if field_name == "order_date":
                val = str(val)[:10]
            elif field_name in ("discount_rate", "tax_rate", "commission_rate"):
                val = float(val) if pd.notnull(val) else 0.0
            elif field_name == "margin_pct":
                val = float(val) / 100.0 if pd.notnull(val) else 0.0
            ws.write(current_row, col_idx, val, cell_fmt)

    end_row = start_row + len(sample_df) - 1
    total_row_idx = end_row + 1

    ws.write(total_row_idx, 1, "TOTAL AMOSTRA", formats["total_row_text"])
    for col_idx in range(2, 10):
        ws.write(total_row_idx, col_idx, "", formats["total_row_text"])

    col_letters = [xlsxwriter.utility.xl_col_to_name(col_idx) for col_idx in range(len(columns_config) + 1)]

    # Colunas numéricas somadas no rodapé: Unidades(10), Caixas(11), Bruto(13), Desc(15),
    # Receita Faturada(16), Impostos(18), Rec Líquida(19), CMV(21), Comissão(23), Frete(24), MC(25)
    for col_idx in (10, 11, 13, 15, 16, 18, 19, 21, 23, 24, 25):
        col_let = col_letters[col_idx]
        ws.write_formula(
            total_row_idx,
            col_idx,
            f"=SUM({col_let}{start_row + 1}:{col_let}{end_row + 1})",
            formats["total_row_currency"],
        )

    # Preço Médio (col 12)
    col_p = col_letters[12]
    ws.write_formula(
        total_row_idx,
        12,
        f"=AVERAGE({col_p}{start_row + 1}:{col_p}{end_row + 1})",
        formats["total_row_currency"],
    )

    # Margem % Média Ponderada da Amostra (col 26)
    col_gross = col_letters[13]
    col_mc = col_letters[25]
    ws.write_formula(
        total_row_idx,
        26,
        f"={col_mc}{total_row_idx + 1}/{col_gross}{total_row_idx + 1}",
        formats["total_row_percent"],
    )
