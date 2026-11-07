# 💡 Radar de Inovação, Evolução de Produto & Backlog Estratégico (`IDEIAS.md`)

> **Propósito deste documento:** Servir como **Bússola de Evolução de Produto (Product Discovery & Innovation Backlog)** da plataforma **Kyberna — Decision Intelligence & Prescriptive Analytics B2B**.
> Enquanto [`VISION.md`](./VISION.md) define a tese de negócio, [`TASKS.md`](./TASKS.md) governa o roadmap dos marcos principais (`M1`..`M7`) e [`TASKS_REFACTORY.md`](./TASKS_REFACTORY.md) organiza os ajustes técnicos imediatos das Telas 1 e 2, este documento consolida **novas ideias de cards, KPIs, gráficos, algoritmos prescritivos e automações comerciais** avaliadas com rigor executivo de **1 a 5 estrelas (`⭐`)**.

---

## 1. Metodologia de Avaliação Multi-Critério (1 a 5 Estrelas ⭐)

Toda proposta de funcionalidade, indicador ou visualização na Kyberna deve ser avaliada através de **5 parâmetros objetivos**, evitando "gráficos de vaidade" que não geram ação:

| Parâmetro | Pergunta-Chave de Avaliação | Escala (1 a 5 ⭐) |
|---|---|---|
| **🎯 Utilidade Prática (Acionabilidade)** | *O usuário sabe exatamente qual decisão tomar em menos de 10 segundos ao olhar para este item?* | `⭐` (Apenas informativo) $\rightarrow$ `⭐⭐⭐⭐⭐` (Gera ordem de ação imediata) |
| **💰 Geração de Valor / ROI (R$)** | *Quanto dinheiro real este recurso protege (evita churn), recupera (corta vazamento de margem) ou destrava (estoque/cross-sell)?* | `⭐` (Impacto marginal) $\rightarrow$ `⭐⭐⭐⭐⭐` (Impacto direto e alto no DRE/Caixa) |
| **🚀 Impacto em Demo ("Fator Uau")** | *Na reunião comercial de 15 minutos, este recurso faz o CEO, o CFO e o Diretor Comercial dizerem "meu ERP nunca me mostrou isso"?* | `⭐` (Commodity de BI) $\rightarrow$ `⭐⭐⭐⭐⭐` (Diferencial matador de fechamento) |
| **⚙️ Viabilidade Técnica & Performance** | *Pode ser construído sobre nossa stack enxuta (`DuckDB` + `Pandas` + `Streamlit`), respondendo em `< 1,5 s` e com custo cloud $\approx 0$?* | `⭐` (Exige infra pesada/dados externos) $\rightarrow$ `⭐⭐⭐⭐⭐` (Dados já prontos no Gold) |
| **🧩 Complexidade de Implementação** | *Qual o esforço de engenharia de dados, ciência de dados e UI necessário?* | 🟢 **Baixa** ($\le 2\text{h}$) · 🟡 **Média** ($2\text{–}6\text{h}$) · 🔴 **Alta** ($> 1\text{ dia}$) |

---

## 2. Ideias & Evoluções — Tela 1: Visão Executiva & Margem Real

**Persona Principal:** CEO / Dono e CFO / Controller.
**Pergunta Central:** *"Estamos ganhando dinheiro de verdade no bolso — ou apenas trocando figurinha e financiando desconto com o nosso caixa?"*

### 2.1 Tabela de Avaliação (Tela 1)

| ID | Nome da Ideia / Funcionalidade | Formato | 🎯 Utilidade | 💰 Valor (R$) | 🚀 Demo ("Uau") | ⚙️ Viabilidade | 🧩 Complexidade | Status / Destino |
|---|---|---|:---:|:---:|:---:|:---:|:---:|---|
| **ID-E01** | **Visão Quádrupla de Detratores e Geradores (`Família`, `SKU`, `Lojista`, `RCA`)** | 4 Abas de Tabelas Prescritivas | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 🟢 Baixa | 🛠️ Em `TASKS_REFACTORY.md` (`R1-S1`/`R1-V2`) |
| **ID-E02** | **Termômetro de Vazamento nos KPI Cards (`Desc. Médio %` + `Frete+Com. %` + `Caixas Master`)** | Sub-rodapé de KPI Card | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 🟢 Baixa | 🛠️ Em `TASKS_REFACTORY.md` (`R1-V2`) |
| **ID-E03** | **Waterfall B2B com Dupla Leitura (`R$` + `% sobre Bruto`) e R$/Caixa no Hover** | Evolução de Gráfico Plotly | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 🟢 Baixa | 🛠️ Em `TASKS_REFACTORY.md` (`R1-V1`) |
| **ID-E04** | **Painel de "Vazamentos Acionáveis do Período" (3 Cards de Erosão)** | Faixa de 3 Mini-Cards de Alerta | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 🟡 Média | 📅 Backlog Curto Prazo (Pós-Refactory) |
| **ID-E05** | **Decomposição Bridge PVM (*Price-Volume-Mix-Discount Bridge*) entre Períodos** | Gráfico Waterfall Comparativo | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 🟡 Média | 📅 Backlog Médio Prazo (`v0.6+`) |
| **ID-E06** | **Dedução do Custo Financeiro de Prazo de Boleto (30/60/90 dias — Margem Ajustada ao Caixa)** | Nova Barra no Waterfall + KPI | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 🟡 Média | 📅 Backlog Médio Prazo (`v0.6+`) |
| **ID-E07** | **Alerta de Pedidos Fracionados com Frete CIF Destruidor ("Frete > Margem")** | Card + Tabela de Auditoria | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 🟢 Baixa | 📅 Backlog Curto Prazo |
| **ID-E08** | **Radar de Concentração de Receita & Margem (Risco de Dependência Top 5 / Top 10)** | Badge / Mini-Gráfico de Pareto | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 🟢 Baixa | 📅 Backlog Médio Prazo |

### 2.2 Detalhamento das Melhores Ideias Futuras da Tela 1

#### 🔥 `ID-E04` — Painel de "Vazamentos Acionáveis do Período" (⭐⭐⭐⭐⭐)
- **O problema:** O Waterfall mostra que a empresa gastou R$ 1,49 mi em descontos e R$ 216 mil em frete, mas o CFO quer saber: *"Quanto disso foi dentro da regra e quanto foi **excesso/erro operacional**?"*
- **A solução:** Uma faixa compacta de 3 indicadores cirúrgicos logo abaixo do Waterfall:
  1. **💸 Desconto Acima da Alçada:** Soma em R$ dos descontos concedidos acima do teto do porte do cliente (`> 12%`), destacando quantos pedidos violaram a política.
  2. **🚚 Pedidos com Frete CIF Antieconômico:** Quantidade de pedidos pequenos onde o frete absorveu mais de $25\%$ da margem bruta do pedido (prescrição: exigir pedido mínimo de $N$ caixas master para frete CIF).
  3. **🩸 Vendas com Margem Crítica ($< 15\%$):** Faturamento total que gerou margem líquida pífia ("troca de dinheiro"), com 1 clique para filtrar esses pedidos.

#### 🔥 `ID-E05` — Decomposição Bridge PVM (*Preço × Volume × Mix × Desconto*) (⭐⭐⭐⭐⭐)
- **O problema:** Quando a margem cai de R$ 500 mil no 1º Tri para R$ 440 mil no 2º Tri, o Diretor Comercial culpa a queda de mercado (Volume), enquanto o Financeiro culpa os descontos.
- **A solução:** Um gráfico *Bridge* que explica matematicamente a variação $\Delta \text{Margem R\$}$ em 4 blocos:
  $$\Delta \text{Margem} = \text{Efeito Volume} + \text{Efeito Preço Tabela} + \text{Efeito Mix de Produtos} + \text{Efeito Desconto/Custos}$$
  Em uma reunião de diretoria, isso encerra discussões subjetivas em 15 segundos.

#### 🔥 `ID-E06` — Custo Financeiro do Prazo Concedido (30/60/90 dias a CDI/Taxa de Capital de Giro) (⭐⭐⭐⭐⭐)
- **O problema:** Prevista na tese central do [`VISION.md`](./VISION.md) (§2.3 e §6.1), na indústria brasileira vender com boleto para 90 dias a uma taxa de desconto/capital de giro de $1,5\%\text{ a.m.}$ corrói $4,5\%$ da receita líquida!
- **A solução:** Incluir na simulação/Waterfall a coluna opcional `financial_cost_amount` baseada no prazo médio concedido pelo RCA (30/60/90 dias), revelando os representantes que "batem meta" esticando prazo de boleto às custas do caixa da indústria.

---

## 3. Ideias & Evoluções — Tela 2: Radar Comercial, RFM & Antecipação de Churn

**Persona Principal:** Diretor Comercial, Gerente Nacional de Vendas e Representantes (RCAs).
**Pergunta Central:** *"Para quais CNPJs minha equipe deve ligar hoje, com qual argumento/produto na ponta da língua e qual representante está comprando volume com desconto?"*

### 3.1 Tabela de Avaliação (Tela 2)

| ID | Nome da Ideia / Funcionalidade | Formato | 🎯 Utilidade | 💰 Valor (R$) | 🚀 Demo ("Uau") | ⚙️ Viabilidade | 🧩 Complexidade | Status / Destino |
|---|---|---|:---:|:---:|:---:|:---:|:---:|---|
| **ID-C01** | **Régua / Funil de Saúde do Ciclo de Recompra (4 Estágios com Destaque p/ Janela Ideal $1,1\times\text{–}1,5\times$)** | Funil Horizontal de 4 Estágios + 5º KPI Card | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 🟢 Baixa | 🛠️ Em `TASKS_REFACTORY.md` (`R2-S1`/`R2-V2`) |
| **ID-C02** | **Explorador Acionável de Cross-Sell (White Space CNPJ a CNPJ com SKU Âncora + Pitch)** | Tabela Prescritiva Interativa | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 🟢 Baixa | 🛠️ Em `TASKS_REFACTORY.md` (`R2-S1`/`R2-V3`) |
| **ID-C03** | **Quadrante de RCAs Colorido por Perfil + Tabela com Positivação % e Penetração de Mix** | Gráfico Scatter 4 Cores + Tabela | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 🟢 Baixa | 🛠️ Em `TASKS_REFACTORY.md` (`R2-V1`/`R2-V3`) |
| **ID-C04** | **Filtros Táticos Rápidos In-Page (`Status do Ciclo` e `Segmento RFM`) + Tabela Caixa-Branca** | Barra de Controle + Tabela | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 🟢 Baixa | 🛠️ Em `TASKS_REFACTORY.md` (`R2-V2`) |
| **ID-C05** | **Motor de Ação em 1 Clique: Planilha Excel Multi-Aba por RCA, CSV e Link Direto WhatsApp (`wa.me`)** | Barra de Exportação + LinkColumn | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 🟡 Média | 📋 Próxima Task Oficial (`M3-V2` em `TASKS.md`) |
| **ID-C06** | **Calculadora de "Recuperação de Alçada por RCA" (*Quanto ganhamos se o RCA parar de dar desconto máximo?*)** | Card Simulador / Tabela Comparativa | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 🟢 Baixa | 📅 Backlog Curto Prazo |
| **ID-C07** | **Detector de "Churn Silencioso / Downgrade de Cesta" (Cliente no ciclo, mas comprando $-40\%$ de mix/ticket)** | Alerta + Filtro Especial | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 🟡 Média | 📅 Backlog Médio Prazo |
| **ID-C08** | **Ficha Raio-X 360° do Lojista (Drawer / Expander ao clicar em um CNPJ da tabela)** | Card Detalhado on-select | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 🟢 Baixa | 📅 Backlog Curto Prazo |
| **ID-C09** | **Meta Semanal de Ataque do RCA ("Agenda de Segunda-Feira: Top 5 Resgates + Top 5 Cross-Sell")** | Visão Resumida p/ Vendedor | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 🟢 Baixa | 📅 Backlog Curto Prazo (Junto ou pós `M3-V2`) |

### 3.2 Detalhamento das Melhores Ideias Futuras da Tela 2

#### 🔥 `ID-C06` — Calculadora de "Recuperação de Alçada por RCA" (⭐⭐⭐⭐⭐)
- **O problema:** No quadrante de RCAs, identificamos 8 representantes no quadrante *"Volume sem Margem"* (dando $+8\text{ p.p.}$ de desconto acima da política). O Diretor Comercial pergunta: *"Quanto dinheiro estamos deixando na mesa com esses 8 vendedores?"*
- **A solução:** Calcular direto sobre `mart_rep_performance`: para todo RCA cujo `avg_discount_pct > median_discount_pct`, apurar:
  $$\text{Margem Recuperável (R\$)} = \text{gross\_revenue}_{\text{RCA}} \times (\text{avg\_discount\_pct}_{\text{RCA}} - \text{median\_discount\_pct}) \times (1 - \text{alíquota\_imposto\_comissão})$$
  Exibir na seção de RCAs: *"🔒 Travar o desconto dos 8 RCAs agressivos na mediana da equipe ($7,2\%$) recupera **+R$ 340 mil/ano** de lucro líquido direto no caixa."*

#### 🔥 `ID-C07` — Detector de "Churn Silencioso / Downgrade de Cesta" (⭐⭐⭐⭐⭐)
- **O problema:** Alguns grandes lojistas continuam comprando a cada 25 dias (`delay_ratio = 1.0`, logo aparecem como *"No Ciclo"*!), mas **reduziram o pedido pela metade** ou pararam de comprar 2 das 4 famílias que compravam (porque um concorrente entrou na loja!).
- **A solução:** A nossa feature store (`M2-S1` — `src/ml/features.py`) **já calcula `revenue_trend_3m_6m`**! Clientes com `delay_ratio <= 1.2` mas com `revenue_trend_3m_6m < 0.65` (queda $> 35\%$ no trimestre recente) recebem a flag **"⚠️ Churn Silencioso (Queda de Mix/Volume)"**, permitindo blindar o cliente antes que o concorrente tome 100% da gôndola.

#### 🔥 `ID-C08` — Ficha Raio-X 360° do Lojista ao Clicar na Tabela (⭐⭐⭐⭐⭐)
- **O problema:** Tabelas com muitas colunas ficam apertadas em telas menores ou projetores.
- **A solução:** Ao clicar em qualquer linha da Tabela Priorizada de Risco (`on_select="rerun"` do `st.dataframe`), abrir logo abaixo um **Card Raio-X do Cliente Selecionado** mostrando:
  - Dados cadastrais (Razão Social, CNPJ, Cidade/UF, Porte, RCA responsável);
  - Régua visual do ciclo (`Última compra há X dias` vs. `Ciclo habitual de Y dias`);
  - As famílias que ele **já compra** vs. as **Top 3 famílias recomendadas pelo White Space** com o botão de **WhatsApp** grande e pronto para disparo.

---

## 4. Ideias Preventivas — Telas 3 (Estoque & Demanda) e 4 (Simulador What-If) (`M4`)

Para garantir que as próximas telas do roadmap (`M4-V1` e `M4-V2`) já nasçam sem pontos cegos executivos, registramos desde já as ideias de maior impacto:

| ID | Tela Alvo | Nome da Ideia / Funcionalidade | 🎯 Utilidade | 💰 Valor (R$) | 🚀 Demo ("Uau") | ⚙️ Viabilidade | 🧩 Complexidade |
|---|---|---|---|---|:---:|:---:|:---:|:---:|
| **ID-I01** | **Tela 3 (Estoque)** | **Casamento Automático "Combo Destrava-Caixa" (SKU Campeão `AX` + SKU Encalhado `CZ`)**<br/>Sugerir automaticamente kits promocionais cruzando um item de altíssimo giro (`AX`) da mesma família com um item em excesso (`> 120d`), permitindo desovar o estoque parado sem destruir o preço do carro-chefe. | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 🟢 Baixa |
| **ID-I02** | **Tela 3 (Estoque)** | **Alerta Sazonal de Sell-in Industrial (Contagem Regressiva p/ Picos B2B)**<br/>Banner mostrando quantos dias faltam para a janela de faturamento industrial (*Dia das Crianças*, *Natal*, *Volta às Aulas*) comparado ao `lead_time_days` de produção. | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 🟢 Baixa |
| **ID-I03** | **Tela 3 (Estoque)** | ** Conversor Físico-Financeiro Instantâneo (`Unidades` $\leftrightarrow$ `Caixas Master` $\leftrightarrow$ `R$ a Custo CMV` $\leftrightarrow$ `R$ a Preço de Venda`)**<br/>Permitir que tanto o PCP (que pensa em caixas/unidades) quanto o CFO (que pensa em R$ imobilizados em CMV) leiam a mesma tabela de ruptura e excesso. | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 🟢 Baixa |
| **ID-S01** | **Tela 4 (Simulador)** | **Gráfico "Zona da Morte do Desconto" (Volume Exigido vs. Volume Projetado pela Elasticidade)**<br/>Visualização direta lado a lado mostrando que dar $10\%$ de desconto exige $+42\%$ de volume para empatar a margem, mas a elasticidade real do mercado entrega apenas $+14\%$. | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 🟢 Baixa |
| **ID-S02** | **Tela 4 (Simulador)** | **Botão "⚡ Encontrar Preço Ótimo Automaticamente" (Maximização de Margem R$)**<br/>Em 1 clique, posicionar o slider de preço exatamente no ponto da curva de resposta que maximiza a Margem de Contribuição Líquida em R$ da família selecionada. | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 🟢 Baixa |

---

## 5. Ideias Cross-Platform & Aceleradores de Venda B2B (SaaS Evolution)

| ID | Nome da Ideia / Funcionalidade | Descrição Executiva | 🎯 Utilidade | 💰 Valor (R$) | 🚀 Demo ("Uau") | ⚙️ Viabilidade | Horizonte |
|---|---|---|:---:|:---:|:---:|:---:|---|
| **ID-X01** | **Briefing Matinal de Segunda-Feira (Preview do WhatsApp Executivo)** | Modal/Expander na UI que simula a mensagem exata que o Diretor Comercial e cada RCA recebem no celular toda segunda-feira às 07h30 com o resumo da semana e os 5 links de clientes prioritários. Materializa o fechamento do roteiro de demo do `VISION.md` §7.1! | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | `M3-V2` / `M7-V1` |
| **ID-X02** | **Personalização Instantânea de Marca para Reunião (*White-Label Demo Mode*)** | Parâmetro de URL ou variável `.env` (`KYBERNA_CLIENT_BRAND="Indústria X"`) que adapta o subtítulo corporativo na reunião ao vivo com o prospect, aumentando drasticamente a percepção de valor e pertencimento. | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | `M7-V1` |
| **ID-X03** | **Template Universal de Ingestão ERP em 24h (Omie / Bling / Sankhya / TOTVS)** | Script/conector na camada Bronze capaz de ler uma planilha/CSV padrão exportada de ERPs nacionais (3 tabelas: Pedidos, Produtos, Clientes) para rodar um *Diagnóstico Real de PoC* para o cliente em 24 horas após a primeira reunião. | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | Pós-MVP (`v1.1`) |

---

## 6. Roteiro Recomendado de Adoção

1. **Imediato (`v0.3.1-refactory` — Documentado em [`TASKS_REFACTORY.md`](./TASKS_REFACTORY.md)):**
   - Executar as Ondas **R1**, **R2** e **R3** (cobrindo `ID-E01`, `ID-E02`, `ID-E03`, `ID-C01`, `ID-C02`, `ID-C03` e `ID-C04`).
2. **Sequência Direta do Marco M3 ([`TASKS.md`](./TASKS.md)):**
   - Executar **`M3-V2`** (`ID-C05` — Exportação Excel multi-aba por RCA, CSV BOM e links diretos de WhatsApp `wa.me`), podendo já incorporar a **Ficha Raio-X 360° (`ID-C08`)** e a **Calculadora de Recuperação de Alçada por RCA (`ID-C06`)**.
3. **Durante o Marco M4 (Telas 3 e 4):**
   - Incorporar nativamente na implementação de `M4-V1` e `M4-V2` as ideias **`ID-I01`** (Combo Destrava-Caixa), **`ID-I03`** (Conversor Físico-Financeiro), **`ID-S01`** (Zona da Morte do Desconto) e **`ID-S02`** (Botão de Preço Ótimo).

