from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any, Final

import duckdb
import numpy as np
import pandas as pd
import yaml
from scipy.stats import norm

from src.core.logging import get_logger
from src.core.paths import config_path, gold_snapshot_path
from src.core.types import ScenarioId
from src.etl.contracts import GoldCustomerRiskSchema, validate_contract
from src.ml.features import compute_customer_features, resolve_as_of_date

logger = get_logger(__name__)

DEFAULT_SCENARIO: Final[ScenarioId] = "c1_toys"
DEFAULT_CUTOFFS: Final[tuple[float, float, float]] = (1.1, 1.5, 2.5)

DEFAULT_STATUS_DEFINITIONS: Final[dict[str, dict[str, str]]] = {
    "No Ciclo": {
        "severity": "low",
        "badge_color": "green",
        "description": "Cliente comprando no ritmo histórico normal; carteira saudável e ativa.",
        "action": (
            "Manutenção do plano de visitas, acompanhamento de satisfação e ofertas "
            "de cross-sell (White Space)."
        ),
    },
    "Atenção": {
        "severity": "medium",
        "badge_color": "yellow",
        "description": (
            "Janela ideal de abordagem: cliente atingiu ou excedeu levemente seu ciclo médio "
            "(10% a 50% de atraso)."
        ),
        "action": (
            "Contato proativo de lembrete pelo RCA responsável antes que o cliente "
            "esfrie ou migre para concorrência."
        ),
    },
    "Em Risco Imediato": {
        "severity": "high",
        "badge_color": "orange",
        "description": (
            "Atraso crítico de recompra (50% a 150% além do ciclo normal); anomalia grave de engajamento."
        ),
        "action": (
            "Prioridade máxima de reativação: contato imediato da gerência/RCA com ofertas especiais "
            "e apuração de motivos."
        ),
    },
    "Adormecido / Perdido": {
        "severity": "critical",
        "badge_color": "red",
        "description": (
            "Cliente excedeu em mais de 150% seu ciclo normal (> 2.5x); provável interrupção "
            "definitiva ou abandono."
        ),
        "action": (
            "Campanha de recuperação com condições agressivas de frete/prazo, visita presencial "
            "ou contato via WhatsApp da diretoria."
        ),
    },
}


def load_churn_config() -> dict[str, Any]:
    """Carrega parâmetros e definições de status de risco de Churn de `config/pipeline.yaml`."""
    pipeline_file = config_path("pipeline.yaml")
    if pipeline_file.exists():
        try:
            with open(pipeline_file, encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            return dict(cfg.get("thresholds", {}).get("churn", {}))
        except Exception as exc:
            logger.warning("Falha ao ler bloco churn de pipeline.yaml: %s. Usando defaults.", exc)
    return {}


def classify_churn_risk_status(
    delay_ratio: float,
    cutoffs: tuple[float, float, float] = DEFAULT_CUTOFFS,
) -> str:
    """Classifica o cliente em um dos 4 status prescritivos de risco de churn baseado no delay_ratio.

    Args:
        delay_ratio: Razão entre recência atual e ciclo médio esperado (recency_days / expected_cycle_days).
        cutoffs: Tupla com os cortes (healthy, attention, at_risk). Default: (1.1, 1.5, 2.5).

    Returns:
        Status do cliente: 'No Ciclo', 'Atenção', 'Em Risco Imediato' ou 'Adormecido / Perdido'.
    """
    if delay_ratio <= cutoffs[0]:
        return "No Ciclo"
    if delay_ratio <= cutoffs[1]:
        return "Atenção"
    if delay_ratio <= cutoffs[2]:
        return "Em Risco Imediato"
    return "Adormecido / Perdido"


def compute_individual_cycle(
    df_features: pd.DataFrame,
    *,
    prior_shrinkage_k: int = 3,
    min_cycle_days: float = 7.0,
    min_std_days: float = 5.0,
    segment_col: str = "customer_segment",
) -> pd.DataFrame:
    """Calcula o ciclo individual esperado com regularização empírica bayesiana em direção ao segmento.

    Fórmula:
        w_i = N_i / (N_i + k), onde N_i = frequency - 1
        mu_shrunk = w_i * median_cycle_i + (1 - w_i) * mu_seg (com piso min_cycle_days)
        sigma_shrunk = w_i * std_cycle_i + (1 - w_i) * sigma_seg (com piso min_std_days)

    Args:
        df_features: DataFrame com métricas de clientes (frequency, median_cycle_days, std_cycle_days).
        prior_shrinkage_k: Constante de amortecimento k (default: 3).
        min_cycle_days: Piso inferior para o ciclo em dias (default: 7.0).
        min_std_days: Piso inferior para o desvio-padrão em dias (default: 5.0).
        segment_col: Coluna de agrupamento para a prior do segmento.

    Returns:
        DataFrame com colunas `expected_cycle_days` e `cycle_std_days` calculadas.
    """
    df = df_features.copy()

    # Resolve colunas de ciclo individual com suporte a sinônimos (interval_days / cycle_days)
    if "median_interval_days" in df.columns:
        raw_cycle = df["median_interval_days"]
    elif "median_cycle_days" in df.columns:
        raw_cycle = df["median_cycle_days"]
    elif "avg_interval_days" in df.columns:
        raw_cycle = df["avg_interval_days"]
    else:
        raw_cycle = pd.Series(np.nan, index=df.index, dtype="float64")

    if "std_interval_days" in df.columns:
        raw_std = df["std_interval_days"]
    elif "std_cycle_days" in df.columns:
        raw_std = df["std_cycle_days"]
    else:
        raw_std = pd.Series(np.nan, index=df.index, dtype="float64")

    # Determina a prior do segmento (ou global caso a coluna não exista)
    has_segment = segment_col in df.columns and df[segment_col].notna().any()
    if has_segment:
        df["_temp_raw_cycle"] = raw_cycle
        df["_temp_raw_std"] = raw_std
        seg_median_cycle = df.groupby(segment_col)["_temp_raw_cycle"].transform("median")
        seg_median_std = df.groupby(segment_col)["_temp_raw_std"].transform("median")
        df.drop(columns=["_temp_raw_cycle", "_temp_raw_std"], inplace=True)
    else:
        seg_median_cycle = pd.Series(raw_cycle.median(), index=df.index)
        seg_median_std = pd.Series(raw_std.median(), index=df.index)

    # Defaults de segurança se todos forem NaN (ex: clientes de compra única)
    fallback_cycle = 45.0
    fallback_std = 15.0
    seg_median_cycle = (
        pd.Series(seg_median_cycle, index=df.index).fillna(raw_cycle.median()).fillna(fallback_cycle)
    )
    seg_median_std = pd.Series(seg_median_std, index=df.index).fillna(raw_std.median()).fillna(fallback_std)

    # N de intervalos entre pedidos: frequency - 1 (mínimo 0)
    if "n_intervals" in df.columns:
        n_intervals = df["n_intervals"].fillna(0).astype(int)
    else:
        n_intervals = pd.Series(
            np.maximum(df["frequency"].fillna(1).astype(int) - 1, 0),
            index=df.index,
            dtype="int64",
        )
    shrinkage_w = n_intervals / (n_intervals + prior_shrinkage_k)

    # Valores individuais (preenche NaN de compra única com a prior do segmento)
    indiv_cycle = raw_cycle.fillna(seg_median_cycle)
    indiv_std = raw_std.fillna(seg_median_std)

    # Regularização empírica
    shrunk_cycle = shrinkage_w * indiv_cycle + (1.0 - shrinkage_w) * seg_median_cycle
    shrunk_std = shrinkage_w * indiv_std + (1.0 - shrinkage_w) * seg_median_std

    # Aplicação de pisos mínimos
    df["expected_cycle_days"] = np.maximum(shrunk_cycle, min_cycle_days).round(2)
    df["cycle_std_days"] = np.maximum(shrunk_std, min_std_days).round(2)

    return df


def compute_churn_risk(
    df_features: pd.DataFrame,
    *,
    config: Mapping[str, Any] | None = None,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
    as_of_date: date | datetime | str | None = None,
) -> pd.DataFrame:
    """Calcula probabilidade de churn e status de risco com valores financeiros expostos.

    Args:
        df_features: DataFrame com features de clientes e atributos cadastrais.
        config: Dicionário opcional com configurações de churn de pipeline.yaml.
        scenario_id: Identificador do cenário comercial.
        as_of_date: Data de corte temporal de referência.

    Returns:
        DataFrame com colunas canônicas prontas para o mart analítico e conformidade Gold.
    """
    churn_cfg = dict(config or load_churn_config())

    prior_k = int(churn_cfg.get("prior_shrinkage_k", 3))
    min_cycle = float(churn_cfg.get("min_cycle_days", 7.0))
    min_std = float(churn_cfg.get("min_std_days", 5.0))

    cutoffs = (
        float(churn_cfg.get("healthy_ratio_cutoff", DEFAULT_CUTOFFS[0])),
        float(churn_cfg.get("attention_ratio_cutoff", DEFAULT_CUTOFFS[1])),
        float(churn_cfg.get("at_risk_ratio_cutoff", DEFAULT_CUTOFFS[2])),
    )

    # 1. Ciclo individual bayesiano
    df = compute_individual_cycle(
        df_features,
        prior_shrinkage_k=prior_k,
        min_cycle_days=min_cycle,
        min_std_days=min_std,
    )

    # 2. Razão de atraso e z-score
    recency = df["recency_days"].fillna(0).astype(float)
    df["delay_ratio"] = (recency / df["expected_cycle_days"]).round(3)

    z_score = (recency - df["expected_cycle_days"]) / df["cycle_std_days"]
    churn_prob = norm.cdf(z_score)
    df["churn_probability"] = np.clip(churn_prob, 0.0, 1.0).round(4)

    # 3. Classificação em 4 status prescritivos
    df["risk_status"] = [classify_churn_risk_status(r, cutoffs) for r in df["delay_ratio"]]

    # 4. Cálculo financeiro de exposição a risco (R$)
    # Prioriza valores acumulados em 12 meses; fallback para totais da carteira
    if "revenue_12m" in df.columns:
        base_rev_series = pd.Series(
            np.where(df["revenue_12m"] > 0, df["revenue_12m"], df["gross_revenue"]),
            index=df.index,
            dtype="float64",
        ).fillna(0.0)
    else:
        base_rev_series = df["gross_revenue"].fillna(0.0).astype(float)

    if "margin_12m" in df.columns:
        base_marg_series = pd.Series(
            np.where(df["margin_12m"].notna(), df["margin_12m"], df["contribution_margin"]),
            index=df.index,
            dtype="float64",
        ).fillna(0.0)
    else:
        base_marg_series = df["contribution_margin"].fillna(0.0).astype(float)

    # Ponderação do risco: 100% para Crítico/Imediato, 50% para Atenção, 0% para No Ciclo
    status_multiplier = (
        df["risk_status"]
        .map(
            {
                "Adormecido / Perdido": 1.0,
                "Em Risco Imediato": 1.0,
                "Atenção": 0.5,
                "No Ciclo": 0.0,
            }
        )
        .fillna(0.0)
    )

    df["annual_revenue_at_risk"] = (base_rev_series * status_multiplier).round(2)
    df["annual_margin_at_risk"] = (base_marg_series * status_multiplier).round(2)

    # 5. Enriquecimento semântico e prescritivo
    descriptions = {k: v["description"] for k, v in DEFAULT_STATUS_DEFINITIONS.items()}
    actions = {k: v["action"] for k, v in DEFAULT_STATUS_DEFINITIONS.items()}
    colors = {k: v["badge_color"] for k, v in DEFAULT_STATUS_DEFINITIONS.items()}

    df["risk_status_description"] = df["risk_status"].map(descriptions).fillna("")
    df["action_prescription"] = df["risk_status"].map(actions).fillna("")
    df["badge_color"] = df["risk_status"].map(colors).fillna("neutral")

    # Metadados de rastreabilidade
    ref_as_of = str(as_of_date) if as_of_date else datetime.now().strftime("%Y-%m-%d")
    df["scenario_id"] = scenario_id
    df["as_of_date"] = ref_as_of
    df["snapshot_date"] = datetime.now().strftime("%Y-%m-%d")

    return df


def compute_customer_risk_summary(df_risk: pd.DataFrame) -> pd.DataFrame:
    """Gera um resumo executivo da distribuição de risco e valores financeiros expostos.

    Args:
        df_risk: DataFrame processado por `compute_churn_risk`.

    Returns:
        DataFrame com colunas agregadas por status de risco.
    """
    total_cust = len(df_risk)
    if total_cust == 0:
        return pd.DataFrame()

    total_rev_risk = df_risk["annual_revenue_at_risk"].sum()
    total_marg_risk = df_risk["annual_margin_at_risk"].sum()

    summary_rows: list[dict[str, Any]] = []
    order = ["Adormecido / Perdido", "Em Risco Imediato", "Atenção", "No Ciclo"]

    for st_name in order:
        subset = df_risk[df_risk["risk_status"] == st_name]
        n_cust = len(subset)
        rev_risk = subset["annual_revenue_at_risk"].sum()
        marg_risk = subset["annual_margin_at_risk"].sum()

        rev_share = round(rev_risk / total_rev_risk * 100.0, 2) if total_rev_risk > 0 else 0.0
        marg_share = round(marg_risk / total_marg_risk * 100.0, 2) if total_marg_risk > 0 else 0.0

        summary_rows.append(
            {
                "risk_status": st_name,
                "customer_count": n_cust,
                "customer_share_pct": round(n_cust / total_cust * 100.0, 2),
                "annual_revenue_at_risk": round(rev_risk, 2),
                "annual_margin_at_risk": round(marg_risk, 2),
                "revenue_share_pct": rev_share,
                "margin_share_pct": marg_share,
                "avg_delay_ratio": round(subset["delay_ratio"].median(), 2) if n_cust > 0 else 0.0,
                "avg_churn_prob": round(subset["churn_probability"].mean(), 4) if n_cust > 0 else 0.0,
            }
        )

    return pd.DataFrame(summary_rows)


def build_customer_risk_mart(
    con: duckdb.DuckDBPyConnection,
    as_of_date: date | datetime | str | None = None,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
) -> pd.DataFrame:
    """Constrói o mart analítico `mart_customer_risk` no DuckDB e Parquet para o cenário especificado.

    Fluxo de execução:
        1. Resolve a data de corte temporal (`as_of_date`).
        2. Extrai features pontuais por cliente com zero vazamento temporal.
        3. Enriquece com atributos cadastrais de `dim_customer` (nome, segmento, UF, RCA).
        4. Calcula ciclos bayesianos e probabilidades de churn com base em regras heurísticas.
        5. Valida contrato de dados Pandera (`GoldCustomerRiskSchema`).
        6. Persiste tabelas `{scenario_id}.mart_customer_risk` e `gold.mart_customer_risk` no DuckDB.
        7. Exporta snapshot Parquet compactado em Zstandard.

    Args:
        con: Conexão ativa com o DuckDB.
        as_of_date: Data de corte temporal (se None, resolve para max(date)).
        scenario_id: Identificador do cenário (default: "c1_toys").

    Returns:
        DataFrame classificado, enriquecido e validado.
    """
    logger.info("Iniciando construção de `mart_customer_risk` para o cenário '%s'...", scenario_id)

    # 1. Resolução da data de corte
    resolved_date = resolve_as_of_date(con, as_of_date, scenario_id=scenario_id)

    # 2. Features de cliente
    cust_features = compute_customer_features(
        con,
        as_of_date=resolved_date,
        scenario_id=scenario_id,
    )

    # 3. Enriquecimento com atributos de dim_customer
    dim_query = """
    SELECT
        customer_id,
        COALESCE(trade_name, company_name) AS customer_name,
        segment AS customer_segment,
        size AS customer_size,
        city,
        state,
        region,
        sales_rep_id,
        whatsapp,
        email
    FROM gold.dim_customer
    """
    dim_df = con.execute(dim_query).df()
    merged_features = cust_features.merge(dim_df, on="customer_id", how="left")

    # 4. Cálculo do risco de Churn
    churn_df = compute_churn_risk(
        merged_features,
        scenario_id=scenario_id,
        as_of_date=resolved_date,
    )

    # 5. Validação com Pandera
    validated_df = validate_contract(churn_df, GoldCustomerRiskSchema, layer="Gold (mart_customer_risk)")

    # 6. Registro no DuckDB local
    con.execute("CREATE SCHEMA IF NOT EXISTS gold")
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {scenario_id}")

    con.register("v_customer_risk_mart", validated_df)
    con.execute(
        f"CREATE OR REPLACE TABLE {scenario_id}.mart_customer_risk AS SELECT * FROM v_customer_risk_mart"
    )
    con.execute("CREATE OR REPLACE TABLE gold.mart_customer_risk AS SELECT * FROM v_customer_risk_mart")
    con.unregister("v_customer_risk_mart")

    # 7. Snapshot Parquet
    out_parquet = gold_snapshot_path(scenario=scenario_id, table="mart_customer_risk")
    out_parquet.parent.mkdir(parents=True, exist_ok=True)
    con.execute(
        f"COPY gold.mart_customer_risk TO '{out_parquet.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)"
    )

    logger.info(
        "mart_customer_risk construído com sucesso para '%s': %d clientes classificados e persistidos em %s.",
        scenario_id,
        len(validated_df),
        out_parquet,
    )
    return validated_df
