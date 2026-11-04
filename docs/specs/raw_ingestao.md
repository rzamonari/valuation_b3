# SPEC TÉCNICA — CAMADA RAW (BRONZE)
## Pipeline de Indicadores Fundamentalistas

**Versão:** 1.1 (M6.1–M6.4: consulta Minha Receita com CNPJ complementado apenas na URL)  
**Stack:** Python 3.13 + uv + DuckDB  
**Arquitetura:** Medallion Architecture  
**Escopo:** Exclusivamente camada Raw/Bronze

---

# 1. CONTEXTO E STACK TECNOLÓGICA

Estou construindo um pipeline de Engenharia de Dados em Python para consolidação de informações fundamentalistas e cadastrais das empresas listadas na B3, incluindo histórico diário de cotações.

O projeto segue a arquitetura Medallion, com separação entre as camadas:

- **Bronze (Raw):** ingestão e preservação dos dados recebidos das fontes originais.
- **Silver (Refined):** tratamento, limpeza, tipagem, padronização e validação dos dados.
- **Gold (Marts):** construção de indicadores, agregações e estruturas analíticas para consumo.

Esta especificação contempla exclusivamente a camada Bronze.

**Princípio fundamental:** a camada Bronze deve preservar os dados em seu estado mais bruto possível, sem tratamento de negócio, limpeza, normalização ou alteração dos valores recebidos.

A especificação é a fonte da verdade para o desenvolvimento. Nenhuma regra de negócio ou transformação não documentada poderá ser introduzida durante a implementação.

## 1.1. Stack tecnológica

- Python 3.13.
- Gerenciamento de dependências com `uv`.
- DuckDB como banco de dados analítico local.
- Arquivo de banco: `fundamentalistas.duckdb`, localizado na raiz do projeto.
- Biblioteca `yfinance` para extração do histórico de cotações.
- Requisições HTTP para as fontes B3 e Fundamentus.
- Consumo da API pública Minha Receita.
- Execução por linha de comando.
- Nenhum orquestrador complexo.

## 1.2. Estrutura de diretórios

Estrutura de referência:

```text
projeto/
│
├── pipeline/
│   ├── __init__.py
│   ├── db.py
│   └── ingestao.py
│
├── raw/
│   └── (artefatos brutos ou locais de apoio)
│
├── fundamentalistas.duckdb
│
├── pyproject.toml
└── uv.lock
```

O arquivo DuckDB deverá ser criado automaticamente na raiz do projeto quando a conexão for solicitada.

## 1.3. Responsabilidades

O projeto terá dois módulos independentes:

**pipeline/db.py**

Responsável exclusivamente pela infraestrutura de conexão, criação de schemas e persistência genérica dos dados.

**pipeline/ingestao.py**

Responsável pela extração das fontes externas, aplicação das regras de preservação Bronze, gerenciamento das falhas e gravação dos dados.

O módulo de banco não poderá conhecer regras específicas das fontes de dados.

---

# 2. SPEC DO MÓDULO pipeline/db.py

## 2.1. O que o módulo expõe

O módulo deverá expor exatamente:

```python
PASTA_RAW
conectar()
criar_schema(con, nome)
gravar(con, df, schema, tabela)
```

Não deverá conter regras de negócio, mapeamentos de fontes ou rotinas de ingestão.

## D1. RESOLUÇÃO DOS CAMINHOS

`PASTA_RAW` e o arquivo `fundamentalistas.duckdb` deverão ser resolvidos a partir da localização física do próprio `db.py`, considerando a raiz do projeto como a pasta imediatamente acima de `pipeline/`.

O diretório corrente do terminal não poderá influenciar a localização do banco.

**Motivação técnica:**

Evita que a execução do pipeline a partir de outra pasta crie arquivos DuckDB vazios ou duplicados em locais diferentes, mascarando falhas de ingestão e comprometendo a confiabilidade do ambiente.

## D2. ISOLAMENTO DE RESPONSABILIDADES

O módulo `db.py` não poderá:

- Realizar requisições HTTP.
- Consumir APIs.
- Ler ou interpretar HTML.
- Conhecer nomes de tabelas específicas das fontes.
- Executar transformações nos dados.
- Imprimir mensagens no terminal.
- Manter conexões globais.
- Implementar regras de negócio.

**Motivação técnica:**

O módulo deve funcionar como infraestrutura reutilizável. A concentração de regras específicas de ingestão em um módulo compartilhado cria dependências ocultas e dificulta a evolução independente das etapas do pipeline.

## D3. FUNÇÃO conectar()

Deverá abrir uma conexão com o arquivo:

`fundamentalistas.duckdb`

Se o arquivo não existir, deverá criá-lo automaticamente na raiz do projeto.

A função deverá devolver a conexão aberta.

O responsável por chamar `conectar()` será também responsável por fechar a conexão, inclusive em caso de exceção.

Não deverá existir conexão global compartilhada.

**Motivação técnica:**

O controle explícito do ciclo de vida da conexão evita conexões esquecidas, conflitos de escrita e problemas de bloqueio do arquivo DuckDB.

## D4. FUNÇÃO criar_schema()

Assinatura:

```python
criar_schema(con, nome)
```

Deverá executar:

```sql
CREATE SCHEMA IF NOT EXISTS nome;
```

O schema de destino desta especificação será:

```sql
raw
```

A função deverá ser genérica, sem assumir nomes específicos de schemas.

**Motivação técnica:**

Permite a criação idempotente da estrutura de armazenamento sem introduzir dependências entre a infraestrutura e as fontes de dados.

## D5. FUNÇÃO gravar()

Assinatura:

```python
gravar(con, df, schema, tabela)
```

Responsabilidades:

1. Receber uma estrutura tabular contendo os dados extraídos.
2. Gravar os dados no schema e tabela informados.
3. Utilizar a política `CREATE OR REPLACE TABLE`.
4. Preservar nomes de colunas e valores recebidos.
5. Garantir que as colunas de negócio sejam persistidas como `VARCHAR`.
6. Preservar valores nulos como `NULL`.
7. Não criar tabelas ou views temporárias permanentes.
8. Retornar a quantidade efetivamente gravada, consultada diretamente no DuckDB.

A contagem deverá ser obtida por consulta equivalente a:

```sql
SELECT COUNT(*)
FROM schema.tabela;
```

A função não poderá devolver simplesmente a quantidade de linhas existente no DataFrame em memória.

**Motivação técnica:**

A contagem precisa refletir o resultado efetivamente persistido no banco, e não uma estimativa baseada nos dados recebidos. Isso permite validar a integridade da gravação.

## D6. POLÍTICA DE REEXECUÇÃO

Todas as gravações deverão utilizar substituição integral da tabela:

```sql
CREATE OR REPLACE TABLE
```

Não será permitido utilizar inserções cumulativas para manter os registros de execuções anteriores.

**Motivação técnica:**

Garante idempotência. Uma nova execução representa uma nova fotografia dos dados disponibilizados pelas fontes, sem duplicação de registros.

## D7. TIPAGEM

Todas as colunas de negócio deverão ser armazenadas como `VARCHAR`.

Nenhuma inferência automática de tipos poderá ocorrer durante a persistência.

Os metadados de ingestão também deverão possuir representação textual.

**Motivação técnica:**

A inferência automática pode causar perdas irreversíveis, como remoção de zeros à esquerda, conversões indevidas de identificadores e alteração de representações originais.

A conversão para tipos analíticos pertence exclusivamente à camada Silver.

## D8. TRANSAÇÕES E CONEXÕES

O módulo deverá permitir que o processo de ingestão controle uma transação envolvendo as gravações das quatro fontes.

O módulo não deverá iniciar ou confirmar transações automaticamente dentro de `gravar()`.

A conexão será fechada pelo módulo responsável pela execução.

**Motivação técnica:**

Permite que o processo de ingestão controle a atomicidade do conjunto de tabelas, impedindo que uma falha deixe uma atualização parcialmente persistida.

## CRITÉRIOS DE ACEITE — db.py

- Importar `pipeline.db` não deverá criar o arquivo DuckDB.
- A função `conectar()` deverá criar o banco na raiz do projeto.
- A execução a partir de outro diretório deverá utilizar o mesmo arquivo.
- `criar_schema()` deverá criar o schema quando inexistente.
- Executar `criar_schema()` repetidamente não deverá provocar erro.
- `gravar()` deverá substituir a tabela existente.
- A contagem retornada deverá corresponder ao `COUNT(*)` do banco.
- As colunas de negócio deverão ser `VARCHAR`.
- Valores nulos deverão continuar nulos.
- Nenhuma conexão deverá permanecer aberta após o encerramento do processo.

---

# 3. SPEC DA INGESTÃO — pipeline/ingestao.py

## 3.1. Escopo e execução

O módulo deverá ser executável por linha de comando:

```bash
uv run python -m pipeline.ingestao
```

Schema de destino:

```sql
raw
```

Tabelas de destino:

```text
raw.b3_empresas
raw.fundamentus_acoes
raw.minhareceita_empresas
raw.yfinance_cotacoes
```

O script deverá executar a ingestão integral das quatro fontes.

Não deverá importar ou executar qualquer funcionalidade pertencente às futuras camadas Silver ou Gold.

## 3.2. MAPEAMENTO DAS FONTES

| Identificador | Origem | Destino |
|---|---|---|
| b3_empresas | Site oficial B3 | raw.b3_empresas |
| fundamentus_acoes | Fundamentus | raw.fundamentus_acoes |
| minhareceitaorg_dadosempresas | API Minha Receita | raw.minhareceita_empresas |
| yfinance_cotacoes | Yahoo Finance via yfinance | raw.yfinance_cotacoes |

## 3.3. ORDEM DE EXECUÇÃO

O fluxo deverá respeitar as seguintes etapas:

1. Configuração do ambiente de execução.
2. Validação prévia das fontes e dos pré-requisitos de extração.
3. Extração dos dados da B3.
4. Extração dos dados do Fundamentus.
5. Identificação dos CNPJs e tickers disponíveis na listagem da B3.
6. Consulta individual dos CNPJs na Minha Receita.
7. Consulta do histórico de cotações de cada ticker no yfinance.
8. Validação de sucesso integral das extrações.
9. Abertura da conexão de escrita no DuckDB.
10. Criação do schema `raw`.
11. Gravação transacional das quatro tabelas.
12. Commit da transação.
13. Impressão do relatório de execução.
14. Fechamento da conexão.

**Motivação técnica:**

Separar extração de persistência evita que uma falha em uma fonte externa deixe apenas parte das tabelas atualizadas.

---

# 4. ESPECIFICAÇÃO INDIVIDUAL DAS FONTES

## 4.1. FONTE: b3_empresas

**Identificador:** `b3_empresas`

**Origem:**

```text
https://www.b3.com.br/pt_br/produtos-e-servicos/negociacao/renda-variavel/empresas-listadas.htm
```

**Método:** HTTP GET.

**Destino:**

```sql
raw.b3_empresas
```

### Regras de extração

B1. Realizar requisição HTTP GET para o endereço oficial informado.

B2. Obter o conteúdo HTML disponibilizado pela fonte.

B3. Interpretar estruturalmente a tabela HTML para extrair seus registros e colunas.

B4. Preservar os nomes originais das colunas.

B5. Preservar os valores originais dos campos, sem correção ou padronização.

B6. Não realizar filtros, deduplicações ou descarte de registros.

B7. Persistir todas as colunas de negócio como `VARCHAR`.

B8. Disponibilizar os CNPJs e tickers extraídos da listagem para alimentar as consultas das fontes dependentes.

B9. Os dados originais da tabela persistida deverão permanecer inalterados. A identificação dos CNPJs e tickers deverá utilizar os campos correspondentes da fonte, sem modificar os valores armazenados.

**Motivação técnica:**

A listagem da B3 representa a referência cadastral utilizada pelas demais fontes. Sua preservação permite rastrear a origem dos identificadores utilizados na construção da base fundamentalista.

### Metadados

Adicionar:

- `_timestamp_ingestao`
- `_source_origin`

### Critério de aceite

A tabela deverá conter todos os registros tabulares obtidos da resposta processada da B3, com colunas de negócio `VARCHAR` e metadados de ingestão.

---

## 4.2. FONTE: fundamentus_acoes

**Identificador:** `fundamentus_acoes`

**Origem:**

```text
https://www.fundamentus.com.br/resultado.php
```

**Método:** HTTP GET.

**Destino:**

```sql
raw.fundamentus_acoes
```

### Regras de extração

F1. Realizar requisição HTTP GET para o endereço informado.

F2. Obter o HTML original retornado pelo servidor.

F3. Interpretar estruturalmente a tabela de indicadores fundamentalistas disponibilizada na página.

F4. Preservar os nomes originais das colunas.

F5. Preservar os valores apresentados pela fonte, inclusive suas representações textuais.

F6. Não converter indicadores financeiros em números.

F7. Não converter percentuais, múltiplos, datas ou demais campos.

F8. Não remover registros duplicados.

F9. Não realizar filtros ou seleção de indicadores.

F10. Persistir todas as colunas de negócio como `VARCHAR`.

**Motivação técnica:**

Os indicadores fundamentalistas constituem dados de origem. Converter valores, percentuais ou múltiplos durante a ingestão introduziria decisões de interpretação antes da camada responsável pelo tratamento analítico.

### Metadados

Adicionar:

- `_timestamp_ingestao`
- `_source_origin`

### Critério de aceite

A tabela deverá reproduzir os registros tabulares disponibilizados pela fonte, preservando as representações originais dos indicadores e utilizando `VARCHAR` nas colunas de negócio.

---

## 4.3. FONTE: minhareceitaorg_dadosempresas

**Identificador:** `minhareceitaorg_dadosempresas`

**Origem:**

```text
https://minhareceita.org/
```

**Método:** consumo da API pública por CNPJ.

**Destino:**

```sql
raw.minhareceita_empresas
```

### Regras de extração

M1. Utilizar os CNPJs obtidos da fonte `b3_empresas`.

M2. Realizar uma consulta individual para cada CNPJ identificado.

M3. Preservar o payload JSON retornado pela API.

M4. Não renomear os campos originais do JSON.

M5. Não converter tipos de dados.

M6. Não formatar ou corrigir CNPJs. O CNPJ persistido deverá ser idêntico ao valor obtido da fonte `b3_empresas` (ex.: `191` permanece `191`).

M6.1. A API Minha Receita exige o CNPJ com 14 dígitos, enquanto a B3 disponibiliza o campo sem os zeros à esquerda (ex.: `191` para `00000000000191`). Exclusivamente na montagem da URL de consulta, valores compostos apenas por dígitos e com menos de 14 posições deverão ser complementados com zeros à esquerda até 14 posições. O complemento é um requisito do mecanismo de consulta, equivalente ao sufixo `.SA` do yfinance (Y3), e não integra o identificador persistido. Valores com caracteres não numéricos deverão ser consultados exatamente como recebidos.

M6.2. O endereço efetivamente consultado (ex.: `https://minhareceita.org/00000000000191`) deverá ser registrado em `_source_origin`, garantindo a rastreabilidade entre o valor de origem e a consulta realizada.

M6.3. Valores vazios ou nulos não identificam um CNPJ e não deverão ser consultados. Valores idênticos deverão gerar uma única consulta.

M6.4. Respostas HTTP 400 ou 404 da API indicam que o identificador foi rejeitado pela fonte (ex.: `0`). Elas não constituem falha permanente da fonte (E2): não serão persistidas, mas a quantidade e a relação dos valores rejeitados deverão ser informadas no terminal. Qualquer outra falha definitiva de uma consulta, após o esgotamento das tentativas (E1), constitui falha permanente da fonte e deverá seguir E2.

M7. Não eliminar campos nulos.

M8. Não remover registros duplicados.

M9. Não realizar enriquecimento ou cruzamento com outras fontes durante a persistência.

M10. Armazenar o payload JSON original em representação textual, utilizando coluna `VARCHAR`.

M11. Identificar o CNPJ consultado e associar o respectivo payload à sua origem, sem modificar o conteúdo original retornado.

M12. Adicionar os metadados técnicos de ingestão.

**Motivação técnica:**

O payload JSON constitui o registro original da resposta da API. Preservá-lo integralmente permite que futuras etapas interpretem os dados de acordo com suas necessidades, sem comprometer a rastreabilidade da resposta original.

### Estrutura lógica de persistência

A tabela deverá possuir uma estrutura capaz de armazenar:

- `cnpj`: identificador exatamente como obtido da fonte `b3_empresas`, sem complemento de zeros.
- Payload JSON bruto.
- `_timestamp_ingestao`.
- `_source_origin`: URL efetivamente consultada (ex.: `https://minhareceita.org/00000000000191`).

O payload JSON deverá ser preservado como texto, sem decomposição ou conversão de seus campos de negócio na camada Bronze.

### Critério de aceite

Cada consulta concluída deverá possuir seu respectivo registro de persistência, mantendo o conteúdo JSON original e os metadados técnicos.

CNPJs disponibilizados pela B3 sem zeros à esquerda (ex.: `191`) deverão ser consultados com sucesso e persistidos com o valor original na coluna `cnpj`.

---

## 4.4. FONTE: yfinance_cotacoes

**Identificador:** `yfinance_cotacoes`

**Origem:** Yahoo Finance, por meio da biblioteca Python `yfinance`.

**Método:** extração por ticker.

**Destino:**

```sql
raw.yfinance_cotacoes
```

### Regras de extração

Y1. Utilizar os tickers identificados na listagem da B3.

Y2. Iterar individualmente sobre os tickers disponíveis.

Y3. Acrescentar o sufixo `.SA` a cada ticker antes da consulta. O sufixo é exclusivamente um requisito de consulta ao Yahoo Finance e não integra o identificador persistido (ver Y16).

Y4. Utilizar a biblioteca `yfinance` para obter o histórico de cotações.

Y5. Solicitar o histórico diário completo disponibilizado pela fonte para cada ticker, sem limitar a consulta aos últimos cinco anos ou a qualquer outra janela temporal fixa.

Y6. Não realizar cálculos sobre os preços.

Y7. Não calcular retornos, médias, volatilidade ou indicadores derivados.

Y8. Não realizar arredondamentos.

Y9. Não aplicar filtros ou deduplicações.

Y10. Preservar os nomes das colunas retornadas pela biblioteca.

Y11. Preservar a representação dos valores retornados, convertendo-os para texto para persistência em `VARCHAR`, sem arredondamento ou formatação adicional.

Y12. Preservar valores ausentes como nulos.

Y13. Não realizar ajustes adicionais nos preços ou nas séries históricas.

Y14. Não acrescentar registros históricos provenientes de execuções anteriores.

Y15. Acrescentar os metadados de ingestão.

Y16. Identificar cada registro pelo ticker exatamente como obtido da fonte `b3_empresas` (ex.: `PETR4`), sem o sufixo `.SA`. O símbolo efetivamente consultado no Yahoo Finance (ex.: `PETR4.SA`) deverá ser registrado em `_source_origin`.

**Motivação técnica:**

O histórico completo permite construir posteriormente séries temporais abrangentes, análises de valorização, retornos e indicadores de mercado.

A representação textual impede que a camada Bronze imponha tipos ou regras analíticas antes da camada Silver.

O ticker persistido deve ser idêntico ao identificador de origem da B3, permitindo o cruzamento direto entre as fontes nas camadas seguintes. O sufixo `.SA` é um artefato do mecanismo de consulta e, se gravado no identificador, constituiria uma alteração do dado de origem (I1).

### Estrutura lógica de persistência

A tabela deverá possuir uma estrutura capaz de armazenar:

- `ticker`: identificador do ticker conforme a fonte `b3_empresas`, sem sufixo.
- Colunas retornadas pela biblioteca `yfinance`, com seus nomes originais.
- `_timestamp_ingestao`.
- `_source_origin`: identificação da fonte acompanhada do símbolo consultado (ex.: `Yahoo Finance via yfinance: PETR4.SA`).

### Critério de aceite

A tabela deverá armazenar os registros diários retornados pelo yfinance para todos os tickers processados, respeitando o histórico completo disponibilizado pela fonte e a tipagem textual, com a coluna `ticker` idêntica ao identificador da B3 (sem o sufixo `.SA`).

---

# 5. REGRAS GERAIS DE IMUTABILIDADE

Esta seção estabelece as regras obrigatórias para todas as quatro fontes.

## I1. PROIBIÇÃO DE TRANSFORMAÇÕES

Não será permitido:

- Alterar nomes de colunas.
- Padronizar nomes de empresas.
- Corrigir valores.
- Corrigir CNPJs.
- Remover espaços.
- Alterar letras maiúsculas ou minúsculas.
- Normalizar acentos.
- Converter datas.
- Converter números.
- Converter percentuais.
- Arredondar valores.
- Preencher valores ausentes.
- Remover registros duplicados.
- Aplicar filtros de negócio.
- Calcular indicadores derivados.

**Motivação técnica:**

A camada Bronze deve representar a fronteira entre o dado recebido e o dado tratado.

Qualquer modificação prematura dificulta a auditoria e compromete a capacidade de reconstruir o dado original.

## I2. TIPAGEM ESTRITA

Todas as colunas de negócio deverão ser persistidas como:

```sql
VARCHAR
```

O payload JSON também deverá ser armazenado em texto.

Os metadados técnicos deverão possuir representação textual.

**Motivação técnica:**

A tipagem é uma decisão de interpretação. A Bronze não deverá assumir que determinado valor representa necessariamente um número, uma data ou outro tipo analítico.

## I3. PRESERVAÇÃO DE NULOS

Valores nulos deverão permanecer nulos.

Não será permitido substituir valores ausentes por:

- Zero.
- String vazia.
- Texto padrão.
- Valores estimados.

**Motivação técnica:**

A ausência de informação também é um dado. Substituí-la introduziria informação artificial que não existe na fonte.

## I4. METADADOS DE AUDITORIA

Todas as tabelas deverão conter os seguintes campos técnicos:

| Campo | Descrição |
|---|---|
| `_timestamp_ingestao` | Data e hora UTC da extração |
| `_source_origin` | Identificação da URL, API ou fonte de origem |

O timestamp deverá ser gerado em UTC no momento da extração.

O valor deverá ser representado textualmente em formato ISO 8601.

O mesmo timestamp deverá ser utilizado para os registros pertencentes ao mesmo lote de extração de uma fonte.

Os metadados deverão ser adicionados sem alterar os campos originais.

**Motivação técnica:**

Permitem rastrear a origem dos registros e identificar quando os dados foram incorporados ao ambiente analítico.

## I5. SUBSTITUIÇÃO INTEGRAL

Todas as tabelas deverão ser recriadas a cada execução.

Não será permitido acumular dados de execuções anteriores.

**Motivação técnica:**

A substituição integral garante comportamento determinístico e evita duplicidade decorrente de reexecuções.

---

# 6. TRATAMENTO DE EXCEÇÕES E RESILIÊNCIA

## E1. RETRY E BACKOFF EXPONENCIAL

As requisições HTTP e chamadas externas deverão implementar tentativas de recuperação.

Política definida:

- Até três tentativas por operação.
- Intervalos progressivos entre as tentativas.
- Backoff exponencial.
- Falha definitiva após o esgotamento das tentativas.

A política deverá ser aplicada às operações externas sujeitas a instabilidade de rede ou limitação de requisições.

**Motivação técnica:**

Fontes públicas podem apresentar indisponibilidade temporária, lentidão ou limitação de acesso. As tentativas controladas reduzem falhas ocasionais sem mascarar indisponibilidades permanentes.

## E2. FALHA DE EXTRAÇÃO

Caso qualquer uma das quatro fontes apresente falha permanente:

1. Encerrar a operação.
2. Não iniciar a persistência.
3. Informar a origem da falha no terminal.
4. Encerrar o processo com:

```python
sys.exit(1)
```

**Motivação técnica:**

Impede que uma execução incompleta seja confundida com uma atualização integral da camada Bronze.

## E3. FALHA DE PERSISTÊNCIA

Caso alguma das quatro gravações apresente erro:

1. Interromper a sequência de gravação.
2. Executar `ROLLBACK` da transação.
3. Não confirmar nenhuma das quatro tabelas.
4. Fechar a conexão.
5. Informar a falha.
6. Encerrar com código de saída `1`.

**Motivação técnica:**

Garante atomicidade entre as quatro tabelas. O banco deverá apresentar o estado anterior à execução ou o novo estado integralmente confirmado, nunca uma atualização parcial.

## E4. CONTROLE DE CONEXÃO

A conexão de escrita deverá ser aberta somente após a conclusão bem-sucedida das quatro extrações.

O processo deverá controlar explicitamente o fechamento da conexão, inclusive em situações de exceção.

**Motivação técnica:**

Evita manter o arquivo DuckDB bloqueado durante operações de rede, que podem ser demoradas ou apresentar instabilidade.

## E5. LOCK DO DUCKDB

A execução de ingestão deverá utilizar acesso exclusivo de escrita ao arquivo DuckDB.

Não deverá existir outro processo concorrente realizando escrita no mesmo arquivo durante a execução.

**Motivação técnica:**

O DuckDB possui restrições de concorrência entre processos para escrita no mesmo arquivo. O controle evita conflitos de bloqueio e falhas de persistência.

---

# 7. CONTROLE DE EXECUÇÃO E SAÍDA NO TERMINAL

## L1. CONFIGURAÇÃO UTF-8

No início da execução, o stdout deverá ser reconfigurado para UTF-8.

**Motivação técnica:**

Garante a apresentação correta de acentos e caracteres especiais, especialmente em terminais Windows.

## L2. RELATÓRIO DE INGESTÃO

Após a confirmação da transação, imprimir uma linha por tabela contendo:

- Nome qualificado da tabela.
- Quantidade de registros efetivamente gravados no DuckDB.

Formato de referência:

```text
raw.b3_empresas                  000.000
raw.fundamentus_acoes            000.000
raw.minhareceita_empresas        000.000
raw.yfinance_cotacoes            000.000
------------------------------------------------
TOTAL                            000.000
```

Os números deverão utilizar ponto como separador de milhar.

A contagem deverá ser obtida diretamente do banco, por consulta `COUNT(*)`.

A linha TOTAL deverá representar a soma das quatro contagens confirmadas.

**Motivação técnica:**

O relatório constitui o instrumento de conferência da execução, permitindo verificar a quantidade de registros efetivamente persistidos.

## L3. ENCERRAMENTO

Após a impressão do relatório, o script deverá finalizar automaticamente e devolver o controle ao terminal.

Não deverá permanecer nenhum processo de ingestão em execução.

---

# 8. CRITÉRIOS DE ACEITE GERAIS

A implementação será considerada aprovada quando atender a todos os critérios abaixo.

## A. Integridade e tipagem

- Todas as quatro tabelas deverão existir no schema `raw`.
- Todas as colunas de negócio deverão ser `VARCHAR`.
- Os metadados técnicos deverão estar presentes em todas as tabelas.
- Nenhum campo de negócio poderá sofrer conversão ou normalização.
- Os valores nulos deverão ser preservados.
- Os registros não poderão ser deduplicados ou filtrados.

## B. B3

- A requisição HTTP deverá utilizar o endereço especificado.
- A tabela deverá conter os registros tabulares extraídos.
- Os CNPJs e tickers deverão estar disponíveis para as fontes dependentes.
- Os nomes originais das colunas deverão ser preservados.

## C. Fundamentus

- A requisição deverá utilizar o endereço especificado.
- A tabela deverá conter os indicadores disponibilizados pela fonte.
- Os valores deverão permanecer em representação textual.
- Não poderão ocorrer conversões numéricas.

## D. Minha Receita

- Deverão ser consultados os CNPJs obtidos da B3.
- A coluna `cnpj` deverá conter o valor da B3 sem alteração (ex.: `191`).
- O complemento com zeros à esquerda deverá ocorrer somente na URL de consulta, registrada em `_source_origin`.
- Identificadores rejeitados pela API (HTTP 400/404) deverão ser informados no terminal.
- Os payloads JSON deverão ser preservados em texto.
- Cada resposta deverá possuir seus respectivos metadados.
- Não poderá ocorrer transformação dos campos originais.

## E. yfinance

- Todos os tickers identificados deverão ser processados.
- O sufixo `.SA` deverá ser aplicado na consulta.
- A coluna `ticker` deverá conter o identificador da B3 sem o sufixo `.SA`.
- O símbolo consultado deverá constar em `_source_origin`.
- O histórico completo disponibilizado deverá ser solicitado.
- A persistência deverá preservar os registros retornados pela biblioteca.
- Não poderão ocorrer cálculos ou arredondamentos.

## F. Idempotência

Executar o pipeline duas vezes consecutivas deverá:

- Substituir integralmente as quatro tabelas.
- Não duplicar registros.
- Não acumular dados de execuções anteriores.
- Produzir contagens correspondentes aos dados obtidos em cada execução.

As contagens poderão variar entre execuções caso as fontes tenham atualizado seus dados.

## G. Atomicidade

- Simular falha em qualquer fonte deverá impedir a persistência.
- Simular falha durante uma gravação deverá provocar rollback.
- Nenhuma das quatro tabelas poderá ficar parcialmente atualizada.
- O processo deverá retornar código de erro `1` nas falhas permanentes.

## H. Conexões

- A conexão deverá ser fechada após a execução.
- Nenhum lock deverá permanecer após o encerramento.
- Uma nova execução deverá conseguir acessar o banco normalmente.

## I. Saída

- O terminal deverá apresentar quatro linhas de tabelas.
- Deverá apresentar uma linha final com o total.
- As contagens deverão vir do DuckDB.
- Os números deverão utilizar separador de milhar com ponto.
- A codificação deverá ser UTF-8.

---

# 9. RELAÇÃO DE PREMISSAS E PONTOS NÃO ESPECIFICADOS

As premissas abaixo não deverão ser confundidas com requisitos já definidos.

1. **Disponibilidade das fontes:** assume-se que B3, Fundamentus, Minha Receita e Yahoo Finance disponibilizam os dados durante a execução.

2. **Estrutura da B3:** assume-se que a página disponibiliza informações suficientes para identificar os CNPJs e tickers das empresas.

3. **Estrutura da API:** assume-se que a API Minha Receita disponibiliza respostas JSON para os CNPJs válidos consultados com 14 dígitos. Identificadores inválidos são tratados conforme M6.4.

4. **Compatibilidade dos tickers:** assume-se que os identificadores obtidos na B3 podem receber o sufixo `.SA` e ser utilizados pelo yfinance.

5. **Histórico completo:** entende-se por histórico completo todo o histórico diário disponibilizado pelo yfinance para cada ticker no momento da consulta.

6. **Comportamento do yfinance:** a preservação será relativa aos dados estruturados retornados pela biblioteca, e não ao payload HTTP original do Yahoo Finance.

7. **Mapeamento dos campos:** os nomes técnicos exatos das colunas de CNPJ e ticker na resposta da B3 ainda precisam ser identificados na implementação. Não deverão ser inventados ou presumidos.

8. **Dependências auxiliares:** as bibliotecas específicas para requisições HTTP e interpretação de HTML ainda não foram determinadas nesta especificação.

9. **Parâmetros do yfinance:** opções adicionais da biblioteca, além do período histórico completo e da periodicidade diária, não foram especificadas e não deverão receber decisões de negócio implícitas.

10. **Concorrência:** assume-se que não haverá outro processo de escrita concorrente no arquivo DuckDB durante a ingestão.

---

# 10. PRINCÍPIO DE ENCERRAMENTO DA ESPECIFICAÇÃO

A camada Bronze deverá ser tratada como a representação persistida dos dados recebidos das fontes, respeitando os limites de cada mecanismo de extração.

Nenhuma transformação analítica deverá ser introduzida nesta etapa.

A responsabilidade desta camada termina na obtenção, preservação, rastreabilidade e persistência dos dados.

A interpretação, tipagem definitiva, padronização, limpeza, validação de negócio e construção de indicadores serão responsabilidades exclusivas das próximas camadas da arquitetura Medallion.

**REGRA FUNDAMENTAL: O dado que chegou à Bronze deve continuar identificável e auditável como dado de origem. A transformação começa somente na Silver.**