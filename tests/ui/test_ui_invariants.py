from __future__ import annotations

import ast
from pathlib import Path

from src.core.paths import get_project_root


def _iter_ui_py_files() -> list[Path]:
    ui_root = get_project_root() / "src" / "ui"
    return sorted(p for p in ui_root.rglob("*.py") if p.name != "__init__.py")


def test_all_plotly_chart_calls_use_theme_none() -> None:
    """Garante theme=None em 100% dos st.plotly_chart para não quebrar Dark Mode."""
    missing: list[str] = []
    for py_file in _iter_ui_py_files():
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            is_plotly_chart = (
                isinstance(func, ast.Attribute)
                and func.attr == "plotly_chart"
                and isinstance(func.value, ast.Name)
                and func.value.id == "st"
            )
            if not is_plotly_chart:
                continue
            theme_kw = next((kw for kw in node.keywords if kw.arg == "theme"), None)
            has_none = (
                theme_kw is not None
                and isinstance(theme_kw.value, ast.Constant)
                and theme_kw.value.value is None
            )
            if not has_none:
                missing.append(f"{py_file.name}:{node.lineno}")
    assert not missing, f"Chamadas st.plotly_chart sem theme=None: {missing}"


def test_no_unescaped_double_dollar_in_ui_captions() -> None:
    """Impede múltiplos cifrões ($) em st.caption que disparam renderização KaTeX acidental."""
    violations: list[str] = []
    for py_file in _iter_ui_py_files():
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            is_caption = (
                isinstance(func, ast.Attribute)
                and func.attr == "caption"
                and isinstance(func.value, ast.Name)
                and func.value.id == "st"
            )
            if not is_caption or not node.args:
                continue
            arg0 = node.args[0]
            literal_dollars = 0
            brl_calls = 0
            for sub in ast.walk(arg0):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    literal_dollars += sub.value.count("$")
                elif isinstance(sub, ast.Call) and (
                    (isinstance(sub.func, ast.Name) and sub.func.id == "format_brl")
                    or (isinstance(sub.func, ast.Attribute) and sub.func.attr == "format_brl")
                ):
                    brl_calls += 1
            if literal_dollars + brl_calls >= 2:
                violations.append(f"{py_file.name}:{node.lineno}")
    assert not violations, f"st.caption com potencial bug KaTeX (>=2 $): {violations}"


def test_one_tab_bar_per_page_and_zero_in_components() -> None:
    """Garante exatamente 1 barra st.tabs por página e 0 sub-abas em components/."""
    ui_root = get_project_root() / "src" / "ui"
    page_violations: list[str] = []
    comp_violations: list[str] = []

    def _count_st_tabs(py_file: Path) -> int:
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        return sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "tabs"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "st"
        )

    for page_file in sorted((ui_root / "pages").glob("*.py")):
        if page_file.name == "__init__.py":
            continue
        count = _count_st_tabs(page_file)
        if count != 1:
            page_violations.append(f"{page_file.name}={count}")

    for comp_file in sorted((ui_root / "components").glob("*.py")):
        if comp_file.name == "__init__.py":
            continue
        count = _count_st_tabs(comp_file)
        if count != 0:
            comp_violations.append(f"{comp_file.name}={count}")

    assert not page_violations, f"Páginas com quantidade inválida de st.tabs: {page_violations}"
    assert not comp_violations, f"Componentes com sub-abas st.tabs proibidas: {comp_violations}"


def test_no_margem_liquida_in_ui_strings() -> None:
    """Impede regressão de 'Margem Líquida' em strings de UI (padronizado para Margem de Contribuição)."""
    ui_root = get_project_root() / "src" / "ui"
    target_files = sorted(
        list((ui_root / "pages").glob("*.py")) + list((ui_root / "components").glob("*.py"))
    )
    violations: list[str] = []
    for py_file in target_files:
        if py_file.name == "__init__.py":
            continue
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        docstring_nodes: set[int] = set()
        for node in ast.walk(tree):
            if (
                isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                and node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
            ):
                docstring_nodes.add(id(node.body[0].value))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstring_nodes
                and "margem líquida" in node.value.lower()
            ):
                violations.append(f"{py_file.name}:{node.lineno}")
    assert not violations, f"Strings de UI com 'Margem Líquida' residual: {violations}"
