# KYBERNA — Decision Intelligence & Prescriptive Analytics

> **Kyberna** (do grego *κυβερνάω — kybernáō*: governar, conduzir o leme).
> Plataforma B2B de inteligência de decisão e análise prescritiva para PMEs e indústrias brasileiras.

---

## 🎯 Arquitetura & Stack Enxuta

- **Processamento & ETL Auditável:** **DuckDB (SQL)** para limpeza Bronze → Silver, âncora temporal, remapeamento multi-cenário e cálculo do Waterfall de Margem de Contribuição + **Pandas 2.x (`pyarrow`)** para geração sintética (`Faker pt_BR`), extração de features, ML e serviços.
- **Catálogo Local & Conciliação:** Todas as camadas (`bronze`, `silver`, `gold`) ficam registradas em `data/kyberna.duckdb` (inspecionável via **DBeaver** ou `duckdb data/kyberna.duckdb -ui`) e a CLI `kyberna audit` gera a planilha `data/reports/conciliacao_<cenario>.xlsx` com a memória de cálculo aberta pedido a pedido.
- **Ciência de Dados & Prescrição:** Matriz ABC/XYZ, RFM por margem, Ciclo de Recompra e Churn (`LightGBM` + heurística empírica), Matriz White Space (cross-sell), Eficiência de RCAs, Previsão 30 dias (`StatsForecast`) e Elasticidade-Preço / Simulador What-If.
- **Serving & Front-end:** **Azure SQL Database Free Tier** com fallback automático para **DuckDB + Parquet local**, servindo o DataApp **Streamlit + Plotly** containerizado no **Azure Container Apps** (`scale-to-zero`).

---

## 🚀 Quickstart (PowerShell / Windows)

### 1. Pré-requisitos
- **Python 3.11+**
- **uv** (gerenciador de pacotes e ambientes)

Instalação do `uv` (caso ainda não possua):
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. Configurar o Ambiente Local
```powershell
# Sincroniza ambiente virtual (.venv) e instala todas as dependências
uv sync --all-extras

# Copia as variáveis de ambiente de exemplo
Copy-Item .env.example .env
```

### 3. Pipeline, Auditoria Pessoal e Aplicação
```powershell
# Consultar comandos da CLI Kyberna
uv run kyberna --help

# Executar pipeline completo (amostra rápida com fixture ou base completa)
uv run kyberna pipeline run --sample
uv run kyberna pipeline run --scenario all

# Gerar planilha Excel de conciliação financeira (DRE + memória de cálculo)
uv run kyberna audit --scenario c1_toys

# Inspecionar tabelas Bronze/Silver/Gold no navegador via DuckDB UI
duckdb data/kyberna.duckdb -ui

# Subir aplicação Streamlit localmente
uv run streamlit run src/ui/app.py
```

### 4. Qualidade de Código e Testes
```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -q
```

---

## 🧭 Organização do Desenvolvimento (Marcos `M1` a `M7`)

O desenvolvimento segue **Marcos Verticais (`M1`..`M7`)**, onde cada marco entrega uma fatia funcional completa e validada entre os **4 Pilares Integrados**:
- 🏗️ **Infraestrutura & Arquitetura (`I`)**
- 🗄️ **Engenharia de Dados & Finanças (`D`)**
- 🧠 **Ciência de Dados & Prescrição (`S`)**
- 🎨 **Interface, UX & Visualização (`V`)**

---

## 🏛️ Documentação Central
- [`VISION.md`](./VISION.md): Visão estratégica do produto, os 4 cenários de negócio, fórmulas canônicas e especificação das 4 telas.
- [`TASKS.md`](./TASKS.md): Quadro de marcos (`M1` a `M7`), tarefas por pilar, critérios de pronto (DoD) e Changelog.
- [`GEMINI.md`](./GEMINI.md) / [`CLAUDE.md`](./CLAUDE.md): Regras de arquitetura, padrões de código e protocolo obrigatório de execução.
