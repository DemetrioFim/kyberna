from __future__ import annotations

from datetime import date
from typing import Any, Final

import duckdb
import numpy as np
import pandas as pd
import yaml

from src.core.logging import get_logger
from src.core.paths import config_path, gold_snapshot_path
from src.core.types import ScenarioId
from src.etl.contracts import GoldRepPerformanceSchema, validate_contract
from src.ml.churn import build_customer_risk_mart
from src.ml.features import resolve_as_of_date
from src.ml.white_space import build_white_space_mart

logger = get_logger(__name__)

DEFAULT_SCENARIO: Final[ScenarioId] = "c1_toys"

DEFAULT_QUADRANTS: Final[dict[str, dict[str, str]]] = {
    "star": {
        "name": "Estrela",
        "description": "Alta receita e alta margem de contribuição (ambas acima da mediana da equipe).",
        "action": (
            "Manter autonomia, reconhecer performance, premiar mix rentável e disseminar boas práticas."
        ),
    },
    "volume_no_margin": {
        "name": "Volume sem margem",
        "description": "Alta receita porém margem abaixo da mediana (concessão excessiva de descontos).",
        "action": (
            "Travar alçada de descontos, condicionar comissão à margem líquida e auditar tabela de preços."
        ),
    },
    "margin_no_volume": {
        "name": "Margem sem volume",
        "description": (
            "Alta margem percentual porém receita abaixo da mediana "
            "(disciplina de preço com baixa positivação)."
        ),
        "action": (
            "Expandir carteira ativa, explorar oportunidades de White Space e aumentar frequência de visitas."
        ),
    },
    "attention": {
        "name": "Atenção",
        "description": "Baixa receita e baixa rentabilidade (ambas abaixo da mediana da equipe).",
        "action": (
            "Plano de recuperação comercial individual, reciclagem em negociação e acompanhamento "
            "semanal pela gerência."
        ),
    },
}


def load_rep_performance_config() -> dict[str, Any]:
    """Carrega parâmetros e definições dos quadrantes de RCAs de `config/pipeline.yaml`."""
    pipeline_file = config_path("pipeline.yaml")
    if pipeline_file.exists():
        try:
            with open(pipeline_file, encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            return dict(cfg.get("thresholds", {}).get("rep_performance", {}))
        except Exception as exc:
            logger.warning("Falha ao ler bloco rep_performance de pipeline.yaml: %s. Usando defaults.", exc)
    return {}


def _ensure_prerequisite_marts(con: duckdb.DuckDBPyConnection, scenario_id: ScenarioId) -> None:
    """Verifica se mart_customer_risk e mart_white_space existem na conexão; constrói se ausentes."""
    risk_exists = con.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_schema IN ('gold', ?) AND table_name = 'mart_customer_risk'
        """,
        [scenario_id],
    ).fetchone()
    if not risk_exists:
        logger.info("Tabela `mart_customer_risk` ausente. Construindo sob demanda...")
        build_customer_risk_mart(con, scenario_id=scenario_id)

    ws_exists = con.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_schema IN ('gold', ?) AND table_name = 'mart_white_space'
        """,
        [scenario_id],
    ).fetchone()
    if not ws_exists:
        logger.info("Tabela `mart_white_space` ausente. Construindo sob demanda...")
        build_white_space_mart(con, scenario_id=scenario_id)


def compute_rep_performance(
    con: duckdb.DuckDBPyConnection,
    *,
    as_of_date: str | date | None = None,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
) -> pd.DataFrame:
    """Extrai e calcula os indicadores de performance, positivação e risco de RCAs.

    Args:
        con: Conexão ativa com o DuckDB.
        as_of_date: Data de corte temporal (None para max da base).
        scenario_id: Identificador do cenário (default: 'c1_toys').

    Returns:
        DataFrame com indicadores agregados e classificados nos 4 quadrantes.
    """
    resolved_date = resolve_as_of_date(con, as_of_date, scenario_id=scenario_id)
    date_key_cutoff = int(resolved_date.strftime("%Y%m%d"))

    _ensure_prerequisite_marts(con, scenario_id)

    query = f"""
    WITH reps_base AS (
        SELECT
            r.sales_rep_id,
            r.name AS sales_rep_name,
            r.region,
            r.commission_rate
        FROM gold.dim_sales_rep r
    ),
    portfolio AS (
        SELECT
            c.sales_rep_id,
            COUNT(DISTINCT c.customer_id) AS portfolio_customers
        FROM gold.dim_customer c
        GROUP BY c.sales_rep_id
    ),
    sales_agg AS (
        SELECT
            f.sales_rep_id,
            COUNT(DISTINCT f.order_id) AS orders_count,
            COUNT(DISTINCT f.customer_id) AS active_customers,
            COALESCE(SUM(f.gross_revenue), 0.0) AS gross_revenue,
            COALESCE(SUM(f.discount_amount), 0.0) AS discount_amount,
            COALESCE(SUM(f.net_revenue), 0.0) AS net_revenue,
            COALESCE(SUM(f.commission_amount), 0.0) AS commission_amount,
            COALESCE(SUM(f.contribution_margin), 0.0) AS contribution_margin
        FROM gold.fact_sales f
        WHERE f.scenario_id = '{scenario_id}'
          AND f.date_key <= {date_key_cutoff}
        GROUP BY f.sales_rep_id
    ),
    cust_families AS (
        SELECT
            f.sales_rep_id,
            f.customer_id,
            COUNT(DISTINCT p.family) AS n_families
        FROM gold.fact_sales f
        JOIN gold.dim_product p ON f.product_id = p.product_id
        WHERE f.scenario_id = '{scenario_id}'
          AND f.date_key <= {date_key_cutoff}
        GROUP BY f.sales_rep_id, f.customer_id
    ),
    mix_agg AS (
        SELECT
            sales_rep_id,
            AVG(n_families) AS avg_families_per_customer
        FROM cust_families
        GROUP BY sales_rep_id
    ),
    risk_agg AS (
        SELECT
            c.sales_rep_id,
            COUNT(DISTINCT cr.customer_id) AS at_risk_customers_count,
            COALESCE(SUM(cr.annual_revenue_at_risk), 0.0) AS revenue_at_risk_brl,
            COALESCE(SUM(cr.annual_margin_at_risk), 0.0) AS margin_at_risk_brl
        FROM gold.mart_customer_risk cr
        JOIN gold.dim_customer c ON cr.customer_id = c.customer_id
        WHERE cr.scenario_id = '{scenario_id}'
          AND cr.risk_status IN ('Em Risco Imediato', 'Adormecido / Perdido')
        GROUP BY c.sales_rep_id
    ),
    ws_agg AS (
        SELECT
            c.sales_rep_id,
            COALESCE(SUM(ws.potential_revenue_brl), 0.0) AS white_space_potential_brl,
            COALESCE(SUM(ws.potential_margin_brl), 0.0) AS white_space_margin_brl
        FROM gold.mart_white_space ws
        JOIN gold.dim_customer c ON ws.customer_id = c.customer_id
        WHERE ws.scenario_id = '{scenario_id}'
        GROUP BY c.sales_rep_id
    )
    SELECT
        r.sales_rep_id,
        r.sales_rep_name,
        r.region,
        r.commission_rate,
        COALESCE(p.portfolio_customers, 0)::INTEGER AS portfolio_customers,
        COALESCE(s.active_customers, 0)::INTEGER AS active_customers,
        COALESCE(m.avg_families_per_customer, 0.0) AS avg_families_per_customer,
        COALESCE(s.orders_count, 0)::INTEGER AS orders_count,
        ROUND(COALESCE(s.gross_revenue, 0.0), 2) AS gross_revenue,
        ROUND(COALESCE(s.discount_amount, 0.0), 2) AS discount_amount,
        ROUND(COALESCE(s.net_revenue, 0.0), 2) AS net_revenue,
        ROUND(COALESCE(s.commission_amount, 0.0), 2) AS commission_amount,
        ROUND(COALESCE(s.contribution_margin, 0.0), 2) AS contribution_margin,
        COALESCE(rk.at_risk_customers_count, 0)::INTEGER AS at_risk_customers_count,
        ROUND(COALESCE(rk.revenue_at_risk_brl, 0.0), 2) AS revenue_at_risk_brl,
        ROUND(COALESCE(rk.margin_at_risk_brl, 0.0), 2) AS margin_at_risk_brl,
        ROUND(COALESCE(w.white_space_potential_brl, 0.0), 2) AS white_space_potential_brl,
        ROUND(COALESCE(w.white_space_margin_brl, 0.0), 2) AS white_space_margin_brl
    FROM reps_base r
    LEFT JOIN portfolio p ON r.sales_rep_id = p.sales_rep_id
    LEFT JOIN sales_agg s ON r.sales_rep_id = s.sales_rep_id
    LEFT JOIN mix_agg m ON r.sales_rep_id = m.sales_rep_id
    LEFT JOIN risk_agg rk ON r.sales_rep_id = rk.sales_rep_id
    LEFT JOIN ws_agg w ON r.sales_rep_id = w.sales_rep_id
    ORDER BY r.sales_rep_id
    """
    df = con.execute(query).df()

    # Índices percentuais vetorizados com proteção estrita contra divisão por zero
    port = df["portfolio_customers"].to_numpy(dtype=float)
    active = df["active_customers"].to_numpy(dtype=float)
    gross = df["gross_revenue"].to_numpy(dtype=float)
    disc = df["discount_amount"].to_numpy(dtype=float)
    margin = df["contribution_margin"].to_numpy(dtype=float)
    at_risk = df["at_risk_customers_count"].to_numpy(dtype=float)

    df["positivation_pct"] = np.round(
        np.divide(active, port, out=np.zeros_like(active), where=port > 0) * 100.0, 2
    )
    df["avg_discount_pct"] = np.round(
        np.divide(disc, gross, out=np.zeros_like(disc), where=gross > 0) * 100.0, 2
    )
    df["margin_pct"] = np.round(
        np.divide(margin, gross, out=np.zeros_like(margin), where=gross > 0) * 100.0, 2
    )
    df["at_risk_customers_pct"] = np.round(
        np.divide(at_risk, port, out=np.zeros_like(at_risk), where=port > 0) * 100.0, 2
    )
    df["avg_families_per_customer"] = np.round(df["avg_families_per_customer"].to_numpy(), 2)

    # Classificação nos 4 Quadrantes via medianas de receita e margem %
    active_mask = df["gross_revenue"] > 0
    if active_mask.any():
        med_rev = float(df.loc[active_mask, "gross_revenue"].median())
        med_margin_pct = float(df.loc[active_mask, "margin_pct"].median())
    else:
        med_rev = float(df["gross_revenue"].median())
        med_margin_pct = float(df["margin_pct"].median())

    conditions = [
        (df["gross_revenue"] >= med_rev) & (df["margin_pct"] >= med_margin_pct),
        (df["gross_revenue"] >= med_rev) & (df["margin_pct"] < med_margin_pct),
        (df["gross_revenue"] < med_rev) & (df["margin_pct"] >= med_margin_pct),
        (df["gross_revenue"] < med_rev) & (df["margin_pct"] < med_margin_pct),
    ]
    choices = [
        "Estrela",
        "Volume sem margem",
        "Margem sem volume",
        "Atenção",
    ]
    df["quadrant"] = np.select(conditions, choices, default="Atenção")

    # Mapeamento de prescrição
    cfg = load_rep_performance_config()
    quad_cfg = cfg.get("quadrants", {})
    prescription_map = {
        "Estrela": quad_cfg.get("star", {}).get("action", DEFAULT_QUADRANTS["star"]["action"]),
        "Volume sem margem": quad_cfg.get("volume_no_margin", {}).get(
            "action", DEFAULT_QUADRANTS["volume_no_margin"]["action"]
        ),
        "Margem sem volume": quad_cfg.get("margin_no_volume", {}).get(
            "action", DEFAULT_QUADRANTS["margin_no_volume"]["action"]
        ),
        "Atenção": quad_cfg.get("attention", {}).get("action", DEFAULT_QUADRANTS["attention"]["action"]),
    }
    df["action_prescription"] = (
        df["quadrant"].map(prescription_map).fillna(DEFAULT_QUADRANTS["attention"]["action"])
    )

    df["scenario_id"] = scenario_id
    df["as_of_date"] = resolved_date.strftime("%Y-%m-%d")
    df["snapshot_date"] = date.today().strftime("%Y-%m-%d")

    # Ordenação canônica das colunas conforme GoldRepPerformanceSchema
    ordered_cols = [
        "scenario_id",
        "as_of_date",
        "sales_rep_id",
        "sales_rep_name",
        "region",
        "commission_rate",
        "portfolio_customers",
        "active_customers",
        "positivation_pct",
        "avg_families_per_customer",
        "orders_count",
        "gross_revenue",
        "discount_amount",
        "avg_discount_pct",
        "net_revenue",
        "commission_amount",
        "contribution_margin",
        "margin_pct",
        "at_risk_customers_count",
        "at_risk_customers_pct",
        "revenue_at_risk_brl",
        "margin_at_risk_brl",
        "white_space_potential_brl",
        "white_space_margin_brl",
        "quadrant",
        "action_prescription",
        "snapshot_date",
    ]
    return df[ordered_cols].copy()


def build_rep_performance_mart(
    con: duckdb.DuckDBPyConnection,
    *,
    as_of_date: str | date | None = None,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
) -> pd.DataFrame:
    """Constrói o mart analítico `mart_rep_performance` no DuckDB e Parquet.

    Args:
        con: Conexão ativa com o DuckDB.
        as_of_date: Data de corte analítica.
        scenario_id: Identificador do cenário (default: 'c1_toys').

    Returns:
        DataFrame validado e persistido.
    """
    logger.info("Iniciando construção de `mart_rep_performance` para cenário '%s'...", scenario_id)

    raw_df = compute_rep_performance(con, as_of_date=as_of_date, scenario_id=scenario_id)
    validated_df = validate_contract(raw_df, GoldRepPerformanceSchema, layer="Gold (mart_rep_performance)")

    con.execute("CREATE SCHEMA IF NOT EXISTS gold")
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {scenario_id}")

    con.register("_tmp_rep_perf_df", validated_df)
    con.execute(
        f"CREATE OR REPLACE TABLE {scenario_id}.mart_rep_performance AS SELECT * FROM _tmp_rep_perf_df"
    )
    con.execute("CREATE OR REPLACE TABLE gold.mart_rep_performance AS SELECT * FROM _tmp_rep_perf_df")
    con.unregister("_tmp_rep_perf_df")

    out_parquet = gold_snapshot_path(scenario=scenario_id, table="mart_rep_performance")
    out_parquet.parent.mkdir(parents=True, exist_ok=True)
    con.execute(
        f"COPY gold.mart_rep_performance TO '{out_parquet.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)"
    )

    logger.info(
        "mart_rep_performance construído com sucesso para '%s': %d RCAs persistidos em %s.",
        scenario_id,
        len(validated_df),
        out_parquet,
    )
    return validated_df


def compute_rep_performance_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Gera resumo consolidado da distribuição dos 4 quadrantes para exibição em CLI/UI."""
    if df.empty:
        return pd.DataFrame()

    total_gross = df["gross_revenue"].sum()
    n_total = len(df)

    summary = (
        df.groupby("quadrant")
        .agg(
            reps_count=("sales_rep_id", "count"),
            gross_revenue=("gross_revenue", "sum"),
            contribution_margin=("contribution_margin", "sum"),
            avg_discount_pct=("avg_discount_pct", "mean"),
            revenue_at_risk_brl=("revenue_at_risk_brl", "sum"),
            white_space_potential_brl=("white_space_potential_brl", "sum"),
        )
        .reset_index()
    )

    summary["reps_pct"] = np.round((summary["reps_count"] / max(n_total, 1)) * 100.0, 1)
    summary["revenue_pct"] = np.round((summary["gross_revenue"] / max(total_gross, 1e-6)) * 100.0, 1)
    summary["margin_pct"] = np.round(
        (summary["contribution_margin"] / np.maximum(summary["gross_revenue"], 1e-6)) * 100.0, 2
    )

    quad_order = ["Estrela", "Volume sem margem", "Margem sem volume", "Atenção"]
    summary["sort_key"] = summary["quadrant"].map(lambda x: quad_order.index(x) if x in quad_order else 99)
    summary = summary.sort_values("sort_key").drop(columns=["sort_key"])
    return summary
