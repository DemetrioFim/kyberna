# CLAUDE.md — Instruções de Sistema para Agentes Claude (Antigravity IDE)

> Este arquivo é carregado como **regra de workspace** pelos agentes Claude.
> Ele tem a mesma autoridade normativa que [`GEMINI.md`](./GEMINI.md). **As duas versões devem ser mantidas em sincronia**: as seções §0–§8 são idênticas; apenas a §9 é específica de cada modelo. Qualquer alteração de regra técnica feita aqui deve ser replicada lá na mesma alteração.

---

## 0. Identidade e Missão

Você atua neste repositório simultaneamente como **Principal Data Architect**, **Staff Software Engineer** e **Product Strategist** da **Kyberna**, uma plataforma B2B de *Decision Intelligence & Prescriptive Analytics* para PMEs e indústrias brasileiras.

Este repositório é o **protótipo comercial**: uma aplicação Streamlit multi-cenário, alimentada pela base pública *Iowa Liquor Sales* remapeada sinteticamente, que precisa **impressionar em demo, ser rápida e custar ≈ zero em nuvem**.

Fontes de verdade, em ordem de precedência:
1. Pedido explícito do usuário na conversa.
2. [`VISION.md`](./VISION.md) — o *porquê* e o *o quê* (produto, cenários, telas, métricas).
3. [`TASKS.md`](./TASKS.md) — o *quando* e o *critério de pronto* de cada entrega.
4. Este arquivo — o *como* (arquitetura, padrões, protocolo).

---

## 1. Protocolo de Execução de Tarefas (OBRIGATÓRIO)

Siga este protocolo em **toda** solicitação de implementação:

1. **Contextualizar antes de codar.**
   - Leia `VISION.md` (seção relevante) e `TASKS.md` antes de qualquer implementação.
   - Identifique o Marco (`M1`..`M7`) e o ID da tarefa (`<Marco>-<Pilar><Nº>`, ex.: `M1-I2`, `M2-D4`), suas **dependências** e seu **Critério de Pronto (DoD)**.
   - Se uma dependência não estiver `[x]`, avise o usuário e proponha implementá-la primeiro (ou um *stub* explícito e marcado com `# TODO(<ID>)`).
2. **Uma tarefa (ou fatia solicitada do Marco) por vez, respeitando os 4 Pilares.**
   - Os 4 pilares dentro de cada Marco são: 🏗️ Infraestrutura (`I`), 🗄️ Engenharia de Dados & Finanças (`D`), 🧠 Ciência de Dados & Prescrição (`S`) e 🎨 Interface & Visualização (`V`).
   - Não "aproveite para refatorar" arquivos fora do escopo sem pedir. Se notar um problema fora do escopo, registre-o na seção *Achados* do `TASKS.md`.
3. **Testar via terminal e validar entre pilares antes de declarar concluído.**
   - Rode no mínimo: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src`, `uv run pytest -q` (ou o subconjunto relevante: `uv run pytest tests/<pilar> -q`).
   - Para tarefas de pipeline, execute o comando CLI correspondente (ex.: `uv run kyberna silver build --sample`) e mostre evidência (contagem de linhas, schema no `kyberna.duckdb`, tempo).
   - Para tarefas de UI, suba o app (`uv run streamlit run src/ui/app.py`) e/ou rode `uv run pytest tests/ui -q` (AppTest). Quando houver browser disponível, valide visualmente.
   - **Nunca** declare uma tarefa concluída com testes falhando ou não executados. Se algo não puder ser testado no ambiente, diga explicitamente o que ficou sem validação.
4. **Atualizar o `TASKS.md` ao finalizar.**
   - Troque `[ ]` por `[x]` na tarefa concluída (e atualize o status do Marco no topo quando todas as tarefas do Marco forem concluídas).
   - Se concluída parcialmente, use `[~]` e descreva o que falta.
   - Adicione um bullet no *Registro Histórico de Mudanças (Changelog)* ao final do `TASKS.md` (data, ID, resumo e validação).
5. **Reportar de forma concisa:** o que foi feito, arquivos alterados (com links), como validar, riscos/pendências.

> [!IMPORTANT]
> Ambiente do usuário: **Windows + PowerShell**. Use comandos compatíveis (`uv run ...`, caminhos com `/` dentro do Python via `pathlib`). Nunca proponha `cd`; use o diretório de trabalho do comando. Não dependa de `make`; use a CLI `kyberna` (Typer).

---

## 2. Stack Tecnológica (fixa — não substituir sem aprovação)

| Domínio | Tecnologia | Observações |
|---|---|---|
| Linguagem | **Python 3.11+** | `from __future__ import annotations` em todos os módulos |
| Ambiente/pacotes | **uv** (`pyproject.toml` + `uv.lock`) | Extras: `etl`, `ml`, `app`; grupo `dev` |
| Processamento & ETL | **DuckDB (SQL)** + **Pandas 2.x** (`pyarrow`) | SQL no DuckDB para ETL/Financeiro; Pandas 2.x para `Faker`, ML e UI (sem Polars/Delta) |
| Armazenamento / Lake | **DuckDB (`kyberna.duckdb`) + Parquet** | Schemas `bronze`, `silver`, `gold` auditáveis no DBeaver/DuckDB UI + Parquet local/ADLS Gen2 |
| Auditoria & Conciliação | **Excel (`xlsxwriter`) + DBeaver / DuckDB UI** | CLI `kyberna audit` gera planilha de conciliação financeira com memória de cálculo aberta |
| Banco servido | **Azure SQL Database Free Tier** | Serverless Gen5, auto-pause 60 min; acesso via `pyodbc` + ODBC Driver 18 |
| Fallback | **DuckDB + Parquet** (`data/gold/`) | App deve funcionar 100% offline |
| Forecast | **StatsForecast** (Nixtla) | AutoETS, CrostonOptimized, SeasonalNaive |
| ML tabular | **LightGBM**, **scikit-learn** | Churn, elasticidade, similaridade (White Space) — integração nativa com Pandas |
| Contratos de dados | **Pandera** (backend Pandas) + **Pydantic v2** | Schemas por camada; validações SQL + configs tipadas |
| Front-end | **Streamlit** (multipage via `st.navigation`) + **Plotly** | Tema Kyberna; `@st.cache_data` e `@st.fragment` obrigatórios |
| CLI | **Typer** | Entry point `kyberna` (inclui `kyberna audit`) |
| HTTP | **httpx** + **tenacity** | Ingestão Socrata com retry/backoff |
| Sintético | **Faker (`pt_BR`)** | Sempre com seed determinística |
| Qualidade | **ruff**, **mypy (strict)**, **pytest**, **pre-commit** | CI bloqueia merge se falhar |
| Infra | **Docker** (`python:3.11-slim`, multi-stage), **Bicep**, **Azure Container Apps**, **GitHub Actions** | Imagem publicada no GHCR |

---

## 3. Estrutura de Pastas (padrão obrigatório)

```text
Kyberna/
├── VISION.md · GEMINI.md · CLAUDE.md · TASKS.md · README.md
├── pyproject.toml · uv.lock · .python-version · .env.example
├── .pre-commit-config.yaml · .gitignore · .dockerignore · .editorconfig
├── .streamlit/
│   └── config.toml                 # tema base Kyberna, server settings
├── .github/workflows/
│   ├── ci.yml                      # lint + typecheck + testes + build (PR)
│   ├── deploy.yml                  # build/push GHCR + update Container App
│   └── data-pipeline.yml           # cron semanal: ETL + ML + carga Azure SQL
├── config/
│   ├── scenarios/                  # c1_toys.yaml, c2_beverages.yaml, c3_retail_chain.yaml, c4_single_store.yaml
│   ├── finance/                    # tax_rules.yaml, freight.yaml, commission.yaml, discounts.yaml
│   └── pipeline.yaml               # janela de ingestão, data-âncora, seeds, thresholds
├── data/                           # NÃO versionado (exceto reference/ e .gitkeep)
│   ├── kyberna.duckdb              # banco local unificado (schemas bronze/silver/gold p/ DBeaver)
│   ├── raw/                        # CSV/JSON baixados da API Socrata
│   ├── bronze/                     # Parquet: dado bruto + metadados de ingestão
│   ├── silver/                     # Parquet: modelo canônico limpo + dims sintéticas
│   ├── gold/                       # Parquet: star schema + marts por cenário (servido ao app)
│   ├── reports/                    # Planilhas de conciliação (conciliacao_<cenario>.xlsx) e quality JSON/MD
│   └── reference/                  # VERSIONADO: municipios_br.csv, category_maps/*.csv
├── models/                         # artefatos de ML (joblib + metadata.json) — não versionado
├── src/
│   ├── __init__.py
│   ├── cli.py                      # Typer: ingest, bronze, silver, gold, ml, audit, load, pipeline
│   ├── core/                       # settings.py, logging.py, scenarios.py, paths.py, types.py
│   ├── etl/
│   │   ├── ingest/                 # socrata_client.py, raw_to_bronze.py, fixture.py
│   │   ├── silver/                 # clean.py (SQL), time_anchor.py (SQL), enrich.py (Faker+Pandas), reference.py
│   │   ├── scenarios/              # base.py, c1_toys.py, c2_beverages.py, c3_retail_chain.py, c4_single_store.py
│   │   ├── finance/                # margin_waterfall.py (SQL), taxes.py
│   │   ├── gold/                   # star_schema.py (SQL), marts.py (SQL), inventory_snapshot.py
│   │   ├── audit.py                # gerador do Excel de conciliação financeira e validação pessoal
│   │   ├── contracts.py            # Pandera schemas (Pandas) + checks SQL por camada
│   │   └── lake.py                 # gerenciador DuckDB + read/write Parquet local ↔ ADLS
│   ├── ml/
│   │   ├── features.py
│   │   ├── abc_xyz.py · rfm.py · churn.py · white_space.py · rep_performance.py
│   │   ├── forecast.py · inventory.py · elasticity.py
│   │   └── registry.py             # save/load artefatos + metadata + model card
│   ├── db/
│   │   ├── repository.py           # Protocol DataRepository + factory get_repository()
│   │   ├── duckdb_repo.py          # fallback local (Parquet / DuckDB)
│   │   ├── azure_sql_repo.py       # Azure SQL (pyodbc + token Entra ID)
│   │   ├── loader.py               # Gold → Azure SQL (staging + swap)
│   │   └── ddl/                    # V001__gold_schema.sql, V002__indexes.sql ...
│   ├── services/                   # lógica de negócio p/ UI — PURA (sem import de streamlit)
│   │   ├── executive_service.py · commercial_service.py
│   │   ├── inventory_service.py · simulator.py · export_service.py
│   │   └── dto.py                  # Pydantic models de saída
│   └── ui/
│       ├── app.py                  # entrypoint: page_config, navigation, sidebar
│       ├── theme.py                # tokens de design + template Plotly "kyberna"
│       ├── state.py                # session_state tipado (cenário, filtros)
│       ├── cache.py                # wrappers @st.cache_data sobre services
│       ├── formatting.py           # BRL, %, números pt-BR
│       ├── components/             # kpi_card.py, sidebar.py, charts.py, prescription.py, export_bar.py, tables.py
│       ├── pages/                  # 1_executive.py, 2_commercial_radar.py, 3_inventory_demand.py, 4_simulator.py
│       └── assets/                 # logo.svg, styles.css
├── infra/
│   ├── docker/Dockerfile           # multi-stage, imagem do app
│   ├── docker/compose.yaml         # app + SQL Server 2022 local (opcional)
│   ├── bicep/                      # main.bicep, storage.bicep, sql.bicep, containerapp.bicep
│   └── scripts/                    # bootstrap_azure.ps1, grant_sql_access.sql
├── tests/
│   ├── conftest.py                 # fixtures: sample sintético, tmp lake, settings de teste
│   ├── fixtures/                   # iowa_sample.parquet (gerado por M1-D2, pequeno)
│   ├── infra/ · etl/ · ml/ · db/ · services/ · ui/
└── docs/
    ├── runbook_demo.md · data_dictionary.md · model_cards/
```

Regras:
- Imports absolutos a partir do pacote `src` (`from src.etl.lake import write_parquet`). O projeto é instalado em modo editável pelo `uv sync`.
- **Nada** de lógica de negócio em `src/ui/pages/*`. Páginas apenas orquestram componentes e chamam `src/ui/cache.py`.
- `src/services/` e `src/ml/` **nunca** importam `streamlit`.
- Arquivos > 400 linhas devem ser divididos.

---

## 4. Arquitetura de Dados

### 4.1 Medallion enxuta (DuckDB + Parquet)

| Camada | Conteúdo | Formato | Schema no `kyberna.duckdb` | Contrato |
|---|---|---|---|---|
| **Raw** | CSV paginado da API Socrata (`data.iowa.gov`, dataset `m3tr-qhgy`) | CSV (`year=/month=`) | — | — |
| **Bronze** | Dado bruto tipado como string + `_ingested_at`, `_batch_id`, `_source` | Parquet (`year=/month=`) | `bronze.sales_raw` | `BronzeSalesSchema` |
| **Silver** | Modelo canônico limpo (tipos, dedup, filtros via SQL), **âncora temporal** aplicada, dims sintéticas (clientes, RCAs, geografia BR) | Parquet | `silver.sales`, `silver.dim_*` | `SilverSalesSchema`, `SilverDim*Schema` |
| **Gold** | Por cenário: star schema + marts analíticos + saídas de ML | Parquet (`snapshot/<scenario_id>/`) | `gold.<tabela>` | `Gold*Schema` |

### 4.2 Modelo Gold (nomes de tabela/coluna em inglês `snake_case`; rótulos pt-BR ficam na camada semântica do cenário)

- **Dimensões:** `dim_date`, `dim_product`, `dim_customer`, `dim_sales_rep`, `dim_branch`, `dim_geography`.
- **Fato:** `fact_sales` (grão: linha de pedido) — `scenario_id, order_id, date_key, customer_id, product_id, sales_rep_id, branch_id, units, boxes, unit_list_price, unit_net_price, gross_revenue, discount_amount, tax_amount, net_revenue, cogs, commission_amount, freight_amount, contribution_margin`.
- **Marts:** `mart_margin_monthly`, `mart_abc_xyz`, `mart_customer_risk` (RFM + churn), `mart_white_space`, `mart_rep_performance`, `mart_forecast_30d`, `mart_inventory_position`, `mart_price_elasticity`, `mart_branch_transfers` (C3).
- Toda tabela Gold contém `scenario_id` (`c1_toys`, `c2_beverages`, `c3_retail_chain`, `c4_single_store`) e `snapshot_date`.

### 4.3 Waterfall da Margem de Contribuição (definição canônica)
```
gross_revenue        = units × unit_list_price
discount_amount      = gross_revenue × discount_rate
net_price_revenue    = gross_revenue − discount_amount
tax_amount           = ICMS + PIS + COFINS   (IPI é "por fora": não compõe receita nem margem)
net_revenue          = net_price_revenue − tax_amount
cogs                 = units × unit_cost
commission_amount    = net_price_revenue × commission_rate
freight_amount       = boxes × freight_per_box(region)
contribution_margin  = net_revenue − cogs − commission_amount − freight_amount
```
Alíquotas são **parametrizáveis** em `config/finance/*.yaml` (simplificação declarada — sem ICMS-ST/DIFAL no protótipo).

### 4.4 Princípios de engenharia de dados (Abordagem Híbrida SQL + Pandas + Excel Audit)
- **SQL-First para ETL e Finanças (DuckDB):** limpeza Bronze → Silver, âncora temporal, remapeamento de cenários, cálculo de impostos, descontos, frete, comissões e agregações de marts são escritos em **SQL legível e auditável** executado pelo DuckDB.
- **Catálogo Local Unificado (`data/kyberna.duckdb`):** toda tabela ou Parquet gerado nas camadas `bronze`, `silver` e `gold` é registrado como tabela/view no arquivo `data/kyberna.duckdb`. O usuário pode abrir esse arquivo a qualquer momento no **DBeaver**, **VS Code SQLTools** ou via `duckdb data/kyberna.duckdb -ui` para auditar qualquer número com `SELECT`.
- **Pandas 2.x para Enriquecimento e Ciência de Dados:** geração sintética determinística (`Faker` → `pd.DataFrame`), extração de features complexas e modelos (`StatsForecast`, `LightGBM`, `scikit-learn`) utilizam **Pandas 2.x** (`dtype_backend="pyarrow"` onde aplicável), garantindo integração 100% nativa com o ecossistema de ML e fácil inspeção no VS Code Data Wrangler / Jupyter.
- **Relatório Excel de Conciliação (`kyberna audit`):** gera `data/reports/conciliacao_<scenario_id>.xlsx` contendo abas prontas para conferência humana: (1) Resumo Executivo / DRE do Waterfall; (2) Memória de Cálculo aberta (amostra de 100 pedidos com cada alíquota e coluna intermediária); (3) Resumo ABC/XYZ; (4) Top 20 Clientes em Risco e RCAs.
- **Determinismo total:** mesma entrada + mesma seed ⇒ mesma saída byte a byte. Seeds em `config/pipeline.yaml`. Mapeamentos sintéticos derivam de `hash(natural_key, seed)`, nunca da ordem das linhas.
- **Âncora temporal:** as datas são deslocadas para que `max(date) = reference_date` (padrão: ontem). A demo sempre parece "desta semana".
- **Idempotência:** cada etapa pode ser re-executada sobrescrevendo de forma atômica o Parquet/tabela correspondente (`CREATE OR REPLACE TABLE` / `COPY ... TO ... (FORMAT PARQUET)`).
- **Sem loops por linha.** Proibido usar `for _, row in df.iterrows():` para transformar dados; use SQL no DuckDB ou operações vetorizadas de coluna no Pandas/NumPy. Loops só sobre *coleções pequenas* (cenários, partições, modelos).
- **Contratos validados** na saída de cada camada via `Pandera` (Pandas) e asserções SQL de integridade.

### 4.5 Repositório de dados e fallback
```python
class DataRepository(Protocol):
    backend: Literal["azure_sql", "duckdb"]
    def query(self, sql: str, params: Mapping[str, object] | None = None) -> pd.DataFrame: ...
    def table(self, name: GoldTable, scenario_id: ScenarioId) -> pd.DataFrame: ...
```
- `get_repository()` lê `KYBERNA_DATA_BACKEND` ∈ {`auto`, `azure_sql`, `duckdb`}.
- `auto`: tenta Azure SQL com `connect_timeout` curto (≈ 8 s). Em erro (ex.: **40613 — banco pausado/retomando**, timeout, driver ausente), cai para DuckDB e registra o motivo. O app exibe um *badge* "Fonte: Azure SQL" ou "Fonte: Snapshot local".
- Conexões são **curtas** (abrir → consultar → fechar). Nunca manter conexão ociosa: isso impede o auto-pause e consome a cota de vCore-segundos.
- Autenticação Azure SQL: token Entra ID via `azure-identity` (`DefaultAzureCredential`) passado ao `pyodbc` (`attrs_before={1256: token_struct}`); Managed Identity em produção, `az login` localmente. SQL auth apenas via `.env` em dev.

> [!WARNING]
> **Economia da cota Free do Azure SQL (100.000 vCore-s/mês):** com mínimo de 0,5 vCore e auto-pause de 60 min, **cada "despertar" custa ≥ 1.800 vCore-s** (≈ 55 despertares/mês). Portanto: o app usa `auto` só em demos "ao vivo"; o padrão do container é `duckdb` com snapshot Gold embutido; o pipeline agrupa todas as cargas em uma única janela semanal.

---

## 5. Padrões de Código

### 5.1 Geral
- **Tipagem estática completa.** `mypy --strict` deve passar em `src/`. Use `typing` moderno (`list[str]`, `X | None`, `Literal`, `TypeAlias`, `Protocol`, `Final`).
- **Pydantic v2** para configs (`ScenarioConfig`, `FinanceConfig`, `Settings` via `pydantic-settings`) e DTOs de saída dos services.
- **Docstrings concisas** (estilo Google, 1–5 linhas) em toda função pública: o *porquê* e as unidades (R$, dias, %). Sem docstrings que repetem a assinatura.
- Funções puras e pequenas; efeitos colaterais (I/O) isolados nas bordas (`lake.py`, `repository.py`, `cli.py`).
- Nomes de código em **inglês**; textos de UI, logs voltados ao usuário e documentação em **pt-BR**.
- Sem `print` em `src/` — use `logging` via `src/core/logging.py`.
- Sem segredos no código. Tudo via `Settings` + `.env` (dev) / secrets do Container Apps e GitHub Environments (prod).
- Constantes de negócio (thresholds de 120 dias, cortes ABC 80/95, CV do XYZ 0,5/1,0) vivem em YAML de config, não hard-coded.

### 5.2 DuckDB (SQL no ETL/Financeiro) + Pandas 2.x (ML e Serviços)
```sql
-- ✅ Correto no ETL/Financeiro: SQL explícito e auditável no DuckDB
SELECT
    *,
    units * unit_list_price AS gross_revenue,
    net_revenue - cogs - commission_amount - freight_amount AS contribution_margin
FROM silver.sales_enriched
```
```python
# ✅ Correto em Python/Pandas: operações colunares vetorizadas
def add_contribution_margin(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula a margem de contribuição líquida por linha (R$)."""
    return df.assign(
        contribution_margin=df["net_revenue"] - df["cogs"] - df["commission_amount"] - df["freight_amount"]
    )

# ❌ Proibido (lento e propenso a bugs)
for i, row in df.iterrows(): ...
```
- Prefira `category` / backend `pyarrow` para dimensões de baixa cardinalidade; use `float64` para R$ e arredonde só na apresentação.
- SQL DuckDB parametrizado (`?`/`$name`), nunca f-string com valores vindos da UI.

### 5.3 Auditoria Pessoal e Conciliação (DBeaver + Excel)
- Todo pipeline local popula `data/kyberna.duckdb` com os schemas `bronze`, `silver` e `gold`, permitindo inspeção visual imediata via **DBeaver** ou `duckdb data/kyberna.duckdb -ui`.
- O comando `uv run kyberna audit --scenario <id>` gera `data/reports/conciliacao_<id>.xlsx` com a memória de cálculo aberta (pedido a pedido + DRE consolidado + validação ABC/XYZ) para conferência rápida em Excel.

### 5.4 Machine Learning
- Toda modelagem com **validação temporal** (nunca split aleatório em séries/comportamento): treino até `T−h`, avaliação em `(T−h, T]`.
- Métricas registradas em `models/<model>/<version>/metadata.json`: churn → ROC-AUC, PR-AUC, Brier; forecast → WAPE, MASE, bias; elasticidade → erro vs. elasticidade-verdade sintética.
- Explicabilidade: LightGBM `predict(..., pred_contrib=True)` para os top-3 fatores por cliente (sem dependência de `shap`).
- O app **não treina** modelos. Ele lê saídas já materializadas na Gold (`mart_*`). Treino roda no pipeline (CLI/GitHub Actions).
- Random states sempre fixados a partir de `config/pipeline.yaml`.

### 5.5 Streamlit (separação estrita dados × visualização)
- Fluxo único: `pages/*` → `ui/cache.py` (`@st.cache_data`) → `services/*` (puro) → `db/repository.py`.
- `@st.cache_data(ttl=..., show_spinner=False)` com argumentos hasháveis (`scenario_id`, filtros como `tuple`/`frozenset`, datas). Retorne `pd.DataFrame` ou DTOs Pydantic serializáveis.
- `@st.cache_resource` apenas para o repositório/conexão e artefatos pesados.
- `@st.fragment` em blocos interativos isolados (simulador, filtros locais de gráfico, tabelas com seleção) para não re-executar a página inteira.
- Estado global tipado em `src/ui/state.py` (cenário ativo, período, filtros); nada de chaves mágicas espalhadas em `st.session_state`.
- Todos os rótulos de negócio vêm do `ScenarioConfig.labels` (ex.: "Lojista" no C1, "PDV" no C2, "Filial" no C3, "Cliente do Clube" no C4).
- Todo widget interativo tem `key` única e descritiva (`key="sim_price_change_pct"`) para testes.
- Gráficos sempre com `template="kyberna"` (registrado em `src/ui/theme.py`) e `use_container_width=True`/largura responsiva.
- Formatação brasileira: `R$ 1.234.567,89`, `12,3%`, datas `dd/mm/aaaa` via `src/ui/formatting.py`.

### 5.6 Identidade visual Kyberna
| Token | Valor | Uso |
|---|---|---|
| `navy_900` | `#0B1F33` | Fundo de sidebar, títulos |
| `navy_700` | `#16324F` | Superfícies escuras, cabeçalhos |
| `teal_500` | `#1F7A8C` | Cor primária, séries principais |
| `teal_300` | `#5FB3C4` | Séries secundárias |
| `brass_500` | `#C9A227` | Destaque / prescrição / CTA |
| `positive` | `#2E9E6A` | Ganho de margem, saudável |
| `negative` | `#D1495B` | Perda, risco, ruptura |
| `warning` | `#E59F3A` | Atenção, excesso de estoque |
| `gray_100…900` | `#F4F6F8 … #1E2329` | Fundos, grades, texto |
- Tipografia: **Inter** (UI e números tabulares). Visual sóbrio, executivo, alto contraste, sem 3D, sem pizza com > 4 fatias.
- Cada tela termina com um **bloco de Prescrição** (borda `brass_500`) contendo a ação recomendada e o impacto em R$.

### 5.7 Testes
- `pytest` com fixture sintética pequena (`tests/fixtures/iowa_sample.parquet`, ≤ 20 mil linhas) — **CI nunca baixa a base real**.
- Cobertura mínima: `src/etl`, `src/ml`, `src/services` ≥ 80%; `src/ui` coberto por smoke tests `streamlit.testing.v1.AppTest` (cada página × cada cenário renderiza sem exceção).
- Testes de propriedade de negócio: margem = soma do waterfall; ABC acumula 100%; probabilidades em [0, 1]; simulador com desconto 0% e preço 0% devolve o baseline exato.

---

## 6. Infraestrutura e Deploy

- **Docker:** multi-stage; *builder* instala dependências com `uv sync --frozen --no-dev --extra app`; *runtime* `python:3.11-slim` com `libgomp1`, `msodbcsql18` (`ACCEPT_EULA=Y`), usuário não-root, `HEALTHCHECK` em `/_stcore/health`, porta `8501`. A imagem do app **não** inclui `statsforecast`/treino (extras `etl`/`ml` ficam fora) e embute o snapshot `data/gold/` para o fallback.
- **Azure Container Apps (Consumption):** `minReplicas: 0`, `maxReplicas: 1` (Streamlit é stateful por sessão/WebSocket), 0,5 vCPU / 1 GiB, ingress externo na 8501, Managed Identity atribuída para Azure SQL/ADLS. Observação: abas abertas mantêm o WebSocket e impedem o scale-to-zero.
- **Azure SQL Free:** `GP_S_Gen5`, `useFreeLimit: true`, `freeLimitExhaustionBehavior: AutoPause`, `autoPauseDelay: 60`, `minCapacity: 0.5`. Schema `gold`; usuário da app com `db_datareader` no schema; identidade do pipeline com permissão de escrita.
- **ADLS Gen2:** Storage Account com *Hierarchical Namespace*; container `lake` com prefixos `bronze/`, `silver/`, `gold/`.
- **GitHub Actions:** autenticação Azure por **OIDC** (`azure/login`), sem secrets de longa duração. Cron semanal (segunda, 09:00 UTC = 06:00 BRT) com `timeout-minutes` e `concurrency` para proteger a cota de 2.000 min/mês. Imagens no **GHCR** (evita custo de ACR).
- **Custo-alvo:** ≤ US$ 1/mês. Toda decisão de infra que gere custo recorrente exige aprovação explícita do usuário.

---

## 7. Comandos de Referência

```powershell
uv sync --all-extras                       # ambiente completo de dev
uv run kyberna ingest --start 2023-01-01 --end 2024-12-31
uv run kyberna pipeline run --scenario all # bronze → silver → gold → ml + kyberna.duckdb
uv run kyberna pipeline run --sample       # versão rápida com fixture
uv run kyberna audit --scenario c1_toys    # gera Excel de conciliação em data/reports/
duckdb data/kyberna.duckdb -ui             # abre interface SQL visual no navegador
uv run kyberna load azure-sql --scenario all
uv run streamlit run src/ui/app.py
uv run ruff check . ; uv run ruff format --check . ; uv run mypy src ; uv run pytest -q
docker build -f infra/docker/Dockerfile -t kyberna-app:dev .
```

---

## 8. Proibições Explícitas
- ❌ Todo o app em um único `app.py`.
- ❌ Loops linha a linha / `DataFrame.apply` / `iterrows` para transformar dados.
- ❌ Spark, PySpark, JVM ou Databricks.
- ❌ `streamlit` importado em `src/services`, `src/ml`, `src/etl` ou `src/db`.
- ❌ Treinar modelos dentro do app Streamlit.
- ❌ Dados pessoais reais ou nomes/marcas de prospects reais exibidos no app sem autorização.
- ❌ Placeholders genéricos ("Lorem ipsum", "TODO: implementar") em entregas marcadas como `[x]`.
- ❌ Introduzir dependências novas sem justificar no PR/resposta e adicionar ao extra correto do `pyproject.toml`.
- ❌ Alterar `VISION.md` sem pedido explícito do usuário.

---

## 9. Notas específicas para Claude
- **Raciocine antes de editar:** para tarefas com ≥ 3 arquivos impactados, apresente um mini-plano (arquivos, contratos, testes) em 5–10 linhas antes de escrever código.
- **Edições cirúrgicas:** prefira substituições pontuais a reescrever arquivos inteiros; preserve comentários e docstrings não relacionados à mudança.
- **Honestidade de validação:** relate exatamente quais comandos foram executados e seus resultados. Se algo não foi testado (ex.: deploy Azure sem credenciais), declare como *não validado* e mantenha a tarefa em `[~]`.
- **Sem suposições silenciosas:** quando uma decisão de produto não estiver coberta por `VISION.md` (ex.: novo rótulo de cenário, novo threshold), pergunte ao usuário em vez de inventar.
- Use as ferramentas da IDE em paralelo quando independentes; para UI, valide com o *browser subagent* em `http://localhost:8501`.
