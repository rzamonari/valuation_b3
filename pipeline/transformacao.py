r"""Transformação da camada Refined (Silver): B3, Fundamentus, yfinance e Minha Receita.

Execução: uv run python -m pipeline.transformacao

# SPEC TÉCNICA FINAL — IMPLEMENTAÇÃO DA CAMADA SILVER
## Projeto: Pipeline de Indicadores Fundamentalistas

# 1. INSTRUÇÃO PRINCIPAL AO CLAUDE CODE

Atue como engenheiro de dados sênior, especialista em Python, DuckDB, SQL, arquitetura Medallion e desenvolvimento orientado a especificações (Spec-Driven Development).

Sua tarefa é implementar a camada Silver do projeto de indicadores fundamentalistas, respeitando integralmente esta especificação.

**Esta especificação é a fonte da verdade para a implementação.**

Regras obrigatórias:

1. Não inventar regras de negócio.
2. Não alterar decisões funcionais estabelecidas nesta especificação.
3. Não modificar a camada Bronze.
4. Não criar funcionalidades que não tenham sido solicitadas.
5. Não descartar colunas, propriedades ou registros silenciosamente.
6. Não substituir conversões estritas por conversões tolerantes a erros.
7. Não escolher arbitrariamente registros conflitantes.
8. Reutilizar a infraestrutura já existente no projeto.
9. Inspecionar os arquivos e dados reais antes de implementar.
10. Se encontrar uma incompatibilidade entre esta especificação e a estrutura real do projeto, interromper a implementação da parte afetada, apresentar o problema e propor uma solução antes de alterar a regra.

Não faça uma implementação baseada em suposições sobre arquivos, funções, tabelas ou estruturas que ainda não tenham sido examinados.

# 2. CONTEXTO DO PROJETO

O projeto utiliza arquitetura Medallion para construir um pipeline de dados fundamentalistas.

A camada Bronze já realiza a ingestão dos dados originais.

A camada Silver deverá realizar:

- Padronização dos nomes das colunas.
- Conversão e validação de tipos.
- Limpeza estrutural restrita.
- Normalização de estruturas JSON.
- Validação de chaves.
- Tratamento de duplicidades.
- Preservação de valores nulos.
- Disponibilização de tabelas estruturadas para as etapas analíticas posteriores.

A camada Silver não deverá realizar cálculos fundamentalistas, análises financeiras, correções de informações de negócio ou preenchimento artificial de dados.

A camada Bronze deverá continuar preservando os dados originais.

# 3. STACK TECNOLÓGICA

- Linguagem: Python 3.13.
- Gerenciador de dependências: uv.
- Banco de dados: DuckDB.
- Arquitetura: Medallion.
- Schema Bronze: raw.
- Schema Silver: refined.
- Banco: fundamentalistas.duckdb.
- Localização do banco: raiz do projeto.

# 4. INSPEÇÃO OBRIGATÓRIA DO PROJETO

Antes de escrever qualquer código:

1. Inspecione a estrutura de diretórios do projeto.
2. Leia integralmente o arquivo pipeline/db.py.
3. Identifique as funções existentes para conexão, criação de schemas e gravação.
4. Identifique como o caminho do banco é determinado.
5. Confira as dependências declaradas no projeto.
6. Confira a existência das tabelas Bronze.
7. Examine o DESCRIBE das tabelas Bronze.
8. Examine os tipos e valores reais das colunas.
9. Examine a estrutura dos JSON da Minha Receita considerando todos os registros.
10. Identifique limitações técnicas do DuckDB relacionadas às conversões e transações necessárias.

Não criar uma nova infraestrutura de conexão com o banco se a existente atender à necessidade.

Não alterar pipeline/db.py sem necessidade comprovada e sem apresentar previamente a justificativa.

Se alguma informação indispensável não puder ser confirmada, apresente a pendência antes de implementar.

# 5. ARTEFATO A PRODUZIR

Arquivo:

pipeline/transformacao.py

Comando de execução:

uv run python -m pipeline.transformacao

A especificação completa deverá ser registrada como docstring no início do arquivo.

A implementação deverá ser organizada, modular, documentada e compatível com a arquitetura existente.

# 6. TABELAS DE ORIGEM E DESTINO

O processo deverá produzir exatamente sete tabelas Silver:

| Origem | Destino |
|---|---|
| raw.b3_empresas | refined.b3_empresas |
| raw.fundamentus_acoes | refined.fundamentus_acoes |
| raw.yfinance_cotacoes | refined.yfinance_cotacoes |
| raw.minhareceita_empresas | refined.minhareceita_empresas |
| JSON qsa | refined.minhareceita_qsa |
| JSON regime_tributario | refined.minhareceita_regime_tributario |
| JSON cnaes_secundarios | refined.minhareceita_cnaes_secundarios |

As três últimas tabelas serão derivadas dos arrays presentes em raw.minhareceita_empresas.payload_json.

# 7. MAPEAMENTO E TRANSFORMAÇÃO DAS TABELAS

## 7.1. B3 — Empresas

Origem: raw.b3_empresas

Destino: refined.b3_empresas

| Coluna Bronze | Coluna Silver | Tipo |
|---|---|---|
| codeCVM | codigo_cvm | VARCHAR |
| issuingCompany | empresa_emissora | VARCHAR |
| companyName | razao_social | VARCHAR |
| tradingName | nome_pregao | VARCHAR |
| cnpj | cnpj | VARCHAR |
| marketIndicator | indicador_mercado | VARCHAR |
| typeBDR | tipo_bdr | VARCHAR |
| dateListing | data_listagem | DATE |
| status | situacao | VARCHAR |
| segment | segmento | VARCHAR |
| segmentEng | segmento_ingles | VARCHAR |
| type | tipo_empresa | VARCHAR |
| market | mercado | VARCHAR |
| _timestamp_ingestao | _timestamp_ingestao | VARCHAR |
| _source_origin | _source_origin | VARCHAR |

### Regras

- codeCVM deverá permanecer VARCHAR.
- cnpj deverá permanecer VARCHAR.
- cnpj deverá ser padronizado conforme a regra geral de CNPJ (seção 7.8): sempre 14 dígitos, completando com zeros à esquerda quando houver menos de 14.
- Exemplos: '191' → '00000000000191'; '973749000115' → '00973749000115'; '0' → '00000000000000'.
- Não aplicar máscaras.
- Não corrigir identificadores além da padronização de CNPJ (não validar nem recalcular dígitos verificadores).
- Converter dateListing de DD/MM/YYYY para DATE, utilizando %d/%m/%Y.
- Preservar 31/12/9999 como 9999-12-31.
- Não interpretar ou corrigir datas futuras.
- Preservar a distinção entre string vazia e NULL.
- Preservar os metadados de ingestão.

### Chave lógica

codigo_cvm

Validar:

- Ausência de valores nulos na chave.
- Unicidade da chave após remoção de duplicatas integralmente idênticas.

Se a mesma chave possuir conteúdos divergentes, interromper a execução e apresentar os registros conflitantes.

## 7.2. Fundamentus — Indicadores

Origem: raw.fundamentus_acoes

Destino: refined.fundamentus_acoes

| Coluna Bronze | Coluna Silver | Tipo |
|---|---|---|
| Papel | ticker | VARCHAR |
| Cotação | cotacao | DECIMAL(p,s) |
| P/L | preco_lucro | DECIMAL(p,s) |
| P/VP | preco_valor_patrimonial | DECIMAL(p,s) |
| PSR | preco_vendas | DECIMAL(p,s) |
| Div.Yield | dividend_yield | DECIMAL(p,s) |
| P/Ativo | preco_ativo | DECIMAL(p,s) |
| P/Cap.Giro | preco_capital_giro | DECIMAL(p,s) |
| P/EBIT | preco_ebit | DECIMAL(p,s) |
| P/Ativ Circ.Liq | preco_ativo_circulante_liquido | DECIMAL(p,s) |
| EV/EBIT | enterprise_value_ebit | DECIMAL(p,s) |
| EV/EBITDA | enterprise_value_ebitda | DECIMAL(p,s) |
| Mrg Bruta | margem_bruta | DECIMAL(p,s) |
| Mrg Ebit | margem_ebit | DECIMAL(p,s) |
| Mrg. Líq. | margem_liquida | DECIMAL(p,s) |
| Liq. Corr. | liquidez_corrente | DECIMAL(p,s) |
| ROIC | roic | DECIMAL(p,s) |
| ROE | roe | DECIMAL(p,s) |
| Liq.2meses | liquidez_2_meses | DECIMAL(p,s) |
| Patrim. Líq | patrimonio_liquido | DECIMAL(p,s) |
| Dív.Líq/ Patrim. | divida_liquida_patrimonio | DECIMAL(p,s) |
| Cresc. Rec.5a | crescimento_receita_5_anos | DECIMAL(p,s) |
| _timestamp_ingestao | _timestamp_ingestao | VARCHAR |
| _source_origin | _source_origin | VARCHAR |

### Conversão numérica

Os dados utilizam notação brasileira:

- Ponto como separador de milhar.
- Vírgula como separador decimal.
- Valores negativos.
- Símbolo de percentual em campos percentuais.

Exemplos:

| Valor original | Valor convertido |
|---|---:|
| 1.083.050.000,00 | 1083050000.00 |
| 6,91% | 6.91 |
| -208,15% | -208.15 |
| 3,423 | 3.423 |

Regras:

1. Interpretar corretamente os separadores brasileiros.
2. Remover o símbolo % quando presente, sem dividir por 100.
3. Preservar valores negativos.
4. Preservar zeros.
5. Preservar NULL.
6. Não arredondar.
7. Não truncar.
8. Não transformar valores inválidos em NULL.

### Precisão e escala DECIMAL

Determinar a precisão e escala individualmente para cada coluna, examinando todos os registros Bronze.

O procedimento deverá:

1. Identificar o maior número de dígitos inteiros.
2. Identificar o maior número de casas decimais.
3. Determinar a precisão e escala necessárias.
4. Criar cada coluna com DECIMAL(p,s) adequado.
5. Garantir representação exata de todos os valores.
6. Interromper a execução se a precisão necessária ultrapassar o limite do DuckDB.

Não utilizar uma precisão arbitrária e uniforme para todas as colunas.

### Tratamento específico da coluna Dív.Líq/ Patrim.

Foi identificada a presença de quebras de linha e tabulações nas extremidades dos valores.

Exemplo:

0A09090909302C3130090909

Representação:

\n\t\t\t\t0,10\t\t\t

Remover exclusivamente os caracteres de formatação externos identificados.

Não executar limpeza genérica que possa alterar o conteúdo numérico.

### Chave lógica

ticker

Validar ausência de nulos e unicidade após a deduplicação integral.

Se houver o mesmo ticker com conteúdos divergentes, interromper a execução e apresentar os registros conflitantes.

## 7.3. YFinance — Cotações

Origem: raw.yfinance_cotacoes

Destino: refined.yfinance_cotacoes

| Coluna Bronze | Coluna Silver | Tipo |
|---|---|---|
| ticker | ticker | VARCHAR |
| Date | data | TIMESTAMP WITH TIME ZONE |
| Open | abertura | DOUBLE |
| High | maxima | DOUBLE |
| Low | minima | DOUBLE |
| Close | fechamento | DOUBLE |
| Adj Close | fechamento_ajustado | DOUBLE |
| Volume | volume | BIGINT |
| Dividends | dividendos | DOUBLE |
| Stock Splits | desdobramentos | DOUBLE |
| _source_origin | _source_origin | VARCHAR |
| _timestamp_ingestao | _timestamp_ingestao | VARCHAR |
| Capital Gains | ganhos_capital | DOUBLE |

### Regras

- ticker permanece VARCHAR.
- Date deverá ser convertido para TIMESTAMP WITH TIME ZONE.
- Preservar o instante temporal.
- Não exigir preservação literal do offset textual original.
- Preços e valores financeiros deverão ser DOUBLE.
- Volume deverá ser BIGINT.
- Preservar zeros.
- Preservar NULL.
- Não preencher Capital Gains com zero.

Exemplo de data:

2026-10-29 00:00:00-03:00

### Diagnóstico conhecido da Bronze

- Total: 1.920.774 registros.
- Capital Gains nulos: 1.908.781.
- Capital Gains vazios: 0.
- Date nulos: 0.
- Capital Gains preenchidos: 11.993.

Esses valores são referências do levantamento. Recalcular as contagens durante cada execução.

### Chave lógica

(ticker, data)

Regras:

1. Validar que os dois componentes da chave não sejam nulos.
2. Remover duplicatas integralmente idênticas.
3. Verificar conflitos de conteúdo para a mesma chave.
4. Interromper a execução se existirem registros divergentes.
5. Apresentar a chave e os registros conflitantes.
6. Não selecionar arbitrariamente uma cotação.

## 7.4. Minha Receita — Empresas

Origem: raw.minhareceita_empresas

Destino: refined.minhareceita_empresas

A coluna payload_json contém propriedades escalares e arrays.

A tabela principal deverá conter todas as propriedades escalares do JSON.

### Regras

- Uma linha por CNPJ.
- Chave lógica: cnpj.
- CNPJ deverá ser VARCHAR.
- CNPJ deverá ser padronizado conforme a regra geral de CNPJ (seção 7.8), tanto na coluna cnpj da linha Bronze quanto na propriedade cnpj do JSON.
- Preservar todas as propriedades escalares.
- Manter propriedades mesmo quando apresentarem NULL.
- Não incluir arrays na tabela principal.
- Não replicar payload_json na Silver.
- O JSON original continuará preservado integralmente na Bronze.
- Preservar os metadados de origem na tabela principal.
- Validar a correspondência entre o CNPJ da linha Bronze e a propriedade cnpj do JSON, ambos já padronizados com 14 dígitos. Divergências deverão gerar erro, sem escolher um valor arbitrariamente.

### Tipagem

A tipagem deverá ser determinada após a inspeção de todos os registros.

Regras:

- Identificadores deverão permanecer textuais quando necessário preservar zeros e representação.
- Campos de data deverão utilizar DATE quando o formato e a semântica forem confirmados.
- Campos numéricos deverão receber tipos compatíveis com os valores encontrados.
- Campos booleanos deverão utilizar BOOLEAN quando confirmados.
- Campos que aparecem NULL na amostra deverão continuar presentes e receber tipo compatível com a estrutura global.
- Não inferir tipos definitivos utilizando somente cinco registros.

A implementação deverá validar a estrutura global do JSON antes da publicação das tabelas.

## 7.5. Minha Receita — QSA

Destino: refined.minhareceita_qsa

Origem: array qsa do payload_json.

Granularidade: uma linha por sócio de cada empresa.

Chave lógica:

(cnpj, sequencia_socio)

A coluna sequencia_socio deverá representar a posição original do objeto no array.

Propriedades observadas:

- pais
- nome_socio
- codigo_pais
- faixa_etaria
- cnpj_cpf_do_socio
- qualificacao_socio
- codigo_faixa_etaria
- data_entrada_sociedade
- identificador_de_socio
- cpf_representante_legal
- nome_representante_legal
- codigo_qualificacao_socio
- qualificacao_representante_legal
- codigo_qualificacao_representante_legal

Incluir também:

- cnpj
- sequencia_socio

Preservar os valores nulos das propriedades.

## 7.6. Minha Receita — Regime Tributário

Destino: refined.minhareceita_regime_tributario

Origem: array regime_tributario do payload_json.

Granularidade: uma linha por ocorrência de regime tributário de cada empresa.

Chave lógica:

(cnpj, ano)

Propriedades observadas:

- ano
- cnpj_da_scp
- forma_de_tributacao
- quantidade_de_escrituracoes

Incluir também cnpj.

## 7.7. Minha Receita — CNAEs Secundários

Destino: refined.minhareceita_cnaes_secundarios

Origem: array cnaes_secundarios do payload_json.

Granularidade: uma linha por CNAE secundário de cada empresa.

Chave lógica:

(cnpj, codigo_cnae)

Mapeamento:

| JSON | Silver |
|---|---|
| codigo | codigo_cnae |
| descricao | descricao |

Incluir também cnpj.

### Regras gerais para as tabelas auxiliares

- Preservar a associação com o CNPJ da empresa.
- Não gerar linhas artificiais para arrays vazios.
- Não gerar linhas artificiais para arrays nulos.
- Preservar a ordem original do QSA.
- Validar as chaves lógicas.
- Não descartar propriedades existentes nos objetos.
- Não descartar objetos inválidos silenciosamente.
- Estruturas incompatíveis deverão gerar erro explícito.

Os tipos das propriedades deverão ser definidos após a inspeção global dos dados, respeitando a natureza de cada campo.

### Metadados nas tabelas auxiliares

Não presumir a inclusão ou exclusão de _timestamp_ingestao e _source_origin nas tabelas auxiliares.

Antes da implementação, verificar a necessidade de propagação desses metadados para os registros derivados e apresentar a proposta, caso a decisão ainda não esteja definida.

## 7.8. Regra geral de padronização de CNPJ

Aplica-se a todas as colunas Silver que contêm CNPJ:

| Tabela | Coluna |
|---|---|
| refined.b3_empresas | cnpj |
| refined.minhareceita_empresas | cnpj |
| refined.minhareceita_qsa | cnpj |
| refined.minhareceita_regime_tributario | cnpj, cnpj_da_scp |
| refined.minhareceita_cnaes_secundarios | cnpj |

Regras:

1. O CNPJ deverá ter sempre 14 dígitos.
2. Quando a quantidade de dígitos for menor que 14, completar com zeros à esquerda até 14 dígitos.
3. Exemplos: '191' → '00000000000191'; '0' → '00000000000000'; '33000167000101' permanece igual.
4. O tipo permanece VARCHAR, para preservar os zeros à esquerda.
5. O valor de origem deverá conter somente dígitos. Valores com pontuação, máscara, espaços ou outros caracteres deverão gerar erro de conversão; não remover caracteres para "consertar" o valor.
6. Valores com mais de 14 dígitos deverão gerar erro de conversão; não truncar.
7. NULL permanece NULL.
8. String vazia permanece string vazia: não há dígitos a padronizar, e completá-la com zeros a tornaria indistinguível de '0'.
9. Não aplicar máscara (pontos, barra, hífen) e não validar ou recalcular dígitos verificadores.

Não se aplica a cnpj_cpf_do_socio e cpf_representante_legal do QSA, que contêm CPFs mascarados ou CNPJs de sócios em formatos variados.

# 8. CONVERSÕES E VALIDAÇÕES ESTRITAS

Não utilizar:

- TRY_CAST.
- TRY_STRPTIME.
- errors="coerce".
- Qualquer mecanismo que converta silenciosamente dados inválidos em NULL.

As conversões deverão falhar quando o valor não puder ser representado no tipo de destino.

Em caso de erro, apresentar:

- Tabela de origem.
- Tabela de destino.
- Coluna.
- Valor inválido de exemplo.
- Motivo da falha.

Encerrar a execução com sys.exit(1).

A implementação não deverá confundir valor inválido com valor ausente.

# 9. REGRAS GERAIS DE DUPLICIDADE

Aplicar a seguinte ordem:

1. Identificar registros integralmente idênticos.
2. Manter uma única ocorrência de cada registro idêntico.
3. Contabilizar quantos registros foram removidos.
4. Validar as chaves lógicas.
5. Identificar chaves nulas.
6. Identificar chaves repetidas com conteúdos divergentes.
7. Interromper a execução em caso de conflito.

Não utilizar DISTINCT indiscriminadamente para resolver conflitos de negócio.

### Quadro de chaves lógicas

| Tabela | Chave |
|---|---|
| b3_empresas | codigo_cvm |
| fundamentus_acoes | ticker |
| yfinance_cotacoes | ticker + data |
| minhareceita_empresas | cnpj |
| minhareceita_qsa | cnpj + sequencia_socio |
| minhareceita_regime_tributario | cnpj + ano |
| minhareceita_cnaes_secundarios | cnpj + codigo_cnae |

Chaves nulas deverão gerar erro.

Chaves repetidas com conteúdo divergente deverão gerar erro.

A mensagem deverá apresentar a chave e os registros conflitantes.

# 10. TRATAMENTO DE NULOS

Nenhuma linha deverá ser eliminada somente por apresentar valores nulos.

Nenhum valor nulo deverá ser preenchido artificialmente.

Não converter zero em NULL.

Não converter NULL em zero.

Preservar a distinção entre NULL e string vazia.

Os nulos deverão permanecer na Silver para tratamento nas camadas analíticas, quando houver regra de negócio específica.

A ausência de elementos em arrays não deverá gerar registros fictícios nas tabelas auxiliares.

# 11. RELATÓRIO DE EXECUÇÃO

Ao final da execução, apresentar um relatório no terminal para cada tabela.

O relatório deverá conter:

- Nome da tabela.
- Quantidade de registros de origem.
- Quantidade de registros considerados antes da deduplicação.
- Quantidade de duplicatas integralmente idênticas removidas.
- Quantidade de registros gravados.
- Quantidade de valores nulos por coluna.
- Total de registros processados.

Para tabelas auxiliares, a contagem de origem deverá representar a quantidade de elementos válidos extraídos dos arrays antes da deduplicação.

Apresentar também o total geral de registros gravados nas sete tabelas.

Os números deverão utilizar separador de milhar com ponto.

A saída deverá utilizar UTF-8.

Todas as contagens deverão ser obtidas efetivamente durante a execução. Não utilizar valores fixos ou estimativas.

# 12. IDEMPOTÊNCIA

A execução deverá ser idempotente.

Utilizar CREATE OR REPLACE TABLE para as tabelas Silver, respeitando a estratégia transacional definida nesta especificação.

Executar novamente o processo com os mesmos dados Bronze deverá produzir o mesmo conteúdo Silver.

Não deverá haver duplicação de registros entre execuções.

A camada Bronze deverá permanecer inalterada.

# 13. ATOMICIDADE DA EXECUÇÃO

A atualização das sete tabelas Silver deverá ocorrer de maneira atômica.

Todas as transformações e validações deverão ser realizadas antes da publicação definitiva das tabelas.

Regras:

1. Validar a existência das tabelas Bronze.
2. Executar as transformações.
3. Validar conversões, estruturas, duplicidades e chaves.
4. Preparar os resultados das sete tabelas.
5. Iniciar a transação de publicação.
6. Substituir as sete tabelas Silver.
7. Confirmar a transação somente após todas as operações concluídas com sucesso.
8. Em caso de erro, executar rollback.

Se qualquer uma das sete tabelas falhar, nenhuma delas poderá ficar parcialmente atualizada.

A versão anterior das sete tabelas deverá ser preservada integralmente em caso de falha.

A estratégia deverá ser implementada de acordo com o comportamento transacional efetivamente suportado pelo DuckDB.

Não assumir que uma operação é transacional sem validar sua compatibilidade.

# 14. TRATAMENTO DE ERROS

Antes do processamento, verificar a existência de todas as tabelas Bronze necessárias.

Se alguma estiver ausente:

- Informar o nome da tabela.
- Orientar a execução da ingestão Bronze.
- Interromper o processo.
- Encerrar com sys.exit(1).

Também deverão interromper a execução:

- Falhas de conversão.
- Estruturas JSON incompatíveis.
- Propriedades obrigatórias ausentes.
- Chaves lógicas nulas.
- Chaves repetidas com conteúdo divergente.
- Precisão DECIMAL insuficiente.
- Falhas de leitura.
- Falhas de gravação.
- Falhas transacionais.

Não ocultar exceções.

Não prosseguir com publicação parcial.

As mensagens deverão identificar a etapa, tabela e coluna envolvidas sempre que aplicável.

# 15. CRITÉRIOS DE ACEITE

A implementação será considerada concluída quando:

1. Executar corretamente com uv run python -m pipeline.transformacao.
2. Reutilizar a infraestrutura existente de pipeline/db.py.
3. Criar o schema refined quando necessário.
4. Ler exclusivamente as tabelas Bronze previstas.
5. Não alterar os dados Bronze.
6. Produzir exatamente as sete tabelas Silver definidas.
7. Aplicar os mapeamentos de nomes e tipos estabelecidos.
8. Converter datas e números com regras estritas.
9. Preservar zeros, nulos e valores originais válidos, exceto a padronização de CNPJ com 14 dígitos (seção 7.8).
10. Remover e contabilizar duplicatas integralmente idênticas.
11. Interromper a execução diante de chaves lógicas nulas.
12. Interromper a execução diante de chaves repetidas com conteúdos divergentes.
13. Preservar os valores do Fundamentus em DECIMAL, sem arredondamento ou truncamento.
14. Preservar os instantes temporais do YFinance em TIMESTAMP WITH TIME ZONE.
15. Normalizar os arrays da Minha Receita nas três tabelas auxiliares.
16. Preservar todas as propriedades escalares da Minha Receita.
17. Validar a estrutura JSON considerando todos os registros.
18. Apresentar relatório com contagens reais.
19. Ser idempotente.
20. Garantir atomicidade na atualização das sete tabelas.
21. Preservar integralmente a versão anterior em caso de falha.
22. Encerrar com código de erro quando houver falha de validação.

# 16. TESTES OBRIGATÓRIOS

Criar ou executar testes para validar, no mínimo:

- Conversão correta de datas B3.
- Preservação de 31/12/9999.
- Preservação de identificadores textuais.
- Padronização de CNPJ com 14 dígitos (zeros à esquerda), preservação de NULL e string vazia, e erro para CNPJ não numérico ou com mais de 14 dígitos.
- Conversão de números brasileiros do Fundamentus.
- Conversão de percentuais sem divisão por 100.
- Preservação de números negativos e zeros.
- Cálculo dinâmico de precisão DECIMAL.
- Falha de conversão diante de valores inválidos.
- Limpeza restrita da coluna Dív.Líq/ Patrim.
- Conversão de datas com fuso horário do YFinance.
- Deduplicação de linhas integralmente idênticas.
- Detecção de chaves divergentes.
- Detecção de chaves nulas.
- Extração dos arrays da Minha Receita.
- Preservação da sequência original do QSA.
- Tratamento de arrays nulos e vazios.
- Preservação de propriedades escalares nulas.
- Rollback quando qualquer tabela falhar.
- Idempotência em duas execuções consecutivas.

Os testes não deverão alterar os dados reais da Bronze.

# 17. PROCEDIMENTO DE IMPLEMENTAÇÃO

Siga esta ordem:

### Etapa 1 — Inspeção

Inspecionar o projeto, o banco, o módulo db.py, as tabelas Bronze e os dados reais.

### Etapa 2 — Diagnóstico

Apresentar um resumo contendo:

- Estrutura encontrada.
- Funções disponíveis.
- Dependências existentes.
- Tipos das tabelas Bronze.
- Estrutura completa da Minha Receita.
- Compatibilidade das operações transacionais.
- Pendências que possam impedir a implementação.

### Etapa 3 — Plano de implementação

Apresentar um plano objetivo de como cada tabela será transformada e validada.

Se houver decisão funcional ainda não definida, solicitar confirmação antes de implementá-la.

### Etapa 4 — Implementação

Implementar pipeline/transformacao.py respeitando integralmente esta especificação.

Não alterar arquivos fora do escopo sem necessidade justificada.

### Etapa 5 — Testes

Executar os testes previstos e corrigir eventuais falhas.

### Etapa 6 — Validação final

Executar o pipeline e verificar:

- Quantidade de registros.
- Tipos das colunas.
- Chaves.
- Duplicidades.
- Nulos.
- Integridade das sete tabelas.
- Idempotência.
- Atomicidade.

### Etapa 7 — Entrega

Apresentar:

- Arquivos criados ou alterados.
- Resumo das implementações.
- Resultado dos testes.
- Resultado da execução.
- Quantidades de registros processados.
- Pendências ou limitações identificadas.

# 18. REGRA FINAL

Não considere a tarefa concluída apenas porque o código executou sem apresentar exceção.

A implementação somente estará concluída quando todos os critérios de aceite forem verificados.

A especificação é a fonte da verdade. Se houver conflito entre uma implementação sugerida e esta especificação, prevalece esta especificação.

# DECISÕES DE IMPLEMENTAÇÃO (confirmadas após a inspeção dos dados reais)

1. refined.minhareceita_regime_tributario usa a chave (cnpj, sequencia_regime), e não
   (cnpj, ano): a mesma empresa tem vários regimes no mesmo ano (um por cnpj_da_scp e,
   em alguns casos, formas de tributação distintas com cnpj_da_scp nulo). sequencia_regime
   é a posição original do objeto no array, como sequencia_socio no QSA.
2. As três tabelas auxiliares herdam _timestamp_ingestao e _source_origin da linha Bronze
   da empresa de origem.
3. sequencia_socio e sequencia_regime começam em 1 (posição ordinal no array).
4. Tipagem da Minha Receita (contrato validado em todos os registros a cada execução):
   strings JSON -> VARCHAR; inteiros JSON -> BIGINT; capital_social (inteiros e decimais)
   -> DECIMAL(p,s) com precisão calculada sobre todos os valores; booleanos -> BOOLEAN;
   propriedades data_* (YYYY-MM-DD) -> DATE; email (sempre nulo na inspeção) -> VARCHAR.
   Propriedades ausentes, não previstas, duplicadas ou com tipo incompatível geram erro.
5. A deduplicação compara os registros já tipados (todas as colunas, incluindo metadados).
6. Publicação: as sete tabelas são preparadas e validadas em tabelas temporárias da conexão
   e substituídas em uma única transação (CREATE OR REPLACE TABLE é transacional no DuckDB:
   ROLLBACK restaura a versão anterior das tabelas).
7. Fundamentus: o valor exatamente igual a '-' (após a limpeza das extremidades, quando
   houver) é o marcador de "sem valor" da própria fonte e vira NULL nas 21 colunas
   numéricas. Qualquer outro texto não numérico continua gerando erro de conversão.
8. CNPJ (seção 7.8): b3_empresas.cnpj, o cnpj da Minha Receita (linha Bronze e JSON),
   o cnpj das tabelas auxiliares e cnpj_da_scp são completados com zeros à esquerda até
   14 dígitos. NULL e string vazia são preservados; valor não numérico ou com mais de
   14 dígitos gera erro.
"""

import json
import re
import sys
import uuid
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

import duckdb
import pyarrow as pa

from pipeline import db

SCHEMA_ORIGEM = "raw"
SCHEMA_DESTINO = "refined"
LIMITE_PRECISAO_DECIMAL = 38  # maior largura de DECIMAL aceita pelo DuckDB
AMOSTRA = 5  # chaves/registros exibidos em mensagens de erro

ORIENTACAO_BRONZE = "Execute a ingestão Bronze: uv run python -m pipeline.ingestao"


class ErroTransformacao(Exception):
    """Falha que interrompe a transformação sem publicar nenhuma tabela Silver."""

    def __init__(
        self, etapa, motivo, *, origem=None, destino=None, coluna=None, exemplo=None
    ):
        super().__init__(motivo)
        self.etapa = etapa
        self.motivo = motivo
        self.origem = origem
        self.destino = destino
        self.coluna = coluna
        self.exemplo = exemplo

    def __str__(self):
        campos = [
            ("Etapa", self.etapa),
            ("Origem", self.origem),
            ("Destino", self.destino),
            ("Coluna", self.coluna),
            ("Exemplo", self.exemplo),
            ("Motivo", self.motivo),
        ]
        return "\n".join(
            f"  {rotulo + ':':<9}{valor}" for rotulo, valor in campos if valor
        )


@dataclass(frozen=True)
class Conversao:
    descricao: str
    formato: str | None = (
        None  # regex (RE2) que todo valor não nulo deve casar por inteiro
    )
    expressao: str = "{v}"  # SQL que leva o texto validado ao tipo de destino
    decimal: bool = False  # DECIMAL(p,s) calculado sobre todos os valores
    ausente: str | None = None  # marcador exato que a fonte usa para "sem valor"


TEXTO = Conversao("VARCHAR")
DATA_BR = Conversao(
    "DATE (DD/MM/YYYY)", r"\d{2}/\d{2}/\d{4}", "CAST(strptime({v}, '%d/%m/%Y') AS DATE)"
)
NUMERO_BR = Conversao(
    "DECIMAL (notação brasileira)",
    r"-?\d{1,3}(\.\d{3})*(,\d+)?%?",
    decimal=True,
    ausente="-",
)
TIMESTAMP_TZ = Conversao(
    "TIMESTAMP WITH TIME ZONE",
    r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)?[+-]\d{2}:\d{2}",
    "CAST({v} AS TIMESTAMPTZ)",
)
DOUBLE = Conversao("DOUBLE", r"-?\d+(\.\d+)?([eE][+-]?\d+)?", "CAST({v} AS DOUBLE)")
BIGINT = Conversao("BIGINT", r"-?\d+", "CAST({v} AS BIGINT)")
# 7.8: até 14 dígitos, completados com zeros à esquerda; string vazia permanece vazia.
CNPJ = Conversao(
    "CNPJ (somente dígitos, no máximo 14)",
    r"\d{0,14}",
    "CASE WHEN {v} = '' THEN {v} ELSE lpad({v}, 14, '0') END",
)

# Texto canônico 'NNNN.DD': sem separador de milhar, ponto decimal e sem % (sem dividir por 100).
NORMALIZACAO_BR = "replace(replace(regexp_replace({v}, '%$', ''), '.', ''), ',', '.')"
# Só as quebras de linha e tabulações externas observadas em Dív.Líq/ Patrim.
LIMPEZA_EXTREMIDADES = r"regexp_replace({v}, '^[\n\t]+|[\n\t]+$', '', 'g')"


@dataclass(frozen=True)
class Coluna:
    origem: str
    destino: str
    conversao: Conversao = TEXTO
    limpeza: str | None = None  # SQL aplicado antes da validação de formato


@dataclass(frozen=True)
class TabelaSql:
    origem: str
    destino: str
    colunas: tuple
    chave: tuple


TABELAS_SQL = (
    TabelaSql(
        "b3_empresas",
        "b3_empresas",
        (
            Coluna("codeCVM", "codigo_cvm"),
            Coluna("issuingCompany", "empresa_emissora"),
            Coluna("companyName", "razao_social"),
            Coluna("tradingName", "nome_pregao"),
            Coluna("cnpj", "cnpj", CNPJ),
            Coluna("marketIndicator", "indicador_mercado"),
            Coluna("typeBDR", "tipo_bdr"),
            Coluna("dateListing", "data_listagem", DATA_BR),
            Coluna("status", "situacao"),
            Coluna("segment", "segmento"),
            Coluna("segmentEng", "segmento_ingles"),
            Coluna("type", "tipo_empresa"),
            Coluna("market", "mercado"),
            Coluna("_timestamp_ingestao", "_timestamp_ingestao"),
            Coluna("_source_origin", "_source_origin"),
        ),
        ("codigo_cvm",),
    ),
    TabelaSql(
        "fundamentus_acoes",
        "fundamentus_acoes",
        (
            Coluna("Papel", "ticker"),
            Coluna("Cotação", "cotacao", NUMERO_BR),
            Coluna("P/L", "preco_lucro", NUMERO_BR),
            Coluna("P/VP", "preco_valor_patrimonial", NUMERO_BR),
            Coluna("PSR", "preco_vendas", NUMERO_BR),
            Coluna("Div.Yield", "dividend_yield", NUMERO_BR),
            Coluna("P/Ativo", "preco_ativo", NUMERO_BR),
            Coluna("P/Cap.Giro", "preco_capital_giro", NUMERO_BR),
            Coluna("P/EBIT", "preco_ebit", NUMERO_BR),
            Coluna("P/Ativ Circ.Liq", "preco_ativo_circulante_liquido", NUMERO_BR),
            Coluna("EV/EBIT", "enterprise_value_ebit", NUMERO_BR),
            Coluna("EV/EBITDA", "enterprise_value_ebitda", NUMERO_BR),
            Coluna("Mrg Bruta", "margem_bruta", NUMERO_BR),
            Coluna("Mrg Ebit", "margem_ebit", NUMERO_BR),
            Coluna("Mrg. Líq.", "margem_liquida", NUMERO_BR),
            Coluna("Liq. Corr.", "liquidez_corrente", NUMERO_BR),
            Coluna("ROIC", "roic", NUMERO_BR),
            Coluna("ROE", "roe", NUMERO_BR),
            Coluna("Liq.2meses", "liquidez_2_meses", NUMERO_BR),
            Coluna("Patrim. Líq", "patrimonio_liquido", NUMERO_BR),
            Coluna(
                "Dív.Líq/ Patrim.",
                "divida_liquida_patrimonio",
                NUMERO_BR,
                LIMPEZA_EXTREMIDADES,
            ),
            Coluna("Cresc. Rec.5a", "crescimento_receita_5_anos", NUMERO_BR),
            Coluna("_timestamp_ingestao", "_timestamp_ingestao"),
            Coluna("_source_origin", "_source_origin"),
        ),
        ("ticker",),
    ),
    TabelaSql(
        "yfinance_cotacoes",
        "yfinance_cotacoes",
        (
            Coluna("ticker", "ticker"),
            Coluna("Date", "data", TIMESTAMP_TZ),
            Coluna("Open", "abertura", DOUBLE),
            Coluna("High", "maxima", DOUBLE),
            Coluna("Low", "minima", DOUBLE),
            Coluna("Close", "fechamento", DOUBLE),
            Coluna("Adj Close", "fechamento_ajustado", DOUBLE),
            Coluna("Volume", "volume", BIGINT),
            Coluna("Dividends", "dividendos", DOUBLE),
            Coluna("Stock Splits", "desdobramentos", DOUBLE),
            Coluna("_source_origin", "_source_origin"),
            Coluna("_timestamp_ingestao", "_timestamp_ingestao"),
            Coluna("Capital Gains", "ganhos_capital", DOUBLE),
        ),
        ("ticker", "data"),
    ),
)

# --------------------------------------------------------------------------- contrato Minha Receita

TEXTO_JSON = "texto"
INTEIRO_JSON = "inteiro"
DECIMAL_JSON = "decimal"
BOOLEANO_JSON = "booleano"
DATA_JSON = "data"
CNPJ_JSON = "cnpj"

TIPOS_ARROW = {
    TEXTO_JSON: pa.string(),
    CNPJ_JSON: pa.string(),
    INTEIRO_JSON: pa.int64(),
    BOOLEANO_JSON: pa.bool_(),
    DATA_JSON: pa.date32(),
}

ORIGEM_MINHARECEITA = "minhareceita_empresas"
COLUNAS_BRONZE_MINHARECEITA = (
    "cnpj",
    "payload_json",
    "_timestamp_ingestao",
    "_source_origin",
)
METADADOS = ("_timestamp_ingestao", "_source_origin")

ESCALARES_EMPRESA = {
    "cnpj": CNPJ_JSON,
    "uf": TEXTO_JSON,
    "cep": TEXTO_JSON,
    "pais": TEXTO_JSON,
    "email": TEXTO_JSON,
    "porte": TEXTO_JSON,
    "bairro": TEXTO_JSON,
    "numero": TEXTO_JSON,
    "ddd_fax": TEXTO_JSON,
    "municipio": TEXTO_JSON,
    "logradouro": TEXTO_JSON,
    "cnae_fiscal": INTEIRO_JSON,
    "codigo_pais": INTEIRO_JSON,
    "complemento": TEXTO_JSON,
    "codigo_porte": INTEIRO_JSON,
    "razao_social": TEXTO_JSON,
    "nome_fantasia": TEXTO_JSON,
    "capital_social": DECIMAL_JSON,
    "ddd_telefone_1": TEXTO_JSON,
    "ddd_telefone_2": TEXTO_JSON,
    "opcao_pelo_mei": BOOLEANO_JSON,
    "codigo_municipio": INTEIRO_JSON,
    "natureza_juridica": TEXTO_JSON,
    "situacao_especial": TEXTO_JSON,
    "opcao_pelo_simples": BOOLEANO_JSON,
    "situacao_cadastral": INTEIRO_JSON,
    "data_opcao_pelo_mei": DATA_JSON,
    "data_exclusao_do_mei": DATA_JSON,
    "cnae_fiscal_descricao": TEXTO_JSON,
    "codigo_municipio_ibge": INTEIRO_JSON,
    "data_inicio_atividade": DATA_JSON,
    "data_situacao_especial": DATA_JSON,
    "data_opcao_pelo_simples": DATA_JSON,
    "data_situacao_cadastral": DATA_JSON,
    "nome_cidade_no_exterior": TEXTO_JSON,
    "codigo_natureza_juridica": INTEIRO_JSON,
    "data_exclusao_do_simples": DATA_JSON,
    "motivo_situacao_cadastral": INTEIRO_JSON,
    "ente_federativo_responsavel": TEXTO_JSON,
    "identificador_matriz_filial": INTEIRO_JSON,
    "qualificacao_do_responsavel": INTEIRO_JSON,
    "descricao_situacao_cadastral": TEXTO_JSON,
    "descricao_tipo_de_logradouro": TEXTO_JSON,
    "descricao_motivo_situacao_cadastral": TEXTO_JSON,
    "descricao_identificador_matriz_filial": TEXTO_JSON,
}


@dataclass(frozen=True)
class ArrayJson:
    propriedade: str
    destino: str
    sequencia: str | None  # coluna com a posição original (1, 2, ...) no array
    propriedades: dict  # propriedade JSON -> (coluna Silver, tipo)
    chave: tuple


ARRAYS_EMPRESA = (
    ArrayJson(
        "qsa",
        "minhareceita_qsa",
        "sequencia_socio",
        {
            "pais": ("pais", TEXTO_JSON),
            "nome_socio": ("nome_socio", TEXTO_JSON),
            "codigo_pais": ("codigo_pais", INTEIRO_JSON),
            "faixa_etaria": ("faixa_etaria", TEXTO_JSON),
            "cnpj_cpf_do_socio": ("cnpj_cpf_do_socio", TEXTO_JSON),
            "qualificacao_socio": ("qualificacao_socio", TEXTO_JSON),
            "codigo_faixa_etaria": ("codigo_faixa_etaria", INTEIRO_JSON),
            "data_entrada_sociedade": ("data_entrada_sociedade", DATA_JSON),
            "identificador_de_socio": ("identificador_de_socio", INTEIRO_JSON),
            "cpf_representante_legal": ("cpf_representante_legal", TEXTO_JSON),
            "nome_representante_legal": ("nome_representante_legal", TEXTO_JSON),
            "codigo_qualificacao_socio": ("codigo_qualificacao_socio", INTEIRO_JSON),
            "qualificacao_representante_legal": (
                "qualificacao_representante_legal",
                TEXTO_JSON,
            ),
            "codigo_qualificacao_representante_legal": (
                "codigo_qualificacao_representante_legal",
                INTEIRO_JSON,
            ),
        },
        ("cnpj", "sequencia_socio"),
    ),
    ArrayJson(
        "regime_tributario",
        "minhareceita_regime_tributario",
        "sequencia_regime",
        {
            "ano": ("ano", INTEIRO_JSON),
            "cnpj_da_scp": ("cnpj_da_scp", CNPJ_JSON),
            "forma_de_tributacao": ("forma_de_tributacao", TEXTO_JSON),
            "quantidade_de_escrituracoes": (
                "quantidade_de_escrituracoes",
                INTEIRO_JSON,
            ),
        },
        ("cnpj", "sequencia_regime"),
    ),
    ArrayJson(
        "cnaes_secundarios",
        "minhareceita_cnaes_secundarios",
        None,
        {
            "codigo": ("codigo_cnae", INTEIRO_JSON),
            "descricao": ("descricao", TEXTO_JSON),
        },
        ("cnpj", "codigo_cnae"),
    ),
)
CHAVE_EMPRESA = ("cnpj",)

TABELAS_BRONZE = tuple(t.origem for t in TABELAS_SQL) + (ORIGEM_MINHARECEITA,)

_FORMATO_DATA_JSON = re.compile(r"\d{4}-\d{2}-\d{2}")
_FORMATO_CNPJ = re.compile(r"\d{0,14}")


@dataclass(frozen=True)
class Preparada:
    """Tabela Silver já convertida, deduplicada e validada, aguardando publicação."""

    destino: str
    temporaria: str
    origem: int  # registros Bronze (ou elementos de array extraídos)
    antes_dedup: int
    duplicatas: int


# --------------------------------------------------------------------------- utilitários


def _bronze(tabela):
    return f"{db._ident(SCHEMA_ORIGEM)}.{db._ident(tabela)}"


def _silver(tabela):
    return f"{db._ident(SCHEMA_DESTINO)}.{db._ident(tabela)}"


def _rotulo_bronze(tabela):
    return f"{SCHEMA_ORIGEM}.{tabela}"


def _rotulo_silver(tabela):
    return f"{SCHEMA_DESTINO}.{tabela}"


def _temporaria(destino, sufixo):
    return f"temp.main.{db._ident(f'_silver_{destino}_{sufixo}')}"


def _fmt(n):
    return f"{n:,}".replace(",", ".")


@contextmanager
def _contexto(etapa, origem=None, destino=None, coluna=None):
    """Converte falhas do DuckDB/Arrow em ErroTransformacao com etapa, tabela e coluna."""
    try:
        yield
    except ErroTransformacao:
        raise
    except (duckdb.Error, pa.ArrowException) as exc:
        raise ErroTransformacao(
            etapa, str(exc), origem=origem, destino=destino, coluna=coluna
        ) from exc


def _contar(con, tabela):
    return con.execute(f"SELECT COUNT(*) FROM {tabela}").fetchall()[0][0]


def _registros(con, sql, parametros=None):
    cursor = con.execute(sql, parametros or [])
    nomes = [d[0] for d in cursor.description]
    return [dict(zip(nomes, linha, strict=True)) for linha in cursor.fetchall()]


def _formatar_registros(registros):
    return "\n" + "\n".join(f"    {r}" for r in registros)


# --------------------------------------------------------------------------- verificação Bronze


def verificar_bronze(con):
    existentes = {
        nome
        for (nome,) in con.execute(
            "SELECT table_name FROM duckdb_tables() "
            "WHERE database_name = current_database() AND schema_name = ?",
            [SCHEMA_ORIGEM],
        ).fetchall()
    }
    ausentes = [t for t in TABELAS_BRONZE if t not in existentes]
    if ausentes:
        raise ErroTransformacao(
            "verificação da Bronze",
            f"tabela(s) Bronze ausente(s): {', '.join(map(_rotulo_bronze, ausentes))}. "
            f"{ORIENTACAO_BRONZE}",
            origem=", ".join(map(_rotulo_bronze, ausentes)),
        )


def _validar_colunas_bronze(con, tabela, esperadas, destino):
    """Nenhuma coluna Bronze pode ser descartada em silêncio nem faltar ao mapeamento."""
    reais = [
        nome
        for (nome,) in con.execute(
            "SELECT column_name FROM duckdb_columns() WHERE database_name = current_database() "
            "AND schema_name = ? AND table_name = ? ORDER BY column_index",
            [SCHEMA_ORIGEM, tabela],
        ).fetchall()
    ]
    faltando = [c for c in esperadas if c not in reais]
    sobrando = [c for c in reais if c not in esperadas]
    if faltando or sobrando:
        partes = []
        if faltando:
            partes.append(f"colunas mapeadas ausentes na Bronze: {faltando}")
        if sobrando:
            partes.append(f"colunas Bronze sem mapeamento na Silver: {sobrando}")
        raise ErroTransformacao(
            "validação de estrutura",
            "; ".join(partes),
            origem=_rotulo_bronze(tabela),
            destino=_rotulo_silver(destino),
            coluna=", ".join(faltando + sobrando),
        )


# --------------------------------------------------------------------------- deduplicação e chaves


def _deduplicar_e_validar(con, destino, staging, chave, origem):
    """Remove duplicatas integralmente idênticas e valida a chave lógica (seção 9)."""
    rotulo = _rotulo_silver(destino)
    final = _temporaria(destino, "final")
    chave_sql = ", ".join(db._ident(c) for c in chave)
    with _contexto("deduplicação", destino=rotulo):
        antes = _contar(con, staging)
        con.execute(
            f"CREATE OR REPLACE TEMP TABLE {final} AS "
            f"SELECT DISTINCT * FROM {staging} ORDER BY ALL"
        )
        con.execute(f"DROP TABLE {staging}")
        depois = _contar(con, final)

    with _contexto("validação de chave", destino=rotulo, coluna=", ".join(chave)):
        filtro_nulo = " OR ".join(f"{db._ident(c)} IS NULL" for c in chave)
        n_nulas = con.execute(
            f"SELECT COUNT(*) FROM {final} WHERE {filtro_nulo}"
        ).fetchall()[0][0]
        nulas = _registros(
            con, f"SELECT * FROM {final} WHERE {filtro_nulo} LIMIT {AMOSTRA}"
        )
    if n_nulas:
        raise ErroTransformacao(
            "validação de chave",
            f"{_fmt(n_nulas)} registro(s) com chave lógica nula ({', '.join(chave)})",
            destino=rotulo,
            coluna=", ".join(chave),
            exemplo=_formatar_registros(nulas),
        )

    with _contexto("validação de chave", destino=rotulo, coluna=", ".join(chave)):
        repetidas = f"SELECT {chave_sql} FROM {final} GROUP BY ALL HAVING COUNT(*) > 1"
        n_conflitos = con.execute(f"SELECT COUNT(*) FROM ({repetidas})").fetchall()[0][
            0
        ]
        conflitos = _registros(
            con,
            f"SELECT f.* FROM {final} f SEMI JOIN "
            f"({repetidas} ORDER BY ALL LIMIT {AMOSTRA}) r USING ({chave_sql}) "
            f"ORDER BY ALL",
        )
    if n_conflitos:
        raise ErroTransformacao(
            "validação de chave",
            f"{_fmt(n_conflitos)} chave(s) ({', '.join(chave)}) com conteúdos divergentes; "
            "nenhum registro foi escolhido arbitrariamente",
            destino=rotulo,
            coluna=", ".join(chave),
            exemplo=_formatar_registros(conflitos),
        )

    return Preparada(destino, final, origem, antes, antes - depois)


# --------------------------------------------------------------------------- tabelas SQL (B3, Fundamentus, yfinance)


def _tipo_decimal(con, tabela, coluna, normalizado):
    """Menor DECIMAL(p,s) que representa exatamente todos os valores da coluna (7.2)."""
    with _contexto(
        "cálculo de precisão DECIMAL",
        _rotulo_bronze(tabela.origem),
        _rotulo_silver(tabela.destino),
        coluna.origem,
    ):
        inteiros, escala = con.execute(
            f"""
            SELECT
                COALESCE(MAX(length(ltrim(split_part(ltrim(n, '-'), '.', 1), '0'))), 0),
                COALESCE(MAX(length(split_part(n, '.', 2))), 0)
            FROM (SELECT {normalizado} AS n FROM {_bronze(tabela.origem)})
            WHERE n IS NOT NULL
            """
        ).fetchall()[0]
    precisao = max(inteiros, 1) + escala
    if precisao > LIMITE_PRECISAO_DECIMAL:
        raise ErroTransformacao(
            "cálculo de precisão DECIMAL",
            f"precisão necessária DECIMAL({precisao},{escala}) ultrapassa o limite do DuckDB "
            f"({LIMITE_PRECISAO_DECIMAL} dígitos)",
            origem=_rotulo_bronze(tabela.origem),
            destino=_rotulo_silver(tabela.destino),
            coluna=coluna.origem,
        )
    return f"DECIMAL({precisao}, {escala})"


def _expressao_coluna(con, tabela, coluna):
    """Valida o formato de todos os valores e devolve a expressão SQL de conversão estrita."""
    origem_sql = _bronze(tabela.origem)
    bruto = db._ident(coluna.origem)
    valor = coluna.limpeza.replace("{v}", bruto) if coluna.limpeza else bruto
    conversao = coluna.conversao
    if conversao.ausente is not None:
        valor = f"NULLIF({valor}, '{conversao.ausente}')"
    contexto = (
        _rotulo_bronze(tabela.origem),
        _rotulo_silver(tabela.destino),
        coluna.origem,
    )
    if conversao.formato is None:
        return valor

    with _contexto("validação de formato", *contexto):
        invalidos = con.execute(
            f"SELECT {bruto} FROM {origem_sql} "
            f"WHERE {valor} IS NOT NULL AND NOT regexp_full_match({valor}, ?) LIMIT 1",
            [conversao.formato],
        ).fetchall()
    if invalidos:
        raise ErroTransformacao(
            "validação de formato",
            f"valor incompatível com o tipo de destino {conversao.descricao}",
            origem=contexto[0],
            destino=contexto[1],
            coluna=coluna.origem,
            exemplo=repr(invalidos[0][0]),
        )

    if conversao.decimal:
        normalizado = NORMALIZACAO_BR.replace("{v}", valor)
        expressao = (
            f"CAST({normalizado} AS {_tipo_decimal(con, tabela, coluna, normalizado)})"
        )
    else:
        expressao = conversao.expressao.replace("{v}", valor)

    # A conversão é executada por coluna para que a falha identifique a coluna envolvida.
    with _contexto("conversão de tipo", *contexto):
        con.execute(f"SELECT MAX({expressao}) FROM {origem_sql}").fetchall()
    return expressao


def preparar_tabela_sql(con, tabela):
    rotulo_origem = _rotulo_bronze(tabela.origem)
    with _contexto("leitura", rotulo_origem, _rotulo_silver(tabela.destino)):
        _validar_colunas_bronze(
            con, tabela.origem, [c.origem for c in tabela.colunas], tabela.destino
        )
        origem = _contar(con, _bronze(tabela.origem))

    selecao = ", ".join(
        f"{_expressao_coluna(con, tabela, c)} AS {db._ident(c.destino)}"
        for c in tabela.colunas
    )
    staging = _temporaria(tabela.destino, "staging")
    with _contexto("conversão de tipo", rotulo_origem, _rotulo_silver(tabela.destino)):
        con.execute(
            f"CREATE OR REPLACE TEMP TABLE {staging} AS "
            f"SELECT {selecao} FROM {_bronze(tabela.origem)}"
        )
    return _deduplicar_e_validar(con, tabela.destino, staging, tabela.chave, origem)


# --------------------------------------------------------------------------- Minha Receita (JSON)


def _erro_json(motivo, destino, coluna, exemplo):
    return ErroTransformacao(
        "validação estrutural JSON",
        motivo,
        origem=f"{_rotulo_bronze(ORIGEM_MINHARECEITA)}.payload_json",
        destino=_rotulo_silver(destino),
        coluna=coluna,
        exemplo=exemplo,
    )


def _decodificar(cnpj, payload):
    def sem_duplicatas(pares):
        objeto = {}
        for chave, valor in pares:
            if chave in objeto:
                raise ValueError(f"propriedade duplicada no objeto JSON: {chave!r}")
            objeto[chave] = valor
        return objeto

    def rejeitar_constante(nome):
        raise ValueError(f"constante numérica não suportada: {nome}")

    if payload is None:
        raise _erro_json(
            "payload_json nulo", ORIGEM_MINHARECEITA, "payload_json", f"cnpj {cnpj}"
        )
    try:
        # Decimal mantém exatamente a representação dos números não inteiros.
        return json.loads(
            payload,
            parse_float=Decimal,
            parse_constant=rejeitar_constante,
            object_pairs_hook=sem_duplicatas,
        )
    except ValueError as exc:
        raise _erro_json(
            f"JSON inválido: {exc}", ORIGEM_MINHARECEITA, "payload_json", f"cnpj {cnpj}"
        ) from exc


def _validar_objeto(objeto, esperadas, destino, caminho, cnpj):
    if not isinstance(objeto, dict):
        raise _erro_json(
            f"esperado objeto JSON, encontrado {type(objeto).__name__}",
            destino,
            caminho,
            f"{objeto!r} (cnpj {cnpj})",
        )
    faltando = [p for p in esperadas if p not in objeto]
    if faltando:
        raise _erro_json(
            f"propriedade(s) obrigatória(s) ausente(s): {faltando}",
            destino,
            caminho,
            f"cnpj {cnpj}",
        )
    sobrando = [p for p in objeto if p not in esperadas]
    if sobrando:
        raise _erro_json(
            f"propriedade(s) não prevista(s) no contrato da Silver: {sobrando}",
            destino,
            caminho,
            f"cnpj {cnpj}",
        )


def _valor(valor, tipo, destino, coluna, cnpj):
    """Valida o tipo JSON e devolve o valor Python correspondente; nulo continua nulo."""
    if valor is None:
        return None
    if tipo == TEXTO_JSON and isinstance(valor, str):
        return valor
    if tipo == CNPJ_JSON and isinstance(valor, str):
        if not _FORMATO_CNPJ.fullmatch(valor):
            raise _erro_json(
                "CNPJ deve conter somente dígitos, no máximo 14",
                destino,
                coluna,
                f"{valor!r} (cnpj {cnpj})",
            )
        return valor.zfill(14) if valor else valor  # 7.8: string vazia permanece vazia
    if tipo == INTEIRO_JSON and type(valor) is int:
        return valor
    if tipo == DECIMAL_JSON and type(valor) in (int, Decimal):
        return Decimal(valor)
    if tipo == BOOLEANO_JSON and type(valor) is bool:
        return valor
    if tipo == DATA_JSON and isinstance(valor, str):
        try:
            if not _FORMATO_DATA_JSON.fullmatch(valor):
                raise ValueError("formato diferente de YYYY-MM-DD")
            return datetime.strptime(valor, "%Y-%m-%d").date()
        except ValueError as exc:
            raise _erro_json(
                f"data inválida: {exc}", destino, coluna, f"{valor!r} (cnpj {cnpj})"
            ) from exc
    raise _erro_json(
        f"tipo JSON {type(valor).__name__} incompatível com o tipo esperado ({tipo})",
        destino,
        coluna,
        f"{valor!r} (cnpj {cnpj})",
    )


def _precisao_escala(valores):
    inteiros = escala = 0
    for valor in valores:
        if valor is None:
            continue
        _, digitos, expoente = valor.as_tuple()
        escala = max(escala, -expoente)
        inteiros = max(inteiros, len(digitos) + expoente)
    return max(inteiros, 1) + escala, escala


def _tabela_arrow(destino, colunas, linhas):
    """colunas: [(nome, tipo JSON)]; DECIMAL recebe precisão calculada sobre todos os valores."""
    arrays, campos = [], []
    for nome, tipo in colunas:
        valores = [linha[nome] for linha in linhas]
        if tipo == DECIMAL_JSON:
            precisao, escala = _precisao_escala(valores)
            if precisao > LIMITE_PRECISAO_DECIMAL:
                raise ErroTransformacao(
                    "cálculo de precisão DECIMAL",
                    f"precisão necessária DECIMAL({precisao},{escala}) ultrapassa o limite "
                    f"do DuckDB ({LIMITE_PRECISAO_DECIMAL} dígitos)",
                    origem=f"{_rotulo_bronze(ORIGEM_MINHARECEITA)}.payload_json",
                    destino=_rotulo_silver(destino),
                    coluna=nome,
                )
            tipo_arrow = pa.decimal128(precisao, escala)
        else:
            tipo_arrow = TIPOS_ARROW[tipo]
        with _contexto(
            "conversão de tipo",
            _rotulo_bronze(ORIGEM_MINHARECEITA),
            _rotulo_silver(destino),
            nome,
        ):
            arrays.append(pa.array(valores, type=tipo_arrow))
        campos.append(pa.field(nome, tipo_arrow))
    return pa.Table.from_arrays(arrays, schema=pa.schema(campos))


def _carregar_staging(con, destino, tabela_arrow):
    staging = _temporaria(destino, "staging")
    visao = f"_arrow_{uuid.uuid4().hex}"
    with _contexto("conversão de tipo", destino=_rotulo_silver(destino)):
        con.register(visao, tabela_arrow)
        try:
            con.execute(
                f"CREATE OR REPLACE TEMP TABLE {staging} AS "
                f"SELECT * FROM {db._ident(visao)}"
            )
        finally:
            con.unregister(visao)
    return staging


def preparar_minhareceita(con):
    """Valida o contrato JSON em todos os registros e prepara as quatro tabelas da Minha Receita."""
    rotulo = _rotulo_bronze(ORIGEM_MINHARECEITA)
    with _contexto("leitura", rotulo, _rotulo_silver(ORIGEM_MINHARECEITA)):
        _validar_colunas_bronze(
            con, ORIGEM_MINHARECEITA, COLUNAS_BRONZE_MINHARECEITA, ORIGEM_MINHARECEITA
        )
        linhas_bronze = con.execute(
            f"SELECT cnpj, payload_json, _timestamp_ingestao, _source_origin "
            f"FROM {_bronze(ORIGEM_MINHARECEITA)} ORDER BY cnpj"
        ).fetchall()

    esperadas_empresa = list(ESCALARES_EMPRESA) + [
        a.propriedade for a in ARRAYS_EMPRESA
    ]
    empresas = []
    derivadas = {a.destino: [] for a in ARRAYS_EMPRESA}
    for cnpj, payload, timestamp, origem in linhas_bronze:
        dados = _decodificar(cnpj, payload)
        _validar_objeto(
            dados, esperadas_empresa, ORIGEM_MINHARECEITA, "payload_json", cnpj
        )
        metadados = {"_timestamp_ingestao": timestamp, "_source_origin": origem}
        empresa = {
            p: _valor(dados[p], tipo, ORIGEM_MINHARECEITA, p, cnpj)
            for p, tipo in ESCALARES_EMPRESA.items()
        }
        # A correspondência é verificada entre os valores já padronizados com 14 dígitos (7.8).
        cnpj_bronze = _valor(
            cnpj, CNPJ_JSON, ORIGEM_MINHARECEITA, "cnpj (linha Bronze)", cnpj
        )
        if empresa["cnpj"] != cnpj_bronze:
            raise _erro_json(
                "CNPJ da linha Bronze diverge da propriedade cnpj do JSON",
                ORIGEM_MINHARECEITA,
                "cnpj",
                f"linha Bronze {cnpj!r} x JSON {dados['cnpj']!r}",
            )
        empresas.append(empresa | metadados)

        for array in ARRAYS_EMPRESA:
            itens = dados[array.propriedade]
            if itens is None:  # array nulo não gera linhas (7.7)
                continue
            if not isinstance(itens, list):
                raise _erro_json(
                    f"esperado array JSON, encontrado {type(itens).__name__}",
                    array.destino,
                    array.propriedade,
                    f"{itens!r} (cnpj {cnpj})",
                )
            for posicao, item in enumerate(itens, start=1):
                caminho = f"{array.propriedade}[{posicao}]"
                _validar_objeto(
                    item, list(array.propriedades), array.destino, caminho, cnpj
                )
                linha = {"cnpj": empresa["cnpj"]}
                if array.sequencia:
                    linha[array.sequencia] = posicao
                for propriedade, (coluna, tipo) in array.propriedades.items():
                    linha[coluna] = _valor(
                        item[propriedade],
                        tipo,
                        array.destino,
                        f"{caminho}.{propriedade}",
                        cnpj,
                    )
                derivadas[array.destino].append(linha | metadados)

    preparadas = []
    colunas_empresa = list(ESCALARES_EMPRESA.items()) + [
        (m, TEXTO_JSON) for m in METADADOS
    ]
    staging = _carregar_staging(
        con,
        ORIGEM_MINHARECEITA,
        _tabela_arrow(ORIGEM_MINHARECEITA, colunas_empresa, empresas),
    )
    preparadas.append(
        _deduplicar_e_validar(
            con, ORIGEM_MINHARECEITA, staging, CHAVE_EMPRESA, len(linhas_bronze)
        )
    )

    for array in ARRAYS_EMPRESA:
        linhas = derivadas[array.destino]
        colunas = (
            [("cnpj", TEXTO_JSON)]
            + ([(array.sequencia, INTEIRO_JSON)] if array.sequencia else [])
            + list(array.propriedades.values())
            + [(m, TEXTO_JSON) for m in METADADOS]
        )
        staging = _carregar_staging(
            con, array.destino, _tabela_arrow(array.destino, colunas, linhas)
        )
        preparadas.append(
            _deduplicar_e_validar(con, array.destino, staging, array.chave, len(linhas))
        )
    return preparadas


# --------------------------------------------------------------------------- publicação atômica


def publicar(con, preparadas):
    """Substitui as tabelas Silver em uma única transação; qualquer falha faz rollback (seção 13)."""
    con.begin()
    try:
        db.criar_schema(con, SCHEMA_DESTINO)
        for p in preparadas:
            con.execute(
                f"CREATE OR REPLACE TABLE {_silver(p.destino)} AS SELECT * FROM {p.temporaria}"
            )
        con.commit()
    except Exception as exc:
        with suppress(duckdb.Error):  # a transação já foi abortada pelo próprio DuckDB
            con.rollback()
        raise ErroTransformacao(
            "publicação",
            f"{exc} — rollback executado: nenhuma tabela Silver foi alterada",
            destino=SCHEMA_DESTINO,
        ) from exc


# --------------------------------------------------------------------------- relatório


def _coletar_relatorio(con, preparadas):
    relatorio = []
    for p in preparadas:
        with _contexto("relatório", destino=_rotulo_silver(p.destino)):
            colunas = [
                nome
                for (nome,) in con.execute(
                    "SELECT column_name FROM duckdb_columns() WHERE database_name = current_database() "
                    "AND schema_name = ? AND table_name = ? ORDER BY column_index",
                    [SCHEMA_DESTINO, p.destino],
                ).fetchall()
            ]
            contagens = con.execute(
                "SELECT COUNT(*), "
                + ", ".join(f"COUNT(*) - COUNT({db._ident(c)})" for c in colunas)
                + f" FROM {_silver(p.destino)}"
            ).fetchall()[0]
        relatorio.append(
            {
                "tabela": _rotulo_silver(p.destino),
                "origem": p.origem,
                "antes_dedup": p.antes_dedup,
                "duplicatas": p.duplicatas,
                "gravados": contagens[0],
                "processados": p.antes_dedup,
                "nulos": dict(zip(colunas, contagens[1:], strict=True)),
            }
        )
    return relatorio


def _imprimir_relatorio(relatorio):
    largura = 44
    numeros = max([len(_fmt(r["gravados"])) for r in relatorio] + [12])

    def linha(rotulo, n, recuo=2):
        print(f"{' ' * recuo}{rotulo:<{largura - recuo}}{_fmt(n):>{numeros}}")

    for r in relatorio:
        print()
        print(r["tabela"])
        print("-" * (largura + numeros))
        linha("Registros de origem", r["origem"])
        linha("Registros antes da deduplicação", r["antes_dedup"])
        linha("Duplicatas idênticas removidas", r["duplicatas"])
        linha("Registros gravados", r["gravados"])
        linha("Total de registros processados", r["processados"])
        print("  Valores nulos por coluna:")
        for coluna, n in r["nulos"].items():
            linha(coluna, n, recuo=4)
    total = sum(r["gravados"] for r in relatorio)
    print()
    print("=" * (largura + numeros))
    print(f"{'TOTAL GRAVADO NAS SETE TABELAS':<{largura}}{_fmt(total):>{numeros}}")


# --------------------------------------------------------------------------- orquestração


def executar(con):
    """Prepara e valida as sete tabelas e só então as publica atomicamente."""
    with _contexto("verificação da Bronze"):
        verificar_bronze(con)
    preparadas = [preparar_tabela_sql(con, t) for t in TABELAS_SQL]
    preparadas += preparar_minhareceita(con)
    publicar(con, preparadas)
    return _coletar_relatorio(con, preparadas)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    try:
        con = db.conectar()
    except duckdb.Error as exc:
        print(
            f"\nERRO DE TRANSFORMAÇÃO\n  Etapa:   conexão\n  Motivo:  {exc}",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        relatorio = executar(con)
    except ErroTransformacao as exc:
        print(f"\nERRO DE TRANSFORMAÇÃO\n{exc}", file=sys.stderr)
        print("Nenhuma tabela Silver foi alterada.", file=sys.stderr)
        sys.exit(1)
    finally:
        con.close()
    _imprimir_relatorio(relatorio)


if __name__ == "__main__":
    main()
