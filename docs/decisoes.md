# Decisões

As especificações abaixo orientaram a implementação de cada camada. Os módulos citam a spec de
origem na docstring, junto das decisões de implementação.

| Spec | Camada | Citada em |
|---|---|---|
| [Bronze — ingestão](specs/raw_ingestao.md) | `raw` | `pipeline/ingestao.py` |
| [Silver — transformação](specs/refined_transformacao.md) | `refined` | `pipeline/transformacao.py` |
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

## Limitações aceitas

Ver a seção *Limitações conhecidas* da [Referência da API](referencia/api.md) e as observações em
[Marts](referencia/marts.md) e [Rankings](referencia/rankings.md).
