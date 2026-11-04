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