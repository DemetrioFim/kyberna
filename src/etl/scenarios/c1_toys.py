from __future__ import annotations

import hashlib
import random
from pathlib import Path
from typing import Final

import duckdb
import pandas as pd

from src.core.logging import get_logger
from src.core.paths import get_data_dir
from src.core.scenarios import ScenarioConfig, load_scenario_config
from src.core.types import ScenarioId
from src.etl.contracts import GoldDimProductSchema, validate_contract
from src.etl.ingest.fixture import generate_fixture
from src.etl.scenarios.base import ScenarioBuilder
from src.etl.silver.enrich import (
    generate_customers,
    generate_geography,
    generate_sales_reps,
)
from src.etl.silver.reference import (
    build_category_case_when_sql,
    compile_category_rules,
    load_category_map,
    match_category,
)

logger = get_logger(__name__)

SCENARIO_ID: Final[ScenarioId] = "c1_toys"
DEFAULT_BRANCH_ID: Final[str] = "FAB-SP01"
DEFAULT_GLOBAL_SEED: Final[int] = 42

# ==============================================================================
# Linhas e Marcas Fictícias da Indústria Nacional de Brinquedos
# ==============================================================================

TOY_BRANDS: Final[list[str]] = [
    "Brinquedos Estrela do Saber",
    "Pedagogix Brasil",
    "Mundo da Imaginação",
    "Oficina da Madeira",
    "Aquarela & Cia",
    "Brinkids Nacional",
    "Lógica & Desafio",
    "Terra do Saber",
    "Mestre dos Jogos",
    "Fábrica dos Sonhos",
    "Criativa Brinquedos",
    "BrinqPedagógica",
]

# ==============================================================================
# Multiplicadores de Preço por Família (Calibrados para a faixa R$ 15 a R$ 350)
# ==============================================================================

FAMILY_PRICE_MULTIPLIERS: Final[dict[str, float]] = {
    "Jogos Educativos": 2.8,
    "Quebra-Cabeças": 2.4,
    "Primeira Infância": 2.2,
    "Brinquedos de Madeira": 3.2,
    "Linha Escolar": 1.8,
    "Jogos de Tabuleiro": 2.5,
    "Pelúcias": 2.5,
    "Outros": 2.0,
}

# ==============================================================================
# Lista Proibida de Termos de Bebidas (DoD: Zero termos de bebida remanescentes)
# ==============================================================================

FORBIDDEN_BEVERAGE_TERMS: Final[list[str]] = [
    "vodka",
    "whisky",
    "whiskey",
    "bourbon",
    "scotch",
    "rum",
    "tequila",
    "mezcal",
    "liqueur",
    "schnapps",
    "cordial",
    "gin",
    "brandy",
    "cocktail",
    "liquor",
    "alcohol",
    "bottle",
    "proof",
    "distilled",
    "cachaça",
    "cachaca",
    "cerveja",
    "vinho",
    "draft",
    "amaretto",
    "triple sec",
    "creme de",
]

# ==============================================================================
# Templates Determinísticos de Nomes e Descrições por Família de Brinquedos
# ==============================================================================

TOY_TEMPLATES: Final[dict[str, dict[str, list[str]]]] = {
    "Jogos Educativos": {
        "substantivos": [
            "Kit Científico",
            "Jogo de Alfabetização",
            "Laboratório Infantil",
            "Ábaco Contador",
            "Kit de Robótica",
            "Prancha de Encaixe",
            "Jogo das Quatro Operações",
            "Dominó de Frações",
            "Encaixe Silábico",
            "Balança Pedagógica",
            "Microscópio Júnior",
            "Jogo da Tabuada Divertida",
            "Kit Magnetismo & Força",
            "Blocos Lógicos Pedagógicos",
            "Painel Sensorial Montessori",
        ],
        "variacoes": [
            "de Ciências e Química",
            "Magnético Ilustrado",
            "com Cartas Desafio",
            "com 50 Peças em Madeira",
            "Iniciante com Motores",
            "Formas Geométricas Coloridas",
            "Matemático Avançado",
            "Educativo Infantil",
            "3 em 1 Cartonado",
            "com Pesos de Precisão",
            "com 24 Lâminas Didáticas",
            "com Cartelas Ilustradas",
            "com 12 Experimentos",
            "com Formas Anatômicas",
            "Multiatividades de Madeira",
        ],
        "linhas": [
            "Linha Aprender Brincando",
            "Coleção Mini Cientista",
            "Série Descobrindo o Mundo",
            "Linha Raciocínio Rápido",
            "Coleção Estrela do Saber",
            "Série Educativa Júnior",
        ],
    },
    "Quebra-Cabeças": {
        "substantivos": [
            "Quebra-Cabeça",
            "Puzzle Panorâmico",
            "Quebra-Cabeça Redondo",
            "Puzzle Tridimensional",
            "Super Puzzle",
            "Quebra-Cabeça Dupla-Face",
            "Maxi Quebra-Cabeça",
            "Quebra-Cabeça Cartonado",
        ],
        "variacoes": [
            "100 Peças — Animais da Floresta",
            "200 Peças — Fundo do Mar",
            "300 Peças — Sistema Solar",
            "500 Peças — Mapas do Brasil",
            "750 Peças — Monumentos Históricos",
            "1000 Peças — Paisagens Brasileiras",
            "1500 Peças — Cidades do Mundo",
            "250 Peças — Dinossauros Pré-Históricos",
            "60 Peças Gigantes — Fazendinha",
            "120 Peças — Aventura Espacial",
        ],
        "linhas": [
            "Coleção Desafio Visual",
            "Série Paisagens Nacionais",
            "Linha Natureza Viva",
            "Coleção Conhecendo o Brasil",
            "Série Grandes Exploradores",
        ],
    },
    "Primeira Infância": {
        "substantivos": [
            "Móbile Musical",
            "Chocalho Mordedor",
            "Torre de Argolas",
            "Tapete de Atividades",
            "Kit de Banho",
            "Centopeia de Encaixe",
            "Cubo de Atividades",
            "Andador de Empurrar",
            "Chaveiro Sonoro",
            "Livrinho de Banho",
            "Bolinhas Sensoriais",
        ],
        "variacoes": [
            "Giratório para Berço",
            "Anatômico com Texturas",
            "Coloridas com Base Oscilante",
            "Sensorial Acolchoado",
            "Patinhos Flutuantes 4 Peças",
            "com Luzes e Sons Suaves",
            "Multifunções de Encaixe",
            "com Freio de Segurança",
            "com Efeitos Sonoros",
            "Impermeável Ilustrado",
            "Texturizadas para Massagem",
        ],
        "linhas": [
            "Linha Baby Comfort",
            "Coleção Pequenos Passos",
            "Série Primeiras Descobertas",
            "Linha Ninho Feliz",
            "Coleção Bebê Brincalhão",
        ],
    },
    "Brinquedos de Madeira": {
        "substantivos": [
            "Blocos de Montar",
            "Carrinho Retrô",
            "Ábaco Vertical",
            "Quebra-Cabeça 3D",
            "Casinha de Boneca",
            "Trem de Madeira",
            "Labirinto de Aramado",
            "Kit Ferramentas",
            "Teatro de Marionetes",
            "Pista de Carrinhos",
            "Xilofone Artesanal",
        ],
        "variacoes": [
            "em Madeira 60 Peças",
            "em Madeira Maciça Reflorestada",
            "de Madeira Nobre Colorido",
            "Animais da Savana em Madeira",
            "com Móveis em Miniatura",
            "com Vagões Magnéticos",
            "com Miçangas Coloridas",
            "com Bancada em Madeira",
            "com 4 Fantoches em Madeira",
            "em Madeira com 3 Níveis",
            "Musical com Baquetas de Madeira",
        ],
        "linhas": [
            "Linha EcoWood Sustentável",
            "Coleção Oficina da Madeira",
            "Série Artesanal Clássica",
            "Linha Madeira Criativa",
        ],
    },
    "Linha Escolar": {
        "substantivos": [
            "Kit Aquarela Escolar",
            "Conjunto de Massinhas",
            "Estojo de Giz de Cera",
            "Kit Tinta Guache",
            "Potes de Areia Mágica",
            "Estojo de Lápis de Cor",
            "Canetinhas Hidrográficas",
            "Kit Tesoura & Cola Colorida",
            "Avental Escolar com Pincéis",
            "Maleta Artística Infantil",
        ],
        "variacoes": [
            "12 Cores com Pincel Macio",
            "12 Cores Perfumadas",
            "Jumbo Triangular 24 Cores",
            "6 Cores Laváveis Atóxicas",
            "com 4 Moldes Temáticos",
            "Aquareláveis 36 Cores",
            "Ponta Grossa Lavável 12 Cores",
            "com 5 Tubos com Glíter",
            "Impermeável Ajustável",
            "Completa com 48 Itens de Desenho",
        ],
        "linhas": [
            "Coleção Aquarela & Arte",
            "Linha Cores da Imaginação",
            "Série Pintando o Sete",
            "Linha Criativa Escolar",
        ],
    },
    "Jogos de Tabuleiro": {
        "substantivos": [
            "Jogo de Tabuleiro",
            "Jogo de Estratégia",
            "Damas e Xadrez",
            "Jogo de Cartas",
            "Jogo de Trilha",
            "Jogo de Mímica",
            "Jogo de Perguntas & Respostas",
            "Jogo de Adivinhação",
            "Batalha Naval",
            "Jogo de Percurso",
        ],
        "variacoes": [
            "Batalha Tática Medieval",
            "Conquista do Território",
            "Estojo 2 em 1 Madeira",
            "Desafio Rápido das Cores",
            "Aventura na Ilha Misteriosa",
            "com Ampulheta e Roleta",
            "Conhecimentos Gerais Júnior",
            "Quem Sou Eu com Tiaras",
            "com Maleta Dobrável",
            "Rumo à Linha de Chegada",
        ],
        "linhas": [
            "Coleção Noite de Jogos",
            "Série Estratégia & Foco",
            "Linha Família Reunida",
            "Coleção Mestres do Tabuleiro",
        ],
    },
    "Pelúcias": {
        "substantivos": [
            "Ursinho de Pelúcia",
            "Bichinho de Pelúcia",
            "Almofada de Pelúcia",
            "Pelúcia Dinossauro",
            "Coelhinho de Pelúcia",
            "Cachorrinho de Pelúcia",
            "Gatinho de Pelúcia",
            "Pinguim de Pelúcia",
            "Elefantinho de Pelúcia",
            "Girafa de Pelúcia",
        ],
        "variacoes": [
            "Antialérgico 35cm com Laço",
            "Leãozinho da Savana 30cm",
            "Bebê Soninho 40cm Macia",
            "T-Rex 40cm com Sons",
            "com Orelhas Longas 28cm",
            "Golden Retriever 32cm Sentado",
            "com Olhos Brilhantes 25cm",
            "com Cachecol de Lã 30cm",
            "com Orelhas Gigantes 35cm",
            "com Pescoço Longo 45cm",
        ],
        "linhas": [
            "Linha Amiguinhos Fofos",
            "Coleção Pelúcias do Coração",
            "Série Safari Pelúcias",
            "Linha Abraço Quentinho",
        ],
    },
    "Outros": {
        "substantivos": [
            "Kit Acessórios Lúdicos",
            "Conjunto de Dados & Peões",
            "Bolsa Organizadora de Brinquedos",
            "Lanterna Infantil Divertida",
            "Kit Lupa & Bússola do Explorador",
        ],
        "variacoes": [
            "Multiuso com 20 Peças",
            "Coloridos para Reposição",
            "com Cordão e Bolsos",
            "com Filtros de Cores",
            "com Guia de Campo Júnior",
        ],
        "linhas": [
            "Linha Acessórios Kyberna",
            "Série BrinqPro",
        ],
    },
}

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

    # Identifica itens únicos da Silver
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

        # 1. Mapeamento da Família via regras regex de toys.csv
        family = match_category(cat_name, rules, default="Outros")

        # 2. Linha / Marca fictícia da indústria
        brand_seed = int(hashlib.sha256(f"{global_seed}:vendor:{vendor_name}".encode()).hexdigest()[:8], 16)
        brand_name = TOY_BRANDS[brand_seed % len(TOY_BRANDS)]

        # 3. Nome e Descrição do brinquedo
        product_name, description = generate_toy_name_and_description(
            item_number=item_num, family=family, global_seed=global_seed
        )

        # 4. Código de barras EAN-13 válido com DV GS1
        product_id = generate_valid_ean13(item_seed)

        # 5. Reescala realista de preço e custo (R$ 15 a R$ 350) preservando proporção
        mult = FAMILY_PRICE_MULTIPLIERS.get(family, 2.5)
        raw_scaled_price = raw_price * mult

        # Garante a faixa estrita de R$ 15 a R$ 350
        base_unit_price = max(15.0, min(350.0, raw_scaled_price))
        # Custo industrial de fabricação de brinquedos: calibrado para refletir a estrutura
        # de custos fabris da indústria nacional (CMV industrial ~ 40% a 48% do preço de tabela).
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


# ==============================================================================
# Classe Builder Concreta para o Cenário 1 (Caso Âncora)
# ==============================================================================


class C1ToysScenarioBuilder(ScenarioBuilder):
    """Builder do Cenário 1 — Indústria B2B Nacional de Brinquedos (Caso Âncora).

    Materializa no DuckDB e em Parquet:
    - `c1_toys.dim_product` (e view `gold.dim_product` se aplicável)
    - `c1_toys.sales_remapped` (vendas remapeadas prontas para o motor de waterfall)
    """

    def __init__(
        self,
        config: ScenarioConfig | None = None,
        duckdb_path: Path | None = None,
        global_seed: int = DEFAULT_GLOBAL_SEED,
    ) -> None:
        cfg = config or load_scenario_config(SCENARIO_ID)
        super().__init__(config=cfg, duckdb_path=duckdb_path)
        self.global_seed = global_seed

    def _ensure_silver_sales(self, con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
        """Garante que a tabela silver.sales existe no DuckDB e retorna seus registros."""
        has_silver = False
        try:
            tables = con.execute("SHOW TABLES FROM silver").fetchall()
            if any(t[0] == "sales" for t in tables):
                has_silver = True
        except Exception:
            has_silver = False

        if has_silver:
            return con.execute("SELECT * FROM silver.sales").df()

        sample_path = get_data_dir().parent / "tests" / "fixtures" / "iowa_sample.parquet"
        if not sample_path.exists():
            generate_fixture(output_path=sample_path)

        sample_sql_p = str(sample_path).replace("\\", "/")
        con.execute("CREATE SCHEMA IF NOT EXISTS silver")
        con.execute(
            f"""
            CREATE OR REPLACE TABLE silver.sales AS
            SELECT
                invoice_and_item_number AS invoice_line_id,
                date::DATE AS date,
                store_number,
                store_name,
                city,
                county,
                zip_code,
                category_name,
                vendor_name,
                item_number,
                item_description,
                pack::INTEGER AS pack,
                state_bottle_cost::DOUBLE AS unit_cost,
                state_bottle_retail::DOUBLE AS unit_price,
                bottles_sold::INTEGER AS units,
                sale_dollars::DOUBLE AS sale_amount
            FROM read_parquet('{sample_sql_p}')
            """
        )
        return con.execute("SELECT * FROM silver.sales").df()

    def _ensure_silver_customers(self, con: duckdb.DuckDBPyConnection) -> None:
        """Garante que a tabela silver.dim_customer existe no DuckDB para enriquecimento."""
        has_customers = False
        try:
            cust_tables = con.execute("SHOW TABLES FROM silver").fetchall()
            if any(t[0] == "dim_customer" for t in cust_tables):
                has_customers = True
        except Exception:
            has_customers = False

        if not has_customers:
            stores_df = con.execute(
                """
                SELECT
                    store_number,
                    FIRST(county) AS county,
                    SUM(sale_amount) AS revenue
                FROM silver.sales
                GROUP BY store_number
                """
            ).df()
            reps_df = generate_sales_reps(global_seed=self.global_seed)
            geo_df = generate_geography()
            cust_df = generate_customers(stores_df, geo_df, reps_df, global_seed=self.global_seed)

            con.register("temp_dim_cust", cust_df)
            con.execute("CREATE OR REPLACE TABLE silver.dim_customer AS SELECT * FROM temp_dim_cust")
            con.register("temp_dim_rep", reps_df)
            con.execute("CREATE OR REPLACE TABLE silver.dim_sales_rep AS SELECT * FROM temp_dim_rep")
            con.register("temp_dim_geo", geo_df)
            con.execute("CREATE OR REPLACE TABLE silver.dim_geography AS SELECT * FROM temp_dim_geo")

    def build(self, con: duckdb.DuckDBPyConnection) -> dict[str, int]:
        """Executa a transformação semântica do Caso Âncora no DuckDB.

        Args:
            con: Conexão ativa com o banco DuckDB.

        Returns:
            Dicionário com a contagem de registros em cada tabela gerada.
        """
        logger.info("Iniciando build do Cenário 1 (%s)...", self.config.display_name)

        # 1. Carrega regras de mapeamento de categoria e dados da Silver
        cat_map_df = load_category_map(self.config.id)
        silver_df = self._ensure_silver_sales(con)

        # 2. Constrói e valida dim_product
        df_product = build_c1_dim_product(
            silver_sales_df=silver_df,
            category_map_df=cat_map_df,
            global_seed=self.global_seed,
        )

        con.execute("CREATE SCHEMA IF NOT EXISTS c1_toys")
        con.execute("CREATE SCHEMA IF NOT EXISTS gold")
        con.register("temp_c1_dim_product", df_product)
        con.execute("CREATE OR REPLACE TABLE c1_toys.dim_product AS SELECT * FROM temp_c1_dim_product")
        con.execute("CREATE OR REPLACE TABLE gold.dim_product AS SELECT * FROM temp_c1_dim_product")

        # 3. Garante dim_customer e constrói c1_toys.sales_remapped
        rules = compile_category_rules(cat_map_df)
        case_sql = build_category_case_when_sql(rules, "s.category_name")
        self._ensure_silver_customers(con)

        remapped_query = f"""
        CREATE OR REPLACE TABLE c1_toys.sales_remapped AS
        SELECT
            s.invoice_line_id,
            s.invoice_line_id AS order_id,
            s.date,
            CAST(strftime(s.date, '%Y%m%d') AS INTEGER) AS date_key,
            s.store_number,
            COALESCE(c.customer_id, 'CLI-' || s.store_number) AS customer_id,
            COALESCE(c.sales_rep_id, 'RCA-001') AS sales_rep_id,
            '{DEFAULT_BRANCH_ID}' AS branch_id,
            p.product_id,
            p.product_name,
            p.brand_name,
            {case_sql} AS family,
            s.pack,
            s.units,
            ROUND(CAST(s.units AS DOUBLE) / CAST(s.pack AS DOUBLE), 2) AS boxes,
            p.base_unit_price AS unit_list_price,
            p.base_unit_cost AS unit_cost,
            ROUND(s.units * p.base_unit_price, 2) AS gross_revenue,
            ROUND(s.units * p.base_unit_cost, 2) AS cogs
        FROM silver.sales s
        JOIN c1_toys.dim_product p ON s.item_number = p.item_number
        LEFT JOIN silver.dim_customer c ON s.store_number = c.store_number
        """
        con.execute(remapped_query)

        # 4. Persiste snapshots Parquet locais em gold/snapshot/c1_toys/
        snapshot_dir = (
            (self.duckdb_path.parent / "gold" / "snapshot" / SCENARIO_ID)
            if self.duckdb_path
            else (get_data_dir() / "gold" / "snapshot" / SCENARIO_ID)
        )
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        product_parquet = snapshot_dir / "dim_product.parquet"
        sales_parquet = snapshot_dir / "sales_remapped.parquet"

        con.execute(
            f"COPY c1_toys.dim_product TO '{product_parquet.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)"
        )
        con.execute(
            f"COPY c1_toys.sales_remapped TO '{sales_parquet.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)"
        )

        n_products = len(df_product)
        res_sales = con.execute("SELECT COUNT(*) FROM c1_toys.sales_remapped").fetchone()
        n_sales = int(res_sales[0]) if res_sales else 0

        logger.info(
            "Build do Cenário C1 concluído: %d produtos e %d transações remapeadas.",
            n_products,
            n_sales,
        )

        return {
            "dim_product": n_products,
            "sales_remapped": n_sales,
        }
