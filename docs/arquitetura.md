# Arquitetura

Arquitetura Medallion sobre um único arquivo DuckDB (`fundamentalistas.duckdb`).

```text
B3 · Fundamentus · Minha Receita · Yahoo Finance
        │  pipeline/ingestao.py
        ▼
raw       (Bronze)  dado como veio, tudo VARCHAR
        │  pipeline/transformacao/
        ▼
refined   (Silver)  tipado, deduplicado, chaves validadas
        │  sql/marts/*.sql + pipeline/materializacao.py
        ▼
marts     (Gold)    indicadores, rankings, recomendação e marts do painel
        │  painel.py + app.py
        ▼
Painel Streamlit (somente leitura)
```

## Camadas

| Camada | Schema | Artefato | Regra |
|---|---|---|---|
| Bronze | `raw` | `pipeline/ingestao.py` | Dado como veio, tudo `VARCHAR`, com `_timestamp_ingestao` e `_source_origin` |
| Silver | `refined` | `pipeline/transformacao/` | Tipagem estrita, deduplicação, validação de chave; **sem cálculo, sem preencher ausentes** |
| Gold | `marts` | `sql/marts/*.sql` + `pipeline/materializacao.py` | Um `SELECT` puro por mart; o `.sql` é a fonte da verdade |
| Apresentação | — | `painel.py` + `app.py` | Só lê, filtra, ordena e formata; **número novo exige mart novo** |

`pipeline/db.py` concentra a conexão e a persistência genérica (`conectar`, `criar_schema`,
`gravar`, `_ident`). Os módulos de `pipeline` nunca importam `painel` nem `app`.

## Garantias

- **Atomicidade:** cada etapa publica numa única transação; falha → `ROLLBACK` e a versão
  anterior é preservada. Na Bronze, se qualquer fonte falhar, nada é gravado.
- **Idempotência:** reexecutar produz o mesmo estado (`CREATE OR REPLACE`, `IF NOT EXISTS`).
- **Isolamento entre camadas:** cada etapa lê apenas a camada anterior.
- **Nulos preservados:** nunca viram zero; divisão por zero resulta em `NULL`.
- **Conversões estritas:** valor fora do formato esperado gera erro com etapa, coluna e exemplo,
  em vez de virar `NULL` sem aviso.
- **Validação antes de publicar:** colunas, tipos e chave lógica (sem nulos nem duplicatas).

## Chamadas externas

Retry com backoff exponencial para erros transitórios (`TENTATIVAS = 3`, `BACKOFF_BASE = 2`,
`TIMEOUT = 30`), sem retry para erros definitivos (HTTP 4xx exceto 429). Paralelismo limitado:
8 workers HTTP e 4 para o Yahoo Finance.

## Fora do escopo

- Dívida Líquida/EBITDA, Sharpe, valor justo por Gordon e comparação setorial.
- Setor econômico (o `segmento` disponível é o de listagem da B3).
- Execução agendada, banco remoto e múltiplos usuários gravando.
