# VIRTUS (by Kyberna) — Visão do Produto

> **Virtus** (do latim *virtus*: excelência moral, força executiva e caráter; estruturado sobre as **4 Virtudes Cardeais** da filosofia clássica — **Prudência, Fortaleza, Justiça e Temperança**) · Motor de engenharia: **Kyberna** (do grego *κυβερνάω — kybernáō*: governar, conduzir o leme).
> Não separamos a empresa em silos engessados ("Comercial" vs. "Financeiro"): **avaliamos e governamos o comportamento integral do negócio.**

**Documento:** Visão Estratégica do Protótipo Comercial · **Versão:** 2.0 (Edição Virtus) · **Status:** Fonte de verdade de produto e regras de negócio
**Público:** fundadores, time técnico, agentes de IA da IDE (Antigravity), parceiros comerciais.

---

## 1. Em uma frase

O **Virtus** (powered by *Kyberna*) é uma plataforma B2B de **Decision Intelligence, Governança Corporativa & Prescriptive Analytics** que entrega a PMEs e indústrias brasileiras (faturamento entre **R$ 200 mil e R$ 5 milhões/mês**) **respostas acionáveis** estruturadas nas **4 Virtudes Cardeais da Gestão**: **1. Prudência** (previsibilidade, metas e simulação de direção), **2. Fortaleza** (solidez de caixa, ciclo financeiro e blindagem contra riscos), **3. Justiça** (equilíbrio de margem, carteira RFM/Churn e mérito da força de vendas) e **4. Temperança** (controle de excessos, sangria de descontos e capital imobilizado em estoque).

---

## 2. O problema de mercado

### 2.1 O que a PME B2B tem hoje
- **ERP que registra, mas não orienta** (TOTVS, Sankhya, Omie, Bling, Tiny, etc.): relatórios estáticos de faturamento bruto, posição física de estoque e contas a receber.
- **Dashboards descritivos** (quando existem): gráficos de barras do mês passado que ninguém abre na segunda-feira de manhã.
- **Planilhas paralelas** do Comercial e do Financeiro, cada uma com sua própria "verdade" e sem conciliação entre venda faturada e margem efetiva em caixa.

### 2.2 O que ela realmente precisa (e não tem)

| Pergunta de negócio | Por que não é respondida hoje |
|---|---|
| "Quais lojistas vão parar de comprar **esta semana**?" | O ERP só mostra quem já está inativo há 90/180 dias. Ninguém calcula o ciclo de recompra individual de cada CNPJ. |
| "Quanto **eu lucro de verdade** em cada pedido?" | Faturamento bruto ignora impostos, comissão, frete, bonificações e o custo financeiro do prazo de pagamento (30/60/90 dias). |
| "Onde está o meu **capital parado**?" | Estoque é visto pelo PCP em unidades físicas, não pelo Financeiro em R$ imobilizados vs. dias de cobertura futura. |
| "Se eu der 8% de desconto, **quanto preciso vender a mais** para empatar?" | Não existe modelo de elasticidade nem cálculo automático de volume de equilíbrio (breakeven). |
| "Que linha de produto **esse cliente ainda não compra**, mas clientes parecidos compram?" | Não há análise cruzada de penetração de mix (White Space / Cross-sell B2B). |

### 2.3 O conflito estrutural que ninguém resolve
Em toda indústria ou distribuidora B2B de médio porte existe uma tensão permanente entre dois silos:

- **Diretor Comercial** é cobrado por **volume e cobertura**: positivação de CNPJs, reativação de inativos, penetração de mix por lojista e meta bruta de representantes (RCAs).
- **Gerente Financeiro** é cobrado por **margem líquida e fluxo de caixa**: margem de contribuição real (descontando impostos, comissões, frete, custo financeiro de prazos longos e inadimplência) e giro de estoque saudável.

Sem uma base comum, o Comercial concede desconto e estica prazo de boleto (60/90/120 dias) para bater meta de faturamento, e o Financeiro descobre o estrago 60 dias depois no DRE e no caixa. **A Kyberna é a ponte definitiva entre os dois**: uma única plataforma onde volume comercial e saúde financeira falam a mesma língua.

---

## 3. Proposta de valor e Regras de Experiência (UX)

> **Empresas não compram gráficos passivos do passado. Compram respostas prescritivas.**

### 3.1 Princípios de produto (inegociáveis)
1. **Prescrever, não descrever.** Todo gráfico precisa terminar em uma recomendação clara e quantificada em R$ ("Acione estes 37 lojistas hoje para proteger R$ 142 mil", "Remaneje 420 caixas da Filial 03 para a 07").
2. **Margem Líquida acima de Faturamento Bruto.** O KPI-mestre é a **Margem de Contribuição Líquida Ajustada**, nunca a receita bruta isolada.
3. **Ação em 1 clique.** Toda lista prescritiva é exportável para Excel/CSV ou acionável via WhatsApp com mensagem estruturada pronta — o valor só se materializa quando o RCA entra em contato com o cliente.
4. **Linguagem do dono, não do cientista de dados.** "Dinheiro travado", "clientes adormecidos", "oportunidade de mix", "fôlego de estoque" — zero jargão estatístico ("p-valor", "R²", "RMSE") na camada principal da interface.
5. **Rápido como uma planilha local.** Toda interação de filtro ou simulação responde em menos de 1,5 s. Lentidão mata demonstrações comerciais e mata adoção.
6. **Explicável (Caixa-Branca).** Cada score (risco de churn, potencial de White Space, elasticidade) exibe em linguagem simples *por que* foi calculado (ex.: *"Ciclo histórico: 28 dias | Dias sem comprar: 49 dias -> Risco Crítico"*).

### 3.2 Padrão de Experiência Executiva (Regras de UI para Agentes)
- **Manchete Executiva Dinâmica (Headline First):** O topo de cada uma das 4 telas deve exibir um banner narrativo gerado dinamicamente pelos dados (ex.: *"Resumo Executivo: A margem líquida caiu 2,4 p.p. no trimestre puxada por descontos na Linha Escolar, mas há R$ 310 mil de oportunidade imediata de recuperação em 64 clientes em risco"*).
- **Hierarquia Visual Sóbria (Light Mode ☀️ e Dark Mode 🌙):** Paleta corporativa Kyberna com suporte a alternância dinâmica entre tema claro executivo (ideal para projetores e apresentações em salas iluminadas) e tema escuro (cockpit para uso diário em monitores), usando azul-marinho profundo, ardósia, verde-esmeralda para ganho de margem, âmbar para atenção e vermelho-coral para risco de churn/ruptura. Proibido visual de "notebook acadêmico".
- **Contexto Persistente:** Ao trocar o cenário na barra lateral, todos os rótulos de negócio (ex.: "Lojista CNPJ" vs. "PDV" vs. "Filial"; "Caixa Master" vs. "Unidade"; "RCA" vs. "Vendedor") adaptam-se automaticamente.

### 3.3 Métrica Norte (North Star)
**R$ prescrito e acionado por mês** — soma da receita recuperada (clientes reativados), margem incremental de cross-sell/pricing e capital de giro liberado do estoque a partir das recomendações da plataforma.

---

## 4. O Framework de Governança **Virtus** e Personas

Em vez de separar os painéis da forma tradicional e engessada ("Comercial", "Financeiro", "Operações"), o **Virtus** estrutura o produto pelas **4 Virtudes Cardeais** da filosofia clássica. Isso muda a pergunta do gestor: ele deixa de olhar apenas números isolados e passa a avaliar o **comportamento do negócio**:

| Página (Virtude Cardeal) | Conceito Filosófico | Tradução Executiva (BI / DaaS) | Foco Principal / Personas |
|---|---|---|---|
| **1. Prudência** (*Prudentia*) | Sabedoria prática para discernir o futuro e agir certo (*auriga virtutum*) | **Direção, Previsibilidade, Pacing de Metas e Cenários (What-If)** | **Diretor / CEO** (*"Para onde estamos indo e o que decidir hoje antes que o mês acabe?"*) |
| **2. Fortaleza** (*Fortitudo*) | Firmeza e resiliência diante das adversidades e choques | **Solidez de Caixa, Break-Even, Ciclo Financeiro (NCG) e Concentração** | **Diretor e Gerente Financeiro** (*"Quão blindada está a empresa contra imprevistos de mercado?"*) |
| **3. Justiça** (*Iustitia*) | Dar a cada parte o que lhe é devido, com equilíbrio (*suum cuique tribuere*) | **Rentabilidade Comercial (Campeões vs. Vampiros), Mérito de RCAs e Carteira RFM/White Space** | **Diretor Comercial, Diretor Geral e RCAs** (*"A troca de valor entre empresa, clientes e vendedores está justa e saudável?"*) |
| **4. Temperança** (*Temperantia*) | Moderação, domínio próprio e aversão ao excesso impulsivo | **Eficiência, Auditoria de Erosão Comercial (Waterfall), Descontos Fora do Teto e Capital Travado (>120d)** | **Gerente Financeiro, Comercial e PCP** (*"Onde estamos perdendo dinheiro por desconto excessivo, estoque parado ou vazamento financeiro?"*) |

---

## 5. Arquitetura Conceitual — Motor de Demonstração Multi-Cenário

### 5.1 O problema da demonstração comercial
Vender analytics prescritivo exige **mostrar** o produto funcionando com dados volumosos, realistas e matematicamente coerentes — sem jamais expor dados confidenciais de clientes. A solução da Kyberna é um **Motor de Remapeamento Semântico e Sazonal** sobre uma base pública B2B real.

### 5.2 Base de origem: *Iowa Liquor Sales*
Base pública do Estado de Iowa (EUA), contendo milhões de transações reais de atacado. Estruturalmente, é uma base **B2B2C completa**: fabricantes vendem caixas fechadas (`pack`) com custo (`state_bottle_cost`) e preço de revenda (`state_bottle_retail`) para milhares de lojas cadastradas em dezenas de cidades.

| Campo original | Semântica original | Transformação no Motor Kyberna |
|---|---|---|
| `vendor_name` | Fabricante | Vira Linha/Marca da Indústria, Fabricante ou Fornecedor |
| `item_number`, `item_description`, `pack`, `bottle_volume_ml` | SKU e embalagem | Vira SKU do catálogo com **Caixa Master** (`pack` = unidades/caixa) |
| `state_bottle_cost` | Custo unitário | Base do CMV / Custo Industrial ou de Aquisição |
| `state_bottle_retail` | Preço de venda unitário | Base do Preço de Tabela antes de descontos comerciais |
| `store_number`, `store_name` | Loja compradora | Vira Lojista (CNPJ), PDV Bar/Supermercado, Filial ou Loja Única |
| `city`, `county`, `zip_code` | Geografia | Vira Município, Polo Regional e UF do Brasil |
| `date`, `bottles_sold`, `sale_dollars` | Transação | Série temporal real deslocada para a **Data-Âncora (`as_of_date`)** da demo |

> **IMPORTANTE — Âncora Temporal e Sazonalidade B2B (Sell-in):**
> O pipeline sempre normaliza a data máxima da base para uma `as_of_date` configurável (ex.: data atual da demonstração), garantindo que "últimos 30 dias" e "clientes em risco hoje" estejam sempre vivos. Além disso, no Cenário 1 (Indústria de Brinquedos), a curva sazonal reflete o calendário real do **Sell-in industrial brasileiro** (onde a fábrica fatura para o varejo de 45 a 60 dias antes da data comemorativa: picos de faturamento B2B em Jul/Ago para o Dia das Crianças, Set/Out para o Natal e Nov/Jan para Volta às Aulas).

### 5.3 Fluxo do Pipeline de Dados (Medallion Architecture + Auditoria Aberta)

1. **[Ingestão] Iowa Liquor Sales (API Socrata / Parquet)**
   `-->` **Camada Bronze:** Dado bruto imutável em Parquet particionado (`year=/month=`) + registrado em `bronze.sales_raw` no catálogo local `data/kyberna.duckdb`.
2. **[Normalização SQL] Camada Silver:**
   `-->` Modelo canônico limpo (via SQL no DuckDB) + deslocamento para Âncora Temporal (`as_of_date`) em `silver.sales`.
3. **[Enriquecimento & Remapeamento] Motor de Cenários (`ScenarioConfig YAML`):**
   `-->` Cruza Camada Silver + Referências BR (Municípios, UFs, Impostos, Frete) + `Faker pt_BR` (Pandas determinístico para CNPJs e RCAs em `silver.dim_*`).
   `-->` Gera 4 visões na **Camada Gold** (`gold.*` no `kyberna.duckdb` + snapshots Parquet):
   - **Gold C1:** Indústria de Brinquedos (B2B Nacional)
   - **Gold C2:** Distribuidora de Bebidas (B2B Regional/Nacional)
   - **Gold C3:** Rede Multi-filial (Varejo Franquias/Filiais)
   - **Gold C4:** PDV Único (Comércio Local)
4. **[Ciência de Dados] Motor Analítico & ML (Pandas 2.x):**
   `-->` Calcula ABC/XYZ, RFM, Risco de Churn por ciclo, Matriz White Space, Eficiência de RCAs, Forecast 30d e Elasticidade de Preço.
5. **[Auditoria & Conciliação Financeira]:**
   `-->` Catálogo local unificado (`data/kyberna.duckdb`) inspecionável via **DBeaver / DuckDB UI** + comando `uv run kyberna audit` gerando a planilha `data/reports/conciliacao_<cenario>.xlsx` com memória de cálculo aberta pedido a pedido.
6. **[Serving & UI] Camada de Consumo:**
   `-->` Persiste no **Azure SQL Free Tier** (com fallback automático para **DuckDB + Parquet local**).
   `-->` Alimenta o **App Streamlit Kyberna** com Seletor Global de Cenários.

### 5.4 Os 4 Cenários de Negócio

O usuário alterna o cenário na barra lateral e **toda a aplicação muda de vocabulário, regras de margem e prescrições** instantaneamente:

#### Cenário 1 — Indústria B2B Nacional (Modo Brinquedos / Bens de Consumo) · Caso Âncora
- **Quem é a empresa:** indústria nacional (sede em SP) vendendo **caixas master** para milhares de lojistas, papelarias, magazines e atacadistas em todo o Brasil.
- **Remapeamento:**
  - Lojas de Iowa viram **Lojistas (CNPJs)** com razão social, nome fantasia, segmento (*Papelaria, Loja de Brinquedos, Magazine, Livraria, Atacadista Regional*) e UF/Município.
  - Categorias viram **Famílias de Brinquedos**: *Jogos Educativos, Primeira Infância, Brinquedos de Madeira, Quebra-Cabeças, Linha Escolar, Jogos de Tabuleiro e Pelúcias*.
  - `pack` vira **Unidades por Caixa Master**.
  - Carteira de **Representantes Comerciais (RCAs)** alocados por região, com taxa de comissão, política de desconto praticada e prazo médio concedido (30/60/90 dias).
- **Estrutura de margem:** Preço de Tabela -> (-) Desconto Comercial/Bonificação -> (-) Impostos (ICMS, PIS/COFINS, IPI parametrizados) -> (-) Custo Industrial (CMV) -> (-) Comissão RCA -> (-) Frete CIF/FOB -> (-) Custo Financeiro do Prazo.
- **Prescrições-chave:** reativar CNPJs adormecidos antes do concorrente, expandir mix (White Space) em lojistas ativos, corrigir RCAs que destroem margem com desconto/prazo excessivo e planejar produção/estoque para os picos de Sell-in (Dia das Crianças, Natal, Volta às Aulas).

#### Cenário 2 — Indústria / Distribuidora B2B de Bebidas
- **Quem é a empresa:** distribuidora regional/nacional atendendo bares, restaurantes, adegas, eventos e supermercados (on-trade e off-trade).
- **Remapeamento:** categorias originais traduzidas (*Vodka, Whisky, Gin, Rum, Tequila, Licores, Cachaças Premium e Aperitivos*); clientes como PDVs cadastrados atendidos por vendedores de rota.
- **Prescrições-chave:** frequência de reposição de rota, perda de giro em PDVs on-trade, proteção de margem em linhas de alto giro vs. alto valor agregado.

#### Cenário 3 — Rede de Lojas / Franquias (Varejo Multi-filial)
- **Quem é a empresa:** rede varejista operando dezenas de lojas próprias ou franquias (**Filial 01 - Centro, Filial 02 - Shopping...**).
- **Inversão de perspectiva:** a rede é a **compradora e varejista**. O valor de aquisição torna-se o **CMV da loja**, aplicando-se markup de varejo para venda ao consumidor.
- **Prescrições-chave:** benchmarking de margem e ticket médio entre filiais, **matriz de remanejamento de estoque entre lojas** (transferir excesso da Filial A para cobrir ruptura iminente na Filial B sem nova compra do fornecedor) e padronização de sortimento ideal.

#### Cenário 4 — Comércio Local (PDV Único)
- **Quem é a empresa:** loja física independente de alto fluxo vendendo direto ao consumidor final no balcão/gôndola.
- **Remapeamento:** compras consolidadas são desmembradas em cupons diários de PDV; inclui um **Clube de Fidelidade** sintético (clientes CPF identificados) para habilitar análise de recorrência no varejo físico.
- **Prescrições-chave:** **Curva ABC de gôndola** (lucro por espaço de prateleira), lista de compras da semana, queima de itens encalhados e reativação de clientes fiéis do clube.

> *Extensibilidade Futura (Cenário 5 — E-commerce/Marketplace):* O modelo canônico da camada Silver permite acoplar futuramente bases como a *Olist* para simular vendas digitais, avaliando impacto de frete e reputação/atraso logístico na recompra.

### 5.5 Matriz de capacidades por cenário

| Capacidade | C1 Brinquedos (B2B) | C2 Bebidas (B2B) | C3 Rede Multi-filial | C4 PDV Único |
|---|:---:|:---:|:---:|:---:|
| Margem real (Waterfall completo) | Sim (Impostos, CMV, RCA, Frete, Prazo) | Sim (Completo B2B) | Sim (Markup e Custos de Loja) | Sim (Simplificada PDV) |
| Matriz ABC / XYZ | Sim (Portfólio Industrial) | Sim (Catálogo Atacado) | Sim (Giro por Filial) | Sim (ABC de Gôndola) |
| RFM + Radar de Churn | Sim (Lojistas CNPJ) | Sim (PDVs CNPJ) | Adaptado (Radar de Saúde das Filiais) | Sim (Clube Fidelidade CPF) |
| White Space (Cross-sell) | Sim (Lojista x Família) | Sim (PDV x Categoria) | Sim (Lacuna de Sortimento/Loja) | Sim (Afinidade de Cesta) |
| Eficiência Comercial | Sim (Quadrante de RCAs) | Sim (Vendedores de Rota) | Sim (Gerentes de Filial) | N/A |
| Forecast 30d e Ruptura | Sim (Produção / Estoque) | Sim (Compra / CD) | Sim (Reposição por Loja) | Sim (Compra Semanal) |
| Remanejamento de Estoque | N/A | N/A | Sim (Transferência entre Lojas) | N/A |
| Simulador What-If | Sim (Preço, Desconto, Comissão) | Sim (Preço e Desconto) | Sim (Promoção de Varejo) | Sim (Preço de Balcão) |

---

## 6. Regras de Negócio e Fórmulas Canônicas (Fonte Única da Verdade)

Para garantir consistência matemática absoluta entre os 4 pilares de cada marco — Infraestrutura (`I`), Engenharia de Dados & Finanças (`D`), Ciência de Dados & Prescrição (`S`) e Interface & Visualização (`V`) —, todo o código do repositório deve obedecer a estas definições:

### 6.1 Waterfall da Margem de Contribuição Líquida (`MC_liq`)
- `Receita Bruta Tabelada = Quantidade * Preco_Tabela`
- `Receita Faturada = Receita_Bruta_Tabelada - Descontos_Comerciais`
- `Receita Liquida = Receita_Faturada - Impostos_Sobre_Venda`
- `Margem Bruta = Receita_Liquida - CMV_Total`
- `Margem Contribuicao Liquida (R$) = Margem_Bruta - Comissao_RCA - Frete_Empresa - Custo_Financeiro_Prazo`
- `Margem Contribuicao Liquida (%) = (Margem_Contribuicao_Liquida / Receita_Faturada) * 100`

### 6.2 Índice de Risco de Churn Individual (Baseado no Ciclo Próprio do Cliente)
- Cada cliente ativo possui um intervalo médio histórico entre compras `ciclo_medio_dias` e desvio-padrão `ciclo_std_dias`.
- `Razao de Atraso (delay_ratio) = dias_sem_comprar_na_as_of_date / ciclo_medio_dias`
- **Classificação Prescritiva:**
  - `delay_ratio <= 1.1` -> **No Ciclo (Saudável)**
  - `1.1 < delay_ratio <= 1.5` -> **Atenção (Janela Ideal de Abordagem)**
  - `1.5 < delay_ratio <= 2.5` -> **Em Risco Imediato (Prioridade Máxima de Reativação)**
  - `delay_ratio > 2.5` -> **Adormecido / Hibernando (Campanha de Recuperação)**
- `Valor Anual em Risco (R$)` = Faturamento anualizado histórico do cliente ponderado pela probabilidade de churn.

### 6.3 Cobertura de Estoque e Capital Travado
- `Demanda Diaria Prevista = Forecast_30_Dias / 30`
- `Dias de Cobertura = Estoque_Atual_Disponivel / max(Demanda_Diaria_Prevista, 0.1)`
- **Ruptura Iminente:** `Dias de Cobertura < Lead_Time_Reposicao_Dias`
- **Capital Travado (Excesso):** `Dias de Cobertura > 120`
  - `Capital Travado (R$) = (Estoque_Atual_Disponivel - (120 * Demanda_Diaria_Prevista)) * Custo_Unitario_CMV`

### 6.4 Simulador What-If e Volume de Equilíbrio (Breakeven de Desconto)
- Dado um percentual de variação de preço/desconto `delta_p` (ex.: `-0.07` para 7% de desconto) e a margem de contribuição percentual atual `mc_0`:
- `Variacao Volume Breakeven (delta_q_breakeven) = (-delta_p) / (mc_0 + delta_p)`
- `Variacao Volume Estimada (delta_q_estimado) = elasticidade_categoria * delta_p` (onde `elasticidade_categoria < 0`)
- **Veredito Automático do Simulador:** Se `delta_q_estimado > delta_q_breakeven`, a ação **Gera Lucro Incremental**; caso contrário, exibe alerta vermelho de **Destruição de Margem**.

### 6.5 Solidez de Caixa, Ciclo Financeiro e Vazamentos (`config/finance/working_capital.yaml`)
Para sustentar os indicadores de **2. Fortaleza** e **4. Temperança** de forma 100% determinística e auditável no DuckDB:
- **Ponto de Equilíbrio Operacional (Break-Even Mensal):**
  - `Receita Break-Even (R$) = Custo_Fixo_Mensal / (Margem_Contribuicao_Pct / 100)`
  - `Dia do Break-Even no Mes = ceil(30 * (Receita_Break_Even / Receita_Bruta_Mensal))`
  - `Folego de Caixa (Runway em Meses) = Reserva_Caixa_Operacional / Custo_Fixo_Mensal`
- **Ciclo Operacional, Ciclo Financeiro (Caixa) e Necessidade de Capital de Giro (NCG):**
  - `PME (Prazo Medio de Estocagem, dias)` = Cobertura média ponderada do estoque ativo (`coverage_days`).
  - `PMR (Prazo Medio de Recebimento, dias)` = Média ponderada dos prazos concedidos por porte de cliente / RCA (ex.: P=28d, M=42d, G=60d; penalidade +18d para RCAs em `high_discount_reps`).
  - `PMP (Prazo Medio de Pagamento a Fornecedores, dias)` = Parâmetro do cenário (ex.: 35 dias na Indústria C1).
  - `Ciclo Financeiro de Caixa (dias) = PME + PMR - PMP`
  - `NCG (Necessidade de Capital de Giro em R$) = ((CMV_Diario + Despesas_Variaveis_Diarias) * max(Ciclo_Financeiro_Dias, 0))`
- **Auditoria de Excesso de Desconto e Vazamento Financeiro de Prazo (Temperança):**
  - `Desconto Excedente Fora da Politica (R$) = sum(max(0, taxa_desconto_praticada - teto_desconto_porte) * Receita_Bruta_Pedido)`
  - `Custo Financeiro do Prazo Excedente (R$) = Receita_Liquida * ((max(0, PMR_pedido - prazo_padrao_30d) / 30) * taxa_custo_capital_mensal)`

---

## 7. Caso Âncora — Indústria de Brinquedos: O "Efeito Virtus" (Fluxo de Diagnóstico em 15 Minutos)

> **NOTA DE CONFIDENCIALIDADE:** O perfil de referência é o de uma indústria nacional consolidada de brinquedos (como a **Nig Brinquedos**). **Nenhum dado confidencial da empresa é utilizado no protótipo.** O nome corporativo exibido na tela é configurável via variável de ambiente/parâmetro para apresentações personalizadas.

### 7.1 A Narrativa de Vendas DaaS ("O Efeito Virtus")
Para vender a plataforma como assinatura recorrente para donos de PMEs e indústrias, o diferencial decisivo é mostrar que as **4 páginas conversam em um fluxo único de diagnóstico executivo**:

1. **O Diretor abre a 1. PRUDÊNCIA (0–4 min)** e vê no Termômetro de Metas e na Projeção de Fechamento que, embora o faturamento bruto tenha subido +12%, a projeção de margem líquida do trimestre caiu -3,1 p.p. No **Simulador What-If**, ele testa na hora: *"E se fizermos a campanha de 7% de desconto na Linha Escolar?"* — o simulador alerta que seria preciso vender **+28% em volume** só para empatar o lucro, mas a elasticidade entrega apenas +11%.
2. **Ele avança para a 2. FORTALEZA (4–7 min)** junto ao Gerente Financeiro e percebe que o fôlego de caixa está pressionado: o **Dia do Break-Even** atrasou do dia 16 para o dia 21 do mês porque o **Ciclo Financeiro ($\text{PME} + \text{PMR} - \text{PMP}$)** subiu para 68 dias, exigindo mais **Capital de Giro (NCG)**, além de notar alta concentração de receita nos Top 10 clientes e exposição no Aging da carteira.
3. **Na 3. JUSTIÇA (7–11 min)**, o Diretor Comercial identifica a assimetria da carteira: a **Matriz Campeões vs. Vampiros** mostra lojistas de grande porte que compram alto volume mas deixam margem líquida mínima; o **Quadrante de RCAs** revela 2 representantes líderes de venda bruta no quadrante *"Volume sem margem"*, enquanto há **214 lojistas em risco no Ciclo de Recompra** e **R$ 890 mil de oportunidade limpa na Matriz White Space** (com argumento pronto para disparo no WhatsApp).
4. **Na 4. TEMPERANÇA (11–15 min)**, o Financeiro e o Comercial descobrem e estancam a causa raiz: o **Waterfall da Erosão Comercial** e a **Auditoria de Política** provam que a equipe comercial queimou **R$ 340 mil em descontos acima do teto permitido** e esticou prazos de boleto para 75 dias, enquanto **R$ 640 mil de capital ficaram imobilizados no estoque (> 120 dias)** em SKUs da curva C e 18 SKUs da curva A entraram em alerta de ruptura antes do pico de Sell-in.

**O Fechamento da Reunião:**
*"Vocês não precisam abrir quatro planilhas desconexas. Toda segunda-feira às 07h30, o Virtus envia no WhatsApp da diretoria os alertas de Prudência e para cada representante a lista justa de lojistas que entraram na janela de compra — já blindada pela margem e pela temperança que o Financeiro aprovou."*

---

## 8. As 4 Páginas do Sistema **Virtus** (Especificação Funcional)

### Página 1 — 🦉 PRUDÊNCIA (*Visão Executiva, Previsibilidade e Direção*)
**Premissa:** *"Para onde estamos indo e o que precisamos decidir hoje antes que o mês acabe?"* (Foco: Diretor / CEO)
- **Manchete Executiva de Prudência** resumindo o ritmo de receita vs. margem líquida e os alertas de direção do período.
- **Termômetro de Metas (Pacing Mensal e do Período):** KPI Cards comparando Faturamento Bruto, Receita Líquida, Margem de Contribuição (R$ e %) e Geração Operacional contra a meta esperada para o período.
- **Projeção de Fechamento (Tendência Dupla + Forecast 30/60/90 dias):** Evolução histórica de Faturamento Bruto vs. Margem Líquida % (evidenciando o "efeito boca de jacaré") combinada com a projeção estatística (`StatsForecast`) dos próximos 30/60/90 dias.
- **Simulador Executivo de Cenários (What-If de 3 Alavancas):** Controles deslizantes rápidos (Variação de Preço/Desconto %, Ajuste de Comissão/Custos % e Sensibilidade de Volume/Elasticidade) exibindo instantaneamente o impacto no Lucro Operacional, o **Volume de Equilíbrio (Breakeven)** e a curva de otimização.
- **Radar de Anomalias (Alertas de Prudência):** Lista automática de desvios críticos detectados na janela (quedas abruptas de margem por família, explosão de descontos fora da média móvel e clientes Classe A que romperam o ciclo).

### Página 2 — 🛡️ FORTALEZA (*Solidez Financeira, Caixa e Resiliência*)
**Premissa:** *"Quão blindada está a empresa contra imprevistos de mercado?"* (Foco: Diretor e Financeiro)
- **Fôlego de Caixa (Runway e Liquidez) & Ponto de Equilíbrio (Break-Even Point):** Indicadores mostrando quantos meses de operação a reserva cobre e em qual **dia do mês** (ou volume de receita) a empresa paga 100% dos seus custos fixos estruturais e passa a gerar caixa livre.
- **Ciclo Financeiro ($\text{PME} + \text{PMR} - \text{PMP}$) e Necessidade de Capital de Giro (NCG):** Comparativo visual entre Prazo Médio de Estocagem (PME), Prazo Médio de Recebimento (PMR) e Prazo Médio de Pagamento (PMP), revelando em dias e em R$ se o crescimento das vendas está gerando ou consumindo caixa.
- **Risco de Concentração (Dependência Comercial e de Portfólio):** Curva de concentração (Top 5 / Top 10 Clientes, RCAs e Famílias/Fornecedores) com semáforo de vulnerabilidade caso os maiores clientes concentrem fatia excessiva da margem.
- **Saúde da Carteira e Exposição por Faixa de Atraso (Aging List):** Distribuição da receita e dos clientes por faixas de atraso em relação ao ciclo esperado (*No Ciclo*, *15–30d / Atenção*, *30–60d / Em Risco*, *>60d / Adormecido*), quantificando o capital exposto.

### Página 3 — ⚖️ JUSTIÇA (*Equilíbrio Comercial, Margem e Valor*)
**Premissa:** *"A troca de valor entre a empresa, seus clientes e sua força de vendas está justa e saudável?"* (Foco: Comercial e Diretor)
- **Matriz de Rentabilidade (Campeões vs. "Clientes/Produtos Vampiros"):** Visão multi-dimensional (`Por Família`, `Por Produto`, `Por Lojista`, `Por Representante`) cruzando Faturamento Bruto e Margem de Contribuição Líquida — separando os geradores reais de lucro dos "vampiros" (alto volume de trabalho, baixíssima margem).
- **Justiça da Força de Vendas (Quadrante de Eficiência de RCAs):** Dispersão em 4 quadrantes (*Estrela*, *Volume sem margem*, *Margem sem volume*, *Atenção*) avaliando representantes pela margem preservada, positivação de carteira e penetração de mix (com tamanho da bolha = R$ em risco).
- **Saúde da Base de Clientes (Treemap RFM por Margem + Funil do Ciclo de Recompra):** Segmentação automática dos 9 grupos RFM ponderada por margem líquida + régua dos 4 estágios do ciclo individual de compra e tabela priorizada caixa-branca.
- **Explorador Acionável White Space (Cross-Sell B2B) & Retenção/LTV:** Recomendações CNPJ a CNPJ com **SKU Âncora**, família recomendada, potencial em R$, estimativa de LTV por segmento e **Motor de Ação em 1 Clique** (planilha Excel por RCA + link direto `wa.me` para WhatsApp com pitch pronto).

### Página 4 — 🏺 TEMPERANÇA (*Eficiência, Controle de Excessos e Desperdícios*)
**Premissa:** *"Onde estamos perdendo dinheiro por falta de controle, desconto excessivo ou ineficiência?"* (Foco: Financeiro, Comercial e Operações)
- **Erosão Comercial (Waterfall Completo da Sangria de Margem):** Decomposição em cascata do Faturamento Bruto Tabelado até a Margem de Contribuição Líquida (`R$` e `% sobre o Bruto`), expondo visualmente o peso de Descontos, Impostos, CMV, Comissões e Frete.
- **Disciplina de Política Comercial (Orçado/Teto vs. Realizado):** Auditoria de descontos concedidos acima do teto da política comercial por porte/família (`excess_discount_brl`) e desvios de frete/comissão por RCA e região.
- **Temperança de Estoque e Operação (Matriz ABC/XYZ + Capital Imobilizado > 120d vs. Ruptura Curva A):** Cruzamento interativo da Matriz ABC/XYZ (3x3) com o valor financeiro parado em estoque sem giro (`> 120 dias`, com prescrição de *Kit Promocional / Bonificação / Liquidação*) versus alertas de **Ruptura Iminente** nos itens de alta demanda (Curva A, com sugestão de ordem em caixas master) e **Transferência entre Filiais** (Cenário 3).
- **Vazamentos Financeiros Invisíveis:** Quantificação em R$ do **Custo Financeiro do Prazo** (erosão causada por prazos de boleto esticados para 60/90 dias) e comissões pagas sobre pedidos com desconto fora da política.

---

## 9. Modelo de Monetização e Go-to-Market

### 9.1 Escada de Valor e Oferta "Cliente Âncora" (2026 -> 2027)

| Modalidade | Escopo da Entrega | Investimento (Referência) | Objetivo Estratégico |
|---|---|---|---|
| **1. Oferta "Cliente Âncora / Case Fundador" (Fast-Track 2026)** | Implantação conectada ao ERP/banco do cliente cobrindo o fluxo Comercial + Financeiro em troca de autorização de uso de marca e depoimento de sucesso após 60 dias. | **Setup reduzido:** R$ 3.500 – R$ 5.000 / **MRR:** R$ 990 – R$ 1.490/mês | Gerar caixa rápido em 2026 e conquistar o estudo de caso industrial de referência para o portfólio da Kyberna. |
| **2. Diagnóstico "Raio-X Kyberna"** (Porta de entrada padrão) | 10 a 15 dias: ingestão de extrato do ERP, entrega do Waterfall de margem real, lista imediata de CNPJs em risco e estoque travado. (100% abatido do Setup se assinar o plano anual). | R$ 3.500 – R$ 7.500 (pagamento único) | Vencer a inércia de TI/Diretoria com ROI provado nos dados reais do cliente em 2 semanas. |
| **3. Setup Padrão de Produção (2027)** | Conectores automatizados, parametrização fiscal/financeira, calibração de ML e treinamento da equipe comercial/financeira. | R$ 8.000 – R$ 25.000 | Cobrir engenharia de integração e implantação sob medida. |
| **4. Assinatura SaaS / MRR (Essencial a Profissional)** | Acesso contínuo às 4 telas, atualização diária/semanal, motor de ML e **Resumo Executivo Semanal Anti-Churn via WhatsApp/E-mail**. | R$ 1.490 – R$ 4.990/mês | Construir receita recorrente previsível com altíssima retenção. |

### 9.2 O Mecanismo Anti-Churn da Própria Kyberna (Retenção em 2027)
O maior risco de qualquer ferramenta de BI é o cliente parar de abrir o link por falta de tempo na rotina. Na Kyberna, o produto **vai até o cliente**: toda segunda-feira às 07h30, um job automatizado dispara para o Diretor e para cada RCA um resumo de 5 linhas no WhatsApp/E-mail com os clientes que entraram em zona de risco naquela semana e o link direto de ação.

### 9.3 Racional de ROI para o Cliente (Exemplo: Indústria faturando R$ 1,5 mi/mês)
- **Carteira ativa:** 1.800 lojistas (ticket médio anual de R$ 10 mil).
- **12% da carteira em risco imediato:** 216 lojistas = **R$ 2,16 mi/ano em risco**.
- **Recuperando apenas 15% desses clientes** com o alerta semanal = **+R$ 324 mil/ano** de faturamento (**+R$ 81 mil/ano de margem líquida** a 25%).
- **Destravando 20% de R$ 600 mil de estoque parado** = **+R$ 120 mil imediatos em caixa**.
- **Resultado:** O sistema se paga múltiplas vezes já nos primeiros 60 dias de uso.

---

## 10. Arquitetura Técnica Enxuta (Custo Próximo de Zero)

| Camada | Tecnologia | Racional Técnico e Financeiro |
|---|---|---|
| **Processamento e ETL** | **DuckDB (SQL) + Pandas 2.x (`pyarrow`)** (Python 3.11+, gerenciado via `uv`) | Transformações pesadas e Waterfall financeiro em SQL explícito e auditável no DuckDB; enriquecimento (`Faker`) e features em Pandas 2.x sem exigir cluster Spark ou Polars/Delta. |
| **Storage / Catálogo Local** | **Catálogo Unificado `data/kyberna.duckdb` + Parquet** local e no **ADLS Gen2** | Arquitetura Medallion (`bronze`, `silver`, `gold`) 100% inspecionável no DBeaver ou `duckdb -ui` e sincronizável com Azure Blob/ADLS Gen2 a custo de centavos. |
| **Auditoria e Conciliação** | **Excel (`xlsxwriter` via `kyberna audit`) + DBeaver / DuckDB UI** | Gera `data/reports/conciliacao_<cenario>.xlsx` com DRE resumido e memória de cálculo aberta pedido a pedido para conferência imediata. |
| **Banco Servido (Gold)** | **Azure SQL Database Free Tier** (Serverless Gen5, 32 GB, auto-pause 1h) | Custo R$ 0,00 dentro dos 100.000 vCore-segundos gratuitos/mês. |
| **Modo Fallback Local** | **DuckDB lendo Parquet Gold local** | Garante que a demonstração funcione em menos de 1s mesmo offline ou enquanto o Azure SQL Serverless estiver despertando do auto-pause. |
| **Ciência de Dados e ML** | **StatsForecast (Nixtla), LightGBM, Scikit-Learn** (nativos sobre Pandas 2.x) | Modelos leves, ultra-rápidos em CPU, altamente explicáveis e sem conversões desnecessárias de DataFrame. |
| **Front-end / DataApp** | **Streamlit + Plotly** (arquitetura modular + `@st.cache_data` / `@st.fragment`) | Acabamento executivo, resposta instantânea e facilidade de manutenção por uma equipe enxuta. |
| **Deploy e Orquestração** | **Docker no Azure Container Apps** (scale-to-zero) + **GitHub Actions** | Hospedagem serverless gratuita quando ociosa e pipelines agendados dentro dos 2.000 min/mês gratuitos do GitHub. |

Detalhes de implementação e padrões de código: ver `GEMINI.md` / `CLAUDE.md` e o plano de execução modular por marcos (`M1` a `M7`) em `TASKS.md`.

---

## 11. Escopo do Protótipo

### Dentro do escopo (Fase 0)
- Pipeline completo e determinístico da base *Iowa Liquor Sales* para os **4 cenários de negócio**.
- Cálculo completo das **fórmulas canônicas** (Seção 6) na camada Gold e nos módulos de ML.
- Aplicativo Streamlit com identidade visual **Kyberna**, **Seletor Global de Cenários**, **Manchetes Executivas Dinâmicas** e as **4 Telas de Alta Conversão**.
- Exportação de listas de ataque em CSV/Excel e geração de links `wa.me` com mensagem comercial pré-formatada por cliente/RCA.
- Deploy conteinerizado na Azure operando em *Fallback Local (DuckDB)* ou *Azure SQL Free Tier*.

### Fora do escopo (Fase 0 — Entra apenas a partir da Fase 1 paga)
- Multi-tenancy complexo, SSO corporativo e controle de acesso por linha (RLS).
- Conectores nativos em tempo real com ERPs (TOTVS, Sankhya, Omie, Bling).
- Disparo ativo via API Oficial do WhatsApp Business (Meta Cloud API) — no protótipo utiliza-se geração de link direto `wa.me`.
- Motor tributário contábil exaustivo por NCM/CEST (no protótipo as alíquotas de impostos são parametrizáveis por UF/Cenário).
- Uso de qualquer dado pessoal real (100% em conformidade com a LGPD usando dados sintéticos determinísticos).

---

## 12. Critérios de Sucesso do Protótipo (Definition of Done)
- [ ] **Fluidez de Demo:** Roteiro de 15 minutos navegável nos 4 cenários sem erros ou telas em branco.
- [ ] **Consistência Matemática:** O valor de Margem de Contribuição Líquida exibido na Tela 1 bate exatamente com a base do Simulador na Tela 4 e com os totais da Tela 2.
- [ ] **Performance:** Troca de filtros, cenários e sliders do simulador respondendo em menos de 1,5 s (com cache aquecido).
- [ ] **Reprodutibilidade e Auditoria:** Pipeline de dados, modelos e planilha Excel de conciliação executáveis ponta a ponta com a CLI (`uv run kyberna pipeline run --scenario all` e `uv run kyberna audit --scenario c1_toys`).
- [ ] **Custo Cloud:** Operação mensal na Azure menor ou igual a US$ 1,00.
- [ ] **Tração Comercial:** Apresentação realizada para o Caso Âncora (Indústria de Brinquedos) e fechamento do primeiro projeto comercial ainda em 2026.
