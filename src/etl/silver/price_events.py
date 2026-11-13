from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.core.logging import logger, timed_step
from src.core.paths import config_path, silver_path
from src.core.settings import get_settings
from src.etl.contracts import (
    SilverElasticityGroundTruthSchema,
    SilverSalesSchema,
    validate_contract,
)
from src.etl.lake import get_duckdb_connection, write_parquet
from src.etl.silver.reference import compile_category_rules, load_category_map, match_category


class PriceEventsConfig(BaseModel):
    """Configuração tipada dos parâmetros de eventos de preço e elasticidade-verdade."""

    model_config = ConfigDict(frozen=True)

    elasticity_ground_truth: dict[str, float]
    promo_fraction_target: float = Field(0.12, ge=0.01, le=0.50)
    markup_fraction_target: float = Field(0.06, ge=0.01, le=0.50)
    promo_delta_range: tuple[float, float] = (-0.20, -0.05)
    markup_delta_range: tuple[float, float] = (0.03, 0.08)
    noise_std: float = Field(0.04, ge=0.0, le=0.25)
    min_cost_floor_ratio: float = Field(0.55, ge=0.50, le=1.0)
    default_seed: int = Field(42, ge=0)

    @model_validator(mode="after")
    def validate_ranges(self) -> PriceEventsConfig:
        """Valida consistência econômica dos intervalos de preço e elasticidades negativas."""
        if not self.elasticity_ground_truth:
            raise ValueError("elasticity_ground_truth não pode estar vazio.")
        for family, beta in self.elasticity_ground_truth.items():
            if beta >= 0:
                raise ValueError(f"Elasticidade-verdade para '{family}' deve ser negativa (recebido {beta}).")
        if self.promo_fraction_target + self.markup_fraction_target >= 1.0:
            raise ValueError("Soma das frações alvo de eventos deve ser inferior a 1.0.")
        if self.promo_delta_range[0] >= self.promo_delta_range[1]:
            raise ValueError("promo_delta_range inválido.")
        if self.markup_delta_range[0] >= self.markup_delta_range[1]:
            raise ValueError("markup_delta_range inválido.")
        return self


def load_price_events_config(pipeline_yaml: Path | None = None) -> PriceEventsConfig:
    """Carrega a configuração de elasticidade-verdade e eventos de preço de `config/pipeline.yaml`."""
    yaml_path = pipeline_yaml or config_path("pipeline.yaml")
    if not yaml_path.exists():
        raise FileNotFoundError(f"Arquivo de configuração não encontrado: {yaml_path}")

    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    thresholds = raw.get("thresholds", {})
    seeds = raw.get("seeds", {})
    pe_raw = thresholds.get("price_events", {})
    gt_raw = thresholds.get("elasticity_ground_truth", {})

    promo_range = pe_raw.get("promo_delta_range", [-0.20, -0.05])
    markup_range = pe_raw.get("markup_delta_range", [0.03, 0.08])

    return PriceEventsConfig(
        elasticity_ground_truth={str(k): float(v) for k, v in gt_raw.items()},
        promo_fraction_target=float(pe_raw.get("promo_fraction_target", 0.12)),
        markup_fraction_target=float(pe_raw.get("markup_fraction_target", 0.06)),
        promo_delta_range=(float(promo_range[0]), float(promo_range[1])),
        markup_delta_range=(float(markup_range[0]), float(markup_range[1])),
        noise_std=float(pe_raw.get("noise_std", 0.04)),
        min_cost_floor_ratio=float(pe_raw.get("min_cost_floor_ratio", 0.55)),
        default_seed=int(seeds.get("sampling", 42)),
    )


def map_categories_to_families(categories: pd.Series) -> pd.Series:
    """Mapeia nomes de categoria brutos para as famílias do Cenário 1 de forma vetorizada."""
    cat_map_df = load_category_map("toys")
    rules = compile_category_rules(cat_map_df)
    unique_cats = categories.dropna().astype(str).unique().tolist()
    cat_to_family = {cat: match_category(cat, rules, default="Outros") for cat in unique_cats}
    return categories.astype(str).map(cat_to_family).fillna("Outros")


def _build_pair_events_table(
    item_numbers: pd.Series,
    year_weeks: pd.Series,
    cfg: PriceEventsConfig,
    seed: int,
) -> pd.DataFrame:
    """Gera atribuição determinística por par único `(item_number, year_week)` via hash SHA-256."""
    pairs_df = (
        pd.DataFrame({"item_number": item_numbers.astype(str), "year_week": year_weeks.astype(str)})
        .drop_duplicates()
        .sort_values(["item_number", "year_week"])
        .reset_index(drop=True)
    )

    promo_cut = cfg.promo_fraction_target
    total_cut = promo_cut + cfg.markup_fraction_target
    p_low, p_high = cfg.promo_delta_range
    m_low, m_high = cfg.markup_delta_range
    denom = float(1 << 64)

    u_types = np.empty(len(pairs_df), dtype=np.float64)
    u_mags = np.empty(len(pairs_df), dtype=np.float64)

    item_vals = pairs_df["item_number"].to_numpy()
    week_vals = pairs_df["year_week"].to_numpy()

    for idx, (item_num, yw) in enumerate(zip(item_vals, week_vals, strict=True)):
        digest = hashlib.sha256(f"{seed}:price_event:{item_num}:{yw}".encode()).digest()
        u_types[idx] = int.from_bytes(digest[:8], "big") / denom
        u_mags[idx] = int.from_bytes(digest[8:16], "big") / denom

    is_promo = u_types < promo_cut
    is_markup = (u_types >= promo_cut) & (u_types < total_cut)

    delta_p = np.zeros(len(pairs_df), dtype=np.float64)
    delta_p[is_promo] = p_low + u_mags[is_promo] * (p_high - p_low)
    delta_p[is_markup] = m_low + u_mags[is_markup] * (m_high - m_low)

    pair_keys = pairs_df["item_number"] + "-" + pairs_df["year_week"]
    event_ids = pd.Series([None] * len(pairs_df), index=pairs_df.index, dtype="object")
    event_ids.loc[is_promo] = "EVT-PROMO-" + pair_keys.loc[is_promo]
    event_ids.loc[is_markup] = "EVT-REAJ-" + pair_keys.loc[is_markup]

    pairs_df["promo_flag"] = is_promo
    pairs_df["delta_p"] = delta_p
    pairs_df["price_event_id"] = event_ids
    return pairs_df


def _compute_ols_recovery(df_events: pd.DataFrame) -> dict[str, float]:
    """Calcula a elasticidade estimada por regressão OLS log-log para cada família afetada."""
    if df_events.empty:
        return {}

    recovered: dict[str, float] = {}
    for family, grp in df_events.groupby("family", sort=True):
        p_ratio = grp["p_ratio"].to_numpy(dtype=np.float64)
        q_ratio = grp["q_ratio"].to_numpy(dtype=np.float64)
        valid = (p_ratio > 0) & (q_ratio > 0) & (np.abs(p_ratio - 1.0) > 1e-9)
        if np.count_nonzero(valid) >= 2:
            slope = float(np.polyfit(np.log(p_ratio[valid]), np.log(q_ratio[valid]), 1)[0])
            recovered[str(family)] = round(slope, 4)
    return recovered


def _build_ground_truth_table(cfg: PriceEventsConfig) -> pd.DataFrame:
    """Constrói e valida a tabela de referência `silver.elasticity_ground_truth`."""
    rows = [
        {
            "scenario_id": "c1_toys",
            "family": family,
            "beta_true": float(beta),
            "promo_fraction_target": float(cfg.promo_fraction_target),
        }
        for family, beta in cfg.elasticity_ground_truth.items()
    ]
    df_gt = pd.DataFrame(rows)
    return validate_contract(df_gt, SilverElasticityGroundTruthSchema, layer="silver")


def _persist_ground_truth(
    con: duckdb.DuckDBPyConnection,
    cfg: PriceEventsConfig,
    target_gt_parquet: Path,
) -> pd.DataFrame:
    """Materializa `silver.elasticity_ground_truth` no DuckDB e em Parquet ZSTD."""
    df_gt = _build_ground_truth_table(cfg)
    con.execute("CREATE SCHEMA IF NOT EXISTS silver")
    con.register("temp_silver_gt", df_gt)
    con.execute("CREATE OR REPLACE TABLE silver.elasticity_ground_truth AS SELECT * FROM temp_silver_gt")
    con.unregister("temp_silver_gt")
    write_parquet(df_gt, target_gt_parquet, compression="zstd")
    return df_gt


def _inject_events_into_dataframe(
    df: pd.DataFrame,
    cfg: PriceEventsConfig,
    seed: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Aplica eventos determinísticos de preço e ajuste de volume no DataFrame Silver."""
    base_price = (
        df["original_unit_price"].where(df["original_unit_price"].notna(), df["unit_price"])
        if "original_unit_price" in df.columns
        else df["unit_price"]
    ).to_numpy(dtype=np.float64)
    base_units = (
        df["original_units"].where(df["original_units"].notna(), df["units"])
        if "original_units" in df.columns
        else df["units"]
    ).to_numpy(dtype=np.int64)

    iso = pd.to_datetime(df["date"]).dt.isocalendar()
    year_week = iso["year"].astype(str) + "-W" + iso["week"].astype(str).str.zfill(2)

    events_df = _build_pair_events_table(df["item_number"], year_week, cfg=cfg, seed=seed)
    keys_df = pd.DataFrame({"item_number": df["item_number"].astype(str), "year_week": year_week.astype(str)})
    merged_events = keys_df.merge(events_df, on=["item_number", "year_week"], how="left")

    promo_flag = merged_events["promo_flag"].fillna(False).to_numpy(dtype=bool)
    delta_p = merged_events["delta_p"].fillna(0.0).to_numpy(dtype=np.float64)
    price_event_id = merged_events["price_event_id"].to_numpy()
    has_event = pd.notna(price_event_id)

    families = map_categories_to_families(df["category_name"])
    beta_series = families.map(cfg.elasticity_ground_truth).fillna(-1.0).to_numpy(dtype=np.float64)

    unit_cost = df["unit_cost"].to_numpy(dtype=np.float64)
    min_floor = np.round(unit_cost * cfg.min_cost_floor_ratio, 2)
    raw_price_adj = np.round(base_price * (1.0 + delta_p), 2)
    unit_price_adj = np.maximum(
        np.where(has_event, np.maximum(raw_price_adj, min_floor), base_price),
        0.01,
    )

    p_ratio = np.where(base_price > 0, unit_price_adj / base_price, 1.0)
    eps = np.random.default_rng(seed).normal(0.0, cfg.noise_std, size=len(df))
    elastic_factor = np.power(p_ratio, beta_series) * np.exp(eps)
    units_adj = np.where(
        has_event,
        np.maximum(1, np.rint(base_units * elastic_factor)).astype(np.int64),
        base_units,
    )

    df_out = df.copy()
    df_out["original_unit_price"] = base_price
    df_out["original_units"] = base_units
    df_out["unit_price"] = unit_price_adj
    df_out["units"] = units_adj
    df_out["sale_amount"] = np.round(units_adj * unit_price_adj, 2)
    df_out["promo_flag"] = promo_flag
    df_out["price_event_id"] = price_event_id
    df_validated = validate_contract(df_out, SilverSalesSchema, layer="silver")

    affected_rows = int(np.count_nonzero(has_event))
    promo_rows = int(np.count_nonzero(promo_flag))
    orig_vol = int(base_units.sum())
    new_vol = int(units_adj.sum())
    vol_change_pct = ((new_vol - orig_vol) / orig_vol * 100.0) if orig_vol > 0 else 0.0

    eval_df = pd.DataFrame(
        {
            "family": families.to_numpy()[has_event],
            "p_ratio": p_ratio[has_event],
            "q_ratio": (units_adj[has_event] / np.maximum(base_units[has_event], 1)),
        }
    )
    metadata: dict[str, Any] = {
        "seed": seed,
        "total_rows": len(df_validated),
        "affected_rows": affected_rows,
        "affected_fraction": affected_rows / max(len(df_validated), 1),
        "promo_rows": promo_rows,
        "markup_rows": affected_rows - promo_rows,
        "original_volume": orig_vol,
        "adjusted_volume": new_vol,
        "volume_change_pct": round(vol_change_pct, 4),
        "ols_recovery_by_family": _compute_ols_recovery(eval_df),
    }
    return df_validated, metadata


def apply_price_events(
    db_con: duckdb.DuckDBPyConnection | None = None,
    seed: int | None = None,
    base_dir: Path | None = None,
    pipeline_yaml: Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Injeta eventos determinísticos de preço e ajusta volume pela elasticidade em `silver.sales`.

    Operação idempotente: preserva `original_unit_price` e `original_units` para evitar
    efeito composto em reexecuções, valida contra `SilverSalesSchema` e materializa
    `silver.elasticity_ground_truth` no DuckDB e em Parquet.
    """
    settings = get_settings()
    cfg = load_price_events_config(pipeline_yaml=pipeline_yaml)
    eff_seed = cfg.default_seed if seed is None else seed

    con = db_con or get_duckdb_connection(settings.duckdb_path)
    target_sales_parquet = silver_path("sales", base=base_dir)
    target_gt_parquet = silver_path("elasticity_ground_truth", base=base_dir)
    target_sales_parquet.parent.mkdir(parents=True, exist_ok=True)

    with timed_step("silver_price_events"):
        tbl_exists = con.execute("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema = 'silver' AND table_name = 'sales';
        """).fetchone()
        if not tbl_exists or tbl_exists[0] == 0:
            raise RuntimeError(
                "Tabela silver.sales não encontrada no DuckDB. Execute 'kyberna silver build' primeiro."
            )

        df = con.execute("SELECT * FROM silver.sales ORDER BY invoice_line_id;").df()
        if df.empty:
            logger.warning("Tabela silver.sales vazia. Nenhum evento de preço aplicado.")
            _persist_ground_truth(con, cfg, target_gt_parquet)
            return target_sales_parquet, {
                "total_rows": 0,
                "affected_rows": 0,
                "affected_fraction": 0.0,
                "volume_change_pct": 0.0,
                "ols_recovery_by_family": {},
            }

        df_validated, metadata = _inject_events_into_dataframe(df, cfg=cfg, seed=eff_seed)

        con.execute("CREATE SCHEMA IF NOT EXISTS silver")
        con.register("temp_silver_sales_events", df_validated)
        con.execute("CREATE OR REPLACE TABLE silver.sales AS SELECT * FROM temp_silver_sales_events")
        con.unregister("temp_silver_sales_events")
        write_parquet(df_validated, target_sales_parquet, compression="zstd")
        _persist_ground_truth(con, cfg, target_gt_parquet)

        logger.info(
            "Eventos de preço aplicados em silver.sales: %d/%d linhas (%.1f%% | promo=%d, reaj=%d) | "
            "variação de volume=%.2f%%.",
            metadata["affected_rows"],
            metadata["total_rows"],
            float(metadata["affected_fraction"]) * 100.0,
            metadata["promo_rows"],
            metadata["markup_rows"],
            metadata["volume_change_pct"],
        )
        return target_sales_parquet, metadata
