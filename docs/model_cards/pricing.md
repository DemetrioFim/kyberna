# Model Card — Precificação Contextual & Drivers Linear SHAP (`V7-S1`)

## 1. Objetivo e Escopo
- **Módulos:** `src/ml/pricing_models.py`, `src/ml/pricing.py`
- **Saídas Gold:** `gold.mart_price_realization` (grão SKU) e `gold.mart_pricing_drivers` (formato longo para SHAP Waterfall por Família e Top SKUs)
- **Alvo:** Índice de Realização de Preço ($Y = \frac{\text{unit\_net\_price}}{\text{base\_unit\_price}} \times 100$)

## 2. Arquitetura do Modelo
- **Banda Contextual Justa ($[P_{25}, P_{75}]$):** `QuantileRegressor(solver="highs")` treinado por família nos quantis `0.25`, `0.50` e `0.75` sobre contrapartidas comerciais legítimas, com ordenação garantida $\hat{P}_{25} \le \hat{P} \le \hat{P}_{75}$.
- **Decomposição Aditiva (Linear SHAP Exato):** `Ridge(alpha=1.0)` sobre os mesmos 5 grupos de features estruturais, calculando contribuições $\phi_g = \sum_{k \in g} \beta_k (x_k - x_{k,\text{ref}})$ a partir de `base_idx = 100.0` (Porte P como âncora inicial) com fechamento exato:
  $$100.0 + \sum_{g=1}^{5} \phi_g = \text{expected\_idx} \quad (\text{tolerância} < 10^{-4}).$$

## 3. Features Normativas e Regra Anti-Camuflagem
1. **Porte do Cliente** (`P`, `M`, `G`)
2. **Volume do Pedido** ($\ln(1 + \text{boxes})$)
3. **Campanha & Sazonalidade** (`promo_flag`, `sin_week`, `cos_week`)
4. **Frete CIF & Prazo Porte** (`freight.yaml` por região + PMR base de `working_capital.yaml`)
5. **Posicionamento SKU** (efeito fixo centrado do SKU na família)

> **Regra Crítica:** `sales_rep_id` é **proibido** nas features do modelo normativo. Descontos discricionários sem contrapartida comercial caem abaixo de $\hat{P}_{25}$ e são expostos integralmente em `price_leakage_brl` e `unjustified_gap_pp`.
