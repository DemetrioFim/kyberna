# KYBERNA — Decision Intelligence & Prescriptive Analytics

> Plataforma B2B de inteligência de decisão e análise prescritiva para PMEs e indústrias brasileiras.

---

## 🚀 Quickstart (PowerShell / Windows)

### 1. Pré-requisitos
- **Python 3.11+**
- **uv** (gerenciador de pacotes ultrarrápido)

Instalação do `uv` (caso ainda não possua):
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. Configurar o Ambiente Local
```powershell
# Sincroniza ambiente virtual e instala todas as dependências
uv sync --all-extras

# Copia as variáveis de ambiente de exemplo
Copy-Item .env.example .env
```

### 3. Execução e Verificação de Qualidade
```powershell
# Verificação de lint e formatação
uv run ruff check .
uv run ruff format --check .

# Verificação estática de tipos
uv run mypy src

# Executar suite de testes
uv run pytest -q

# Executar aplicação Streamlit localmente
uv run streamlit run src/ui/app.py
```

### 4. Linha de Comando (CLI)
```powershell
uv run kyberna --help
```

---

## 🏛️ Documentação de Referência
- [`VISION.md`](./VISION.md): Visão de produto, cenários de negócio e regras prescritivas.
- [`GEMINI.md`](./GEMINI.md) / [`CLAUDE.md`](./CLAUDE.md): Arquitetura de dados, stack e padrões técnicos.
- [`TASKS.md`](./TASKS.md): Backlog e critérios de aceite (DoD) de cada entrega.

