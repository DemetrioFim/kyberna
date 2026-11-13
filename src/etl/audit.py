from __future__ import annotations

from pathlib import Path
from typing import Final

import duckdb
import xlsxwriter

from src.core.logging import get_logger
from src.core.paths import get_data_dir, get_duckdb_path
from src.core.types import ScenarioId
from src.etl.audit_formats import _create_excel_formats
from src.etl.audit_queries import (
    _extract_abc_xyz_data,
    _extract_dre_data,
    _extract_families_summary,
    _extract_integrity_stats,
    _extract_rcas_summary,
    _extract_sample_orders,
    _extract_top_customers,
)
from src.etl.audit_sheets_dre import _build_calc_memory_sheet, _build_dre_sheet
from src.etl.audit_sheets_ops import (
    _build_abc_xyz_sheet,
    _build_families_sheet,
    _build_rcas_and_audit_sheet,
)

logger = get_logger(__name__)

DEFAULT_SCENARIO: Final[ScenarioId] = "c1_toys"

__all__ = [
    "DEFAULT_SCENARIO",
    "_build_abc_xyz_sheet",
    "_build_calc_memory_sheet",
    "_build_dre_sheet",
    "_build_families_sheet",
    "_build_rcas_and_audit_sheet",
    "_create_excel_formats",
    "_extract_abc_xyz_data",
    "_extract_dre_data",
    "_extract_families_summary",
    "_extract_integrity_stats",
    "_extract_rcas_summary",
    "_extract_sample_orders",
    "_extract_top_customers",
    "generate_audit_report",
]


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
    5. Aba `Matriz_ABC_XYZ`: Matriz 3x3 ABC/XYZ e políticas prescritivas de estoque.

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
        reports_dir = get_data_dir() / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        if output_path is None:
            output_path = reports_dir / f"conciliacao_{scenario_id}.xlsx"

        dre_data = _extract_dre_data(con, scenario_id)
        sample_df = _extract_sample_orders(con, scenario_id, limit=100)
        families_df = _extract_families_summary(con, scenario_id)
        rcas_df = _extract_rcas_summary(con, scenario_id)
        top_customers_df = _extract_top_customers(con, scenario_id, limit=20)
        integrity_data = _extract_integrity_stats(con, scenario_id)
        abc_xyz_df, matrix_summary_df = _extract_abc_xyz_data(con, scenario_id)

        workbook = xlsxwriter.Workbook(str(output_path), {"nan_inf_to_errors": True})
        formats = _create_excel_formats(workbook)

        _build_dre_sheet(workbook, formats, dre_data, scenario_id)
        _build_calc_memory_sheet(workbook, formats, sample_df)
        _build_families_sheet(workbook, formats, families_df)
        _build_rcas_and_audit_sheet(
            workbook, formats, rcas_df, top_customers_df, integrity_data, scenario_id=scenario_id
        )
        _build_abc_xyz_sheet(workbook, formats, abc_xyz_df, matrix_summary_df)

        workbook.close()
        logger.info("Planilha de conciliação gerada com sucesso em: %s", output_path)
        return output_path

    finally:
        if close_con:
            con.close()
