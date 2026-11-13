from __future__ import annotations

import hashlib
import random
from typing import Final

import pandas as pd

from src.etl.contracts import SilverGeographySchema, validate_contract
from src.etl.silver.reference import load_municipios

# ==============================================================================
# Mapeamento Oficial de DDDs por UF (ANATEL) e Parâmetros B2B
# ==============================================================================

UF_DDDS: Final[dict[str, list[int]]] = {
    "SP": [11, 12, 13, 14, 15, 16, 17, 18, 19],
    "RJ": [21, 22, 24],
    "ES": [27, 28],
    "MG": [31, 32, 33, 34, 35, 37, 38],
    "PR": [41, 42, 43, 44, 45, 46],
    "SC": [47, 48, 49],
    "RS": [51, 53, 54, 55],
    "DF": [61],
    "GO": [62, 64],
    "TO": [63],
    "MT": [65, 66],
    "MS": [67],
    "AC": [68],
    "RO": [69],
    "BA": [71, 73, 74, 75, 77],
    "SE": [79],
    "PE": [81, 87],
    "AL": [82],
    "PB": [83],
    "RN": [84],
    "CE": [85, 88],
    "PI": [86, 89],
    "MA": [98, 99],
    "PA": [91, 93, 94],
    "AP": [96],
    "AM": [92, 97],
    "RR": [95],
}

RETAIL_SEGMENTS: Final[list[str]] = [
    "Papelaria e Bazar",
    "Loja de Brinquedos",
    "Magazine e Variedades",
    "Livraria e Papelaria",
    "Atacadista Regional",
    "Supermercado Regional",
]

DEFAULT_NUM_REPS: Final[int] = 30
DEFAULT_GLOBAL_SEED: Final[int] = 42


def compute_cnpj_dv(digits: list[int]) -> tuple[int, int]:
    """Calcula os dois dígitos verificadores (DVs) de um CNPJ brasileiro pelo algoritmo Módulo 11."""
    weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    s1 = sum(d * w for d, w in zip(digits[:12], weights1, strict=False))
    r1 = s1 % 11
    dv1 = 0 if r1 < 2 else 11 - r1

    weights2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    first13 = [*digits[:12], dv1]
    s2 = sum(d * w for d, w in zip(first13, weights2, strict=False))
    r2 = s2 % 11
    dv2 = 0 if r2 < 2 else 11 - r2

    return dv1, dv2


def generate_valid_cnpj(seed_key: str | int, formatted: bool = True) -> str:
    """Gera um número de CNPJ brasileiro 100% válido determinístico a partir de uma semente."""
    seed_int = (
        int(hashlib.sha256(str(seed_key).encode()).hexdigest()[:12], 16)
        if isinstance(seed_key, str)
        else int(seed_key)
    )
    rng = random.Random(seed_int)

    base_digits = [rng.randint(0, 9) for _ in range(8)]
    if len(set(base_digits)) == 1:
        base_digits[0] = (base_digits[0] + 1) % 10

    branch_digits = [0, 0, 0, 1]
    first12 = base_digits + branch_digits
    dv1, dv2 = compute_cnpj_dv(first12)
    all14 = [*first12, dv1, dv2]

    digits_str = "".join(str(d) for d in all14)
    if formatted:
        return f"{digits_str[0:2]}.{digits_str[2:5]}.{digits_str[5:8]}/{digits_str[8:12]}-{digits_str[12:14]}"
    return digits_str


def validate_cnpj(cnpj: str) -> bool:
    """Valida se uma string representa um CNPJ brasileiro válido via cálculo de dígitos verificadores."""
    clean_digits = [int(c) for c in str(cnpj) if c.isdigit()]
    if len(clean_digits) != 14:
        return False
    if len(set(clean_digits)) == 1:
        return False

    dv1, dv2 = compute_cnpj_dv(clean_digits[:12])
    return clean_digits[12] == dv1 and clean_digits[13] == dv2


def generate_geography(municipios_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Padroniza a tabela de municípios de referência na dimensão canônica de geografia brasileira."""
    df = municipios_df if municipios_df is not None else load_municipios()
    df_geo = df.rename(columns={"nome": "city", "uf": "state", "regiao": "region"})[
        [
            "codigo_ibge",
            "city",
            "state",
            "region",
            "latitude",
            "longitude",
            "populacao",
            "capital",
        ]
    ].copy()

    df_geo["codigo_ibge"] = df_geo["codigo_ibge"].astype("int64")
    df_geo["populacao"] = df_geo["populacao"].astype("int64")
    df_geo["latitude"] = df_geo["latitude"].astype("float64")
    df_geo["longitude"] = df_geo["longitude"].astype("float64")
    df_geo["capital"] = df_geo["capital"].astype("boolean")

    return validate_contract(df_geo, SilverGeographySchema, layer="Silver (dim_geography)")
