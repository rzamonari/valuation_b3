# Decisões

As especificações abaixo orientaram a implementação de cada camada. Os módulos citam a spec de
origem na docstring, junto das decisões de implementação.

| Spec | Camada | Citada em |
|---|---|---|
| [Bronze — ingestão](specs/raw_ingestao.md) | `raw` | `pipeline/ingestao.py` |
| [Silver — transformação](specs/refined_transformacao.md) | `refined` | `pipeline/transformacao/` |
| [Gold — materialização](specs/marts_materializacao.md) | `marts` | `pipeline/materializacao.py`, `sql/marts/README.md` |
| [Gold — indicadores](specs/marts_sql_indicadores.md) | `marts` | `sql/marts/README.md` |
| [Gold — rankings](specs/marts_sql_rank.md) | `marts` | `sql/marts/RANKINGS.md` |
| [Apresentação — painel](specs/dashboard_apresentacao.md) | — | `painel.py`, `app.py` |
| [Testes](specs/testes_codigo.md) | — | `test/` |

## Decisões transversais

- **Banco local único.** Um arquivo DuckDB na raiz; caminho derivado de `Path(__file__)`, não do
  diretório corrente.
- **Bronze sem interpretação.** Tudo é gravado como `VARCHAR` exatamente como veio, para que a
  tipagem e as regras fiquem na Silver e possam ser refeitas sem nova extração.
- **SQL como fonte da verdade da Gold.** Cada mart é um `SELECT` puro em `sql/marts/`; a
  materialização só executa, valida e publica.
- **Painel sem cálculo.** Todo número exibido vem de um mart; o painel só filtra, ordena e
  formata.
- **Zeros do Fundamentus preservados.** Podem significar ausência de dado; os rankings os excluem
  com critérios `> 0` em vez de reescrevê-los.
- **Cards copiam a consulta de `marts_50`.** Cada mart do painel é autocontido; a consistência
  com a recomendação consolidada é garantida por teste (`test/test_sql_marts.py`).
- **Toda mudança entra por PR com o CI verde, inclusive `data:` e `docs:`.** A `main` é
  protegida: sem push direto nem force push; os checks `ruff`, `pytest (ubuntu-latest)` e
  `pytest (windows-latest)` são obrigatórios e a branch precisa estar atualizada com a `main`
  antes do merge. Sem exigência de revisor (projeto de um autor só); a branch é apagada no merge.

## Limitações aceitas

Ver a seção *Limitações conhecidas* da [Referência da API](referencia/api.md) e as observações em
[Marts](referencia/marts.md) e [Rankings](referencia/rankings.md).

## Contrato das fontes e observabilidade

- **Contrato das fontes fora do pytest padrão.** Os testes de `test/contrato/`
  (`@pytest.mark.contrato`) fazem uma chamada real e pequena a cada fonte e comparam a resposta
  com o contrato da própria Silver: colunas mapeadas em `pipeline/transformacao/` e os formatos de
  cada `Conversao`. Campo a mais também conta como mudança, porque a Silver recusa coluna Bronze
  sem mapeamento. Ficam fora do `pytest` do CI de PR (`addopts = -m "not contrato"`): o CI não
  pode depender de rede nem de terceiros. Rodam toda segunda pelo workflow
  `contrato-fontes.yml`, que abre uma issue (ou comenta na aberta) com a mensagem de cada teste.
  A falha do contrato avisa antes que a próxima ingestão quebre no meio.
- **Registro de execução no próprio banco.** Cada etapa grava uma linha em `meta.execucoes`
  (etapa, início, fim, duração, linhas por tabela, status, avisos e erro), sem dependência nova:
  o erro e os avisos vêm do próprio log da etapa (`pipeline.log.capturar`). O registro nunca muda
  o resultado da etapa: se não puder gravar (banco bloqueado), só avisa.
- **Saúde como mart, idade fora dele.** `marts_painel_saude_pipeline` traz a última execução de
  cada etapa e é republicado pelo registro com a mesma materialização da Gold, para o painel ler a
  saúde como lê qualquer outro mart. A idade dos dados em dias úteis depende do dia em que o painel
  é aberto. Num mart materializado, ou na fotografia, ela ficaria congelada; por isso é calculada
  na leitura (`pipeline.execucao.idade`), com alerta acima de 5 dias úteis.
- **Saúde fora do hash da fotografia.** O mart de saúde tem arquivo e SHA-256 no manifesto, mas
  não entra no hash total: o hash identifica os dados, e os horários das execuções mudam a cada
  ciclo mesmo quando os dados são iguais.

## Por que materialização própria, e não dbt-duckdb

A Gold são 33 `SELECT`s em `sql/marts/`. Quem os executa e publica é
`pipeline/materializacao.py` (~560 linhas), e não o dbt com o adaptador `dbt-duckdb`. A escolha
vale para o tamanho e o modo de uso atuais do projeto. Não é uma posição contra o dbt.

### O que a materialização própria garante

| Garantia | Como funciona aqui | No dbt |
|---|---|---|
| **Grão obrigatório** | Todo `.sql` precisa de uma chave declarada em `MARTS`, senão a execução para antes de começar. Chave vazia = exatamente uma linha. | Modelo sem teste roda normalmente. Exigir `unique` + `not_null` em todo modelo pede um pacote (ex.: dbt-project-evaluator) ou uma checagem própria no CI. "Exatamente uma linha" é teste customizado. |
| **Ordem topológica** | Extrai `marts.<nome>` do texto sem comentários e ordena (empate alfabético); dependência não declarada ou ciclo param no inventário. | Nativo com `ref()`, e mais robusto: o grafo vem do código, não de uma expressão regular. **Aqui o dbt é melhor.** |
| **Validação na temporária** | Cada consulta roda uma vez numa tabela temporária; colunas e tipos são conferidos contra o `DESCRIBE`, e a chave contra nulos e duplicatas, **antes** de tocar a Gold. | `dbt build` testa depois de materializar: o teste que falha impede os modelos seguintes, mas a tabela do modelo testado já foi trocada. Model contracts conferem colunas e tipos no build; a chave fica para depois. |
| **Transação única** | Os 33 marts são trocados numa transação. Falha em qualquer um = `ROLLBACK` e a Gold anterior inteira continua valendo. | Cada modelo tem a sua transação. Uma falha no meio deixa a Gold mista (parte nova, parte antiga) até a próxima execução. Dá para montar blue/green (schema de staging + troca num `run-operation`), mas é código próprio do mesmo jeito. |
| **EXCEPT ALL antes do COMMIT** | Cada tabela publicada é comparada com a temporária: contagem, colunas, tipos e valores nos dois sentidos. | Não existe. É uma defesa contra erro de publicação, rara mas barata no DuckDB local. |
| **Portão de qualidade** | `pipeline.qualidade` (79 verificações, ERRO ou AVISO) bloqueia a fotografia. | Equivalente direto: cada `Verificacao` já é um teste singular do dbt (um `SELECT` das violações), e ERRO/AVISO é o `severity: error/warn`. **Aqui o dbt cobriria igual.** |

### O que o dbt daria de graça

- **Lineage e documentação navegável** (`dbt docs generate`): grafo de dependências, descrição
  por coluna e catálogo com tipos. Hoje isso é escrito à mão em `sql/marts/README.md` e
  `doc_api.md`, e pode ficar desatualizado.
- **Testes genéricos prontos** (`unique`, `not_null`, `accepted_values`, `relationships`) e
  pacotes como `dbt_utils` e `dbt_expectations`, em vez de escrever cada regra em SQL.
- **Freshness de fonte** (`dbt source freshness`), que cobriria parte da idade dos dados feita
  aqui à mão.
- **Seleção e CI incremental**: `dbt build -s +marts_50` e *slim CI* (`state:modified`), que só
  reconstroem o que mudou.
- **Materialização incremental** para séries grandes, como `marts_cotacao`.
- **Familiaridade**: quem chega conhece o dbt; a `materializacao.py` precisa ser lida.

### Custos de adotar agora

- Duas orquestrações: a Bronze e a Silver continuam em Python (extração com retry, conversões
  estritas, contrato JSON da Minha Receita), e o dbt cobriria só a Gold.
- Os `.sql` deixam de ser `SELECT`s puros: `{{ ref() }}` e `{{ source() }}` exigem compilação.
  Hoje cada arquivo roda como está na DuckDB UI e nos testes.
- Perda da atomicidade da Gold inteira, ou código próprio para recuperá-la.
- Dependências novas (`dbt-core`, `dbt-duckdb` e as transitivas) e `profiles.yml`. Também é
  preciso confirmar o suporte a Python 3.13 a cada atualização.

### Quando valeria migrar

- A Gold passa de algumas dezenas para uma centena de modelos, ou mais de uma pessoa edita SQL:
  o lineage, a documentação gerada e a seleção passam a pagar o custo.
- `marts_cotacao` ou outra série fica grande demais para a substituição integral: o incremental
  do dbt entra.
- O banco sai do arquivo local (MotherDuck, Postgres, um warehouse) ou outros times consomem a
  Gold e precisam de catálogo e contratos.
- A Silver também vira SQL: aí uma ferramenta orquestra as duas camadas.

**Caminho de migração**, se chegar a hora: cada `.sql` vira um modelo, com `marts.<nome>` →
`{{ ref('<nome>') }}` e `refined.<tabela>` → `{{ source('refined', '<tabela>') }}`. A chave de
`MARTS` vira `unique` + `not_null` (ou `dbt_utils.unique_combination_of_columns`), e as
verificações da qualidade viram testes singulares com a mesma severidade. A atomicidade vira um
build num schema de staging seguido de troca. A fotografia e o registro de execução continuam em
Python, lendo o resultado do dbt.
