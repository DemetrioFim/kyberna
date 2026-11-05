from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date, datetime
from typing import Any, Final

import duckdb
import pandas as pd
import yaml

from src.core.logging import get_logger
from src.core.paths import config_path, gold_snapshot_path
from src.core.types import ScenarioId
from src.etl.contracts import GoldRfmSchema, validate_contract
from src.ml.features import compute_customer_features, resolve_as_of_date

logger = get_logger(__name__)

DEFAULT_SCENARIO: Final[ScenarioId] = "c1_toys"
DEFAULT_RECENCY_COL: Final[str] = "recency_days"
DEFAULT_FREQUENCY_COL: Final[str] = "frequency"
DEFAULT_MONETARY_COL: Final[str] = "contribution_margin"
DEFAULT_QUANTILES: Final[int] = 5

DEFAULT_SEGMENT_DEFINITIONS: Final[dict[str, dict[str, str]]] = {
    "Campeões": {
        "description": (
            "Clientes mais valiosos: compram com alta frequência, recência recente "
            "e geram alta margem líquida."
        ),
        "action": (
            "Tratamento VIP, acesso antecipado a lançamentos, bonificação de mix e "
            "canal direto com diretoria."
        ),
    },
    "Não Pode Perder": {
        "description": (
            "Clientes de altíssima rentabilidade e histórico consistente que estão "
            "se distanciando (risco crítico)."
        ),
        "action": (
            "Visita imediata da gerência comercial / diretoria, diagnóstico de insatisfação "
            "e renegociação personalizada de condições."
        ),
    },
    "Fiéis": {
        "description": (
            "Base sólida da carteira: compram regularmente com rentabilidade saudável e boa frequência."
        ),
        "action": (
            "Programas de fidelidade, incentivos de cross-sell (White Space) e manutenção "
            "de relacionamento próximo."
        ),
    },
    "Promissores": {
        "description": (
            "Compradores recentes com boa margem unitária/ticket, mas baixa frequência histórica."
        ),
        "action": (
            "Estimular o segundo e terceiro pedidos com ofertas personalizadas de famílias complementares."
        ),
    },
    "Novos Clientes": {
        "description": "Primeira compra faturada recentemente; início do ciclo de relacionamento.",
        "action": (
            "Onboarding assistido pelo RCA, pesquisa de satisfação pós-venda e catálogo completo de produtos."
        ),
    },
    "Em Risco": {
        "description": (
            "Clientes que compravam com boa frequência, mas cujo intervalo sem compras excedeu o esperado."
        ),
        "action": (
            "Contato proativo do RCA com tabela de ofertas de reativação e apuração "
            "de motivos de afastamento."
        ),
    },
    "Precisam de Atenção": {
        "description": (
            "Clientes intermediários com recência e frequência medianas; correm o risco de esfriar."
        ),
        "action": (
            "Apresentação de novidades do catálogo, condições facilitadas de frete e "
            "sugestões de abastecimento."
        ),
    },
    "Hibernando": {
        "description": "Baixa frequência e longa inatividade, mas com histórico anterior de compras.",
        "action": (
            "Campanhas sazonais de reativação via WhatsApp, saldões promocionais e recontato comercial."
        ),
    },
    "Perdidos": {
        "description": (
            "Piores indicadores: compra única distante no passado e margem líquida residual ou negativa."
        ),
        "action": "Comunicação automatizada de baixo custo ou exclusão de roteiros presenciais de visitação.",
    },
}

VALID_RFM_SEGMENTS: Final[list[str]] = list(DEFAULT_SEGMENT_DEFINITIONS.keys())


def _build_rfm_cell_map() -> dict[tuple[int, int, int], str]:
    """Constrói o mapeamento exaustivo das 125 células RFM (r, f, m) para os 9 segmentos B2B."""
    rules: list[tuple[Callable[[int, int, int], bool], str]] = [
        (lambda r, f, m: r <= 2 and f >= 3 and m >= 4, "Não Pode Perder"),
        (lambda r, f, m: r >= 4 and f >= 4 and m >= 4, "Campeões"),
        (lambda r, f, m: r >= 3 and f >= 3 and m >= 2, "Fiéis"),
        (lambda r, f, m: r >= 4 and f == 1, "Novos Clientes"),
        (
            lambda r, f, m: (r >= 4 and f == 2 and m >= 3) or (r == 3 and f == 2 and m >= 4),
            "Promissores",
        ),
        (
            lambda r, f, m: (r <= 2 and f >= 3) or (r <= 2 and f == 2 and m >= 3),
            "Em Risco",
        ),
        (
            lambda r, f, m: (
                (r == 3 and f in (1, 2))
                or (r in (4, 5) and f == 2 and m <= 2)
                or (r >= 3 and f >= 3 and m == 1)
            ),
            "Precisam de Atenção",
        ),
        (lambda r, f, m: r == 1 and f == 1 and m <= 2, "Perdidos"),
        (lambda r, f, m: r <= 2 and f <= 2, "Hibernando"),
    ]

    cell_map: dict[tuple[int, int, int], str] = {}
    for r in range(1, 6):
        for f in range(1, 6):
            for m in range(1, 6):
                segment = "Precisam de Atenção"
                for predicate, seg_name in rules:
                    if predicate(r, f, m):
                        segment = seg_name
                        break
                cell_map[(r, f, m)] = segment
    return cell_map


_RFM_CELL_MAP: Final[dict[tuple[int, int, int], str]] = _build_rfm_cell_map()


def load_rfm_config() -> dict[str, Any]:
    """Carrega parâmetros da segmentação RFM a partir de `config/pipeline.yaml`.

    Returns:
        Dicionário com métricas, quantis e definições de segmentos.
    """
    cfg_file = config_path("pipeline.yaml")
    if not cfg_file.exists():
        logger.warning("Arquivo '%s' não encontrado. Usando parâmetros padrão de RFM.", cfg_file)
        return {
            "recency_metric": DEFAULT_RECENCY_COL,
            "frequency_metric": DEFAULT_FREQUENCY_COL,
            "monetary_metric": DEFAULT_MONETARY_COL,
            "quantiles": DEFAULT_QUANTILES,
            "segments": DEFAULT_SEGMENT_DEFINITIONS.copy(),
        }

    try:
        data = yaml.safe_load(cfg_file.read_text(encoding="utf-8")) or {}
        rfm_cfg = data.get("thresholds", {}).get("rfm", {})
        return {
            "recency_metric": rfm_cfg.get("recency_metric", DEFAULT_RECENCY_COL),
            "frequency_metric": rfm_cfg.get("frequency_metric", DEFAULT_FREQUENCY_COL),
            "monetary_metric": rfm_cfg.get("monetary_metric", DEFAULT_MONETARY_COL),
            "quantiles": int(rfm_cfg.get("quantiles", DEFAULT_QUANTILES)),
            "segments": DEFAULT_SEGMENT_DEFINITIONS.copy(),
        }
    except Exception as exc:
        logger.warning("Erro ao ler configuração RFM de '%s' (%s). Usando defaults.", cfg_file, exc)
        return {
            "recency_metric": DEFAULT_RECENCY_COL,
            "frequency_metric": DEFAULT_FREQUENCY_COL,
            "monetary_metric": DEFAULT_MONETARY_COL,
            "quantiles": DEFAULT_QUANTILES,
            "segments": DEFAULT_SEGMENT_DEFINITIONS.copy(),
        }


def classify_rfm_cell(r: int, f: int, m: int) -> str:
    """Classifica deterministicamente uma célula RFM (r, f, m) em um dos 9 segmentos B2B.

    Args:
        r: Score de Recência (1 a 5, onde 5 é o mais recente).
        f: Score de Frequência (1 a 5, onde 5 é o mais frequente).
        m: Score de Margem de Contribuição (1 a 5, onde 5 é o mais rentável).

    Returns:
        Nome do segmento RFM associado.
    """
    return _RFM_CELL_MAP.get((r, f, m), "Precisam de Atenção")


def _compute_rank_quantile(series: pd.Series, ascending: bool, quantiles: int = 5) -> pd.Series:
    """Calcula quintis (1 a quantiles) usando desempate por rank 'first' para evitar quintis vazios."""
    n = len(series)
    if n == 0:
        return pd.Series(dtype=int)
    if n < quantiles:
        ranks = series.rank(method="first", ascending=ascending)
        scaled = (ranks * (quantiles / max(n, 1))).round().clip(lower=1, upper=quantiles)
        return scaled.astype(int)

    ranks = series.rank(method="first", ascending=ascending)
    return pd.qcut(ranks, q=quantiles, labels=list(range(1, quantiles + 1))).astype(int)


def assign_rfm_quintiles(
    df: pd.DataFrame,
    recency_col: str = DEFAULT_RECENCY_COL,
    frequency_col: str = DEFAULT_FREQUENCY_COL,
    monetary_col: str = DEFAULT_MONETARY_COL,
    quantiles: int = DEFAULT_QUANTILES,
) -> pd.DataFrame:
    """Calcula os scores R, F e M em quintis (1 a 5) com desempate por rank.

    Regras:
        - Recência: relação inversa (menor dias_sem_comprar -> maior score R).
        - Frequência: relação direta (maior pedidos distintos -> maior score F).
        - Margem: relação direta (maior margem líquida -> maior score M).

    Args:
        df: DataFrame de entrada contendo as métricas de recência, frequência e margem.
        recency_col: Nome da coluna de recência em dias.
        frequency_col: Nome da coluna de contagem de pedidos.
        monetary_col: Nome da coluna monetária (margem de contribuição).
        quantiles: Quantidade de faixas percentis (default: 5).

    Returns:
        DataFrame com colunas adicionadas: `r_score`, `f_score`, `m_score`, `rfm_cell`, `rfm_score`.
    """
    out = df.copy()
    out["r_score"] = _compute_rank_quantile(out[recency_col], ascending=False, quantiles=quantiles)
    out["f_score"] = _compute_rank_quantile(out[frequency_col], ascending=True, quantiles=quantiles)
    out["m_score"] = _compute_rank_quantile(out[monetary_col], ascending=True, quantiles=quantiles)

    out["rfm_cell"] = out["r_score"].astype(str) + out["f_score"].astype(str) + out["m_score"].astype(str)
    out["rfm_score"] = ((out["r_score"] + out["f_score"] + out["m_score"]) / 3.0).round(2)
    return out


def compute_rfm_scores(
    df_customer_features: pd.DataFrame,
    config: Mapping[str, Any] | None = None,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
    as_of_date: date | datetime | str | None = None,
) -> pd.DataFrame:
    """Computa a segmentação RFM B2B completa a partir do catálogo de features de clientes.

    Aplica os scores em quintis e mapeia para os 9 segmentos prescritivos,
    adicionando descrição executiva e prescrição de ação comercial.

    Args:
        df_customer_features: Features geradas por `compute_customer_features`.
        config: Dicionário opcional sobrescrevendo as configurações do YAML.
        scenario_id: Identificador do cenário analítico (ex: 'c1_toys').
        as_of_date: Data de corte das features.

    Returns:
        DataFrame enriquecido e pronto para validação de contrato e consumo.
    """
    cfg = dict(config) if config else load_rfm_config()
    rec_col = cfg.get("recency_metric", DEFAULT_RECENCY_COL)
    freq_col = cfg.get("frequency_metric", DEFAULT_FREQUENCY_COL)
    mon_col = cfg.get("monetary_metric", DEFAULT_MONETARY_COL)
    quantiles = int(cfg.get("quantiles", DEFAULT_QUANTILES))
    segment_defs = cfg.get("segments", DEFAULT_SEGMENT_DEFINITIONS)

    for col in (rec_col, freq_col, mon_col):
        if col not in df_customer_features.columns:
            msg = f"Coluna obrigatória '{col}' ausente no DataFrame de features de cliente."
            raise ValueError(msg)

    scored = assign_rfm_quintiles(
        df_customer_features,
        recency_col=rec_col,
        frequency_col=freq_col,
        monetary_col=mon_col,
        quantiles=quantiles,
    )

    # Classificação nos 9 segmentos
    segments: list[str] = [
        classify_rfm_cell(int(r), int(f), int(m))
        for r, f, m in zip(scored["r_score"], scored["f_score"], scored["m_score"], strict=True)
    ]
    scored["rfm_segment"] = segments

    # Injeção de textos explicativos e prescrições
    scored["rfm_segment_description"] = scored["rfm_segment"].map(
        lambda s: segment_defs.get(s, {}).get("description", "")
    )
    scored["action_prescription"] = scored["rfm_segment"].map(
        lambda s: segment_defs.get(s, {}).get("action", "")
    )

    # Metadados
    if "scenario_id" not in scored.columns:
        scored["scenario_id"] = scenario_id
    if as_of_date is not None and "as_of_date" not in scored.columns:
        date_str = as_of_date.isoformat() if isinstance(as_of_date, date) else str(as_of_date)[:10]
        scored["as_of_date"] = date_str
    if "snapshot_date" not in scored.columns:
        scored["snapshot_date"] = date.today().isoformat()

    return scored


def compute_rfm_segment_summary(rfm_df: pd.DataFrame) -> pd.DataFrame:
    """Gera a tabela executiva agregada por segmento RFM para painéis e relatórios.

    Args:
        rfm_df: DataFrame com as colunas computadas por `compute_rfm_scores`.

    Returns:
        DataFrame agregado com métricas por segmento: clientes, faturamento, margem e médias.
    """
    if rfm_df.empty:
        return pd.DataFrame(
            columns=[
                "rfm_segment",
                "customer_count",
                "customer_share_pct",
                "gross_revenue",
                "revenue_share_pct",
                "contribution_margin",
                "margin_share_pct",
                "avg_margin_pct",
                "avg_ticket",
                "avg_recency_days",
                "avg_frequency",
                "action_prescription",
            ]
        )

    total_customers = len(rfm_df)
    total_rev = float(rfm_df["gross_revenue"].sum()) if "gross_revenue" in rfm_df.columns else 0.0
    total_margin = (
        float(rfm_df["contribution_margin"].sum()) if "contribution_margin" in rfm_df.columns else 0.0
    )

    summary_rows: list[dict[str, Any]] = []
    grouped = rfm_df.groupby("rfm_segment", as_index=False)

    for seg, group in grouped:
        c_count = len(group)
        c_share = (c_count / total_customers * 100.0) if total_customers > 0 else 0.0
        g_rev = float(group["gross_revenue"].sum()) if "gross_revenue" in group.columns else 0.0
        r_share = (g_rev / total_rev * 100.0) if total_rev > 0 else 0.0
        c_margin = (
            float(group["contribution_margin"].sum()) if "contribution_margin" in group.columns else 0.0
        )
        m_share = (c_margin / total_margin * 100.0) if total_margin > 0 else 0.0
        avg_m_pct = (c_margin / g_rev * 100.0) if g_rev > 0 else 0.0
        avg_t = float(group["avg_ticket"].mean()) if "avg_ticket" in group.columns else 0.0
        avg_rec = float(group["recency_days"].mean()) if "recency_days" in group.columns else 0.0
        avg_freq = float(group["frequency"].mean()) if "frequency" in group.columns else 0.0
        prescription = str(group["action_prescription"].iloc[0])

        summary_rows.append(
            {
                "rfm_segment": seg,
                "customer_count": c_count,
                "customer_share_pct": round(c_share, 1),
                "gross_revenue": round(g_rev, 2),
                "revenue_share_pct": round(r_share, 1),
                "contribution_margin": round(c_margin, 2),
                "margin_share_pct": round(m_share, 1),
                "avg_margin_pct": round(avg_m_pct, 1),
                "avg_ticket": round(avg_t, 2),
                "avg_recency_days": round(avg_rec, 1),
                "avg_frequency": round(avg_freq, 1),
                "action_prescription": prescription,
            }
        )

    summary_df = pd.DataFrame(summary_rows)
    # Ordena por margem de contribuição decrescente
    return summary_df.sort_values(by="contribution_margin", ascending=False).reset_index(drop=True)


def build_rfm_mart(
    con: duckdb.DuckDBPyConnection,
    as_of_date: date | datetime | str | None = None,
    scenario_id: ScenarioId = DEFAULT_SCENARIO,
) -> pd.DataFrame:
    """Constrói o mart analítico `mart_rfm` no DuckDB e Parquet para o cenário especificado.

    Fluxo de execução:
        1. Resolve a data de corte (`as_of_date`).
        2. Computa features pontuais por cliente com zero vazamento temporal.
        3. Enriquece com dados cadastrais de `dim_customer` (nome, segmento, UF, RCA).
        4. Calcula quintis RFM baseados em Margem de Contribuição e classifica nos 9 segmentos.
        5. Valida contrato de dados Pandera (`GoldRfmSchema`).
        6. Persiste tabelas `{scenario_id}.mart_rfm` e `gold.mart_rfm` no DuckDB.
        7. Exporta snapshot Parquet compactado em Zstandard.

    Args:
        con: Conexão ativa com o DuckDB.
        as_of_date: Data de corte temporal (se None, resolve para max(date)).
        scenario_id: Identificador do cenário (default: "c1_toys").

    Returns:
        DataFrame classificado, enriquecido e validado.
    """
    logger.info("Iniciando construção de `mart_rfm` para o cenário '%s'...", scenario_id)

    # 1. Resolução da data de corte
    resolved_date = resolve_as_of_date(con, as_of_date, scenario_id=scenario_id)

    # 2. Features de cliente
    cust_features = compute_customer_features(
        con,
        as_of_date=resolved_date,
        scenario_id=scenario_id,
    )

    # 3. Enriquecimento com atributos cadastrais de dim_customer
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

    # 4. Classificação RFM
    rfm_df = compute_rfm_scores(
        merged_features,
        scenario_id=scenario_id,
        as_of_date=resolved_date,
    )

    # 5. Validação com Pandera
    validated_df = validate_contract(rfm_df, GoldRfmSchema, layer="Gold (mart_rfm)")

    # 6. Registro no DuckDB local
    con.execute("CREATE SCHEMA IF NOT EXISTS gold")
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {scenario_id}")

    con.register("v_rfm_mart", validated_df)
    con.execute(f"CREATE OR REPLACE TABLE {scenario_id}.mart_rfm AS SELECT * FROM v_rfm_mart")
    con.execute("CREATE OR REPLACE TABLE gold.mart_rfm AS SELECT * FROM v_rfm_mart")
    con.unregister("v_rfm_mart")

    # 7. Snapshot Parquet
    out_parquet = gold_snapshot_path(scenario=scenario_id, table="mart_rfm")
    out_parquet.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY gold.mart_rfm TO '{out_parquet.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)")

    logger.info(
        "mart_rfm construído com sucesso para '%s': %d clientes classificados e persistidos em %s.",
        scenario_id,
        len(validated_df),
        out_parquet,
    )
    return validated_df
