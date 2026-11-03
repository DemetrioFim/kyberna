from __future__ import annotations

from pathlib import Path
from typing import Final

import yaml
from pydantic import BaseModel, ConfigDict, Field

from src.core.paths import config_path

DEFAULT_ORIGIN_UF: Final[str] = "SP"


class IcmsRulesConfig(BaseModel):
    """Regras de alíquotas do ICMS a partir da UF de origem (São Paulo)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    internal_rate: float = Field(0.18, ge=0.0, le=0.35, description="Alíquota interna (SP -> SP)")
    south_southeast_rate: float = Field(
        0.12, ge=0.0, le=0.25, description="Alíquota interestadual para Sul/Sudeste exceto ES"
    )
    north_northeast_co_rate: float = Field(
        0.07, ge=0.0, le=0.20, description="Alíquota interestadual para N/NE/CO e ES"
    )
    destinations: dict[str, float] = Field(
        default_factory=dict, description="Mapeamento explícito de alíquotas por UF de destino"
    )


class FederalTaxesConfig(BaseModel):
    """Alíquotas dos tributos federais sobre o faturamento."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pis_rate: float = Field(0.0165, ge=0.0, le=0.05, description="PIS Não-Cumulativo (1.65%)")
    cofins_rate: float = Field(0.0760, ge=0.0, le=0.15, description="COFINS Não-Cumulativo (7.60%)")
    ipi_rate: float = Field(0.0500, ge=0.0, le=0.30, description="IPI por fora (5.00%)")


class TaxRulesConfig(BaseModel):
    """Modelo canônico de regras fiscais da Kyberna."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    origin_uf: str = Field(DEFAULT_ORIGIN_UF, min_length=2, max_length=2)
    icms: IcmsRulesConfig = Field(default_factory=IcmsRulesConfig)
    federal_taxes: FederalTaxesConfig = Field(default_factory=FederalTaxesConfig)


def load_tax_rules(
    config_file: str = "tax_rules.yaml",
    base_dir: Path | None = None,
) -> TaxRulesConfig:
    """Carrega e valida o arquivo de regras tributárias YAML.

    Args:
        config_file: Nome do arquivo YAML em config/finance/.
        base_dir: Diretório base opcional.

    Returns:
        Instância tipada e imutável de `TaxRulesConfig`.
    """
    target_path = (base_dir or config_path("finance")) / config_file
    if not target_path.exists():
        raise FileNotFoundError(f"Arquivo de regras tributárias não encontrado: {target_path}")

    raw_data = yaml.safe_load(target_path.read_text(encoding="utf-8"))
    return TaxRulesConfig.model_validate(raw_data)


def get_icms_rate(dest_uf: str, config: TaxRulesConfig | None = None) -> float:
    """Retorna a alíquota de ICMS aplicável a uma UF de destino a partir de SP.

    Regras canônicas da Federação:
    - Destino SP (Interno): 18.0%
    - Destino Sul e Sudeste (exceto ES): RJ, MG, PR, SC, RS = 12.0%
    - Destino Norte, Nordeste, Centro-Oeste e ES: 7.0%

    Args:
        dest_uf: Sigla da UF de destino (ex: 'RJ', 'BA', 'SP').
        config: Configuração tributária opcional. Se None, carrega tax_rules.yaml.

    Returns:
        Alíquota fracionária de ICMS (ex: 0.12 para 12%).
    """
    cfg = config or load_tax_rules()
    uf_upper = dest_uf.upper().strip()

    if uf_upper in cfg.icms.destinations:
        return float(cfg.icms.destinations[uf_upper])

    if uf_upper == cfg.origin_uf:
        return cfg.icms.internal_rate
    if uf_upper in {"RJ", "MG", "PR", "SC", "RS"}:
        return cfg.icms.south_southeast_rate
    return cfg.icms.north_northeast_co_rate


def get_total_sales_tax_rate(dest_uf: str, config: TaxRulesConfig | None = None) -> float:
    """Retorna a alíquota total de impostos incidentes sobre a venda (ICMS + PIS + COFINS).

    Nota: IPI é imposto "por fora" e não compõe a receita líquida nem a dedução da margem.
    """
    cfg = config or load_tax_rules()
    icms = get_icms_rate(dest_uf, cfg)
    return round(icms + cfg.federal_taxes.pis_rate + cfg.federal_taxes.cofins_rate, 4)


def build_icms_case_when_sql(
    uf_col: str = "state",
    config: TaxRulesConfig | None = None,
) -> str:
    """Gera cláusula SQL CASE WHEN compatível com DuckDB para cálculo de ICMS por UF."""
    cfg = config or load_tax_rules()
    origin = cfg.origin_uf

    return f"""CASE
        WHEN {uf_col} = '{origin}' THEN {cfg.icms.internal_rate}
        WHEN {uf_col} IN ('RJ', 'MG', 'PR', 'SC', 'RS') THEN {cfg.icms.south_southeast_rate}
        ELSE {cfg.icms.north_northeast_co_rate}
    END"""


def build_total_tax_sql(
    uf_col: str = "state",
    config: TaxRulesConfig | None = None,
) -> str:
    """Gera expressão SQL compatível com DuckDB somando ICMS, PIS e COFINS."""
    cfg = config or load_tax_rules()
    icms_sql = build_icms_case_when_sql(uf_col=uf_col, config=cfg)
    fed_sum = round(cfg.federal_taxes.pis_rate + cfg.federal_taxes.cofins_rate, 4)
    return f"({icms_sql} + {fed_sum})"
