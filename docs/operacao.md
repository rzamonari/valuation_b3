# Operação

O que roda sozinho, o que avisa antes de quebrar e onde ver a saúde do pipeline.

## Agendamento

| O quê | Quando | Onde | Falha |
|---|---|---|---|
| CI: `ruff`, `pytest` (Ubuntu e Windows), `requirements.txt`, integridade da fotografia | todo push na `main` e todo PR | `.github/workflows/ci.yml` | bloqueia o merge |
| Contrato das fontes (`pytest -m contrato`) | toda segunda, 06:00 de Brasília (`cron: 0 9 * * 1`), e sob demanda (*Run workflow*) | `.github/workflows/contrato-fontes.yml` | abre uma issue com o rótulo `contrato-fontes` ou comenta na que já está aberta |
| Atualização dos dados (ingestão → fotografia) | manual, na máquina local | [Instalação e uso](uso.md#atualizar-a-fotografia-publicada) | código de saída 1 e registro `falha` em `meta.execucoes` |

A atualização dos dados não é agendada: a execução automática do pipeline está fora do escopo
(ver [Arquitetura](arquitetura.md#fora-do-escopo)). O alerta de idade cobre esse risco: o painel
avisa quando os dados passam de **5 dias úteis** (`pipeline.execucao.LIMITE_DIAS_UTEIS`).

## Contrato das fontes

```powershell
uv run pytest test/contrato -m contrato --no-cov -rf   # ou: uv run task contrato
```

Uma chamada real e pequena por fonte, contra o formato que a ingestão e a Silver esperam. As
colunas e os formatos vêm das definições da Silver (`pipeline/transformacao/`). Se o contrato
mudar no código, o teste acompanha.

| Fonte | Chamada | O que confere |
|---|---|---|
| B3 | `GetInitialCompanies`, páginas 1 e 2 com 20 registros; `GetDetail` da Petrobras | `page.pageNumber/pageSize/totalRecords/totalPages` coerentes, páginas sem repetição, os 13 campos de `refined.b3_empresas` (nem a menos, nem a mais), CNPJ e `dateListing` no formato da Silver, `issuingCompany` com 4 caracteres, `otherCodes[].code` com PETR4 |
| Fundamentus | `resultado.php` (a mesma extração da ingestão) | cabeçalho da tabela com as 22 colunas mapeadas, pelo menos 500 linhas, números em notação brasileira (ou `-`), `Papel` com formato de ticker |
| Minha Receita | um CNPJ (Petrobras) | as 45 propriedades escalares e os 3 arrays do contrato JSON, com o tipo JSON de cada uma; as mensagens citam só nomes e tipos, nunca valores |
| Yahoo Finance | histórico completo de PETR4 e VALE3 (a mesma extração da ingestão) | colunas de `refined.yfinance_cotacoes` (`Capital Gains` é opcional), data com fuso e números no formato da Silver |

A falha diz qual fonte mudou e o quê, por exemplo:

```text
[Fundamentus] campos obrigatórios ausentes: ['Cresc. Rec.5a']; campos novos, sem mapeamento na Silver: ['Cresc. Rec. 5a']
[B3] indisponível: HTTPError: 503 Server Error
```

Os testes não rodam no `pytest` padrão (`addopts = --cov -m "not contrato"`), porque o CI de PR
não pode depender de rede nem de terceiros. Antes de rodar a ingestão depois de uma falha, ajuste
o contrato da Silver: a própria transformação recusaria o dado novo.

## Registro de execução

Cada comando `uv run python -m pipeline.<etapa>` grava, ao terminar com sucesso ou falha, uma
linha em `meta.execucoes`:

| Coluna | Conteúdo |
|---|---|
| `id` | identificador da execução |
| `etapa` | `ingestao`, `transformacao`, `materializacao`, `qualidade` ou `fotografia` |
| `inicio_utc`, `fim_utc`, `duracao_s` | horários em UTC, sem fuso; duração pelo relógio monotônico |
| `status` | `sucesso` ou `falha` |
| `linhas_por_tabela` | lista `(tabela, linhas)` do que a etapa publicou (`raw.*`, `refined.*`, `marts.*` ou os arquivos da fotografia) |
| `avisos` | na qualidade e na fotografia, as verificações com AVISO e o número de violações; nas demais, os avisos do log (retries, falhas por item), até 20 |
| `erro` | mensagem de erro do log da etapa, quando falha |

```sql
-- últimas execuções (DuckDB UI ou uv run python ui.py)
SELECT etapa, status, inicio_utc, duracao_s, len(avisos) AS avisos
FROM meta.execucoes ORDER BY inicio_utc DESC LIMIT 10;
```

O registro nunca muda o resultado da etapa. Se não puder gravar (banco bloqueado pela DuckDB UI,
por exemplo), ele avisa no log e o código de saída continua o da etapa. Sem o arquivo do banco,
nada é gravado. A fotografia também leva o registro: `execucoes` no `manifesto.json` traz a
execução mais recente de cada etapa e, por último, a da própria fotografia.

## Saúde do pipeline no painel

A aba **🩺 Saúde do pipeline** lê `marts_painel_saude_pipeline` (uma linha por etapa, de
`meta.execucoes`):

- idade dos dados em dias úteis e corridos, a partir da data de referência, com alerta acima de
  5 dias úteis (o alerta também aparece no cabeçalho);
- última execução de cada etapa: status, início, duração, camada, tabelas, linhas e avisos, e o
  último sucesso quando a última execução falhou (com o erro);
- duração por etapa em gráfico, linhas por tabela e a lista de avisos;
- na fotografia, quando ela foi gerada e quanto tempo levou.

O mart é republicado ao fim de cada etapa e fica fora do hash total da fotografia: o hash
continua mudando só quando os dados mudam. Fotografias anteriores a este registro abrem
normalmente, e a aba explica que ainda não há registro.
