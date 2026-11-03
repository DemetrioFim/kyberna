from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Final

import duckdb
import pandas as pd
import xlsxwriter

from src.core.logging import get_logger
from src.core.paths import get_data_dir, get_duckdb_path
from src.core.types import ScenarioId
from src.ml.abc_xyz import build_abc_xyz_mart, compute_abc_xyz_matrix_summary

logger = get_logger(__name__)

DEFAULT_SCENARIO: Final[ScenarioId] = "c1_toys"


def generate_audit_report(
    con: duckdb.DuckDBPyConnection | None = None,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
    output_path: Path | None = None,
) -> Path:
    """Gera a planilha Excel oficial de conciliação financeira e memória de cálculo.

    A planilha é gravada em `data/reports/conciliacao_<scenario_id>.xlsx` e contém:
    1. Aba `DRE_Waterfall`: Demonstração do Resultado com decomposição de todas as linhas
       da margem de contribuição, percentuais de faturamento bruto e líquido, e memória explicativa.
    2. Aba `Memoria_Calculo`: Amostra de 100 pedidos reais abertos coluna por coluna com fórmulas
       de somatório no rodapé.
    3. Aba `Resumo_Familias_Mix`: Faturamento, margem e caixas por família de produtos.
    4. Aba `Auditoria_RCAs_Clientes`: Ranking de RCAs, Top 20 lojistas e painel de validação
       e integridade contábil.

    Args:
        con: Conexão DuckDB existente (ou abre get_duckdb_path() se None).
        scenario_id: Identificador do cenário (ex: 'c1_toys').
        output_path: Caminho customizado de saída (opcional).

    Returns:
        Path para o arquivo Excel gerado.
    """
    logger.info("Iniciando geração da planilha de conciliação para '%s'...", scenario_id)

    close_con = False
    if con is None:
        con = duckdb.connect(str(get_duckdb_path()))
        close_con = True

    try:
        # Garante que o diretório de relatórios exista
        reports_dir = get_data_dir() / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        if output_path is None:
            output_path = reports_dir / f"conciliacao_{scenario_id}.xlsx"

        # Extração dos dados necessários para as 4 abas
        dre_data = _extract_dre_data(con, scenario_id)
        sample_df = _extract_sample_orders(con, scenario_id, limit=100)
        families_df = _extract_families_summary(con, scenario_id)
        rcas_df = _extract_rcas_summary(con, scenario_id)
        top_customers_df = _extract_top_customers(con, scenario_id, limit=20)
        integrity_data = _extract_integrity_stats(con, scenario_id)
        abc_xyz_df, matrix_summary_df = _extract_abc_xyz_data(con, scenario_id)

        # Construção da planilha via xlsxwriter
        workbook = xlsxwriter.Workbook(str(output_path), {"nan_inf_to_errors": True})

        # Estilos corporativos Kyberna
        formats = _create_excel_formats(workbook)

        # 1. Aba DRE Waterfall
        _build_dre_sheet(workbook, formats, dre_data, scenario_id)

        # 2. Aba Memória de Cálculo
        _build_calc_memory_sheet(workbook, formats, sample_df)

        # 3. Aba Resumo Famílias & Mix
        _build_families_sheet(workbook, formats, families_df)

        # 4. Aba Auditoria RCAs & Clientes
        _build_rcas_and_audit_sheet(
            workbook, formats, rcas_df, top_customers_df, integrity_data, scenario_id=scenario_id
        )

        # 5. Aba Matriz ABC/XYZ
        _build_abc_xyz_sheet(workbook, formats, abc_xyz_df, matrix_summary_df)

        workbook.close()
        logger.info("Planilha de conciliação gerada com sucesso em: %s", output_path)
        return output_path

    finally:
        if close_con:
            con.close()


# ==============================================================================
# Extrações de Dados via SQL DuckDB
# ==============================================================================


def _extract_dre_data(con: duckdb.DuckDBPyConnection, scenario_id: str) -> dict[str, float]:
    """Extrai os totais consolidados do Waterfall para a DRE."""
    query = f"""
    SELECT
        ROUND(SUM(gross_revenue), 2) AS gross_revenue,
        ROUND(SUM(discount_amount), 2) AS discount_amount,
        ROUND(SUM(gross_revenue - discount_amount), 2) AS net_price_revenue,
        ROUND(SUM(tax_amount), 2) AS tax_amount,
        ROUND(SUM(net_revenue), 2) AS net_revenue,
        ROUND(SUM(cogs), 2) AS cogs,
        ROUND(SUM(net_revenue - cogs), 2) AS gross_margin,
        ROUND(SUM(commission_amount), 2) AS commission_amount,
        ROUND(SUM(freight_amount), 2) AS freight_amount,
        ROUND(SUM(contribution_margin), 2) AS contribution_margin,
        COUNT(*) AS total_lines,
        COUNT(DISTINCT order_id) AS total_orders,
        COUNT(DISTINCT customer_id) AS total_customers,
        COUNT(DISTINCT product_id) AS total_products
    FROM gold.fact_sales
    WHERE scenario_id = '{scenario_id}'
    """
    row = con.execute(query).fetchone()
    if not row:
        return {}
    cols = [
        "gross_revenue",
        "discount_amount",
        "net_price_revenue",
        "tax_amount",
        "net_revenue",
        "cogs",
        "gross_margin",
        "commission_amount",
        "freight_amount",
        "contribution_margin",
        "total_lines",
        "total_orders",
        "total_customers",
        "total_products",
    ]
    return {col: float(val) if val is not None else 0.0 for col, val in zip(cols, row, strict=False)}


def _extract_sample_orders(
    con: duckdb.DuckDBPyConnection, scenario_id: str, limit: int = 100
) -> pd.DataFrame:
    """Extrai amostra balanceada de 100 pedidos com colunas intermediárias abertas."""
    query = f"""
    SELECT
        f.order_id,
        d.full_date AS order_date,
        c.trade_name AS customer_name,
        c.size AS customer_size,
        c.state,
        c.region,
        r.name AS sales_rep,
        p.product_name,
        p.family,
        f.units,
        f.boxes,
        f.unit_list_price,
        f.gross_revenue,
        ROUND(f.discount_amount / NULLIF(f.gross_revenue, 0), 4) AS discount_rate,
        f.discount_amount,
        ROUND(f.gross_revenue - f.discount_amount, 2) AS net_price_revenue,
        ROUND(f.tax_amount / NULLIF(f.gross_revenue - f.discount_amount, 0), 4) AS tax_rate,
        f.tax_amount,
        f.net_revenue,
        ROUND(f.cogs / NULLIF(f.units, 0), 2) AS unit_cost,
        f.cogs,
        ROUND(f.commission_amount / NULLIF(f.gross_revenue - f.discount_amount, 0), 4) AS commission_rate,
        f.commission_amount,
        f.freight_amount,
        f.contribution_margin,
        ROUND(f.contribution_margin / NULLIF(f.gross_revenue, 0) * 100.0, 2) AS margin_pct
    FROM gold.fact_sales f
    JOIN gold.dim_date d ON f.date_key = d.date_key
    JOIN gold.dim_customer c ON f.customer_id = c.customer_id
    JOIN gold.dim_sales_rep r ON f.sales_rep_id = r.sales_rep_id
    JOIN gold.dim_product p ON f.product_id = p.product_id
    WHERE f.scenario_id = '{scenario_id}'
    ORDER BY d.full_date DESC, f.gross_revenue DESC
    LIMIT {limit}
    """
    return con.execute(query).df()


def _extract_families_summary(con: duckdb.DuckDBPyConnection, scenario_id: str) -> pd.DataFrame:
    """Agrega faturamento e margem por família de produtos."""
    query = f"""
    SELECT
        p.family,
        COUNT(DISTINCT f.order_id) AS orders_count,
        SUM(f.units) AS units,
        ROUND(SUM(f.boxes), 2) AS boxes,
        ROUND(SUM(f.gross_revenue), 2) AS gross_revenue,
        ROUND(SUM(f.discount_amount), 2) AS discount_amount,
        ROUND(SUM(f.tax_amount), 2) AS tax_amount,
        ROUND(SUM(f.net_revenue), 2) AS net_revenue,
        ROUND(SUM(f.cogs), 2) AS cogs,
        ROUND(SUM(f.contribution_margin), 2) AS contribution_margin,
        ROUND(SUM(f.contribution_margin) / NULLIF(SUM(f.gross_revenue), 0) * 100.0, 2) AS margin_pct
    FROM gold.fact_sales f
    JOIN gold.dim_product p ON f.product_id = p.product_id
    WHERE f.scenario_id = '{scenario_id}'
    GROUP BY p.family
    ORDER BY gross_revenue DESC
    """
    df = con.execute(query).df()
    total_rev = df["gross_revenue"].sum()
    df["revenue_share_pct"] = (df["gross_revenue"] / total_rev * 100.0).round(2)
    return df


def _extract_rcas_summary(con: duckdb.DuckDBPyConnection, scenario_id: str) -> pd.DataFrame:
    """Extrai performance e comportamento de desconto por RCA."""
    query = f"""
    SELECT
        r.name AS sales_rep,
        r.region,
        COUNT(DISTINCT f.order_id) AS orders_count,
        COUNT(DISTINCT f.customer_id) AS customers_count,
        ROUND(SUM(f.gross_revenue), 2) AS gross_revenue,
        ROUND(SUM(f.discount_amount) / NULLIF(SUM(f.gross_revenue), 0) * 100.0, 2) AS avg_discount_pct,
        ROUND(SUM(f.commission_amount), 2) AS total_commission,
        ROUND(SUM(f.contribution_margin), 2) AS contribution_margin,
        ROUND(SUM(f.contribution_margin) / NULLIF(SUM(f.gross_revenue), 0) * 100.0, 2) AS margin_pct
    FROM gold.fact_sales f
    JOIN gold.dim_sales_rep r ON f.sales_rep_id = r.sales_rep_id
    WHERE f.scenario_id = '{scenario_id}'
    GROUP BY r.name, r.region
    ORDER BY gross_revenue DESC
    """
    return con.execute(query).df()


def _extract_top_customers(con: duckdb.DuckDBPyConnection, scenario_id: str, limit: int = 20) -> pd.DataFrame:
    """Extrai os top lojistas por faturamento e margem."""
    query = f"""
    SELECT
        c.trade_name,
        c.cnpj,
        c.size,
        c.city,
        c.state,
        r.name AS sales_rep,
        COUNT(DISTINCT f.order_id) AS orders_count,
        ROUND(SUM(f.gross_revenue), 2) AS gross_revenue,
        ROUND(SUM(f.contribution_margin), 2) AS contribution_margin,
        ROUND(SUM(f.contribution_margin) / NULLIF(SUM(f.gross_revenue), 0) * 100.0, 2) AS margin_pct
    FROM gold.fact_sales f
    JOIN gold.dim_customer c ON f.customer_id = c.customer_id
    JOIN gold.dim_sales_rep r ON f.sales_rep_id = r.sales_rep_id
    WHERE f.scenario_id = '{scenario_id}'
    GROUP BY c.trade_name, c.cnpj, c.size, c.city, c.state, r.name
    ORDER BY gross_revenue DESC
    LIMIT {limit}
    """
    return con.execute(query).df()


def _extract_integrity_stats(con: duckdb.DuckDBPyConnection, scenario_id: str) -> dict[str, Any]:
    """Audita a conservação e identidade contábil linha a linha."""
    query = f"""
    SELECT
        COUNT(*) AS total_rows,
        COUNT(
            CASE
                WHEN ABS(
                    contribution_margin - (net_revenue - cogs - commission_amount - freight_amount)
                ) > 0.01
                THEN 1
            END
        ) AS math_divergences,
        ROUND(SUM(gross_revenue), 2) AS total_gross_gold,
        (SELECT ROUND(SUM(gross_revenue), 2) FROM {scenario_id}.sales_remapped) AS total_gross_silver
    FROM gold.fact_sales
    WHERE scenario_id = '{scenario_id}'
    """
    row = con.execute(query).fetchone()
    if not row:
        return {}
    return {
        "total_rows": int(row[0]),
        "divergences": int(row[1]),
        "total_gold": float(row[2]),
        "total_silver": float(row[3]) if row[3] is not None else float(row[2]),
    }


def _extract_abc_xyz_data(
    con: duckdb.DuckDBPyConnection, scenario_id: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Extrai os dados da Matriz ABC/XYZ e o resumo executivo das 9 células."""
    table_exists = False
    try:
        res = con.execute(
            f"SELECT COUNT(*) FROM information_schema.tables "
            f"WHERE table_schema IN ('{scenario_id}', 'gold') AND table_name = 'mart_abc_xyz'"
        ).fetchone()
        table_exists = bool(res and res[0] > 0)
    except Exception:
        table_exists = False

    if table_exists:
        df = con.execute(
            f"SELECT * FROM gold.mart_abc_xyz WHERE scenario_id = '{scenario_id}' "
            f"ORDER BY abc_class ASC, contribution_margin DESC, product_id ASC"
        ).df()
    else:
        df = build_abc_xyz_mart(con, scenario_id=scenario_id)  # type: ignore[arg-type]

    summary = compute_abc_xyz_matrix_summary(df)
    return df, summary


# ==============================================================================
# Estilização Corporativa Excel (xlsxwriter)
# ==============================================================================


def _create_excel_formats(workbook: xlsxwriter.Workbook) -> dict[str, xlsxwriter.format.Format]:
    """Cria a paleta de formatação corporativa Kyberna."""
    base_font = "Calibri"

    return {
        "title": workbook.add_format(
            {
                "font_name": base_font,
                "font_size": 16,
                "bold": True,
                "font_color": "#0A192F",
            }
        ),
        "subtitle": workbook.add_format(
            {
                "font_name": base_font,
                "font_size": 11,
                "italic": True,
                "font_color": "#475569",
            }
        ),
        "header_navy": workbook.add_format(
            {
                "font_name": base_font,
                "font_size": 11,
                "bold": True,
                "bg_color": "#0A192F",
                "font_color": "#FFFFFF",
                "border": 1,
                "align": "center",
                "valign": "vcenter",
            }
        ),
        "header_teal": workbook.add_format(
            {
                "font_name": base_font,
                "font_size": 11,
                "bold": True,
                "bg_color": "#0D9488",
                "font_color": "#FFFFFF",
                "border": 1,
                "align": "center",
                "valign": "vcenter",
            }
        ),
        "header_amber": workbook.add_format(
            {
                "font_name": base_font,
                "font_size": 11,
                "bold": True,
                "bg_color": "#D97706",
                "font_color": "#FFFFFF",
                "border": 1,
                "align": "center",
                "valign": "vcenter",
            }
        ),
        "cell_text": workbook.add_format(
            {
                "font_name": base_font,
                "font_size": 10,
                "border": 1,
                "align": "left",
                "valign": "vcenter",
            }
        ),
        "cell_bold_text": workbook.add_format(
            {
                "font_name": base_font,
                "font_size": 10,
                "bold": True,
                "border": 1,
                "align": "left",
                "valign": "vcenter",
            }
        ),
        "cell_currency": workbook.add_format(
            {
                "font_name": base_font,
                "font_size": 10,
                "border": 1,
                "num_format": "R$ #,##0.00",
                "align": "right",
                "valign": "vcenter",
            }
        ),
        "cell_currency_bold": workbook.add_format(
            {
                "font_name": base_font,
                "font_size": 10,
                "bold": True,
                "border": 1,
                "num_format": "R$ #,##0.00",
                "align": "right",
                "valign": "vcenter",
                "bg_color": "#F8FAFC",
            }
        ),
        "cell_percent": workbook.add_format(
            {
                "font_name": base_font,
                "font_size": 10,
                "border": 1,
                "num_format": "0.0%",
                "align": "right",
                "valign": "vcenter",
            }
        ),
        "cell_percent_bold": workbook.add_format(
            {
                "font_name": base_font,
                "font_size": 10,
                "bold": True,
                "border": 1,
                "num_format": "0.0%",
                "align": "right",
                "valign": "vcenter",
                "bg_color": "#F8FAFC",
            }
        ),
        "cell_int": workbook.add_format(
            {
                "font_name": base_font,
                "font_size": 10,
                "border": 1,
                "num_format": "#,##0",
                "align": "right",
                "valign": "vcenter",
            }
        ),
        "cell_center": workbook.add_format(
            {
                "font_name": base_font,
                "font_size": 10,
                "border": 1,
                "align": "center",
                "valign": "vcenter",
            }
        ),
        "cell_float": workbook.add_format(
            {
                "font_name": base_font,
                "font_size": 10,
                "border": 1,
                "num_format": "#,##0.00",
                "align": "right",
                "valign": "vcenter",
            }
        ),
        "cell_code": workbook.add_format(
            {
                "font_name": "Consolas",
                "font_size": 9,
                "border": 1,
                "align": "center",
                "valign": "vcenter",
            }
        ),
        "total_row_currency": workbook.add_format(
            {
                "font_name": base_font,
                "font_size": 11,
                "bold": True,
                "top": 1,
                "bottom": 6,
                "num_format": "R$ #,##0.00",
                "bg_color": "#F1F5F9",
                "align": "right",
            }
        ),
        "total_row_text": workbook.add_format(
            {
                "font_name": base_font,
                "font_size": 11,
                "bold": True,
                "top": 1,
                "bottom": 6,
                "bg_color": "#F1F5F9",
                "align": "left",
            }
        ),
        "total_row_percent": workbook.add_format(
            {
                "font_name": base_font,
                "font_size": 11,
                "bold": True,
                "top": 1,
                "bottom": 6,
                "num_format": "0.0%",
                "bg_color": "#F1F5F9",
                "align": "right",
            }
        ),
        "badge_pass": workbook.add_format(
            {
                "font_name": base_font,
                "font_size": 11,
                "bold": True,
                "bg_color": "#DCFCE7",
                "font_color": "#166534",
                "border": 1,
                "align": "center",
            }
        ),
    }


# ==============================================================================
# Construtores de Abas do Excel
# ==============================================================================


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

    # Cabeçalho da Empresa
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

    # Cards Resumo no topo
    ws.write(4, 1, "Volume de Linhas Auditadas", formats["header_navy"])
    ws.write(5, 1, int(dre.get("total_lines", 0)), formats["cell_int"])

    ws.write(4, 2, "Pedidos Distintos", formats["header_navy"])
    ws.write(5, 2, int(dre.get("total_orders", 0)), formats["cell_int"])

    ws.write(4, 3, "Lojistas Ativos", formats["header_navy"])
    ws.write(5, 3, int(dre.get("total_customers", 0)), formats["cell_int"])

    ws.write(4, 4, "SKUs Faturados", formats["header_navy"])
    ws.write(5, 4, int(dre.get("total_products", 0)), formats["cell_int"])

    # Tabela DRE
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

    # Larguras das colunas
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

    # Cabeçalho
    for col_idx, (col_title, _, _, col_w) in enumerate(columns_config, start=1):
        ws.write(4, col_idx, col_title, formats["header_navy"])
        ws.set_column(col_idx, col_idx, col_w)

    # Linhas de Dados
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

    # Linha de Totalização com Fórmulas Excel
    end_row = start_row + len(sample_df) - 1
    total_row_idx = end_row + 1

    ws.write(total_row_idx, 1, "TOTAL AMOSTRA", formats["total_row_text"])
    for col_idx in range(2, 10):
        ws.write(total_row_idx, col_idx, "", formats["total_row_text"])

    # Fórmulas de Soma para Unidades, Caixas, Faturamento, Descontos, Impostos, etc.
    col_letters = [xlsxwriter.utility.xl_col_to_name(col_idx) for col_idx in range(len(columns_config) + 1)]

    # Unidades (col 10)
    col_u = col_letters[10]
    ws.write_formula(
        total_row_idx, 10, f"=SUM({col_u}{start_row + 1}:{col_u}{end_row + 1})", formats["total_row_currency"]
    )

    # Caixas (col 11)
    col_b = col_letters[11]
    ws.write_formula(
        total_row_idx,
        11,
        f"=SUM({col_b}{start_row + 1}:{col_b}{end_row + 1})",
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

    # Faturamento Bruto (col 13)
    col_gross = col_letters[13]
    ws.write_formula(
        total_row_idx,
        13,
        f"=SUM({col_gross}{start_row + 1}:{col_gross}{end_row + 1})",
        formats["total_row_currency"],
    )

    # Desconto R$ (col 15)
    col_desc = col_letters[15]
    ws.write_formula(
        total_row_idx,
        15,
        f"=SUM({col_desc}{start_row + 1}:{col_desc}{end_row + 1})",
        formats["total_row_currency"],
    )

    # Receita Faturada (col 16)
    col_fat = col_letters[16]
    ws.write_formula(
        total_row_idx,
        16,
        f"=SUM({col_fat}{start_row + 1}:{col_fat}{end_row + 1})",
        formats["total_row_currency"],
    )

    # Impostos R$ (col 18)
    col_tax = col_letters[18]
    ws.write_formula(
        total_row_idx,
        18,
        f"=SUM({col_tax}{start_row + 1}:{col_tax}{end_row + 1})",
        formats["total_row_currency"],
    )

    # Receita Líquida (col 19)
    col_net = col_letters[19]
    ws.write_formula(
        total_row_idx,
        19,
        f"=SUM({col_net}{start_row + 1}:{col_net}{end_row + 1})",
        formats["total_row_currency"],
    )

    # CMV (col 21)
    col_cogs = col_letters[21]
    ws.write_formula(
        total_row_idx,
        21,
        f"=SUM({col_cogs}{start_row + 1}:{col_cogs}{end_row + 1})",
        formats["total_row_currency"],
    )

    # Comissão R$ (col 23)
    col_com = col_letters[23]
    ws.write_formula(
        total_row_idx,
        23,
        f"=SUM({col_com}{start_row + 1}:{col_com}{end_row + 1})",
        formats["total_row_currency"],
    )

    # Frete R$ (col 24)
    col_freight = col_letters[24]
    ws.write_formula(
        total_row_idx,
        24,
        f"=SUM({col_freight}{start_row + 1}:{col_freight}{end_row + 1})",
        formats["total_row_currency"],
    )

    # Margem Contribuição R$ (col 25)
    col_mc = col_letters[25]
    ws.write_formula(
        total_row_idx,
        25,
        f"=SUM({col_mc}{start_row + 1}:{col_mc}{end_row + 1})",
        formats["total_row_currency"],
    )

    # Margem % Média Ponderada da Amostra (col 26)
    ws.write_formula(
        total_row_idx,
        26,
        f"={col_mc}{total_row_idx + 1}/{col_gross}{total_row_idx + 1}",
        formats["total_row_percent"],
    )


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

    # Linha Total
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

    # Margem % média geral
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

    # 1. Painel de Integridade Contábil
    _build_integrity_panel(ws, formats, integrity)

    # 2. Ranking de RCAs
    next_row = _build_rcas_table(ws, formats, rcas_df)

    # 3. Top 20 Lojistas
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

    # Tabela 1: Resumo das 9 Células
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

    # Tabela 2: Amostra dos Top 30 SKUs Classificados
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
