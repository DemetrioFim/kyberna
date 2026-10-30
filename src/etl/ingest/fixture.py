from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.core.logging import logger, timed_step
from src.core.paths import get_project_root
from src.etl.contracts import BronzeSalesSchema, validate_contract

# ==============================================================================
# Catálogos de Referência Sintética (Baseados no Iowa Alcoholic Beverages Division)
# ==============================================================================

IOWA_CITIES_COUNTIES = [
    ("Des Moines", "Polk", "77", "50309", "41.5868", "-93.6250"),
    ("Cedar Rapids", "Linn", "57", "52401", "41.9779", "-91.6656"),
    ("Davenport", "Scott", "82", "52801", "41.5236", "-90.5776"),
    ("Sioux City", "Woodbury", "97", "51101", "42.4999", "-96.4003"),
    ("Iowa City", "Johnson", "52", "52240", "41.6611", "-91.5302"),
    ("Waterloo", "Black Hawk", "07", "50701", "42.4928", "-92.3426"),
    ("Ames", "Story", "85", "50010", "42.0308", "-93.6319"),
    ("West Des Moines", "Polk", "77", "50265", "41.5772", "-93.7439"),
    ("Council Bluffs", "Pottawattamie", "78", "51501", "41.2619", "-95.8608"),
    ("Dubuque", "Dubuque", "31", "52001", "42.5006", "-90.6646"),
    ("Ankeny", "Polk", "77", "50021", "41.7297", "-93.6058"),
    ("Urbandale", "Polk", "77", "50322", "41.6267", "-93.7122"),
    ("Cedar Falls", "Black Hawk", "07", "50613", "42.5349", "-92.4453"),
    ("Marion", "Linn", "57", "52302", "42.0325", "-91.5977"),
    ("Bettendorf", "Scott", "82", "52722", "41.5245", "-90.5154"),
    ("Mason City", "Cerro Gordo", "17", "50401", "43.1536", "-93.2010"),
    ("Clinton", "Clinton", "23", "52732", "41.8445", "-90.1887"),
    ("Burlington", "Des Moines", "29", "52601", "40.8075", "-91.1129"),
    ("Fort Dodge", "Webster", "94", "50501", "42.5069", "-94.1803"),
    ("Ottumwa", "Wapello", "90", "52501", "41.0200", "-92.4113"),
]

STORE_CHAINS = [
    ("Hy-Vee #{}", "Hy-Vee Food Store #{}"),
    ("Fareway Stores #{}", "Fareway Stores #{}"),
    ("Casey's General Store #{}", "Casey's General Store #{}"),
    ("Kum & Go #{}", "Kum & Go #{}"),
    ("Smokin' Joe's #{}", "Smokin' Joe's Tobacco and Liquor Outlet #{}"),
    ("Central City Liquor #{}", "Central City Liquor #{}"),
    ("Wal-Mart #{}", "Wal-Mart Community Market #{}"),
    ("Target Store #{}", "Target Store T-{}"),
]

VENDORS = [
    ("260", "DIAGEO AMERICAS"),
    ("370", "PERNOD RICARD USA"),
    ("035", "BACARDI USA INC"),
    ("065", "JIM BEAM BRANDS / BEAM SUNTORY"),
    ("259", "HEAVEN HILL BRANDS"),
    ("421", "SAZERAC COMPANY INC"),
    ("305", "MHW LTD"),
    ("380", "PHILLIPS PRODUCTS CO"),
    ("395", "PROXIMO"),
    ("268", "FIFTH GENERATION INC"),
    ("085", "BROWN FORMAN CORP"),
    ("115", "CONSTELLATION BRANDS"),
    ("389", "CAMPARI AMERICA"),
    ("434", "LUXCO INC"),
    ("277", "E & J GALLO WINERY"),
]

CATEGORIES = [
    ("1011100", "VODKA 80 PROOF", 0.22),
    ("1011200", "STRAIGHT BOURBON WHISKIES", 0.16),
    ("1012100", "CANADIAN WHISKIES", 0.12),
    ("1041100", "SPICED RUM", 0.10),
    ("1022100", "100% AGAVE TEQUILA", 0.09),
    ("1031100", "AMERICAN DRY GINS", 0.07),
    ("1051100", "AMERICAN BRANDIES", 0.05),
    ("1011300", "TENNESSEE WHISKIES", 0.05),
    ("1012200", "SCOTCH WHISKIES", 0.04),
    ("1012300", "IRISH WHISKIES", 0.03),
    ("1042100", "IMPORTED VODKA", 0.03),
    ("1081100", "COFFEE LIQUEURS", 0.02),
    ("1081200", "CREAM LIQUEURS", 0.01),
    ("1081300", "AMERICAN CORDIALS & LIQUEURS", 0.01),
]

ITEM_TEMPLATES = [
    ("Hawkeye Vodka", 12, 750, 4.50),
    ("Smirnoff 80 Proof", 12, 750, 8.25),
    ("Tito's Handmade Vodka", 12, 750, 13.00),
    ("Absolut Swedish Vodka", 12, 750, 14.50),
    ("Grey Goose Vodka", 6, 750, 21.00),
    ("Jim Beam Bourbon", 12, 750, 11.50),
    ("Maker's Mark", 12, 750, 18.50),
    ("Woodford Reserve Bourbon", 6, 750, 24.00),
    ("Wild Turkey 101", 12, 750, 15.00),
    ("Buffalo Trace Bourbon", 12, 750, 17.50),
    ("Black Velvet Canadian", 12, 750, 6.25),
    ("Crown Royal Canadian", 12, 750, 17.00),
    ("Canadian Club", 12, 750, 8.50),
    ("Fireball Cinnamon Whisky", 12, 750, 10.50),
    ("Captain Morgan Spiced Rum", 12, 750, 10.00),
    ("Bacardi Superior Rum", 12, 750, 9.25),
    ("Sailor Jerry Spiced Navy Rum", 12, 750, 11.20),
    ("Malibu Coconut Rum", 12, 750, 9.80),
    ("Jose Cuervo Especial Gold", 12, 750, 12.00),
    ("Patron Silver Tequila", 6, 750, 31.00),
    ("Don Julio Blanco", 6, 750, 34.00),
    ("1800 Silver Tequila", 12, 750, 19.50),
    ("Espolon Blanco Tequila", 6, 750, 18.00),
    ("Seagrams Extra Dry Gin", 12, 750, 7.50),
    ("Tanqueray Gin", 12, 750, 15.00),
    ("Bombay Sapphire English Gin", 12, 750, 16.50),
    ("Hendrick's Gin", 6, 750, 24.50),
    ("E & J VS Brandy", 12, 750, 7.20),
    ("Paul Masson Grande Amber", 12, 750, 6.80),
    ("Hennessy VS Cognac", 12, 750, 26.00),
    ("Jack Daniel's Old #7 Black", 12, 750, 16.50),
    ("Johnnie Walker Black", 12, 750, 23.50),
    ("Johnnie Walker Red", 12, 750, 15.00),
    ("Jameson Irish Whiskey", 12, 750, 17.50),
    ("Kahlua Coffee Liqueur", 12, 750, 14.00),
    ("Baileys Original Irish Cream", 12, 750, 16.00),
    ("Jagermeister Liqueur", 12, 750, 15.50),
    ("DeKuyper Peachtree Schnapps", 12, 750, 7.00),
    ("Southern Comfort", 12, 750, 10.50),
]


def _build_stores(rng: np.random.Generator, num_stores: int = 300) -> list[dict[str, str]]:
    """Gera metadados consistentes para ~300 lojas em municípios de Iowa."""
    stores: list[dict[str, str]] = []
    n_cities = len(IOWA_CITIES_COUNTIES)

    for i in range(num_stores):
        store_num = 2000 + i + 1
        city_info = IOWA_CITIES_COUNTIES[i % n_cities]
        chain = STORE_CHAINS[i % len(STORE_CHAINS)]
        store_name = chain[0].format(store_num)

        # Flag de cliente "adormecido" no último trimestre (15% das lojas)
        is_sleeping = 1 if (i % 7 == 0) else 0

        stores.append(
            {
                "store_number": str(store_num),
                "store_name": store_name,
                "address": f"{100 + i * 3} Main Street",
                "city": city_info[0],
                "zip_code": city_info[3],
                "store_location": f"POINT ({city_info[5]} {city_info[4]})",
                "county_number": city_info[2],
                "county": city_info[1],
                "is_sleeping": str(is_sleeping),
            }
        )
    return stores


def _build_items(rng: np.random.Generator, num_items: int = 400) -> list[dict[str, Any]]:
    """Gera catálogo de ~400 SKUs distribuídos por categorias e fornecedores."""
    items: list[dict[str, Any]] = []
    n_vendors = len(VENDORS)
    n_categories = len(CATEGORIES)
    n_templates = len(ITEM_TEMPLATES)

    volumes = [375, 750, 1000, 1750]
    volume_weights = [0.15, 0.55, 0.15, 0.15]
    packs = [6, 12, 24]
    pack_weights = [0.20, 0.70, 0.10]

    for i in range(num_items):
        item_num = 10000 + i + 1
        cat_info = CATEGORIES[i % n_categories]
        vend_info = VENDORS[i % n_vendors]
        template = ITEM_TEMPLATES[i % n_templates]

        # Variação determinística no tamanho/volume
        vol = int(rng.choice(volumes, p=volume_weights))
        pack = int(rng.choice(packs, p=pack_weights))
        cost_multiplier = vol / 750.0
        base_cost = round(float(template[3]) * cost_multiplier, 2)
        # Markup clássico do Iowa Alcoholic Beverages Division (~50%)
        retail_price = round(base_cost * 1.50, 2)

        desc = f"{template[0]} {vol}ml" if (i >= n_templates) else template[0]

        items.append(
            {
                "item_number": str(item_num),
                "item_description": desc,
                "category": cat_info[0],
                "category_name": cat_info[1],
                "vendor_number": vend_info[0],
                "vendor_name": vend_info[1],
                "pack": str(pack),
                "bottle_volume_ml": str(vol),
                "cost": base_cost,
                "retail": retail_price,
            }
        )
    return items


def _compute_date_probabilities(
    start_date: datetime.date, total_days: int
) -> tuple[list[datetime.date], np.ndarray]:
    """Calcula distribuição probabilística de datas com sazonalidade semanal e anual."""
    dates_pool = [start_date + datetime.timedelta(days=d) for d in range(total_days)]

    # Pesos de sazonalidade semanal (quinta a sábado mais forte, Monday=0, Sunday=6)
    day_weights = np.array([0.7, 0.8, 1.0, 1.3, 1.6, 1.4, 0.6])
    # Pesos de sazonalidade anual (pico em Nov/Dez)
    month_weights = np.array([0.8, 0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.0, 0.95, 1.1, 1.35, 1.55])

    date_probabilities = np.zeros(total_days)
    for i, d in enumerate(dates_pool):
        dw = day_weights[d.weekday()]
        mw = month_weights[d.month - 1]
        date_probabilities[i] = dw * mw
    date_probabilities /= date_probabilities.sum()

    return dates_pool, date_probabilities


def _create_sales_line(
    invoice_id: str,
    order_date_str: str,
    store: dict[str, str],
    item: dict[str, Any],
    rng: np.random.Generator,
) -> dict[str, str]:
    """Cria uma linha de venda com métricas monetárias e volumétricas calculadas."""
    pack_val = int(item["pack"])
    case_factor = int(rng.choice([1, 1, 2, 2, 3, 5, 10], p=[0.45, 0.25, 0.15, 0.08, 0.04, 0.02, 0.01]))
    bottles = max(1, pack_val * case_factor)

    cost_val = float(item["cost"])
    retail_val = float(item["retail"])
    sale_dollars_val = round(bottles * retail_val, 2)
    vol_ml = float(item["bottle_volume_ml"])
    liters_val = round((bottles * vol_ml) / 1000.0, 2)
    gallons_val = round(liters_val * 0.264172, 2)

    return {
        "invoice_and_item_number": invoice_id,
        "date": order_date_str,
        "store_number": store["store_number"],
        "store_name": store["store_name"],
        "address": store["address"],
        "city": store["city"],
        "zip_code": store["zip_code"],
        "store_location": store["store_location"],
        "county_number": store["county_number"],
        "county": store["county"],
        "category": item["category"],
        "category_name": item["category_name"],
        "vendor_number": item["vendor_number"],
        "vendor_name": item["vendor_name"],
        "item_number": item["item_number"],
        "item_description": item["item_description"],
        "pack": item["pack"],
        "bottle_volume_ml": item["bottle_volume_ml"],
        "state_bottle_cost": f"{cost_val:.2f}",
        "state_bottle_retail": f"{retail_val:.2f}",
        "bottles_sold": str(bottles),
        "sale_dollars": f"{sale_dollars_val:.2f}",
        "volume_sold_liters": f"{liters_val:.2f}",
        "volume_sold_gallons": f"{gallons_val:.2f}",
        "_ingested_at": "2024-12-31T23:59:59Z",
        "_batch_id": "fixture-sample-01",
        "_source": "fixture_generator",
    }


def generate_fixture(
    num_rows: int = 20000,
    seed: int = 42,
    output_path: Path | None = None,
) -> pd.DataFrame:
    """Gera fixture sintética de vendas determinística no formato exato da API Socrata (Bronze).

    Args:
        num_rows: Quantidade aproximada de linhas de vendas a gerar (padrão: ~20.000).
        seed: Semente pseudo-aleatória determinística.
        output_path: Caminho opcional para salvar o arquivo Parquet. Se omitido, salva
            em tests/fixtures/iowa_sample.parquet.

    Returns:
        pd.DataFrame validado contra o BronzeSalesSchema.
    """
    rng = np.random.default_rng(seed)
    with timed_step("Geração da fixture sintética determinística", row_count=num_rows):
        stores = _build_stores(rng, num_stores=300)
        items = _build_items(rng, num_items=400)

        # Distribuição de probabilidade Zipf (Pareto 80/20) para itens
        item_indices = np.arange(len(items))
        item_weights = 1.0 / (item_indices + 1.0) ** 0.85
        item_weights /= item_weights.sum()

        # Janela temporal: 2023-01-01 a 2024-12-31 (731 dias)
        total_days = 731
        dates_pool, date_probabilities = _compute_date_probabilities(datetime.date(2023, 1, 1), total_days)

        rows: list[dict[str, str]] = []
        n_stores = len(stores)
        churn_cutoff = datetime.date(2024, 9, 1)

        while len(rows) < num_rows:
            store = stores[int(rng.integers(0, n_stores))]
            order_date = dates_pool[int(rng.choice(total_days, p=date_probabilities))]

            # Se a loja for "adormecida" (churn), não compra nos últimos 120 dias
            if store["is_sleeping"] == "1" and order_date >= churn_cutoff:
                continue

            order_date_str = order_date.isoformat()
            items_in_order = int(rng.integers(1, 7))
            chosen_item_indices = rng.choice(item_indices, size=items_in_order, replace=False, p=item_weights)
            invoice_prefix = (
                f"INV-{order_date.year}{order_date.month:02d}-{order_date.day:02d}-{store['store_number']}"
            )

            for line_no, it_idx in enumerate(chosen_item_indices, start=1):
                item = items[it_idx]
                invoice_id = f"{invoice_prefix}-{line_no:02d}"
                rows.append(_create_sales_line(invoice_id, order_date_str, store, item, rng))
                if len(rows) >= num_rows:
                    break

        df = pd.DataFrame(rows)

        # Ordenação determinística estrita para garantir reprodutibilidade byte a byte
        df = df.sort_values(
            by=["date", "store_number", "invoice_and_item_number"],
            ascending=[True, True, True],
        ).reset_index(drop=True)

        # Validação do contrato Bronze
        validated_df = validate_contract(df, BronzeSalesSchema, layer="Bronze")

        # Persistência em Parquet
        target_path = output_path or (get_project_root() / "tests" / "fixtures" / "iowa_sample.parquet")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        validated_df.to_parquet(target_path, index=False, compression="zstd")

        file_size_kb = target_path.stat().st_size / 1024
        logger.info(
            "Fixture sintética salva em %s (%.1f KB, %d linhas)",
            target_path,
            file_size_kb,
            len(validated_df),
        )

        return validated_df
