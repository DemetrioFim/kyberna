# Model Card — Elasticidade-Preço da Demanda (`mart_price_elasticity`)

- **Identificador / Tarefa:** `M4-S3` (`DS-10`) · `src/ml/elasticity.py` + `src/ml/elasticity_models.py`
- **Camada de Saída:** `gold.mart_price_elasticity` e `data/gold/snapshot/<scenario_id>/mart_price_elasticity.parquet`
- **Contrato Pandera:** `GoldPriceElasticitySchema` (`src/etl/gold_contracts.py`)

## 1. Formulação Dual (Econometria Robusta + ML Monotônico)

1. **Preparação de Dados sem Viés de Porte:**
   - Preço relativo de lista: `price_ratio = unit_list_price / median_sku_price`, `ln_p = ln(price_ratio)` (evitando atenuação causada por descontos exógenos por porte em `unit_net_price`).
   - Volume ajustado por efeitos fixos aditivos de SKU e cliente: $\ln Q_{\text{adj}} = \ln(u) - \overline{\ln(u)}_{\text{SKU}} - \overline{\text{res}}_{\text{cliente}}$.
   - Controles sazonais harmônicos semanais (`sin_week`, `cos_week`).

2. **Abordagem 1 — Regressão Log-Log Robusta (`HuberRegressor`) + Bootstrap (`B=200`):**
   - Estima $\hat{\beta}$ sobre $\ln Q_{\text{adj}} \sim \ln P_{\text{rel}} + \sin(\omega) + \cos(\omega)$ com `HuberRegressor(max_iter=500)`. Em comparação com OLS pura e `Ridge(alpha=1.0)`, o estimador de Huber neutraliza pedidos atípicos de cauda pesada sem comprimir a inclinação em famílias menores com baixa variância de preço, mantendo $| \hat{\beta} - \beta_{\text{true}} | < 0.25$ em 100% das famílias do C1 e cobertura de `IC 95%` (via 200 reamostragens bootstrap determinísticas, `seed=42`) $\ge 80\%$.

3. **Abordagem 2 — `LGBMRegressor` Monotônico:**
   - Ajusta `LGBMRegressor(monotone_constraints=[-1, 0, 0], n_estimators=80, learning_rate=0.05, random_state=42)` sobre `(price_ratio, sin_week, cos_week) -> q_rel`, garantindo matematicamente que a curva de resposta de demanda seja estritamente não-crescente no preço ao longo da grade $[0.75, 1.30]$.

## 2. Otimização de Margem & Limitações Conhecidas

- **Variação Ótima de Preço (`optimal_price_change_pct`):** avaliada na grade $[-25\%, +25\%]$ maximizando a contribuição unitária esperada $\left((1 + \Delta p - c_{\text{ratio}})\cdot (1 + \Delta p)^{\hat{\beta}}\right)$ com base na razão média de CMV da família.
- **Limitações:** assume elasticidade constante em torno da faixa histórica observada ($\pm 20\%$) e não modela elasticidade cruzada entre SKUs concorrentes da mesma família.

