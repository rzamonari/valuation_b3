# SPEC — Implementação dos 10 Rankings Fundamentalistas de Ações B3

## 1. Objetivo

Implementar uma camada Gold, seguindo a arquitetura Medallion já existente no projeto, para disponibilizar 10 rankings fundamentalistas de ações negociadas na B3.

Os rankings devem ser construídos exclusivamente a partir dos dados já disponíveis na camada Silver (`refined`) do DuckDB.

O objetivo é apresentar indicadores e classificações de forma clara, consistente e compreensível, inclusive para investidores iniciantes, permitindo comparar empresas sob diferentes perspectivas fundamentalistas.

Complementarmente, os 10 rankings deverão ser consolidados em uma consulta de recomendações por empresa, com os status `Compra`, `Manter` e `Venda`, conforme a seção 7.

A implementação deverá respeitar integralmente a arquitetura atual do projeto, sem modificar as camadas Bronze e Silver.

## 2. Diretrizes obrigatórias de implementação

### 2.1. Arquitetura e tecnologias

- Linguagem: Python 3.13.
- Gerenciador de dependências: `uv`.
- Banco de dados: DuckDB local, arquivo `fundamentalistas.duckdb` na raiz do projeto.
- Arquitetura: Medallion.
- Bronze: schema `raw`.
- Silver: schema `refined`.
- Gold: consultas e resultados analíticos, organizados em marts.

### 2.2. Restrições absolutas

A implementação deverá:

1. Consumir exclusivamente tabelas existentes no schema `refined`.
2. Não modificar nenhuma tabela, coluna ou estrutura do schema `raw`.
3. Não modificar nenhuma tabela, coluna ou estrutura do schema `refined`.
4. Não alterar os processos de ingestão ou transformação existentes.
5. Não criar novas fontes de dados, integrações ou dependências externas.
6. Não implementar indicadores que dependam de informações inexistentes na Silver.
7. Não preencher valores nulos com zero.
8. Não criar aproximações para substituir dados ausentes.
9. Não alterar a precisão decimal dos dados de origem sem necessidade.
10. Não utilizar `DISTINCT` para mascarar duplicidades decorrentes de joins.
11. Não alterar arquivos existentes sem antes avaliar o impacto e apresentar o diagnóstico.

**A camada Silver é considerada estável e não deverá ser modificada em hipótese alguma nesta implementação.**

## 3. Diagnóstico obrigatório antes de implementar

Antes de escrever qualquer código ou SQL, inspecione a estrutura atual do projeto.

Verifique:

- Organização dos diretórios.
- Arquivos Python existentes.
- Funcionamento de `pipeline/db.py`.
- Forma de conexão com o DuckDB.
- Existência e funcionamento dos schemas.
- Existência dos diretórios de SQL.
- Estrutura real das tabelas Silver.
- Tipos de dados das colunas utilizadas.
- Cardinalidade das chaves utilizadas nos joins.
- Existência de duplicidades que possam multiplicar os registros.
- Compatibilidade dos nomes de colunas utilizados nas consultas.

Não presuma que funções, tabelas ou colunas existem apenas porque foram mencionadas nesta SPEC.

### 3.1. Tabelas autorizadas

As consultas Gold poderão utilizar exclusivamente:

- `refined.fundamentus_acoes`
- `refined.b3_empresas`
- `refined.minhareceita_empresas`

As demais tabelas Silver não deverão ser utilizadas nesta entrega, salvo se houver necessidade expressamente aprovada posteriormente.

### 3.2. Colunas autorizadas de Fundamentus

A tabela `refined.fundamentus_acoes` disponibiliza, entre outras, as seguintes colunas:

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

A tabela `refined.b3_empresas` disponibiliza:

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

A tabela `refined.minhareceita_empresas` contém os dados cadastrais das empresas, incluindo propriedades escalares provenientes da fonte Minha Receita.

**Importante:** os nomes reais das colunas de Minha Receita deverão ser validados diretamente no DuckDB antes da implementação. Não criar nomes de colunas presumidos.

## 4. Consulta-base obrigatória

Todos os rankings deverão preservar os joins da consulta-base:

```sql
FROM refined.fundamentus_acoes a

INNER JOIN refined.b3_empresas b
    ON b.empresa_emissora = SUBSTRING(a.ticker, 1, 4)

LEFT JOIN refined.minhareceita_empresas c
    ON c.cnpj = b.cnpj
```

Os joins não deverão ser modificados sem autorização.

A consulta-base deverá disponibilizar, quando existentes e validados:

- `ticker`
- `empresa`
- `razao_social`
- `segmento`
- `atividade`
- `mercado`
- `municipio`
- `uf`
- `natureza_juridica`
- `data_inicio_atividade`
- `situacao`

E os indicadores necessários para cada ranking.

**Atenção:** `b.segmento` representa o segmento de listagem da B3. Não deverá ser tratado como setor econômico.

## 5. Regras gerais de cálculo e classificação

### 5.1. Indicadores já disponíveis

Quando o indicador estiver pronto na tabela `refined.fundamentus_acoes`, deverá ser utilizado diretamente.

Não recalcular indicadores já fornecidos pelo Fundamentus sem necessidade expressamente justificada.

### 5.2. Indicadores calculados

Quando um indicador não estiver pronto, poderá ser calculado somente se todos os seus insumos estiverem disponíveis na Silver e sua fórmula estiver definida nesta SPEC.

Se os dados necessários não estiverem disponíveis, o indicador deverá ser desconsiderado.

### 5.3. Percentuais

Os indicadores percentuais provenientes do Fundamentus estão armazenados na escala de 0 a 100.

Exemplos:

- ROE = 15 significa 15%.
- ROIC = 12 significa 12%.
- Dividend Yield = 6 significa 6%.
- Margem EBIT = 20 significa 20%.

Não converter esses valores para escala decimal.

### 5.4. Segurança das operações

- Utilizar `NULLIF` em todas as divisões.
- Não converter valores nulos em zero.
- Excluir valores inválidos conforme os critérios de cada ranking.
- Não aceitar múltiplos negativos quando o ranking exigir múltiplos positivos.
- Preservar valores negativos de Dívida Líquida/Patrimônio Líquido, pois podem representar posição de caixa líquido.
- Evitar duplicidade de registros nos resultados.

### 5.5. Critério de classificação

Utilizar `DENSE_RANK()` para gerar as classificações.

Os critérios quantitativos deverão estar explicitamente definidos em cada consulta.

Quando houver composição de mais de um indicador, utilizar ranks individuais e, quando previsto nesta SPEC, somar os ranks para formar a classificação composta.

Não inventar pesos, médias ou pontuações arbitrárias.

## 6. Os 10 rankings

### 01 — Rank Valor

**Objetivo:** identificar empresas com boa rentabilidade sobre o capital investido e preço atrativo em relação ao resultado operacional.

**Conceito:** versão simplificada da Magic Formula.

Indicadores:

- ROIC.
- EV/EBIT.

Critérios de elegibilidade:

- ROIC maior que zero.
- EV/EBIT maior que zero.
- Ambos os indicadores não nulos.

Classificação:

1. Rank individual de ROIC, em ordem decrescente.
2. Rank individual de EV/EBIT, em ordem crescente.
3. Somar os dois ranks.
4. Gerar o rank final em ordem crescente da soma.

A menor soma representa a melhor classificação.

Não apresentar este cálculo como reprodução exata da metodologia original de Joel Greenblatt. Trata-se de uma versão simplificada, limitada aos indicadores disponíveis.

Arquivo:

`sql/marts/marts_01_rank_valor.sql`

### 02 — Rank Proventos

**Objetivo:** identificar empresas com Dividend Yield positivo e uma relação indicativa equilibrada entre distribuição de dividendos e lucro.

Indicadores:

- Dividend Yield.
- P/L.
- Payout estimado.

Fórmula:

```sql
payout = dividend_yield * preco_lucro
```

A fórmula utiliza o Dividend Yield e o P/L em suas escalas originais. O resultado representa um payout estimado em percentual.

Critérios de elegibilidade:

- Dividend Yield maior que zero.
- P/L maior que zero.
- Payout maior ou igual a zero.
- Payout menor ou igual a 100%.

Classificação:

1. Dividend Yield em ordem decrescente.
2. Payout em ordem crescente.

Utilizar `DENSE_RANK()` com os critérios acima, nesta ordem.

**Limitação:** o payout estimado não comprova a sustentabilidade futura dos dividendos, a recorrência dos pagamentos ou a capacidade de geração de caixa da empresa. Não afirmar que o indicador garante sustentabilidade.

Arquivo:

`sql/marts/marts_02_rank_proventos.sql`

### 03 — Rank Eficiência

**Objetivo:** identificar empresas com maior eficiência operacional e capacidade de transformar receita em lucro.

Indicadores:

- Margem EBIT.
- Margem líquida.

Critérios de elegibilidade:

- Margem EBIT maior que zero.
- Margem líquida maior que zero.
- Ambos os indicadores não nulos.

Classificação:

1. Margem EBIT em ordem decrescente.
2. Margem líquida em ordem decrescente.

Utilizar `DENSE_RANK()` com ordenação lexicográfica, sem criar média ou peso entre os indicadores.

Arquivo:

`sql/marts/marts_03_rank_eficiencia.sql`

### 04 — Rank Retorno

**Objetivo:** identificar empresas com maior retorno sobre o patrimônio líquido, considerando um limite de alavancagem financeira.

Indicadores:

- ROE.
- Dívida Líquida/Patrimônio Líquido.

Critérios de elegibilidade:

- ROE maior que zero.
- Dívida Líquida/Patrimônio Líquido não nula.
- Dívida Líquida/Patrimônio Líquido menor ou igual a 1,5.

Classificação:

1. ROE em ordem decrescente.
2. Dívida Líquida/Patrimônio Líquido em ordem crescente.

Utilizar `DENSE_RANK()`.

O limite de 1,5 será adotado como critério conservador para esta versão dos rankings.

Não calcular Dívida Líquida/EBITDA, pois a Silver não disponibiliza a dívida líquida necessária para esse cálculo.

Arquivo:

`sql/marts/marts_04_rank_retorno.sql`

### 05 — Rank Pechincha

**Objetivo:** identificar empresas com múltiplos de avaliação positivos e relativamente baixos.

Indicadores:

- P/L.
- EV/EBIT.

Critérios de elegibilidade:

- P/L maior que zero.
- EV/EBIT maior que zero.
- Ambos os indicadores não nulos.

Classificação:

1. Rank individual de P/L em ordem crescente.
2. Rank individual de EV/EBIT em ordem crescente.
3. Somar os dois ranks.
4. Gerar rank final em ordem crescente da soma.

Não somar diretamente os múltiplos originais, pois possuem escalas diferentes.

Não estabelecer limites máximos arbitrários para P/L ou EV/EBIT.

Arquivo:

`sql/marts/marts_05_rank_pechincha.sql`

### 06 — Rank Patrimônio

**Objetivo:** identificar empresas com relação atrativa entre preço sobre valor patrimonial e retorno sobre o patrimônio.

Indicadores:

- P/VP.
- ROE.

Fórmula:

```sql
preco_valor_patrimonial / NULLIF(roe, 0)
```

Critérios de elegibilidade:

- P/VP maior que zero.
- ROE maior que zero.
- Ambos os indicadores não nulos.

Classificação:

- Resultado da divisão em ordem crescente.

Utilizar `DENSE_RANK()`.

A fórmula deverá respeitar a escala percentual original do ROE, de 0 a 100.

Não calcular preço justo pelo modelo de Gordon ou qualquer outra metodologia não definida nesta SPEC.

Arquivo:

`sql/marts/marts_06_rank_patrimonio.sql`

### 07 — Rank Crescimento

**Objetivo:** identificar empresas com maior crescimento de receita nos últimos cinco anos, exigindo rentabilidade mínima sobre o capital investido.

Indicadores:

- Crescimento da Receita em 5 anos.
- ROIC.

Critérios de elegibilidade:

- Crescimento da Receita em 5 anos não nulo.
- ROIC maior que 10%.
- ROIC não nulo.

Classificação:

- Crescimento da Receita em 5 anos em ordem decrescente.

Utilizar o indicador já disponibilizado pelo Fundamentus.

Não recalcular CAGR, pois o indicador já existe na Silver e não há necessidade de reconstruí-lo.

Arquivo:

`sql/marts/marts_07_rank_crescimento.sql`

### 08 — Rank Operacional

**Objetivo:** identificar empresas com maior margem operacional.

Indicador:

- Margem EBIT.

Critérios de elegibilidade:

- Margem EBIT maior que zero.
- Margem EBIT não nula.

Classificação:

- Margem EBIT em ordem decrescente.

**Limitação obrigatória:** a camada Silver não disponibiliza Fluxo de Caixa Operacional. Portanto, não será implementada a dimensão de geração de caixa operacional.

Não utilizar EBITDA como substituto do Fluxo de Caixa Operacional.

O ranking deverá ser entregue exclusivamente com a Margem EBIT, sem criar indicadores aproximados.

Arquivo:

`sql/marts/marts_08_rank_operacional.sql`

### 09 — Rank Seguro

**Objetivo:** identificar empresas com menor alavancagem financeira e rentabilidade positiva.

Indicadores:

- Dívida Líquida/Patrimônio Líquido.
- ROIC.
- ROE.

Critérios de elegibilidade:

- Dívida Líquida/Patrimônio Líquido não nula.
- Dívida Líquida/Patrimônio Líquido menor ou igual a 1,5.
- ROIC maior que zero.
- ROE maior que zero.

Classificação:

1. Dívida Líquida/Patrimônio Líquido em ordem crescente.
2. ROIC em ordem decrescente.
3. ROE em ordem decrescente.

Utilizar `DENSE_RANK()`.

Preservar valores negativos de Dívida Líquida/Patrimônio Líquido, pois podem representar caixa líquido.

**Limitação:** o ranking avalia apenas os indicadores disponíveis. Não representa uma avaliação completa de risco de crédito, liquidez ou solvência.

Arquivo:

`sql/marts/marts_09_rank_seguro.sql`

### 10 — Rank Rentabilidade

**Objetivo:** identificar empresas com maior retorno do lucro em relação ao preço da ação.

Indicadores:

- P/L.
- Earnings Yield.

Fórmula:

```sql
100.0 / NULLIF(preco_lucro, 0)
```

Critérios de elegibilidade:

- P/L maior que zero.
- P/L não nulo.

Classificação:

- Earnings Yield em ordem decrescente.

Utilizar `DENSE_RANK()`.

O Earnings Yield deverá ser apresentado em percentual, respeitando a escala de 0 a 100.

Arquivo:

`sql/marts/marts_10_rank_rentabilidade.sql`

## 7. Recomendações consolidadas (Compra / Manter / Venda)

**Objetivo:** consolidar os 10 rankings em uma única recomendação por ticker, compreensível para o investidor iniciante, ordenada da melhor (`Compra`) para a pior (`Venda`), com `Manter` no meio.

**Princípio:**

- Melhores classificações nos 10 rankings → `Compra`.
- Classificações neutras → `Manter`.
- Piores classificações → `Venda`.

Arquivo:

`sql/marts/marts_50_rank_recomendacoes.sql`

### 7.1. Reprodução dos rankings

A consulta deverá ser autocontida (sem depender da execução de outro arquivo) e reproduzir, sobre a consulta-base da seção 4, exatamente a mesma elegibilidade e o mesmo `DENSE_RANK()` de cada um dos 10 rankings da seção 6.

O rank de cada ticker em cada ranking deverá ser idêntico ao retornado pelo arquivo individual correspondente. Qualquer alteração futura em um ranking individual deverá ser replicada em `marts_50_rank_recomendacoes.sql`.

### 7.2. Faixa de cada ticker em cada ranking

Para cada um dos 10 rankings, cada ticker da consulta-base recebe uma faixa, calculada pela posição relativa do seu rank em relação ao maior rank daquele ranking (`max_rank`):

| Faixa | Regra | Pontos |
|---|---|---|
| `Superior` | `(rank - 1) * 3 < (max_rank - 1)`, ou `max_rank = 1` (terço melhor) | +1 |
| `Intermediário` | demais casos elegíveis (terço do meio) | 0 |
| `Inferior` | `(rank - 1) * 3 > 2 * (max_rank - 1)` (terço pior) | −1 |
| `Não elegível` | ticker não atende aos critérios de elegibilidade do ranking | −1 |

Regras:

- A faixa é calculada sobre o rank (`DENSE_RANK`), e não com `NTILE`, para que tickers empatados (ex.: classes ON/PN da mesma emissora) fiquem sempre na mesma faixa.
- A comparação é feita em aritmética inteira, sem divisões.
- `Não elegível` conta como pior classificação, pois a elegibilidade de cada ranking exclui justamente os casos desfavoráveis naquela perspectiva (ROIC/ROE/margens não positivos, múltiplos não positivos, Dívida Líquida/PL acima de 1,5, ausência de dividendos etc.). Tratá-lo como neutro faria empresas reprovadas em todos os rankings receberem `Manter`.

### 7.3. Saldo e recomendação

Para cada ticker:

- `qtd_superior`, `qtd_intermediario`, `qtd_inferior`, `qtd_nao_elegivel`: contagem de faixas nos 10 rankings (a soma das quatro é sempre 10).
- `saldo = qtd_superior - qtd_inferior - qtd_nao_elegivel` (de −10 a +10).

Recomendação:

| Status | Regra | Leitura para o investidor iniciante |
|---|---|---|
| `Compra` | `saldo > 0` | Ficou entre as melhores em mais rankings do que entre as piores. |
| `Manter` | `saldo = 0` | Resultados bons e ruins se equilibram. |
| `Venda` | `saldo < 0` | Ficou entre as piores (ou não se qualificou) em mais rankings do que entre as melhores. |

Não criar pesos entre rankings: todos os 10 rankings têm o mesmo peso.

### 7.4. Universo e ordenação

- Universo de cálculo dos ranks: a consulta-base completa (mesmo universo dos 10 rankings individuais).
- Universo de saída: somente tickers com `liquidez_2_meses > 0`. Tickers sem negociação nos últimos dois meses não recebem recomendação, pois o investidor não conseguiria executá-la.
- Ordenação: `saldo` decrescente, depois `qtd_superior` decrescente, depois `ticker`. Como o status é determinado pelo sinal do saldo, essa ordem posiciona `Compra` no topo, `Manter` no meio e `Venda` no final.
- Coluna `posicao`: `DENSE_RANK() OVER (ORDER BY saldo DESC, qtd_superior DESC)`.

### 7.5. Colunas de saída

- `posicao`
- `recomendacao`
- `ticker`, `empresa`, `razao_social`, `segmento`, `atividade`, `mercado`, `municipio`, `uf`, `natureza_juridica`, `data_inicio_atividade`, `situacao`
- `cotacao`, `liquidez_2_meses`
- `saldo`, `qtd_superior`, `qtd_intermediario`, `qtd_inferior`, `qtd_nao_elegivel`
- Uma coluna de faixa por ranking, para auditoria: `faixa_valor`, `faixa_proventos`, `faixa_eficiencia`, `faixa_retorno`, `faixa_pechincha`, `faixa_patrimonio`, `faixa_crescimento`, `faixa_operacional`, `faixa_seguro`, `faixa_rentabilidade`.

### 7.6. Limitação obrigatória

A recomendação é um sinal **relativo e mecânico**, derivado exclusivamente dos 10 rankings, de uma única fotografia dos indicadores do Fundamentus. Não considera preço-alvo, valor intrínseco, histórico, perspectivas, governança, contexto setorial ou o perfil do investidor, e **não constitui recomendação de investimento**. O cabeçalho do SQL e a documentação deverão deixar isso explícito.

## 8. Estrutura dos arquivos SQL

Criar os seguintes arquivos individualizados:

```text
sql/
â””â”€â”€ marts/
    â”œâ”€â”€ marts_01_rank_valor.sql
    â”œâ”€â”€ marts_02_rank_proventos.sql
    â”œâ”€â”€ marts_03_rank_eficiencia.sql
    â”œâ”€â”€ marts_04_rank_retorno.sql
    â”œâ”€â”€ marts_05_rank_pechincha.sql
    â”œâ”€â”€ marts_06_rank_patrimonio.sql
    â”œâ”€â”€ marts_07_rank_crescimento.sql
    â”œâ”€â”€ marts_08_rank_operacional.sql
    â”œâ”€â”€ marts_09_rank_seguro.sql
    â”œâ”€â”€ marts_10_rank_rentabilidade.sql
    â””â”€â”€ marts_50_rank_recomendacoes.sql
```

Cada arquivo deverá:

1. Conter cabeçalho descritivo.
2. Informar o objetivo do ranking.
3. Descrever os indicadores utilizados.
4. Documentar as regras de elegibilidade.
5. Documentar a fórmula dos indicadores calculados.
6. Apresentar a consulta SQL completa.
7. Ser executável diretamente no DuckDB.
8. Utilizar nomes de colunas claros e consistentes.
9. Retornar o rank final e os indicadores utilizados para sua composição.
10. Manter as informações cadastrais da consulta-base, quando disponíveis.

Os arquivos deverão ser SQLs de consulta, sem comandos que alterem as tabelas Bronze ou Silver.

## 9. Estrutura recomendada dos resultados

Cada ranking deverá apresentar, sempre que aplicável:

- `rank`
- `ticker`
- `empresa`
- `razao_social`
- `segmento`
- `atividade`
- `mercado`
- `municipio`
- `uf`
- `situacao`
- Indicadores utilizados no ranking.

Nos rankings compostos, apresentar também os ranks individuais e a soma dos ranks, para permitir auditoria e compreensão da classificação.

Os campos cadastrais de Minha Receita deverão ser incluídos somente após validação dos nomes reais das colunas.

A estrutura de saída de `marts_50_rank_recomendacoes.sql` é definida na seção 7.5.

## 10. Validação técnica e testes obrigatórios

Após implementar os dez SQLs, executar testes de validação.

### 10.1. Validação estrutural

- Confirmar que os dez arquivos foram criados nos caminhos especificados.
- Confirmar que todos os arquivos possuem SQL válido para DuckDB.
- Confirmar que todos os rankings utilizam as tabelas autorizadas.
- Confirmar que não há referências a fontes externas.
- Confirmar que não há comandos de alteração das tabelas Bronze ou Silver.

### 10.2. Validação dos cálculos

Testar:

- Divisões por zero.
- Valores nulos.
- Múltiplos negativos.
- ROE e ROIC negativos.
- Dívida Líquida/PL negativa.
- Payout acima de 100%.
- Empresas sem dados cadastrais completos.
- Tickers sem correspondência na B3.
- Empates nos critérios de classificação.

### 10.3. Validação de cardinalidade

Verificar se os joins provocam multiplicação de registros.

Em especial:

- `b.empresa_emissora` deve ser avaliada quanto à unicidade.
- `b.cnpj` deve ser avaliado quanto à unicidade.
- `c.cnpj` deve ser avaliado quanto à unicidade.

Se houver duplicidade que provoque multiplicação de registros, não aplicar `DISTINCT` automaticamente.

Apresentar o diagnóstico e solicitar definição da regra de relacionamento antes de implementar uma solução que altere a cardinalidade.

### 10.4. Validação dos resultados

Executar individualmente os dez SQLs e verificar:

- Quantidade de registros retornados.
- Ausência de duplicidades indevidas.
- Coerência dos critérios de ordenação.
- Coerência dos ranks.
- Ausência de valores inválidos nos indicadores calculados.

Se algum SQL não puder ser executado devido à ausência de coluna ou dado, não modificar a Silver para resolver o problema. Apresentar a limitação e solicitar orientação.

### 10.5. Validação das recomendações

Executar `marts_50_rank_recomendacoes.sql` e verificar:

- Uma linha por ticker, sem duplicidades.
- Todos os tickers da saída com `liquidez_2_meses > 0`.
- Para cada um dos 10 rankings, o rank reproduzido é idêntico ao do arquivo individual (mesmos tickers elegíveis e mesmo rank).
- `qtd_superior + qtd_intermediario + qtd_inferior + qtd_nao_elegivel = 10` em todas as linhas.
- `saldo` coerente com as contagens e `recomendacao` coerente com o sinal do saldo.
- Ordenação: nenhum `Manter` antes de um `Compra` e nenhum `Venda` antes de um `Manter`.
- Distribuição de tickers por status.

## 11. Documentação das limitações

A documentação final deverá deixar explícito:

1. O Rank Valor é uma versão simplificada da Magic Formula.
2. O Rank Proventos utiliza payout estimado e não comprova sustentabilidade futura dos dividendos.
3. O Rank Operacional não contempla geração de caixa operacional porque esse dado não está disponível na Silver.
4. Não existe cálculo de Dívida Líquida/EBITDA nesta entrega.
5. O Rank Seguro não representa análise completa de solvência ou risco de crédito.
6. Os rankings individuais são classificações relativas entre empresas elegíveis.
7. As recomendações `Compra`, `Manter` e `Venda` são um sinal relativo e mecânico derivado dos 10 rankings (seção 7.6) e não constituem recomendação de investimento.

## 12. Entrega final

Ao concluir, apresentar:

1. Diagnóstico inicial da estrutura do projeto.
2. Confirmação das tabelas e colunas efetivamente utilizadas.
3. Relação dos dez arquivos SQL criados.
4. Conteúdo ou referência de cada consulta.
5. Resultado dos testes de execução.
6. Quantidade de registros retornados por ranking.
7. Problemas de cardinalidade encontrados.
8. Limitações identificadas.
9. Confirmação expressa de que os schemas `raw` e `refined` não foram modificados.
10. Distribuição das recomendações por status e resultado da validação da seção 10.5.

## 13. Ordem de execução do trabalho

Seguir rigorosamente esta sequência:

**Etapa 1 — Diagnóstico**

Inspecionar o projeto, o DuckDB, as tabelas e as colunas reais. Não implementar nada nesta etapa.

**Etapa 2 — Apresentação do diagnóstico**

Apresentar o que foi encontrado, eventuais incompatibilidades e riscos de cardinalidade. Se houver divergência relevante em relação à SPEC, interromper e solicitar orientação.

**Etapa 3 — Implementação**

Criar os dez arquivos SQL em `sql/marts/`, respeitando integralmente as regras definidas. Em seguida, criar `sql/marts/marts_50_rank_recomendacoes.sql` conforme a seção 7.

**Etapa 4 — Testes**

Executar os dez SQLs individualmente e validar os resultados. Em seguida, executar `marts_50_rank_recomendacoes.sql` e aplicar a validação da seção 10.5.

**Etapa 5 — Relatório final**

Apresentar os arquivos criados, os resultados dos testes e confirmar que nenhuma estrutura de Bronze ou Silver foi alterada.

---

**REGRA FINAL:** Não interpretar esta SPEC como autorização para ampliar o escopo. Não criar novas fontes, indicadores, tabelas ou colunas. Não modificar a ingestão, a transformação ou a camada Silver. Em caso de dúvida sobre uma regra de negócio ou incompatibilidade técnica, interromper a implementação e solicitar esclarecimento antes de tomar decisões por conta própria.