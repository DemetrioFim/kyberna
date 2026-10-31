from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.core.logging import get_logger
from src.core.paths import config_path
from src.core.types import ScenarioId

logger = get_logger(__name__)


class ScenarioNotFoundError(FileNotFoundError):
    """Lançada quando o arquivo YAML de configuração do cenário não é encontrado."""


class ScenarioValidationError(ValueError):
    """Lançada quando o conteúdo YAML de um cenário é inválido perante o modelo Pydantic."""


class ScenarioCapabilities(BaseModel):
    """Matriz de capacidades e módulos habilitados por cenário (conforme §5.5 do VISION.md)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    margin_waterfall: bool = Field(
        default=True,
        description="Waterfall canônico da Margem de Contribuição Líquida",
    )
    abc_xyz: bool = Field(
        default=True,
        description="Classificação matricial ABC (margem) / XYZ (volatilidade da demanda)",
    )
    rfm_churn: bool = Field(
        default=True,
        description="Radar de Churn individualizado por ciclo e RFM",
    )
    white_space: bool = Field(
        default=True,
        description="Matriz de penetração e cross-selling B2B (White Space)",
    )
    rep_efficiency: bool = Field(
        default=True,
        description="Quadrante de eficiência e dispersão de margem por RCA / Vendedor",
    )
    forecast_30d: bool = Field(
        default=True,
        description="Previsão de demanda para 30 dias com StatsForecast",
    )
    inventory_stock: bool = Field(
        default=True,
        description="Inteligência de estoque, ruptura iminente e capital travado (> 120d)",
    )
    branch_transfers: bool = Field(
        default=False,
        description="Matriz de remanejamento de estoque entre filiais (exclusivo C3)",
    )
    simulator_what_if: bool = Field(
        default=True,
        description="Simulador prescritivo de elasticidade, preço e breakeven de desconto",
    )


class ScenarioLabels(BaseModel):
    """Vocabulário de negócio e rótulos semânticos adaptados para a interface e relatórios."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    customer: str = Field(..., description="Nome no singular do cliente/comprador (ex: Lojista (CNPJ))")
    customer_plural: str = Field(..., description="Nome no plural de clientes (ex: Lojistas)")
    product_family: str = Field(..., description="Rótulo da família de produtos (ex: Família de Brinquedos)")
    sales_rep: str = Field(..., description="Nome do responsável comercial (ex: RCA (Representante))")
    sales_rep_plural: str = Field(
        default="Representantes",
        description="Nome no plural dos responsáveis comerciais (ex: Representantes Comerciais)",
    )
    branch: str = Field(default="Fábrica / CD", description="Ponto de expedição/origem (ex: Fábrica / CD)")
    unit: str = Field(default="Unidade", description="Unidade de medida unitária de consumo (ex: Unidade)")
    box: str = Field(
        default="Caixa Master",
        description="Unidade de embalagem coletiva/fardo (ex: Caixa Master)",
    )
    order: str = Field(default="Pedido", description="Nome do documento de venda (ex: Pedido de Venda)")
    order_plural: str = Field(default="Pedidos", description="Plural dos pedidos (ex: Pedidos de Venda)")


class ScenarioFinanceProfile(BaseModel):
    """Apontamento dos arquivos de parâmetros financeiros (alíquotas, frete, comissões)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tax_rules_file: str = Field(
        default="tax_rules.yaml",
        description="Arquivo de regras tributárias em config/finance/",
    )
    freight_file: str = Field(
        default="freight.yaml",
        description="Arquivo de tabelas de frete em config/finance/",
    )
    commission_file: str = Field(
        default="commission.yaml",
        description="Arquivo de parâmetros de comissão em config/finance/",
    )
    discounts_file: str = Field(
        default="discounts.yaml",
        description="Arquivo de políticas de desconto em config/finance/",
    )


class ScenarioFilters(BaseModel):
    """Configuração dos filtros e seletores permitidos na barra lateral da aplicação."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    supported_regions: list[str] = Field(
        default_factory=lambda: ["Todas", "Sudeste", "Sul", "Nordeste", "Centro-Oeste", "Norte"],
        description="Lista de regiões geográficas disponíveis para filtro",
    )
    has_geographic_filter: bool = Field(
        default=True,
        description="Indica se o filtro de Região e UF faz sentido para o cenário",
    )
    has_rep_filter: bool = Field(
        default=True,
        description="Indica se o filtro por RCA / Vendedor é aplicável",
    )
    has_family_filter: bool = Field(
        default=True,
        description="Indica se o filtro por família/categoria é aplicável",
    )


class ScenarioConfig(BaseModel):
    """Configuração mestra e canônica de um cenário analítico na Kyberna."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: ScenarioId = Field(..., description="Identificador único canônico do cenário")
    display_name: str = Field(..., description="Nome de exibição completo para menus e cabeçalhos")
    short_name: str = Field(..., description="Nome curto para badges e tags")
    company_profile: str = Field(..., description="Descrição executiva da empresa simulada")
    perspective: Literal["seller", "buyer"] = Field(
        default="seller",
        description="Perspectiva da cadeia: seller (indústria/distribuidora) ou buyer (varejo)",
    )
    category_map: str | None = Field(
        default=None,
        description="Caminho relativo para a tabela de categorias em data/reference/",
    )
    retail_markup: float | None = Field(
        default=None,
        description="Markup sobre o custo de aquisição para cenários de varejo (buyer: C3/C4)",
    )
    labels: ScenarioLabels = Field(..., description="Rótulos semânticos de interface")
    capabilities: ScenarioCapabilities = Field(
        default_factory=ScenarioCapabilities,
        description="Matriz de módulos analíticos habilitados",
    )
    filters: ScenarioFilters = Field(
        default_factory=ScenarioFilters,
        description="Configuração de filtros para a UI",
    )
    finance_profile: ScenarioFinanceProfile = Field(
        default_factory=ScenarioFinanceProfile,
        description="Perfis financeiros de impostos, frete e comissão",
    )


# Cache local de configurações carregadas
_SCENARIO_CONFIGS_CACHE: dict[str, ScenarioConfig] = {}


def get_scenarios_dir(base: Path | None = None) -> Path:
    """Retorna o diretório base onde residem os arquivos YAML de cenários."""
    return config_path("scenarios", base=base)


def load_scenario_config(scenario_id: ScenarioId | str, scenarios_dir: Path | None = None) -> ScenarioConfig:
    """Carrega e valida o arquivo YAML de um cenário de negócio.

    Args:
        scenario_id: Identificador canônico do cenário (ex: 'c1_toys').
        scenarios_dir: Diretório opcional contendo os arquivos YAML.

    Returns:
        Instância validada e imutável de `ScenarioConfig`.

    Raises:
        ScenarioNotFoundError: Se o arquivo `<scenario_id>.yaml` não existir.
        ScenarioValidationError: Se o YAML estiver mal formatado ou não cumprir o contrato Pydantic.
    """
    target_dir = scenarios_dir or get_scenarios_dir()
    yaml_file = target_dir / f"{scenario_id}.yaml"

    if not yaml_file.exists():
        raise ScenarioNotFoundError(
            f"Arquivo de configuração do cenário '{scenario_id}' não encontrado em: {yaml_file}"
        )

    try:
        raw_text = yaml_file.read_text(encoding="utf-8")
        parsed_dict = yaml.safe_load(raw_text)
    except Exception as exc:
        raise ScenarioValidationError(
            f"Erro de sintaxe ao carregar arquivo YAML do cenário '{scenario_id}': {exc}"
        ) from exc

    if not isinstance(parsed_dict, dict):
        raise ScenarioValidationError(
            f"Conteúdo do arquivo YAML do cenário '{scenario_id}' deve ser um dicionário/mapeamento."
        )

    try:
        config = ScenarioConfig.model_validate(parsed_dict)
    except ValidationError as exc:
        logger.error("Falha de validação no cenário '%s': %s", scenario_id, exc)
        raise ScenarioValidationError(
            f"Validação Pydantic falhou para o cenário '{scenario_id}':\n{exc}"
        ) from exc

    _SCENARIO_CONFIGS_CACHE[str(scenario_id)] = config
    return config


def list_scenario_configs(scenarios_dir: Path | None = None) -> dict[ScenarioId, ScenarioConfig]:
    """Descobre e carrega todos os cenários disponíveis no diretório de cenários.

    Returns:
        Dicionário mapeando ScenarioId para ScenarioConfig validado.
    """
    target_dir = scenarios_dir or get_scenarios_dir()
    configs: dict[ScenarioId, ScenarioConfig] = {}

    expected_scenarios: list[ScenarioId] = [
        "c1_toys",
        "c2_beverages",
        "c3_retail_chain",
        "c4_single_store",
    ]

    for sc_id in expected_scenarios:
        sc_file = target_dir / f"{sc_id}.yaml"
        if sc_file.exists():
            cfg = load_scenario_config(sc_id, scenarios_dir=target_dir)
            configs[cfg.id] = cfg

    return configs
