from __future__ import annotations

from typing import Any, Final

import numpy as np
import pandas as pd
import yaml

from src.core.logging import get_logger
from src.core.paths import config_path
from src.core.types import ScenarioId

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
