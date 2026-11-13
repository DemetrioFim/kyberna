# Model Card — Previsão de Demanda 30 Dias (`mart_forecast_30d`)

- **Identificador / Tarefa:** `M4-S1` (`DS-08`) · `src/ml/forecast.py`
- **Camada de Saída:** `gold.mart_forecast_30d` e `data/gold/snapshot/<scenario_id>/mart_forecast_30d.parquet`
- **Contrato Pandera:** `GoldForecast30dSchema` (`src/etl/gold_contracts.py`)

## 1. Arquitetura e Roteamento por Série

Para lidar simultaneamente com séries contínuas e demanda intermitente B2B sem penalizar o tempo de execução no Windows (`n_jobs=1`), o motor preenche os zeros diários nos **180 dias** anteriores a `as_of_date` e roteia cada SKU pelo seu intervalo médio entre demandas (**ADI** = `n_days / n_nonzero_days`) e densidade histórica:

1. **Séries Curtas ou Muito Esparsas (`< 60` dias ou `< 5` dias não-nulos):** `MovingAverage28d` (média diária dos últimos 28 dias com bandas gaussianas truncadas em zero).
2. **Séries Intermitentes (`ADI > 1,32` e `>= 5` dias não-nulos):** competição entre `CrostonOptimized` e `SeasonalNaive(season_length=7)`.
3. **Séries Regulares (`ADI <= 1,32` e `>= 5` dias não-nulos):** competição entre `AutoETS(season_length=7)` e `SeasonalNaive(season_length=7)`.

## 2. Seleção de Modelo e Incerteza

- **Holdout Temporal (Zero Data Leakage):** últimos `28` dias antes de `as_of_date` avaliados pelo erro médio de horizonte (`|sum(y_actual) - sum(y_hat)| / 28`) por SKU contra `SeasonalNaive(7)`, evitando o viés de séries intermitentes em que prever zeros diários recompensa artificialmente o MAE ponto a ponto.
- **Métrica de Família (`family_wape_pct`):** WAPE agregado por família no holdout comparando volume total previsto vs. volume realizado na janela de 28 dias.
- **Intervalos de Confiança (80% e 95%):** `ConformalIntervals(h=30, n_windows=2)` quando o histórico comporta 2 janelas conformais; fallback analítico baseado em desvio padrão histórico para séries esparsas/constantes.
- **Invariantes Garantidas:** `lo_95 >= 0` e `lo_95 <= lo_80 <= forecast_units <= hi_80 <= hi_95`.

## 3. Limitações Conhecidas

- Não incorpora variáveis exógenas de calendário promocional futuro (tratadas no simulador e elasticidade em `M4-S3` / `M4-S4`).
- SKUs recém-cadastrados sem vendas nos últimos 180 dias recebem projeção zerada via `MovingAverage28d`.
