from __future__ import annotations

import hashlib
import random

import pandas as pd

from src.etl.contracts import GoldDimProductSchema, validate_contract
from src.etl.scenarios.c1_toys_templates import (
    DEFAULT_GLOBAL_SEED,
    FAMILY_PRICE_MULTIPLIERS,
    TOY_BRANDS,
    TOY_TEMPLATES,
)
from src.etl.silver.reference import compile_category_rules, match_category

# ==============================================================================
# Algoritmo EAN-13 Padrão GS1 Oficial
# ==============================================================================


def compute_ean13_dv(digits12: str) -> int:
    """Calcula o dígito verificador módulo 10 padrão GS1 para código EAN-13."""
    if len(digits12) != 12 or not digits12.isdigit():
        raise ValueError("O prefixo do EAN-13 deve conter exatamente 12 dígitos numéricos.")

    total = 0
    for idx, char in enumerate(digits12):
        digit = int(char)
        # Posições ímpares (0, 2, 4...) peso 1; posições pares (1, 3, 5...) peso 3
        weight = 3 if idx % 2 == 1 else 1
        total += digit * weight

    remainder = total % 10
    return 0 if remainder == 0 else (10 - remainder)


def generate_valid_ean13(seed: int) -> str:
    """Gera um EAN-13 brasileiro determinístico e válido com dígito verificador GS1.

    Estrutura:
    - Prefixo Brasil: 789
    - Código de fabricante (4 dígitos): derivado da seed
    - Código de item (5 dígitos): derivado da seed
    - Dígito verificador: módulo 10
    """
    rng = random.Random(seed)
    mfg_code = rng.randint(1000, 9999)
    prod_code = rng.randint(10000, 99999)
    first12 = f"789{mfg_code:04d}{prod_code:05d}"
    dv = compute_ean13_dv(first12)
    return f"{first12}{dv}"


def validate_ean13(barcode: str) -> bool:
    """Valida se uma sequência de 13 dígitos é um código EAN-13 com DV correto."""
    if len(barcode) != 13 or not barcode.isdigit():
        return False
    return compute_ean13_dv(barcode[:12]) == int(barcode[12])


# ==============================================================================
# Geração Determinística de Nomes e Descrições de Brinquedos
# ==============================================================================


def generate_toy_name_and_description(
    item_number: str,
    family: str,
    global_seed: int = DEFAULT_GLOBAL_SEED,
) -> tuple[str, str]:
    """Gera nome e descrição de brinquedo determinísticos e livres de termos de bebidas.

    Args:
        item_number: Chave natural do produto.
        family: Família de brinquedos (ex.: 'Quebra-Cabeças', 'Jogos Educativos').
        global_seed: Semente pseudo-aleatória.

    Returns:
        Tupla contendo `(product_name, description)`.
    """
    item_seed = int(hashlib.sha256(f"{global_seed}:toy:{item_number}".encode()).hexdigest()[:12], 16)

    templates = TOY_TEMPLATES.get(family, TOY_TEMPLATES["Outros"])
    substantivos = templates["substantivos"]
    variacoes = templates["variacoes"]
    linhas = templates["linhas"]

    subst = substantivos[item_seed % len(substantivos)]
    var = variacoes[(item_seed // 13) % len(variacoes)]
    linha = linhas[(item_seed // 37) % len(linhas)]

    product_name = f"{subst} {var}".strip()
    description = (f"{product_name} — {linha}. Certificado Inmetro, padrão escolar e lojista B2B.").strip()

    return product_name, description


# ==============================================================================
# Construtor da Dimensão de Produtos (dim_product) do Cenário 1
# ==============================================================================


def build_c1_dim_product(
    silver_sales_df: pd.DataFrame,
    category_map_df: pd.DataFrame,
    global_seed: int = DEFAULT_GLOBAL_SEED,
) -> pd.DataFrame:
    """Constrói a dimensão de produtos da indústria de brinquedos com EAN-13 e reescala de preço.

    Args:
        silver_sales_df: DataFrame contendo as vendas Silver com colunas de produto.
        category_map_df: Regras de mapeamento taxonômico de brinquedos.
        global_seed: Semente para reprodutibilidade estrita.

    Returns:
        pd.DataFrame validado contra `GoldDimProductSchema`.
    """
    rules = compile_category_rules(category_map_df)

    distinct_items = (
        silver_sales_df.groupby("item_number")
        .agg(
            category_name=("category_name", "first"),
            vendor_name=("vendor_name", "first"),
            pack=("pack", "first"),
            raw_unit_cost=("unit_cost", "median"),
            raw_unit_price=("unit_price", "median"),
        )
        .reset_index()
        .sort_values("item_number")
        .reset_index(drop=True)
    )

    records: list[dict[str, object]] = []

    for _, row in distinct_items.iterrows():
        item_num = str(row["item_number"]).strip()
        cat_name = str(row["category_name"]).strip()
        vendor_name = str(row["vendor_name"]).strip()
        pack_val = int(row["pack"])
        raw_cost = float(row["raw_unit_cost"])
        raw_price = float(row["raw_unit_price"])

        item_seed = int(hashlib.sha256(f"{global_seed}:item:{item_num}".encode()).hexdigest()[:12], 16)

        family = match_category(cat_name, rules, default="Outros")

        brand_seed = int(hashlib.sha256(f"{global_seed}:vendor:{vendor_name}".encode()).hexdigest()[:8], 16)
        brand_name = TOY_BRANDS[brand_seed % len(TOY_BRANDS)]

        product_name, description = generate_toy_name_and_description(
            item_number=item_num, family=family, global_seed=global_seed
        )

        product_id = generate_valid_ean13(item_seed)

        mult = FAMILY_PRICE_MULTIPLIERS.get(family, 2.5)
        raw_scaled_price = raw_price * mult

        base_unit_price = max(15.0, min(350.0, raw_scaled_price))
        # Custo industrial de fabricação de brinquedos: CMV industrial ~ 40% a 48% do preço de tabela.
        industrial_cost_factor = 0.65
        margin_ratio = (
            max(0.15, min(0.60, (raw_cost / raw_price) * industrial_cost_factor)) if raw_price > 0 else 0.42
        )
        base_unit_cost = max(3.0, min(base_unit_price * 0.70, base_unit_price * margin_ratio))

        records.append(
            {
                "product_id": product_id,
                "item_number": item_num,
                "product_name": product_name,
                "brand_name": brand_name,
                "family": family,
                "description": description,
                "pack": pack_val,
                "base_unit_cost": round(base_unit_cost, 2),
                "base_unit_price": round(base_unit_price, 2),
            }
        )

    df_dim_product = pd.DataFrame(records)
    return validate_contract(df_dim_product, GoldDimProductSchema, layer="Gold (dim_product c1_toys)")
