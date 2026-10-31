from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from src.core.logging import get_logger
from src.core.paths import get_project_root

logger = get_logger(__name__)

# ==============================================================================
# Modelos Tipados Pydantic para Entidades de Referência
# ==============================================================================


class UfReference(BaseModel):
    """Representação estruturada de uma Unidade Federativa brasileira."""

    model_config = ConfigDict(frozen=True)

    uf: str = Field(..., min_length=2, max_length=2, description="Sigla da UF com 2 caracteres maiúsculos")
    nome: str = Field(..., min_length=3, description="Nome por extenso do Estado")
    regiao: str = Field(..., description="Região geográfica (Sudeste, Sul, Nordeste, Centro-Oeste, Norte)")
    codigo_ibge: int = Field(..., ge=11, le=53, description="Código IBGE da UF de 2 dígitos")
    aliquota_icms_interna: float = Field(
        ..., ge=0.0, le=0.35, description="Alíquota ICMS interna de referência"
    )


class MunicipioReference(BaseModel):
    """Representação estruturada de um município brasileiro de referência."""

    model_config = ConfigDict(frozen=True)

    codigo_ibge: int = Field(
        ..., ge=1100000, le=5399999, description="Código IBGE do município com 7 dígitos"
    )
    nome: str = Field(..., min_length=2, description="Nome do município")
    uf: str = Field(..., min_length=2, max_length=2, description="Sigla da UF")
    regiao: str = Field(..., description="Região geográfica brasileira")
    latitude: float = Field(..., ge=-35.0, le=6.0, description="Latitude geográfica no território nacional")
    longitude: float = Field(
        ..., ge=-75.0, le=-34.0, description="Longitude geográfica no território nacional"
    )
    populacao: int = Field(..., gt=0, description="População estimada ou censitária")
    capital: bool = Field(default=False, description="Indica se é capital de estado")


class CategoryRule(BaseModel):
    """Regra de mapeamento taxonômico baseada em expressão regular."""

    model_config = ConfigDict(frozen=True)

    priority: int = Field(..., ge=0, description="Ordem de avaliação (menor prioridade avaliada primeiro)")
    pattern: str = Field(..., min_length=1, description="Padrão regex compatível com RE2/Python")
    family: str = Field(..., min_length=1, description="Família ou categoria de destino")
    description: str = Field(default="", description="Descrição de negócio da família")


# ==============================================================================
# Constantes e Diretórios Canônicos
# ==============================================================================

REFERENCE_DIR_NAME: Final[str] = "reference"
CATEGORY_MAPS_DIR_NAME: Final[str] = "category_maps"

EXPECTED_UF_COUNT: Final[int] = 27
VALID_REGIOES: Final[set[str]] = {"Sudeste", "Sul", "Nordeste", "Centro-Oeste", "Norte"}


def get_reference_dir() -> Path:
    """Retorna o diretório base de arquivos de referência versionados (`data/reference`)."""
    return get_project_root() / "data" / REFERENCE_DIR_NAME


def get_category_maps_dir() -> Path:
    """Retorna o diretório de mapeamentos de famílias por cenário (`data/reference/category_maps`)."""
    return get_reference_dir() / CATEGORY_MAPS_DIR_NAME


# ==============================================================================
# Loaders Tipados
# ==============================================================================


def load_ufs(file_path: Path | None = None) -> pd.DataFrame:
    """Carrega a tabela de UFs brasileiras com validação de esquema e cobertura total das 27 UFs.

    Args:
        file_path: Caminho opcional do arquivo CSV. Se omitido, usa `data/reference/ufs_br.csv`.

    Returns:
        pd.DataFrame tipado com colunas: `uf`, `nome`, `regiao`, `codigo_ibge`, `aliquota_icms_interna`.

    Raises:
        FileNotFoundError: Se o arquivo CSV de UFs não for encontrado.
        ValueError: Se colunas obrigatórias faltarem ou se não contiver exatamente 27 UFs.
    """
    path = file_path or (get_reference_dir() / "ufs_br.csv")
    if not path.exists():
        raise FileNotFoundError(f"Arquivo de UFs não encontrado: {path}")

    df = pd.read_csv(path, dtype={"uf": "string", "nome": "string", "regiao": "string"})
    required_cols = {"uf", "nome", "regiao", "codigo_ibge", "aliquota_icms_interna"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Colunas obrigatórias ausentes em {path}: {missing}")

    if len(df) != EXPECTED_UF_COUNT or df["uf"].nunique() != EXPECTED_UF_COUNT:
        raise ValueError(
            f"Tabela de UFs deve conter exatamente {EXPECTED_UF_COUNT} estados distintos. "
            f"Encontrados: {df['uf'].nunique()}"
        )

    invalid_regioes = set(df["regiao"].unique()) - VALID_REGIOES
    if invalid_regioes:
        raise ValueError(f"Regiões inválidas encontradas em {path}: {invalid_regioes}")

    # Tipagem PyArrow / Pandas estrita
    df["codigo_ibge"] = df["codigo_ibge"].astype("int64")
    df["aliquota_icms_interna"] = df["aliquota_icms_interna"].astype("float64")

    logger.debug("Tabela de UFs carregada com sucesso: %d UFs presentes.", len(df))
    return df


def load_municipios(file_path: Path | None = None) -> pd.DataFrame:
    """Carrega a tabela de municípios de referência brasileiros com validação de coordenadas e IBGE.

    Args:
        file_path: Caminho opcional do arquivo CSV. Se omitido, usa `data/reference/municipios_br.csv`.

    Returns:
        pd.DataFrame tipado com colunas: `codigo_ibge`, `nome`, `uf`, `regiao`, `latitude`, `longitude`,
        `populacao`, `capital`.

    Raises:
        FileNotFoundError: Se o arquivo CSV de municípios não for encontrado.
        ValueError: Se houver colunas ausentes, UFs não cobertas ou coordenadas fora do Brasil.
    """
    path = file_path or (get_reference_dir() / "municipios_br.csv")
    if not path.exists():
        raise FileNotFoundError(f"Arquivo de municípios não encontrado: {path}")

    df = pd.read_csv(
        path,
        dtype={"nome": "string", "uf": "string", "regiao": "string", "capital": "boolean"},
    )
    required_cols = {
        "codigo_ibge",
        "nome",
        "uf",
        "regiao",
        "latitude",
        "longitude",
        "populacao",
        "capital",
    }
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Colunas obrigatórias ausentes em {path}: {missing}")

    # Validação de cobertura geográfica: todas as 27 UFs devem possuir ao menos 1 município
    ufs_presentes = set(df["uf"].unique())
    if len(ufs_presentes) < EXPECTED_UF_COUNT:
        raise ValueError(
            f"Municípios devem cobrir todas as {EXPECTED_UF_COUNT} UFs. "
            f"Presentes apenas: {len(ufs_presentes)}"
        )

    # Validação de integridade de coordenadas brasileiras
    # Latitude Brasil: entre -34.0 e +5.5 | Longitude Brasil: entre -74.0 e -34.5
    invalid_coords = df[
        (df["latitude"] < -35.0)
        | (df["latitude"] > 6.0)
        | (df["longitude"] < -75.0)
        | (df["longitude"] > -34.0)
    ]
    if not invalid_coords.empty:
        raise ValueError(
            f"Municípios com coordenadas geográficas fora dos limites do Brasil: "
            f"{invalid_coords[['codigo_ibge', 'nome', 'latitude', 'longitude']].to_dict(orient='records')}"
        )

    df["codigo_ibge"] = df["codigo_ibge"].astype("int64")
    df["populacao"] = df["populacao"].astype("int64")
    df["latitude"] = df["latitude"].astype("float64")
    df["longitude"] = df["longitude"].astype("float64")

    logger.debug(
        "Tabela de municípios carregada com sucesso: %d municípios em %d UFs.",
        len(df),
        len(ufs_presentes),
    )
    return df


def load_category_map(scenario_id: str, base_dir: Path | None = None) -> pd.DataFrame:
    """Carrega as regras taxonômicas de mapeamento de categorias para um cenário específico.

    O arquivo procurado é `<base_dir>/<nome_cenario>.csv` (ex.: `toys.csv` ou `beverages.csv`).

    Args:
        scenario_id: Identificador do cenário (ex.: "c1_toys", "toys", "c2_beverages", "beverages").
        base_dir: Diretório base opcional contendo os arquivos de mapeamento.

    Returns:
        pd.DataFrame ordenado por `priority` crescente com colunas:
        `priority`, `pattern`, `family`, `description`.

    Raises:
        FileNotFoundError: Se o arquivo do cenário não for localizado.
        ValueError: Se faltarem colunas obrigatórias.
    """
    clean_id = scenario_id.lower().replace("c1_", "").replace("c2_", "").replace("c3_", "").replace("c4_", "")
    target_dir = base_dir or get_category_maps_dir()
    map_path = target_dir / f"{clean_id}.csv"

    if not map_path.exists():
        raise FileNotFoundError(
            f"Arquivo de mapeamento de categoria não encontrado para cenário '{scenario_id}': {map_path}"
        )

    df = pd.read_csv(map_path, dtype={"pattern": "string", "family": "string", "description": "string"})
    required_cols = {"priority", "pattern", "family"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Colunas obrigatórias ausentes em {map_path}: {missing}")

    df["priority"] = df["priority"].astype("int64")
    df = df.sort_values(by="priority", ascending=True).reset_index(drop=True)

    logger.debug(
        "Mapeamento taxonômico carregado para cenário '%s': %d regras ordenadas por prioridade.",
        scenario_id,
        len(df),
    )
    return df


# ==============================================================================
# Motor de Compilação e Matching de Expressões Regulares
# ==============================================================================


def compile_category_rules(category_map_df: pd.DataFrame) -> list[tuple[re.Pattern[str], str]]:
    """Compila a tabela de padrões em lista ordenada de tuplas (regex_compilado, familia).

    Args:
        category_map_df: DataFrame contendo as colunas `pattern` e `family` ordenado por prioridade.

    Returns:
        Lista de tuplas `(pattern_compilado_re, nome_da_familia)` com flag `re.IGNORECASE`.
    """
    rules: list[tuple[re.Pattern[str], str]] = []
    for _, row in category_map_df.iterrows():
        pat_str = str(row["pattern"]).strip()
        family_str = str(row["family"]).strip()
        compiled = re.compile(pat_str, re.IGNORECASE)
        rules.append((compiled, family_str))
    return rules


def match_category(
    category_name: str | None,
    rules: list[tuple[re.Pattern[str], str]],
    default: str = "Outros",
) -> str:
    """Avalia um nome de categoria contra as regras ordenadas e retorna a família correspondente.

    Args:
        category_name: String com o nome original da categoria (ex.: "STRAIGHT BOURBON WHISKIES").
        rules: Lista compilada de regras `(pattern, family)`.
        default: Família padrão caso nenhuma regra dê match (padrão: "Outros").

    Returns:
        Nome da família atribuída.
    """
    if not category_name or pd.isna(category_name):
        return default

    clean_name = str(category_name).strip()
    for pattern, family in rules:
        if pattern.search(clean_name):
            return family
    return default


def apply_category_mapping(
    df: pd.DataFrame,
    rules: list[tuple[re.Pattern[str], str]],
    source_col: str = "category_name",
    target_col: str = "product_family",
    default: str = "Outros",
) -> pd.DataFrame:
    """Aplica o mapeamento de categorias em lote vetorizado em um DataFrame Pandas.

    Args:
        df: DataFrame de entrada contendo a coluna `source_col`.
        rules: Lista compilada de regras `(pattern, family)`.
        source_col: Nome da coluna de entrada com a categoria bruta.
        target_col: Nome da coluna que receberá a família remapeada.
        default: Valor padrão para casos sem match.

    Returns:
        DataFrame com a nova coluna `target_col` populada.
    """
    if source_col not in df.columns:
        raise ValueError(f"Coluna de origem '{source_col}' não encontrada no DataFrame.")

    # Mapeamento via list comprehension com cache de valores únicos para máxima performance
    unique_categories = df[source_col].dropna().unique()
    cat_to_family: dict[str, str] = {
        cat: match_category(cat, rules, default=default) for cat in unique_categories
    }

    mapped_series = df[source_col].map(cat_to_family).fillna(default).astype("string")
    return df.assign(**{target_col: mapped_series})


def build_category_case_when_sql(
    rules: list[tuple[re.Pattern[str], str]],
    source_col: str = "category_name",
    default: str = "Outros",
) -> str:
    """Gera cláusula SQL CASE WHEN compatível com DuckDB/PostgreSQL para remapeamento de categorias.

    Exemplo gerado:
        CASE
            WHEN regexp_matches(category_name, '(?i).*VODKA.*') THEN 'Jogos Educativos'
            WHEN regexp_matches(category_name, '(?i).*WHISK.*') THEN 'Quebra-Cabeças'
            ELSE 'Outros'
        END

    Args:
        rules: Lista de tuplas `(pattern, family)`.
        source_col: Nome da coluna SQL de categoria original.
        default: Rótulo default para o ELSE.

    Returns:
        String SQL pura para ser injetada em consultas DuckDB.
    """
    when_clauses: list[str] = []
    for pattern, family in rules:
        # Se for o padrão curinga fallback '.*', vira o próprio ELSE
        if pattern.pattern.strip() in {".*", "^.*$", ".*?"}:
            continue
        # Sanitiza aspas simples para SQL
        pat_escaped = pattern.pattern.replace("'", "''")
        family_escaped = family.replace("'", "''")
        when_clauses.append(f"WHEN regexp_matches({source_col}, '(?i){pat_escaped}') THEN '{family_escaped}'")

    default_escaped = default.replace("'", "''")
    clauses_joined = "\n    ".join(when_clauses)
    return f"CASE\n    {clauses_joined}\n    ELSE '{default_escaped}'\nEND"
