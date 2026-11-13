from __future__ import annotations

import xlsxwriter


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
