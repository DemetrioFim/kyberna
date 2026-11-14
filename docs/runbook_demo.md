# Runbook de Demonstração Executiva — Virtus (by Kyberna)

> **Duração alvo:** 15 minutos ("O Efeito Virtus", conforme `VISION.md` §7.1).  
> **Cenário Âncora:** `C1 — Indústria de Brinquedos` (base pública *Iowa Liquor Sales* remapeada sinteticamente para operação B2B brasileira — **nenhum dado confidencial real é utilizado**).

---

## 1. Checklist Pré-Demo (5 minutos antes da reunião)

1. **Garantir snapshot Gold e planilha de auditoria atualizados:**
   ```powershell
   uv run kyberna pipeline run --sample
   ```
   - Verifique se foram gerados `data/reports/conciliacao_c1_toys.xlsx` e `data/reports/quality_<YYYYMMDD>.md`.
2. **Definir o modo de acesso:**
   - **Apresentação local na própria máquina:**
     ```powershell
     $env:KYBERNA_AUTH_MODE = "none"
     uv run streamlit run src/ui/app.py
     ```
   - **Link externo / Container Apps com senha:**
     ```powershell
     $env:KYBERNA_AUTH_MODE = "demo_password"
     $env:KYBERNA_APP_PASSWORD = "sua-senha-segura-aqui"
     uv run streamlit run src/ui/app.py
     ```
   - **Ambiente corporativo Azure Easy Auth:** `KYBERNA_AUTH_MODE=entra_id`.
3. **Conferência visual rápida (30 segundos):**
   - Abrir em tela cheia `1920x1080` (ou modo projetor).
   - Confirmar badge inferior da sidebar indicando `Fonte: Snapshot Local (DuckDB)` (modo offline seguro) ou `Fonte: Azure SQL`.
   - Testar alternância de tema (Claro/Escuro) caso a sala esteja com projetor de baixo contraste.

---

## 2. Roteiro Cronometrado (15 Minutos — As 4 Virtudes Cardeais)

### Bloco 1 — `0:00 – 4:00` · **1. Prudência** (*Direção, Pacing & Simulador What-If*)
*Pergunta-guia para o CEO:* *"Para onde estamos indo e o que acontece com o lucro se mexermos em preço ou desconto hoje?"*
1. Mostrar os **5 KPI Cards** no topo: destacar o contraste entre Faturamento Bruto e **Margem Líquida %** contra a meta.
2. No gráfico **Ritmo Mensal: Volume vs. Margem %**, apontar a evolução mês a mês frente à linha de meta e abrir a aba **Decomposição DRE (Waterfall)** para mostrar cada degrau da receita até a margem de contribuição.
3. No bloco direito (**Rentabilidade & Elasticidade-Preço por Família**), alternar para a aba **Elasticidade-Preço (β)** e explicar que o Virtus mede a sensibilidade real de demanda por linha de produto.
4. Na faixa inferior direita (**Simulador Rápido What-If**), aplicar uma simulação ao vivo:
   - Selecionar uma família (ex.: *Linha Escolar*) e mover **Ajuste de Preço (%)** para `-7%` (ou **Variação no Desconto** para `+5 p.p.`).
   - Mostrar o callout **Volume de Equilíbrio (Breakeven) vs. Volume Projetado (β)**: provar em segundos que dar desconto exige mais volume do que a demanda entrega, destruindo margem.

### Bloco 2 — `4:00 – 7:00` · **2. Fortaleza** (*Caixa, Solvência & Risco*)
*Pergunta-guia para o Financeiro:* *"Quanto tempo de fôlego temos e onde o capital de giro está sendo drenado?"*
1. Apresentar **Runway de Caixa**, **Dia do Break-Even Mensal** (mostrando em que dia do mês a operação paga seus custos fixos) e **NCG (Necessidade de Capital de Giro)**.
2. No gráfico de **Ciclo Financeiro (`PME + PMR - PMP`)**, explicar os dias médios de estoque, recebimento e pagamento.
3. Na base, mostrar **Concentração Top 5/10 Clientes** e a **Auditoria de Vencimentos (Aging)** para evidenciar risco de crédito concentrado.

### Bloco 3 — `7:00 – 11:00` · **3. Justiça** (*Radar Comercial, Carteira & Ação 1-Clique*)
*Pergunta-guia para o Diretor Comercial:* *"Quem está trazendo margem real vs. quem só gera volume, e quem está prestes a parar de comprar?"*
1. Mostrar o **Quadrante de RCAs** (identificando representantes em *"Volume sem Margem"* vs. *"Estrela"*) e o **Funil de Saúde do Ciclo de Recompra**.
2. Abrir a tabela **Lista de Ação Priorizada (Churn & Recompra)** e clicar no link **Chamar** (WhatsApp `wa.me`) para demonstrar que a mensagem já sai pronta com contexto do cliente e do RCA.
3. Abrir a aba **Oportunidades White Space** (produtos que clientes parecidos compram e aquele lojista ainda não leva) e demonstrar os botões de **Exportar Excel (.xlsx)** (uma aba por RCA) e **CSV**.

### Bloco 4 — `11:00 – 15:00` · **4. Temperança** (*Erosão Comercial & Estoque Prescritivo*)
*Pergunta-guia para Operações & Controladoria:* *"Onde estamos sangrando margem por indisciplina e onde há capital parado no galpão?"*
1. No gráfico **Decomposição da Erosão Comercial**, apontar **Desconto Fora do Teto**, **Custo de Prazo Esticado (>30d)**, **Comissões RCA** e **Frete CIF**.
2. Na **Matriz ABC/XYZ 3x3**, ler junto com a legenda inferior (ABC = relevância na margem; XYZ = regularidade de giro), depois alternar para **Forecast 30d por SKU** (bandas 80%/95%) e **Treemap Capital Travado (>120d)**.
3. Fechar no **Veredito de Temperança** (canto inferior direito) somando quanto retorna ao caixa operacional ao travar descontos fora da política e liquidar excesso para reabastecer os SKUs da Curva A em ruptura iminente.

---

## 3. FAQ Comercial (Perguntas Frequentes em Reunião)

- **Os dados da demonstração pertencem a algum cliente real?**  
  Não. Os dados transacionais vêm da base pública *Iowa Liquor Sales* remapeada de forma determinística para CNPJs, nomes, cidades brasileiras e regras financeiras sintéticas.
- **Quanto tempo leva para conectar o ERP do cliente?**  
  O núcleo do modelo estrela (`dim_product`, `dim_customer`, `dim_sales_rep`, `fact_sales` e snapshot de estoque) exige apenas exportações padrão de faturamento, cadastro e estoque (CSV, Parquet ou SQL). Um piloto funcional sobe em poucos dias.
- **Qual é o custo de nuvem para manter o ambiente rodando?**  
  O protótipo foi projetado para custo próximo de zero: empacotado em Docker sobre Azure Container Apps com `minReplicas: 0` (*scale-to-zero*) e Azure SQL Database Free Tier Serverless com *auto-pause*, além de operar 100% offline com DuckDB + Parquet.
- **Posso auditar os números de DRE e impostos fora do painel?**  
  Sim. O comando `uv run kyberna audit` gera a planilha `conciliacao_<cenario>.xlsx` com memória de cálculo linha a linha, e o banco `data/kyberna.duckdb` pode ser aberto diretamente no DBeaver.

