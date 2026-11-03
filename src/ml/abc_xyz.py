from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from itertools import product
from typing import Any, Final, Literal

import duckdb
import pandas as pd
import yaml

from src.core.logging import get_logger
from src.core.paths import config_path, gold_snapshot_path
from src.core.types import ScenarioId
from src.etl.contracts import GoldAbcXyzSchema, validate_contract
from src.ml.features import compute_sku_features, resolve_as_of_date

logger = get_logger(__name__)

DEFAULT_SCENARIO: Final[ScenarioId] = "c1_toys"
DEFAULT_METRIC: Final[str] = "contribution_margin"
DEFAULT_A_CUTOFF: Final[float] = 0.80
DEFAULT_B_CUTOFF: Final[float] = 0.95
DEFAULT_X_CUTOFF: Final[float] = 0.50
DEFAULT_Y_CUTOFF: Final[float] = 1.00

DEFAULT_POLICIES: Final[dict[str, str]] = {
    "AX": "Ruptura zero / Estoque de segurança alto e ressuprimento contínuo (JIT)",
    "AY": "Estoque de segurança moderado / Atenção a picos sazonais e campanhas",
    "AZ": "Estoque de segurança sob medida / Produção puxada ou sob encomenda flexível",
    "BX": "Ressuprimento automático / Ponto de pedido fixo e lote econômico",
    "BY": "Revisão periódica / Gestão padrão por ponto de pedido",
    "BZ": "Estoque mínimo / Reposição por lote econômico ou sob demanda",
    "CX": "Estoque enxuto / Compras programadas e automatizadas em lote padrão",
    "CY": "Estoque mínimo / Compra em lotes pequenos apenas com giro garantido",
    "CZ": "Sob encomenda ou descontinuar / Liquidar estoque excedente",
}


def load_abc_xyz_config() -> dict[str, Any]:
    """Carrega as configurações e políticas da Matriz ABC/XYZ de `config/pipeline.yaml`.

    Returns:
        Dicionário com parâmetros `abc_metric`, `abc_a_cutoff`, `abc_b_cutoff`,
        `xyz_x_cutoff`, `xyz_y_cutoff` e dicionário `abc_xyz_policies`.
    """
    cfg_file = config_path("pipeline.yaml")
    if not cfg_file.exists():
        logger.warning(
            "Arquivo '%s' não encontrado. Utilizando parâmetros padrão de ABC/XYZ.",
            cfg_file,
        )
        return {
            "abc_metric": DEFAULT_METRIC,
            "abc_a_cutoff": DEFAULT_A_CUTOFF,
            "abc_b_cutoff": DEFAULT_B_CUTOFF,
            "xyz_x_cutoff": DEFAULT_X_CUTOFF,
            "xyz_y_cutoff": DEFAULT_Y_CUTOFF,
            "abc_xyz_policies": DEFAULT_POLICIES.copy(),
        }

    try:
        with open(cfg_file, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        thresholds = raw.get("thresholds", {})
        policies = thresholds.get("abc_xyz_policies", DEFAULT_POLICIES)

        return {
            "abc_metric": thresholds.get("abc_metric", DEFAULT_METRIC),
            "abc_a_cutoff": float(thresholds.get("abc_a_cutoff", DEFAULT_A_CUTOFF)),
            "abc_b_cutoff": float(thresholds.get("abc_b_cutoff", DEFAULT_B_CUTOFF)),
            "xyz_x_cutoff": float(thresholds.get("xyz_x_cutoff", DEFAULT_X_CUTOFF)),
            "xyz_y_cutoff": float(thresholds.get("xyz_y_cutoff", DEFAULT_Y_CUTOFF)),
            "abc_xyz_policies": {**DEFAULT_POLICIES, **policies},
        }
    except Exception as exc:
        logger.warning(
            "Erro ao ler '%s': %s. Utilizando parâmetros padrão de ABC/XYZ.",
            cfg_file,
            exc,
        )
        return {
            "abc_metric": DEFAULT_METRIC,
            "abc_a_cutoff": DEFAULT_A_CUTOFF,
            "abc_b_cutoff": DEFAULT_B_CUTOFF,
            "xyz_x_cutoff": DEFAULT_X_CUTOFF,
            "xyz_y_cutoff": DEFAULT_Y_CUTOFF,
            "abc_xyz_policies": DEFAULT_POLICIES.copy(),
        }


def _calculate_abc_classes(
    df: pd.DataFrame,
    metric: str,
    a_cutoff: float,
    b_cutoff: float,
) -> list[str]:
    """Calcula as classes A, B ou C para cada SKU a partir do acumulado da métrica."""
    target_cum = df["cum_margin_share"] if metric == "contribution_margin" else df["cum_revenue_share"]
    prev_cum = target_cum.shift(1).fillna(0.0)

    abc_classes: list[str] = []
    for i, (_, row) in enumerate(df.iterrows()):
        val = row[metric]
        p_cum = prev_cum.iloc[i]

        if val <= 0:
            abc_classes.append("C")
        elif p_cum < a_cutoff or i == 0:
            abc_classes.append("A")
        elif p_cum < b_cutoff:
            abc_classes.append("B")
        else:
            abc_classes.append("C")
    return abc_classes


def _calculate_xyz_classes(
    df: pd.DataFrame,
    x_cutoff: float,
    y_cutoff: float,
) -> list[str]:
    """Calcula as classes X, Y ou Z para cada SKU a partir do coeficiente de variação."""
    xyz_classes: list[str] = []
    for _, row in df.iterrows():
        mean_demand = row["weekly_demand_mean"]
        cv = row["weekly_cv"]

        if mean_demand <= 0 or pd.isna(cv):
            xyz_classes.append("Z")
        elif cv <= x_cutoff:
            xyz_classes.append("X")
        elif cv <= y_cutoff:
            xyz_classes.append("Y")
        else:
            xyz_classes.append("Z")
    return xyz_classes


def classify_abc_xyz(
    sku_features_df: pd.DataFrame,
    *,
    metric: Literal["contribution_margin", "gross_revenue"] = "contribution_margin",
    a_cutoff: float = DEFAULT_A_CUTOFF,
    b_cutoff: float = DEFAULT_B_CUTOFF,
    x_cutoff: float = DEFAULT_X_CUTOFF,
    y_cutoff: float = DEFAULT_Y_CUTOFF,
    policies: Mapping[str, str] | None = None,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
    as_of_date: date | datetime | str | None = None,
) -> pd.DataFrame:
    """Classifica produtos na Matriz ABC/XYZ 3x3 e associa a política prescritiva.

    Regras de negócio:
        - Curva ABC: ranqueamento decrescente por `metric` (margem de contribuição ou receita).
          Cortes configuráveis:
            - Classe A: Top 80% do acumulado (ou primeiro item que atinge o limiar)
            - Classe B: Próximos 15% (de 80% a 95% do acumulado)
            - Classe C: Cauda longa (> 95% do acumulado ou margem/receita zerada/negativa)
        - Curva XYZ: previsibilidade da demanda semanal (lookback de 26 semanas):
          - Classe X: Demanda estável e altamente previsível (CV <= 0,50 e demanda > 0)
          - Classe Y: Demanda com variabilidade moderada (0,50 < CV <= 1,00 e demanda > 0)
          - Classe Z: Demanda errática/intermitente (CV > 1,00 ou sem vendas no período)

    Args:
        sku_features_df: DataFrame gerado por `compute_sku_features`.
        metric: Métrica de valor para o corte ABC ("contribution_margin" ou "gross_revenue").
        a_cutoff: Limiar acumulado para Classe A (default: 0.80).
        b_cutoff: Limiar acumulado para Classe B (default: 0.95).
        x_cutoff: Limiar superior de CV para Classe X (default: 0.50).
        y_cutoff: Limiar superior de CV para Classe Y (default: 1.00).
        policies: Dicionário mapeando as 9 células ("AX" a "CZ") para políticas em texto.
        scenario_id: Identificador do cenário de negócio.
        as_of_date: Data de corte temporal analítica.

    Returns:
        pd.DataFrame validado contra `GoldAbcXyzSchema`.
    """
    if sku_features_df.empty:
        logger.warning("DataFrame de features de SKU está vazio.")
        return pd.DataFrame()

    active_policies = {**DEFAULT_POLICIES, **(policies or {})}
    df = sku_features_df.copy()

    # Data de corte e snapshot
    if as_of_date is not None:
        if isinstance(as_of_date, date | datetime):
            cutoff_str = as_of_date.strftime("%Y-%m-%d")
        else:
            cutoff_str = str(as_of_date)[:10]
    elif "as_of_date" in df.columns and not df["as_of_date"].isna().all():
        cutoff_str = str(df["as_of_date"].iloc[0])[:10]
    else:
        cutoff_str = date.today().isoformat()

    snapshot_str = date.today().isoformat()

    # 1. Participações Individuais e Acumuladas de Receita Bruta
    total_rev = float(df["gross_revenue"].sum())
    if total_rev > 0:
        df["revenue_share"] = (df["gross_revenue"] / total_rev).round(4)
        rev_sorted = df.sort_values(by=["gross_revenue", "product_id"], ascending=[False, True])
        cum_rev = (rev_sorted["gross_revenue"] / total_rev).cumsum().clip(0.0, 1.0)
        df["cum_revenue_share"] = cum_rev.reindex(df.index).round(4)
    else:
        df["revenue_share"] = 0.0
        df["cum_revenue_share"] = 0.0

    # 2. Participações Individuais e Acumuladas de Margem de Contribuição
    pos_margin_mask = df["contribution_margin"] > 0
    total_pos_margin = float(df.loc[pos_margin_mask, "contribution_margin"].sum())

    if total_pos_margin > 0:
        df["margin_share"] = 0.0
        df.loc[pos_margin_mask, "margin_share"] = (
            df.loc[pos_margin_mask, "contribution_margin"] / total_pos_margin
        ).round(4)

        margin_sorted = df.sort_values(by=["contribution_margin", "product_id"], ascending=[False, True])
        cum_margin = (
            (margin_sorted.loc[pos_margin_mask, "contribution_margin"] / total_pos_margin)
            .cumsum()
            .clip(0.0, 1.0)
        )
        df["cum_margin_share"] = cum_margin.reindex(df.index, fill_value=1.0).round(4)
    else:
        df["margin_share"] = 0.0
        df["cum_margin_share"] = 1.0

    # 3. Classificação ABC e XYZ
    df = df.sort_values(by=[metric, "product_id"], ascending=[False, True]).reset_index(drop=True)
    df["abc_class"] = _calculate_abc_classes(df, metric, a_cutoff, b_cutoff)
    df["xyz_class"] = _calculate_xyz_classes(df, x_cutoff, y_cutoff)

    # 4. Célula Combinada (AX a CZ) e Política Prescritiva
    df["abc_xyz_class"] = df["abc_class"] + df["xyz_class"]
    df["policy"] = df["abc_xyz_class"].map(active_policies).fillna("Revisar estratégia de mix e estoque")

    # 5. Metadados e Ajuste de Tipos
    df["scenario_id"] = scenario_id
    df["as_of_date"] = cutoff_str
    df["snapshot_date"] = snapshot_str

    # Ordenação final executiva: ABC (A->B->C), Margem desc, Product_id asc
    class_order = {"A": 1, "B": 2, "C": 3}
    df["_abc_rank"] = df["abc_class"].map(class_order)
    df = (
        df.sort_values(by=["_abc_rank", metric, "product_id"], ascending=[True, False, True])
        .drop(columns=["_abc_rank"])
        .reset_index(drop=True)
    )

    # 6. Validação estrita contra Pandera
    validated_df = validate_contract(df, GoldAbcXyzSchema, layer="Gold (mart_abc_xyz)")
    logger.info(
        "Classificação ABC/XYZ concluída para '%s': %d SKUs (A: %d, B: %d, C: %d).",
        scenario_id,
        len(validated_df),
        (validated_df["abc_class"] == "A").sum(),
        (validated_df["abc_class"] == "B").sum(),
        (validated_df["abc_class"] == "C").sum(),
    )
    return validated_df
    return validated_df


def compute_abc_xyz_matrix_summary(
    mart_df: pd.DataFrame,
    policies: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    """Gera a tabela resumo da Matriz 3x3 ABC/XYZ com todas as 9 células garantidas.

    Grão de saída: 9 linhas (AX, AY, AZ, BX, BY, BZ, CX, CY, CZ).

    Colunas retornadas:
        - cell: identificador da célula ("AX" ... "CZ")
        - abc_class: "A", "B", "C"
        - xyz_class: "X", "Y", "Z"
        - sku_count: quantidade de SKUs na célula
        - sku_pct: percentual do portfólio de SKUs (%)
        - gross_revenue: faturamento bruto total da célula (R$)
        - revenue_pct: percentual do faturamento total (%)
        - contribution_margin: margem de contribuição total da célula (R$)
        - margin_pct: percentual da margem total (%)
        - avg_margin_rate: margem percentual média na célula (%)
        - policy: recomendação prescritiva para a célula

    Args:
        mart_df: DataFrame retornado por `classify_abc_xyz` ou `mart_abc_xyz`.
        policies: Dicionário opcional sobrescrevendo as políticas padrão.

    Returns:
        pd.DataFrame com 9 linhas representando a matriz 3x3.
    """
    active_policies = {**DEFAULT_POLICIES, **(policies or {})}
    total_skus = len(mart_df)
    total_rev = float(mart_df["gross_revenue"].sum()) if not mart_df.empty else 0.0
    total_margin = float(mart_df["contribution_margin"].sum()) if not mart_df.empty else 0.0

    cells_order = [f"{abc}{xyz}" for abc, xyz in product(["A", "B", "C"], ["X", "Y", "Z"])]
    rows: list[dict[str, Any]] = []

    for cell in cells_order:
        abc = cell[0]
        xyz = cell[1]
        cell_mask = (mart_df["abc_class"] == abc) & (mart_df["xyz_class"] == xyz)
        cell_df = mart_df.loc[cell_mask]

        count = len(cell_df)
        rev = float(cell_df["gross_revenue"].sum())
        margin = float(cell_df["contribution_margin"].sum())

        sku_pct = round((count / total_skus * 100.0), 2) if total_skus > 0 else 0.0
        rev_pct = round((rev / total_rev * 100.0), 2) if total_rev > 0 else 0.0
        margin_pct = round((margin / total_margin * 100.0), 2) if total_margin > 0 else 0.0
        avg_margin_rate = round((margin / rev * 100.0), 2) if rev > 0 else 0.0

        rows.append(
            {
                "cell": cell,
                "abc_class": abc,
                "xyz_class": xyz,
                "sku_count": count,
                "sku_pct": sku_pct,
                "gross_revenue": round(rev, 2),
                "revenue_pct": rev_pct,
                "contribution_margin": round(margin, 2),
                "margin_pct": margin_pct,
                "avg_margin_rate": avg_margin_rate,
                "policy": active_policies.get(cell, DEFAULT_POLICIES.get(cell, "")),
            }
        )

    summary_df = pd.DataFrame(rows)
    return summary_df


def build_abc_xyz_mart(
    con: duckdb.DuckDBPyConnection,
    as_of_date: date | datetime | str | None = None,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
    metric: Literal["contribution_margin", "gross_revenue"] | None = None,
    lookback_weeks: int = 26,
) -> pd.DataFrame:
    """Calcula e persiste `mart_abc_xyz` na Gold do DuckDB e como snapshot Parquet.

    Args:
        con: Conexão ativa com o DuckDB (`kyberna.duckdb`).
        as_of_date: Data de corte temporal (se None, resolve para max(date)).
        scenario_id: Identificador do cenário (default: "c1_toys").
        metric: Métrica do corte ABC ("contribution_margin" ou "gross_revenue").
        lookback_weeks: Janela semanal para apuração da volatilidade XYZ.

    Returns:
        pd.DataFrame classificado e validado.
    """
    logger.info("Iniciando construção de `mart_abc_xyz` para o cenário '%s'...", scenario_id)

    # 1. Carrega parâmetros de configuração
    cfg = load_abc_xyz_config()
    chosen_metric = metric or cfg["abc_metric"]

    # 2. Computa features de SKU até a data de corte
    resolved_date = resolve_as_of_date(con, as_of_date, scenario_id=scenario_id)
    sku_features = compute_sku_features(
        con,
        as_of_date=resolved_date,
        scenario_id=scenario_id,
        lookback_weeks=lookback_weeks,
    )

    # 3. Classifica na matriz 3x3
    abc_xyz_df = classify_abc_xyz(
        sku_features,
        metric=chosen_metric,
        a_cutoff=cfg["abc_a_cutoff"],
        b_cutoff=cfg["abc_b_cutoff"],
        x_cutoff=cfg["xyz_x_cutoff"],
        y_cutoff=cfg["xyz_y_cutoff"],
        policies=cfg["abc_xyz_policies"],
        scenario_id=scenario_id,
        as_of_date=resolved_date,
    )

    # 4. Registra no DuckDB local
    con.execute("CREATE SCHEMA IF NOT EXISTS gold")
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {scenario_id}")

    con.register("v_abc_xyz_mart", abc_xyz_df)
    con.execute(f"CREATE OR REPLACE TABLE {scenario_id}.mart_abc_xyz AS SELECT * FROM v_abc_xyz_mart")
    con.execute("CREATE OR REPLACE TABLE gold.mart_abc_xyz AS SELECT * FROM v_abc_xyz_mart")
    con.unregister("v_abc_xyz_mart")

    # 5. Exporta snapshot Parquet (zstd)
    out_parquet = gold_snapshot_path(scenario=scenario_id, table="mart_abc_xyz")
    out_parquet.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY gold.mart_abc_xyz TO '{out_parquet.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)")

    logger.info(
        "mart_abc_xyz persistido com sucesso no DuckDB e em: %s",
        out_parquet,
    )
    return abc_xyz_df
