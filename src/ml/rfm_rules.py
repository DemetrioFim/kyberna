from __future__ import annotations

from collections.abc import Callable
from typing import Any, Final

import yaml

from src.core.logging import get_logger
from src.core.paths import config_path
from src.core.types import ScenarioId

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
    """Carrega parâmetros da segmentação RFM a partir de `config/pipeline.yaml`."""
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
    """Classifica deterministicamente uma célula RFM (r, f, m) em um dos 9 segmentos B2B."""
    return _RFM_CELL_MAP.get((r, f, m), "Precisam de Atenção")
