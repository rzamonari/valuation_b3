# ESPECIFICAÇÃO TÉCNICA FINAL — CAMADA GOLD (MARTS)
## Pipeline de Indicadores Fundamentalistas — Arquitetura Medallion

**Versão:** 1.0  
**Linguagem:** Python 3.13 / SQL DuckDB  
**Gerenciador de dependências:** uv  
**Banco de dados:** `fundamentalistas.duckdb`  
**Camada de origem:** Silver (`refined`)  
**Camada de destino:** Gold (Marts)  
**Diretório obrigatório dos arquivos SQL:** `sql/marts/`

---

# 1. PAPEL E DIRETRIZES DO DESENVOLVIMENTO

Atue como consultor especialista e perito em Engenharia de Dados, com mais de 20 anos de experiência em arquitetura de dados, modelagem dimensional, SQL analítico, DuckDB e desenvolvimento orientado por especificações (Spec-Driven Development).

O desenvolvimento deverá seguir rigorosamente esta especificação.

A especificação é a fonte única da verdade do projeto. O código SQL deverá ser consequência direta das regras aqui documentadas.

Não invente regras de negócio, fórmulas financeiras, fontes de dados, relacionamentos ou premissas que não estejam documentados.

Quando uma informação indispensável não estiver definida, não presuma uma resposta. Registre a pendência e solicite confirmação antes de implementar a funcionalidade afetada.

## 1.1 Objetivo

Implementar a camada Gold (Marts) do pipeline de indicadores fundamentalistas, utilizando exclusivamente os dados já existentes na camada Silver do banco `fundamentalistas.duckdb`.

O objetivo é disponibilizar consultas SQL independentes para os indicadores financeiros e fundamentalistas definidos nesta especificação.

Os indicadores deverão ser obtidos seguindo esta prioridade:

1. Utilizar diretamente os indicadores já disponibilizados pelo Fundamentus na camada Silver.
2. Quando o indicador não existir pronto no Fundamentus, verificar se todos os dados necessários para calculá-lo estão disponíveis nas tabelas Silver.
3. Se os dados estiverem disponíveis e a fórmula estiver definida, realizar o cálculo na própria camada Gold.
4. Se algum dado necessário não existir na Silver, desconsiderar o indicador.
5. Se a fórmula ou metodologia necessária não estiver definida, não implementar até que haja confirmação.

**É expressamente proibido ampliar ou modificar as camadas Bronze e Silver para viabilizar qualquer indicador.**

---

# 2. ARQUITETURA E RESTRIÇÕES OBRIGATÓRIAS

O projeto utiliza arquitetura Medallion:

- Bronze: schema `raw`.
- Silver: schema `refined`.
- Gold: camada de indicadores e consultas analíticas (Marts).

## 2.1 Regra inviolável: preservar Bronze e Silver

As camadas `raw` e `refined` são consideradas concluídas e não fazem parte do escopo desta implementação.

O Claude Code não poderá:

- Alterar estruturas de tabelas Bronze ou Silver.
- Adicionar, remover ou modificar colunas nessas camadas.
- Criar novas tabelas nos schemas `raw` ou `refined`.
- Atualizar, excluir ou inserir registros nessas camadas.
- Modificar os processos de ingestão ou transformação existentes.
- Alterar arquivos responsáveis pela implementação da Bronze ou Silver.
- Buscar novas fontes de dados para completar indicadores.
- Criar campos artificiais ou valores estimados para contornar ausência de dados.

As tabelas Silver deverão ser utilizadas exclusivamente para leitura.

**Qualquer indicador que dependa de informações inexistentes na Silver deverá ser desconsiderado, sem exceções.**

## 2.2 Escopo permitido

A implementação deverá ficar restrita à camada Gold e aos arquivos necessários para sua documentação.

O diretório obrigatório para as consultas é:

`sql/marts/`

Os dez arquivos SQL individuais deverão ser armazenados nesse diretório, respeitando os nomes definidos nesta especificação.

Não espalhar consultas SQL em outros diretórios.

Não misturar as consultas dos diferentes indicadores em um único arquivo.

## 2.3 Banco de dados

Arquivo:

`fundamentalistas.duckdb`

As consultas deverão ser compatíveis com DuckDB.

Antes de implementar, inspecionar o código existente e identificar como o projeto realiza conexão com o banco, organização dos schemas e execução de SQL.

Não criar uma nova implementação de conexão caso já exista uma função apropriada no projeto.

---

# 3. DIAGNÓSTICO OBRIGATÓRIO ANTES DA IMPLEMENTAÇÃO

Antes de escrever qualquer código, o Claude Code deverá inspecionar a estrutura real do projeto.

O diagnóstico deverá identificar:

1. Estrutura de diretórios.
2. Arquivo de configuração e dependências.
3. Implementação de conexão com DuckDB.
4. Schemas existentes no banco.
5. Estrutura real das tabelas Silver.
6. Tipos de dados das colunas.
7. Chaves disponíveis para relacionamentos.
8. Existência de nulos e valores inválidos relevantes para os cálculos.
9. Compatibilidade das funções SQL pretendidas com DuckDB.
10. Existência de convenções de nomenclatura e execução já adotadas pelo projeto.

O arquivo `pipeline/db.py` já foi definido como parte da infraestrutura existente. Inspecione sua implementação real antes de utilizá-lo. Não presuma funções, parâmetros ou comportamentos além dos efetivamente existentes.

Não modifique arquivos existentes apenas para adequá-los à implementação Gold.

## 3.1 Relatório de diagnóstico

Antes de implementar, apresentar um relatório contendo:

- Estrutura identificada.
- Tabelas e colunas disponíveis.
- Indicadores prontos encontrados.
- Indicadores que podem ser calculados.
- Indicadores que deverão ser desconsiderados.
- Fórmulas que podem ser implementadas sem novas premissas.
- Pendências metodológicas.
- Arquivos que serão criados.
- Confirmação de que Bronze e Silver permanecerão intactas.

Se a inspeção identificar divergência entre esta especificação e a estrutura real do banco, não adaptar silenciosamente a especificação. Apresentar a divergência e solicitar decisão.

---

# 4. ESTRUTURA DA CAMADA SILVER — FONTES DISPONÍVEIS

A implementação Gold deverá considerar exclusivamente as tabelas já existentes na Silver.

As estruturas abaixo representam o esquema previamente definido para o projeto. O Claude Code deverá validar os nomes e tipos reais no banco antes de implementar.

## 4.1 `refined.b3_empresas`

Campos:

- `codigo_cvm`
- `empresa_emissora`
- `razao_social`
- `nome_pregao`
- `cnpj`
- `indicador_mercado`
- `tipo_bdr`
- `data_listagem`
- `situacao`
- `segmento`
- `segmento_ingles`
- `tipo_empresa`
- `mercado`
- `_timestamp_ingestao`
- `_source_origin`

Observação: o campo `segmento` representa o segmento de listagem da B3. Não presumir que seja uma classificação de setor econômico.

## 4.2 `refined.fundamentus_acoes`

Campos:

- `ticker`
- `cotacao`
- `preco_lucro`
- `preco_valor_patrimonial`
- `preco_vendas`
- `dividend_yield`
- `preco_ativo`
- `preco_capital_giro`
- `preco_ebit`
- `preco_ativo_circulante_liquido`
- `enterprise_value_ebit`
- `enterprise_value_ebitda`
- `margem_bruta`
- `margem_ebit`
- `margem_liquida`
- `liquidez_corrente`
- `roic`
- `roe`
- `liquidez_2_meses`
- `patrimonio_liquido`
- `divida_liquida_patrimonio`
- `crescimento_receita_5_anos`
- `_timestamp_ingestao`
- `_source_origin`

Observações:

- Os indicadores percentuais são armazenados na escala de 0 a 100.
- Exemplo: `6,91%` na origem é armazenado como `6.91`.
- Os campos numéricos foram tratados na Silver para preservar precisão decimal.
- A chave lógica da tabela é `ticker`, conforme regras já estabelecidas.

## 4.3 `refined.yfinance_cotacoes`

Campos:

- `ticker`
- `data`
- `abertura`
- `maxima`
- `minima`
- `fechamento`
- `fechamento_ajustado`
- `volume`
- `dividendos`
- `desdobramentos`
- `_source_origin`
- `_timestamp_ingestao`
- `ganhos_capital`

Observações:

- A chave lógica é `(ticker, data)`.
- `data` é TIMESTAMP WITH TIME ZONE.
- `fechamento_ajustado` está disponível para análises de retorno histórico.
- `dividendos` está disponível como histórico de proventos.
- Nulos devem ser preservados.
- Não preencher valores nulos de proventos com zero sem regra expressamente aprovada.

## 4.4 Tabelas auxiliares Minha Receita

Também existem:

- `refined.minhareceita_empresas`
- `refined.minhareceita_qsa`
- `refined.minhareceita_regime_tributario`
- `refined.minhareceita_cnaes_secundarios`

Essas tabelas não deverão ser utilizadas para inventar classificações setoriais ou relacionamentos entre CNPJ e ticker.

Só poderão ser utilizadas se o relacionamento necessário estiver comprovadamente disponível na Silver e for indispensável para um indicador definido.

Não criar relacionamentos por aproximação de nomes de empresas.

---

# 5. REGRAS GERAIS PARA OS INDICADORES

## 5.1 Prioridade de utilização

Para cada indicador:

**Prioridade 1 — Indicador pronto**

Se existir um campo correspondente na tabela `refined.fundamentus_acoes`, utilizar diretamente seu valor.

**Prioridade 2 — Indicador derivado**

Se não existir pronto, verificar se os dados necessários estão disponíveis nas tabelas Silver.

O cálculo somente poderá ser implementado se:

- Todos os campos necessários existirem.
- Os dados forem compatíveis.
- A fórmula estiver definida.
- Não houver necessidade de buscar novas fontes.

**Prioridade 3 — Desconsideração**

Se faltar qualquer dado necessário, desconsiderar o indicador e documentar a justificativa.

## 5.2 Preservação de valores

Não modificar os valores originais fornecidos pelo Fundamentus.

Não arredondar ou truncar valores sem necessidade técnica justificada.

Não converter percentuais de escala 0–100 para escala 0–1 indiscriminadamente.

A unidade de cada indicador deverá ser documentada no resultado ou na especificação do respectivo Mart.

## 5.3 Tratamento de nulos e divisões

- Preservar valores nulos.
- Não substituir nulos por zero.
- Não interpretar ausência de informação como resultado financeiro zero.
- Evitar divisão por zero.
- Não gerar resultados infinitos.
- Não transformar indicadores negativos em positivos.
- Não descartar automaticamente valores negativos sem regra específica.
- Não aplicar filtros de qualidade financeira que não estejam documentados.

Quando o cálculo não puder ser realizado por causa de denominador zero, retornar NULL ou excluir apenas o resultado calculado, conforme a estrutura da consulta e a regra aplicável. Não eliminar desnecessariamente o registro completo da empresa.

## 5.4 Identificação das empresas

Utilizar `ticker` como identificador principal dos indicadores fundamentalistas.

Para análises históricas, relacionar os dados por `ticker`.

Não realizar joins que provoquem multiplicação de registros.

Antes de qualquer relacionamento, verificar cardinalidade e unicidade das chaves envolvidas.

---

# 6. INDICADORES E ARQUIVOS SQL

Deverão ser criados os dez arquivos SQL individuais abaixo.

Todos deverão ficar dentro de `sql/marts/`.

## 6.1 ROIC

**Arquivo:** `sql/marts/marts_roic.sql`

**Indicador:** `roic`

**Fonte:** `refined.fundamentus_acoes.roic`

Diretriz analítica:

O ROIC representa a capacidade de geração de retorno sobre o capital investido.

A referência de custo de capital nominal entre 14% e 16% foi apresentada como diretriz de interpretação, não como fórmula ou parâmetro obrigatório de cálculo.

Regras:

- Utilizar diretamente o ROIC do Fundamentus.
- Preservar a escala percentual original.
- Não recalcular o ROIC.
- Não criar classificação de empresas acima ou abaixo do custo de capital sem regra adicional aprovada.

**Status:** implementar.

## 6.2 EV/EBIT

**Arquivo:** `sql/marts/marts_ev_ebit.sql`

**Indicador:** `enterprise_value_ebit`

**Fonte:** `refined.fundamentus_acoes.enterprise_value_ebit`

Diretriz analítica:

Representa o múltiplo do valor da firma sobre o resultado operacional.

É utilizado como referência na estratégia Magic Formula, em conjunto com ROIC.

Regras:

- Utilizar diretamente o indicador do Fundamentus.
- Não recalcular Enterprise Value.
- Não recalcular EBIT.
- Preservar valores negativos e nulos conforme a origem.

**Status:** implementar.

## 6.3 Alavancagem

**Arquivo:** `sql/marts/marts_alavancagem.sql`

Indicadores previstos:

- `divida_liquida_patrimonio`
- `divida_liquida_ebitda`

Fonte disponível:

`refined.fundamentus_acoes.divida_liquida_patrimonio`

Diretriz analítica:

Avaliar a estrutura de capital e o risco de alavancagem das empresas.

O patamar de 3 vezes dívida líquida/EBITDA foi apresentado como referência de alerta, mas não autoriza criar esse indicador sem os dados necessários.

Regras:

- Disponibilizar diretamente dívida líquida/PL.
- Não calcular dívida líquida/EBITDA sem dívida líquida e EBITDA em valores monetários.
- Não buscar essas informações em novas fontes.
- Não alterar Silver para adicionar os campos ausentes.

**Status:**

- Dívida líquida/PL: implementar.
- Dívida líquida/EBITDA: desconsiderar, pois não consta no esquema Silver disponível.

## 6.4 ROE

**Arquivo:** `sql/marts/marts_roe.sql`

**Indicador:** `roe`

**Fonte:** `refined.fundamentus_acoes.roe`

Diretriz analítica:

Representa o retorno sobre o patrimônio líquido.

Deve ser interpretado em conjunto com o ROIC. Um ROE significativamente superior ao ROIC pode indicar efeito de alavancagem.

É um indicador especialmente relevante para bancos e seguradoras.

Regras:

- Utilizar diretamente o ROE do Fundamentus.
- Não recalcular o indicador.
- Preservar escala percentual.
- Não criar classificação automática de alavancagem sem regra aprovada.

**Status:** implementar.

## 6.5 P/L e Earnings Yield

**Arquivo:** `sql/marts/marts_preco_lucro.sql`

Indicadores:

- `preco_lucro`
- `earnings_yield`

Fonte:

`refined.fundamentus_acoes.preco_lucro`

Diretriz analítica:

O P/L representa o múltiplo entre preço e lucro.

O Earnings Yield representa o inverso do P/L, expresso em percentual.

Fórmula definida:

`earnings_yield = 100.0 / preco_lucro`

Regras:

- Utilizar diretamente o P/L do Fundamentus.
- Calcular Earnings Yield na Gold.
- Se P/L for zero ou NULL, Earnings Yield deverá ser NULL.
- Preservar P/L negativo.
- Não aplicar automaticamente filtro de P/L negativo ou superior a 50.
- A interpretação analítica desses casos deverá permanecer separada do cálculo.

**Status:** implementar os dois indicadores.

## 6.6 Margens

**Arquivo:** `sql/marts/marts_margens.sql`

Indicadores:

- `margem_ebit`
- `margem_liquida`
- `margem_bruta`

Fontes:

- `refined.fundamentus_acoes.margem_ebit`
- `refined.fundamentus_acoes.margem_liquida`
- `refined.fundamentus_acoes.margem_bruta`

Diretriz analítica:

Avaliar eficiência operacional, rentabilidade e capacidade de preservação de margens.

A diferença entre margem EBIT e margem líquida pode auxiliar na análise do impacto financeiro e tributário.

Regras:

- Utilizar diretamente os três indicadores.
- Preservar a escala percentual.
- Não recalcular as margens.
- Não criar agrupamento setorial nesta versão.

Justificativa da ausência de agrupamento:

O campo `segmento` da B3 representa segmento de listagem e não comprova classificação econômica. A Silver atual não possui relacionamento setorial confiável entre ticker e setor econômico.

**Status:** implementar os indicadores sem agrupamento setorial.

## 6.7 Crescimento da receita em cinco anos

**Arquivo:** `sql/marts/marts_crescimento_receita_5_anos.sql`

**Indicador:** `crescimento_receita_5_anos`

**Fonte:** `refined.fundamentus_acoes.crescimento_receita_5_anos`

Diretriz analítica:

Representa o crescimento histórico da receita em cinco anos.

É uma referência para análises de crescimento e modelos de fluxo de caixa descontado.

Regras:

- Utilizar diretamente o indicador do Fundamentus.
- Não recalcular CAGR.
- Preservar a escala percentual.
- Não projetar crescimento futuro a partir do indicador histórico.
- Não criar estimativas de receita.

**Status:** implementar.

## 6.8 Dividend Yield e Payout

**Arquivo:** `sql/marts/marts_dividend_yield_payout.sql`

Indicadores:

- `dividend_yield`
- `payout`

Fontes:

- `refined.fundamentus_acoes.dividend_yield`
- `refined.fundamentus_acoes.preco_lucro`

Diretriz analítica:

Avaliar a remuneração do acionista e a relação entre distribuição de proventos e lucro.

Fórmula definida:

`payout = dividend_yield * preco_lucro`

Considerar que o Dividend Yield está armazenado na escala percentual de 0 a 100.

Exemplo:

- Dividend Yield = 6%
- P/L = 10
- Payout = 60%

Regras:

- Utilizar diretamente o Dividend Yield do Fundamentus.
- Calcular Payout na Gold.
- Se qualquer componente for NULL, Payout será NULL.
- Se P/L for zero, Payout será zero matematicamente, sem divisão.
- Preservar valores negativos, sem aplicar filtros não especificados.
- Não substituir Dividend Yield por cálculo próprio.
- Não validar ou reconciliar o DY com os proventos do YFinance nesta versão.

A validação independente do Dividend Yield exigiria definição adicional de janela temporal, preço de referência e metodologia. Portanto, não faz parte desta implementação.

**Status:** implementar DY e Payout.

## 6.9 P/VP e relação P/VP ÷ ROE

**Arquivo:** `sql/marts/marts_p_vp.sql`

Indicadores:

- `preco_valor_patrimonial`
- relação `preco_valor_patrimonial / roe`

Fontes:

- `refined.fundamentus_acoes.preco_valor_patrimonial`
- `refined.fundamentus_acoes.roe`

Diretriz analítica:

O P/VP isolado possui limitações e deverá ser analisado em conjunto com a rentabilidade do patrimônio líquido.

A relação P/VP dividido pelo ROE permite avaliar o prêmio pago por unidade de rentabilidade.

Regras:

- Utilizar diretamente P/VP e ROE.
- Calcular a relação na Gold.
- Não realizar divisão quando ROE for zero ou NULL.
- Preservar valores negativos sem alterar a origem.
- Não calcular preço justo pela equação de Gordon nesta versão.
- Não definir Ke ou crescimento perpétuo sem parâmetros aprovados.

**Status:** implementar P/VP e sua relação com ROE. Desconsiderar cálculo de valor justo por Gordon.

## 6.10 Retorno total e risco histórico

**Arquivo:** `sql/marts/marts_retorno_total_risco.sql`

Indicadores originalmente previstos:

- CAGR do fechamento ajustado.
- Volatilidade anualizada.
- Máximo drawdown.
- Sharpe.

Fonte:

`refined.yfinance_cotacoes`

Campos disponíveis:

- `ticker`
- `data`
- `fechamento_ajustado`
- `fechamento`
- `dividendos`
- `desdobramentos`
- `volume`

Diretriz analítica:

Avaliar o comportamento histórico das cotações, retorno e risco.

Regras:

- Utilizar exclusivamente o histórico disponível na Silver.
- Utilizar `fechamento_ajustado` para os cálculos baseados em retorno total.
- Não buscar cotações externas.
- Não preencher datas ausentes artificialmente.
- Não gerar retornos quando os preços necessários forem nulos ou inválidos.
- Não misturar séries de tickers diferentes.
- Ordenar cronologicamente os dados por ticker.

Indicadores:

**CAGR:** calcular a taxa composta de crescimento anual com base nos preços ajustados inicial e final e no intervalo temporal efetivamente utilizado.

**Volatilidade:** poderá ser calculada a partir dos retornos periódicos da série ajustada, com anualização baseada na periodicidade efetiva dos dados. A convenção de anualização deverá ser explicitada antes da implementação.

**Máximo drawdown:** poderá ser calculado a partir da série ajustada, comparando a evolução acumulada com os máximos históricos anteriores.

**Sharpe:** não implementar nesta versão, pois não foi definida uma taxa livre de risco nem uma metodologia aprovada para o cálculo.

### Pendência obrigatória antes da implementação

Ainda não foi aprovada a janela temporal do histórico:

- 1 ano;
- 3 anos;
- 5 anos;
- todo o histórico disponível.

Também não foi aprovada a convenção de anualização da volatilidade.

O Claude Code deverá identificar essas pendências no diagnóstico e solicitar confirmação antes de implementar os cálculos afetados. Não escolher silenciosamente uma das opções.

Os demais indicadores deste arquivo só poderão ser implementados depois de formalizadas as regras metodológicas necessárias.

### D1. Ajuste retroativo inválido do Yahoo (aprovada em 2026-11-04)

**Evidência (base de 2026-10-30).** 18.350 linhas de 8 tickers (PPAR3, MMAQ4, MMAQ3, SANB3,
SANB4, CTAX3, PPLA11, EPAR3) têm `fechamento_ajustado ≤ 0`; o `fechamento` bruto nunca é
negativo. O Yahoo ajusta o passado pelo fator `1 − provento / fechamento anterior`. Quando o
provento é maior ou igual ao fechamento anterior, o fator fica ≤ 0 e inverte o sinal de toda a
série anterior. As 39 trocas de sinal da base coincidem com um provento assim, confirmado em
`yf.Ticker(t).actions` (ex.: PPAR3 em 2024-11-07, provento 128,05 com fechamento 125,01). Os
trechos positivos entre duas inversões (MMAQ3, MMAQ4, PPLA11) também estão errados, porque são o
produto de dois fatores negativos.

**Decisão.** A Silver preserva o dado como veio. Em `marts_retorno_total_risco`, se a janela de
5 anos tem alguma data com `fechamento_ajustado ≤ 0`, ou algum provento ≥ fechamento do pregão
anterior, o ticker fica **sem cálculo**:

- `cagr`, `volatilidade_anualizada`, `max_drawdown`, `preco_inicial` e `preco_final` ficam NULL;
- `motivo_sem_calculo` = `Ajuste retroativo inválido do Yahoo (provento >= fechamento anterior)`;
- datas e contagens da janela continuam preenchidas, para rastreio.

Na base de 2026-10-30, isso atinge PPAR3, MMAQ3 e MMAQ4. Os outros 5 tickers só têm o defeito
antes da janela, e os demais 606 tickers não mudam.

**Alternativa descartada.** Começar a janela depois do último provento inválido. Isso daria a um
indicador de "5 anos" um intervalo variável (PPAR3 ficaria com 1,98 ano) e não corrige MMAQ3 e
MMAQ4. Esses dois têm um segundo defeito: o fechamento bruto salta de 3,00 e 163,86 para
2.550,01 em 2024-12-27 sem desdobramento registrado.

**Qualidade.** Continua o AVISO na Silver (`fechamento_ajustado > 0`). É ERRO se algum indicador
do mart for calculado com `fechamento_ajustado ≤ 0` na janela, ou se um ticker sem cálculo tiver
algum indicador preenchido.

---

# 7. MATRIZ CONSOLIDADA DE DISPONIBILIDADE

A matriz deverá ser utilizada como referência para a implementação.

| Indicador | Fonte ou cálculo | Decisão |
|---|---|---|
| ROIC | Fundamentus | Implementar |
| EV/EBIT | Fundamentus | Implementar |
| Dívida líquida/PL | Fundamentus | Implementar |
| Dívida líquida/EBITDA | Dados insuficientes | Desconsiderar |
| ROE | Fundamentus | Implementar |
| P/L | Fundamentus | Implementar |
| Earnings Yield | Derivado do P/L | Implementar |
| Margem EBIT | Fundamentus | Implementar |
| Margem líquida | Fundamentus | Implementar |
| Margem bruta | Fundamentus | Implementar |
| Crescimento da receita em 5 anos | Fundamentus | Implementar |
| Dividend Yield | Fundamentus | Implementar |
| Payout | Derivado de DY e P/L | Implementar |
| P/VP | Fundamentus | Implementar |
| P/VP ÷ ROE | Derivado de P/VP e ROE | Implementar |
| CAGR de retorno total | YFinance ajustado | Pendente de definição metodológica |
| Volatilidade anualizada | YFinance ajustado | Pendente de definição metodológica |
| Máximo drawdown | YFinance ajustado | Pendente de definição metodológica |
| Sharpe | Falta taxa livre de risco e metodologia | Desconsiderar nesta versão |
| Comparação setorial de margens | Falta classificação econômica confiável | Desconsiderar nesta versão |
| Valor justo por Gordon | Faltam parâmetros aprovados | Desconsiderar nesta versão |

---

# 8. ORGANIZAÇÃO OBRIGATÓRIA DOS ARQUIVOS

Os arquivos deverão ser criados exatamente dentro da pasta:

`sql/marts/`

Estrutura esperada:

```text
projeto/
â”‚
â”œâ”€â”€ fundamentalistas.duckdb
â”‚
â”œâ”€â”€ pipeline/
â”‚   â”œâ”€â”€ db.py
â”‚   â””â”€â”€ transformacao.py
â”‚
â”œâ”€â”€ sql/
â”‚   â””â”€â”€ marts/
â”‚       â”œâ”€â”€ marts_roic.sql
â”‚       â”œâ”€â”€ marts_ev_ebit.sql
â”‚       â”œâ”€â”€ marts_alavancagem.sql
â”‚       â”œâ”€â”€ marts_roe.sql
â”‚       â”œâ”€â”€ marts_preco_lucro.sql
â”‚       â”œâ”€â”€ marts_margens.sql
â”‚       â”œâ”€â”€ marts_crescimento_receita_5_anos.sql
â”‚       â”œâ”€â”€ marts_dividend_yield_payout.sql
â”‚       â”œâ”€â”€ marts_p_vp.sql
â”‚       â””â”€â”€ marts_retorno_total_risco.sql
â”‚
â””â”€â”€ ...
```

Não criar arquivos SQL fora de `sql/marts/`.

Cada arquivo deverá:

1. Ser independente.
2. Possuir identificação clara do indicador.
3. Documentar sua fonte Silver.
4. Documentar fórmulas, quando aplicáveis.
5. Identificar unidades e escalas.
6. Tratar nulos e divisões por zero.
7. Ser compatível com DuckDB.
8. Ser executável de forma independente, respeitando as dependências documentadas.
9. Não executar alterações nos schemas `raw` e `refined`.

As consultas deverão ser organizadas de maneira que possam ser executadas individualmente.

Não criar dependências entre arquivos SQL que obriguem a execução de um indicador para que outro funcione, salvo se houver justificativa técnica documentada e aprovada.

Os arquivos poderão conter comentários SQL explicando as regras de negócio.

---

# 9. PADRÃO DE RESULTADO DOS MARTS

Cada consulta deverá retornar os campos necessários para identificar a empresa e seus indicadores.

Regras:

- Utilizar `ticker` como identificador.
- Utilizar nomes claros e consistentes para as colunas.
- Preservar os valores originais quando forem indicadores do Fundamentus.
- Identificar claramente os indicadores derivados.
- Não duplicar empresas por causa de joins.
- Não agregar empresas sem regra definida.
- Não eliminar registros sem justificativa documentada.

O Claude Code deverá inspecionar o projeto para identificar se já existe padrão de schema de destino ou de materialização dos Marts.

Não presumir nomes de schemas, tabelas ou rotinas de persistência que não estejam definidos no projeto.

Se houver necessidade de criar objetos persistentes na camada Gold, apresentar a proposta de estrutura antes da implementação caso não exista convenção previamente estabelecida.

As consultas SQL devem permanecer disponíveis nos arquivos individuais de `sql/marts/`, independentemente da forma de execução ou materialização adotada.

---

# 10. QUALIDADE E VALIDAÇÃO

Cada SQL deverá ser validado individualmente.

Verificações obrigatórias:

1. Compatibilidade sintática com DuckDB.
2. Existência das tabelas e colunas referenciadas.
3. Ausência de divisão por zero.
4. Preservação de valores nulos.
5. Ausência de multiplicação indevida de registros.
6. Unicidade esperada por ticker quando aplicável.
7. Coerência das fórmulas implementadas.
8. Compatibilidade dos tipos de dados.
9. Ausência de alterações em Bronze e Silver.
10. Ausência de dependências externas.

Os testes deverão ser executados preferencialmente em transações ou consultas somente de leitura, evitando qualquer alteração nas camadas protegidas.

Não modificar os dados de origem para fazer um teste passar.

## 10.1 Indicadores desconsiderados

A ausência de um indicador não deverá ser tratada como falha técnica do pipeline quando sua exclusão estiver prevista nesta especificação.

A exclusão deverá ser documentada no respectivo arquivo ou na documentação técnica, conforme aplicável.

---

# 11. DOCUMENTAÇÃO TÉCNICA FINAL

Além dos dez arquivos SQL, entregar uma documentação técnica da Gold contendo:

- Objetivo e escopo.
- Arquitetura.
- Fontes Silver utilizadas.
- Mapeamento completo das colunas.
- Indicadores disponibilizados diretamente.
- Indicadores calculados.
- Fórmulas utilizadas.
- Tratamento de nulos e divisões.
- Indicadores desconsiderados.
- Justificativa de cada exclusão.
- Dependências entre tabelas.
- Critérios de validação.
- Instruções de execução dos arquivos SQL.
- Pendências metodológicas que ainda dependem de decisão.

A documentação deverá deixar claro que a Bronze e a Silver não foram modificadas.

---

# 12. CRITÉRIOS DE ACEITE

A implementação será considerada concluída somente quando:

1. Os dez arquivos SQL estiverem armazenados em `sql/marts/`.
2. Cada arquivo possuir consulta individual e documentação pertinente.
3. Todos os indicadores implementados possuírem fonte e fórmula rastreáveis.
4. Indicadores sem dados suficientes tiverem sido desconsiderados.
5. Nenhuma fonte externa tiver sido utilizada.
6. Nenhuma tabela Bronze ou Silver tiver sido alterada.
7. Todos os SQLs implementados tiverem sido validados no DuckDB.
8. As pendências metodológicas estiverem identificadas.
9. A documentação técnica estiver concluída.
10. A estrutura final do projeto estiver consistente com a arquitetura Medallion.

---

# 13. ORIENTAÇÃO FINAL AO CLAUDE CODE

Execute o trabalho seguindo rigorosamente esta sequência:

**ETAPA 1 — INSPEÇÃO**

Inspecione o projeto, o banco DuckDB, as tabelas Silver e os arquivos existentes.

Não escreva código nesta etapa.

**ETAPA 2 — DIAGNÓSTICO**

Apresente o relatório de disponibilidade dos indicadores, as dependências, as divergências encontradas e as pendências metodológicas.

Confirme expressamente que nenhuma alteração será realizada em `raw` ou `refined`.

**ETAPA 3 — VALIDAÇÃO DAS PENDÊNCIAS**

Antes de implementar indicadores cuja metodologia ainda não foi aprovada, solicite as definições necessárias.

Não utilize valores padrão arbitrários.

**ETAPA 4 — IMPLEMENTAÇÃO**

Após a validação das pendências, crie os arquivos SQL individuais exclusivamente em `sql/marts/`.

Não altere os processos anteriores do pipeline.

**ETAPA 5 — TESTES**

Execute e valide cada consulta individualmente no DuckDB.

Confira os resultados, tipos, nulos, cardinalidade e fórmulas.

**ETAPA 6 — ENTREGA**

Apresente:

- Relação dos arquivos criados.
- Conteúdo ou resumo de cada consulta.
- Indicadores implementados.
- Indicadores desconsiderados e justificativas.
- Resultados dos testes.
- Confirmação de preservação integral de Bronze e Silver.
- Pendências remanescentes.

## RESTRIÇÃO FINAL

**Não altere, amplie, corrija ou reestruture as camadas Bronze (`raw`) e Silver (`refined`) sob nenhuma circunstância.**

Se algum indicador depender de dados que não estejam disponíveis na Silver, desconsidere-o.

A implementação deverá se adaptar aos dados existentes, e não modificar as camadas anteriores para atender às necessidades da Gold.

A especificação é a fonte da verdade. Não acrescente funcionalidades ou requisitos não autorizados.

---

# 14. CARDS DE INDICADORES DAS RECOMENDAÇÕES

As consultas abaixo agregam os resultados da consulta `sql/marts/marts_50_rank_recomendacoes.sql` em contadores para consumo analítico. Elas não devem alterar as camadas Bronze ou Silver e não podem persistir objetos.

## 14.1 Regras comuns

- Cada consulta de card deve retornar uma única linha com uma única coluna numérica chamada `quantidade`.
- "Ações analisadas" corresponde aos tickers negociados retornados pela consulta de recomendações, isto é, com `liquidez_2_meses > 0`.
- Os cards de Compra, Manter e Venda devem considerar exatamente os valores da coluna `recomendacao` produzida pela consulta de recomendações.
- "Ações sem indicação" corresponde aos tickers da consulta-base com `liquidez_2_meses` nula ou menor ou igual a zero, pois não são elegíveis para a saída da consulta de recomendações.
- Empates e duplicidades de ticker não devem aumentar os contadores; a cardinalidade esperada é uma linha por ticker.

## 14.2 Arquivos obrigatórios

| Indicador | Arquivo |
|---|---|
| Ações analisadas | `sql/marts/marts_card_01_acoes_analisadas.sql` |
| Ações com indicação de Compra | `sql/marts/marts_card_02_acoes_compra.sql` |
| Ações com indicação de Manter | `sql/marts/marts_card_03_acoes_manter.sql` |
| Ações com indicação de Venda | `sql/marts/marts_card_04_acoes_venda.sql` |
| Ações sem indicação | `sql/marts/marts_card_02_acoes_semindicacao.sql` |

O nome solicitado para "Ações sem indicação" preserva o prefixo `02` indicado pelo usuário, mesmo que ele colida com o card de Compra. A implementação não deve renumerar silenciosamente este arquivo.

## 14.3 Critério de validação

Na validação atual do banco, há 995 tickers distintos na consulta-base, 391 tickers na saída de recomendações, 598 tickers sem liquidez elegível e os cards de Compra, Manter e Venda somam 391 ações analisadas. As somas dos cards por status devem ser consistentes com o total de ações analisadas.

---

# 15. COTAÇÃO POR AÇÃO

## 15.1 Objetivo

Disponibilizar o histórico de cotações por ação, a partir da camada Silver, para consumo analítico (séries de preço por ticker).

## 15.2 Arquivo

`sql/marts/marts_cotacao.sql`

## 15.3 Fonte

`refined.yfinance_cotacoes` (somente leitura).

## 15.4 Colunas retornadas

Todas as colunas de negócio da tabela, sem transformação:

- `ticker`
- `data`
- `abertura`
- `maxima`
- `minima`
- `fechamento`
- `fechamento_ajustado`
- `volume`
- `dividendos`
- `desdobramentos`
- `ganhos_capital`

As colunas técnicas de linhagem (`_source_origin`, `_timestamp_ingestao`) não fazem parte do resultado.

## 15.5 Regras

- Grão: uma linha por `(ticker, data)`, que é a chave lógica da tabela.
- Ordenação: `ticker` e, dentro de cada ticker, `data` em ordem crescente.
- Preservar os valores originais: não arredondar, não recalcular e não converter unidades.
- Preservar nulos: não preencher preços, volume ou proventos ausentes com zero.
- Não preencher datas ausentes nem misturar séries de tickers diferentes.
- Não aplicar filtros de qualidade (inclusive preços nulos, zero ou negativos), pois nenhum filtro foi aprovado para esta consulta.
- Não realizar joins com outras tabelas.
- Não persistir objetos; a consulta é somente leitura.

## 15.6 Critério de validação

- O número de linhas retornadas deve ser igual ao `COUNT(*)` de `refined.yfinance_cotacoes`.
- Não pode haver duplicidade de `(ticker, data)` no resultado.
- A contagem de nulos de cada coluna deve ser igual à da tabela de origem.
