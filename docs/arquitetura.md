# Arquitetura

Arquitetura Medallion sobre um único arquivo DuckDB (`fundamentalistas.duckdb`).

```text
B3 · Fundamentus · Minha Receita · Yahoo Finance
        │  pipeline/ingestao.py
        ▼
raw (Bronze)        dado como veio, tudo VARCHAR
        │  pipeline/transformacao/
        ▼
refined (Silver)    tipado, deduplicado, chaves validadas
        │  sql/marts/*.sql + pipeline/materializacao.py
        ▼
marts (Gold)        indicadores, rankings, recomendação e marts do painel
        │  pipeline/qualidade.py   reconciliação raw → refined → marts e regras de domínio
        │  pipeline/fotografia.py  marts.* em Parquet + manifesto (data de referência, hash)
        ▼
fotografia/         versionada no git
        │  painel.py + app.py (somente leitura: banco local ou fotografia)
        ▼
Painel Streamlit    local ou Streamlit Community Cloud
```

## Camadas

| Camada | Schema | Artefato | Regra |
|---|---|---|---|
| Bronze | `raw` | `pipeline/ingestao.py` | Dado como veio, tudo `VARCHAR`, com `_timestamp_ingestao` e `_source_origin` |
| Silver | `refined` | `pipeline/transformacao/` | Tipagem estrita, deduplicação, validação de chave; **sem cálculo, sem preencher ausentes** |
| Gold | `marts` | `sql/marts/*.sql` + `pipeline/materializacao.py` | Um `SELECT` puro por mart; o `.sql` é a fonte da verdade |
| Qualidade | — | `pipeline/qualidade.py` | Só lê; erro = código de saída 1 e nenhuma fotografia nova |
| Fotografia | `fotografia/` | `pipeline/fotografia.py` | Cópia fiel de `marts.*` (tipos conferidos), hash por arquivo e total |
| Apresentação | — | `painel.py` + `app.py` | Só lê, filtra, ordena e formata; **número novo exige mart novo** |

`pipeline/db.py` concentra a conexão e a persistência genérica (`conectar`, `criar_schema`,
`gravar`, `_ident`) e não importa nada de `pipeline`. Os módulos do pipeline nunca importam
`painel` nem `app`; `painel` lê só `marts.*`.

## Garantias

- **Atomicidade:** cada etapa publica numa única transação; falha → `ROLLBACK` e a versão
  anterior é preservada. Na Bronze, se qualquer fonte falhar, nada é gravado.
- **Idempotência:** reexecutar produz o mesmo estado (`CREATE OR REPLACE`, `IF NOT EXISTS`).
- **Isolamento entre camadas:** cada etapa lê apenas a camada anterior e grava só no seu schema.
  Na Gold, um mart pode ler outro mart da mesma execução (`marts.<nome>`, resolvido em ordem
  topológica pela materialização), nunca a versão publicada anterior.
- **Nulos preservados:** nunca viram zero; divisão por zero resulta em `NULL`.
- **Conversões estritas:** valor fora do formato esperado gera erro com etapa, coluna e exemplo,
  em vez de virar `NULL` sem aviso.
- **Validação antes de publicar:** colunas, tipos e chave lógica (sem nulos nem duplicatas).
- **Código de saída:** `0` em sucesso, `1` em falha (mensagem em `stderr`, sem traceback).

## Chamadas externas

Retry com backoff exponencial para erros transitórios (`TENTATIVAS = 3`, `BACKOFF_BASE = 2`,
`TIMEOUT = 30`), sem retry para erros definitivos (HTTP 4xx exceto 429). Paralelismo limitado:
8 workers HTTP e 4 para o Yahoo Finance. `validar_fontes()` confirma a disponibilidade da B3
antes de qualquer extração.

## Fora do escopo

- Dívida Líquida/EBITDA, Sharpe, valor justo por Gordon e comparação setorial.
- Setor econômico (o `segmento` disponível é o de listagem da B3).
- Execução agendada, banco remoto e múltiplos processos gravando.
