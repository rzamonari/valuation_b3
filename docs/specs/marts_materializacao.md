# ESPECIFICAÇÃO TÉCNICA — CAMADA GOLD (MARTS)
## Pipeline de Indicadores Fundamentalistas — Arquitetura Medallion

**Versão:** 1.0  
**Linguagem:** Python 3.13 / SQL DuckDB  
**Gerenciador de dependências:** uv  
**Banco de dados:** `fundamentalistas.duckdb`  
**Camada:** Gold (Marts)  
**Diretório obrigatório dos arquivos SQL:** `sql/marts/`

---

# 1. PAPEL E DIRETRIZES DO DESENVOLVIMENTO

Atue como consultor especialista e perito em Engenharia de Dados, com mais de 20 anos de experiência em arquitetura de dados, modelagem dimensional, SQL analítico, DuckDB e desenvolvimento orientado por especificações (Spec-Driven Development).

O desenvolvimento deverá seguir rigorosamente esta especificação.

A especificação é a fonte única da verdade do projeto. O código SQL deverá ser consequência direta das regras aqui documentadas.

Não invente regras de negócio, fórmulas financeiras, fontes de dados, relacionamentos ou premissas que não estejam documentados.

Quando uma informação indispensável não estiver definida, não presuma uma resposta. Registre a pendência e solicite confirmação antes de implementar a funcionalidade afetada.

# AJUSTE DA SPEC — MATERIALIZAÇÃO DOS RESULTADOS NA CAMADA GOLD

## 1. Objetivo adicional

Além da análise, revisão e validação das consultas SQL existentes em `sql/marts/`, o trabalho deverá contemplar a implementação da materialização de seus resultados em tabelas físicas no banco de dados `fundamentalistas.duckdb`, utilizando o schema `marts`.

O objetivo é garantir que os resultados produzidos pelas consultas SQL estejam efetivamente disponíveis e atualizados como tabelas persistentes da camada Gold.

O escopo permanece restrito às consultas SQL existentes em `sql/marts/`.

## 2. Materialização das consultas

Para cada arquivo SQL encontrado em `sql/marts/`, deverá ser avaliada e implementada a correspondente materialização de seu resultado em uma tabela física no schema `marts`.

A implementação deverá:

1. Identificar a consulta SQL existente.
2. Compreender sua finalidade e seu resultado.
3. Identificar as colunas retornadas e seus respectivos tipos.
4. Identificar a granularidade e a chave lógica do resultado.
5. Validar a consulta no DuckDB.
6. Definir o nome da tabela de destino, respeitando as convenções existentes no projeto.
7. Criar a tabela física correspondente no schema `marts`.
8. Carregar os resultados produzidos pela consulta.
9. Validar a consistência entre o resultado da consulta original e os registros materializados.

Não criar tabelas para funcionalidades ou consultas que não existam no inventário de `sql/marts/`.

## 3. Banco de dados e schema de destino

Banco de dados:

`fundamentalistas.duckdb`

Schema de destino:

`marts`

Todas as tabelas materializadas deverão pertencer ao schema `marts`.

Antes de implementar, verificar se o schema já existe e respeitar a estrutura e as convenções atuais do projeto.

Caso o schema não exista, sua criação deverá ser realizada de maneira controlada, sem modificar os schemas `raw` e `refined`.

## 4. Estratégia de atualização das tabelas

As tabelas Gold deverão refletir os resultados atuais das respectivas consultas SQL.

A estratégia de atualização deverá evitar registros duplicados, dados obsoletos e inconsistências entre execuções.

Para consultas que representam uma fotografia atual dos indicadores, rankings, recomendações ou cards, avaliar a substituição integral dos dados da tabela de destino a cada atualização.

Para consultas que representam séries históricas, como cotações, respeitar a granularidade temporal e a regra de atualização efetivamente definida pela consulta existente.

Não presumir que todas as tabelas devam utilizar a mesma estratégia de atualização.

A estratégia deverá ser definida considerando a finalidade, a granularidade e a natureza dos dados de cada consulta.

## 5. Integridade e consistência da materialização

Após a carga, executar validações para garantir que:

- A quantidade de registros materializados corresponda à quantidade de registros retornados pela consulta de origem.
- As colunas da tabela de destino correspondam às colunas retornadas pelo SQL.
- Os tipos de dados sejam compatíveis.
- Não existam duplicações indevidas.
- Os valores materializados correspondam aos valores produzidos pela consulta.
- Os valores nulos sejam preservados conforme o resultado original.
- A granularidade da tabela seja respeitada.
- Uma nova execução não provoque duplicação de registros.

A validação deverá considerar a chave lógica de cada resultado, quando identificável.

## 6. Segurança e atomicidade da atualização

A atualização das tabelas deverá ser realizada de forma controlada.

Sempre que tecnicamente aplicável, utilizar transações para garantir que uma falha durante a atualização não deixe a tabela de destino em estado inconsistente.

Não remover os dados anteriores antes de garantir que a consulta de origem foi executada e validada com sucesso.

Em caso de falha:

- Preservar os dados anteriormente materializados sempre que possível.
- Registrar o erro.
- Identificar a consulta responsável.
- Não declarar a atualização como concluída.

## 7. Integração com a estrutura existente do projeto

Antes de implementar o mecanismo de materialização, analisar a estrutura atual do projeto para identificar:

- Como o DuckDB é inicializado.
- Como o banco `fundamentalistas.duckdb` é acessado.
- Como os arquivos SQL são executados.
- Se já existe algum mecanismo de atualização de tabelas.
- Se existe uma convenção para nomes de tabelas Gold.
- Se existe um fluxo de execução ou orquestração das consultas.

Reutilizar os mecanismos existentes sempre que possível.

Não inventar APIs, funções, módulos ou padrões de execução sem antes verificar o que já existe no projeto.

A implementação deverá manter a arquitetura atual e evitar duplicação desnecessária de código.

## 8. Restrições

A materialização deverá utilizar exclusivamente os resultados das consultas SQL existentes em `sql/marts/`.

Não criar novas regras de negócio.

Não adicionar cálculos ou indicadores que não estejam nas consultas existentes.

Não alterar os dados das tabelas `raw` e `refined`.

Não modificar os processos de ingestão ou transformação.

Não criar tabelas fora do schema `marts` para atender a esta etapa.

Não substituir consultas existentes por novas implementações sem justificativa e autorização.

## 9. Critérios adicionais de aceite

A etapa de materialização será considerada concluída quando:

1. Todas as consultas existentes em `sql/marts/` tiverem sido inventariadas.
2. Todas as consultas aplicáveis tiverem sido validadas.
3. Cada consulta elegível possuir sua correspondente tabela física no schema `marts`.
4. Os resultados tiverem sido efetivamente carregados no banco `fundamentalistas.duckdb`.
5. A quantidade de registros e os valores materializados tiverem sido validados.
6. A estratégia de atualização de cada tabela estiver documentada.
7. A execução repetida não provocar duplicações indevidas.
8. Falhas de execução não comprometerem os dados anteriormente materializados.
9. Os schemas `raw` e `refined` permanecerem inalterados.

**Resultado esperado:** o banco `fundamentalistas.duckdb` deverá possuir uma camada Gold (`marts`) materializada, composta pelas tabelas correspondentes às consultas SQL efetivamente existentes em `sql/marts/`, com dados consistentes e atualizáveis.