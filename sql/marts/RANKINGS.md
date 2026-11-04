# Camada Gold (Marts) — Rankings Fundamentalistas

Especificação de origem: `docs/specs/marts_sql_rank.md`.

Dez consultas `SELECT` independentes (DuckDB), somente leitura da Silver (`refined`). Nenhuma
tabela, coluna ou registro de `raw`/`refined` foi alterado. As próprias consultas não criam
objetos persistentes. A persistência em `marts.<arquivo>` é feita por `pipeline/materializacao.py`
(ver README §12).

## 1. Consulta-base

Todos os rankings usam os mesmos joins (spec §4):

```sql
FROM refined.fundamentus_acoes a
INNER JOIN refined.b3_empresas b
    ON b.empresa_emissora = SUBSTRING(a.ticker, 1, 4)
LEFT JOIN refined.minhareceita_empresas c
    ON c.cnpj = b.cnpj
```

| Coluna de saída | Origem |
|---|---|
| `ticker` | `a.ticker` |
| `empresa` | `b.nome_pregao` |
| `razao_social` | `b.razao_social` |
| `segmento` | `b.segmento` (segmento de **listagem** da B3, não setor econômico) |
| `atividade` | `c.cnae_fiscal_descricao` |
| `mercado` | `b.mercado` |
| `municipio`, `uf`, `natureza_juridica`, `data_inicio_atividade` | colunas homônimas de `c` |
| `situacao` | `b.situacao` |

### Cardinalidade (validada em 2026-11-02)

| Chave | Linhas | Distintos | Observação |
|---|---|---|---|
| `fundamentus_acoes.ticker` | 995 | 995 | única |
| `b3_empresas.empresa_emissora` | 3.548 | 3.548 | única → join a↔b é N:1 |
| `b3_empresas.cnpj` | 3.548 | 3.222 | placeholders `00000000000000` (318) e `''` (9); 1 CNPJ real repetido |
| `minhareceita_empresas.cnpj` | 3.220 | 3.220 | única → join b↔c é N:1 |

Os placeholders de `b.cnpj` não existem em `c` e não aparecem nos tickers que cruzam. A
consulta-base retorna 541 linhas = 541 tickers (sem multiplicação); todos têm dados de Minha
Receita. 454 tickers do Fundamentus não têm emissora correspondente na B3 e ficam fora pelo
`INNER JOIN` (apenas 6 deles com `liquidez_2_meses > 0`).

## 2. Rankings

| Arquivo | Indicadores | Elegibilidade | Classificação (`DENSE_RANK`) | Linhas |
|---|---|---|---|---|
| `marts_01_rank_valor.sql` | ROIC, EV/EBIT | ambos > 0 | soma de rank ROIC ↓ e rank EV/EBIT ↑, soma ↑ | 387 |
| `marts_02_rank_proventos.sql` | DY, P/L, payout | DY > 0, P/L > 0, 0 ≤ payout ≤ 100 | DY ↓, payout ↑ | 200 |
| `marts_03_rank_eficiencia.sql` | Margem EBIT, margem líquida | ambas > 0 | margem EBIT ↓, margem líquida ↓ | 335 |
| `marts_04_rank_retorno.sql` | ROE, DL/PL | ROE > 0, DL/PL não nula e ≤ 1,5 | ROE ↓, DL/PL ↑ | 367 |
| `marts_05_rank_pechincha.sql` | P/L, EV/EBIT | ambos > 0 | soma de rank P/L ↑ e rank EV/EBIT ↑, soma ↑ | 336 |
| `marts_06_rank_patrimonio.sql` | P/VP, ROE, P/VP÷ROE | P/VP > 0, ROE > 0 | P/VP÷ROE ↑ | 384 |
| `marts_07_rank_crescimento.sql` | Cresc. receita 5a, ROIC | cresc. não nulo, ROIC > 10 | cresc. ↓ | 222 |
| `marts_08_rank_operacional.sql` | Margem EBIT | > 0 | margem EBIT ↓ | 394 |
| `marts_09_rank_seguro.sql` | DL/PL, ROIC, ROE | DL/PL não nula e ≤ 1,5, ROIC > 0, ROE > 0 | DL/PL ↑, ROIC ↓, ROE ↓ | 277 |
| `marts_10_rank_rentabilidade.sql` | P/L, earnings yield | P/L > 0 | earnings yield ↓ | 397 |

Rankings compostos (01, 05) expõem os ranks individuais e `soma_ranks` para auditoria.
Empates recebem o mesmo rank (`DENSE_RANK`); a saída é desempatada visualmente por `ticker`.

### Fórmulas derivadas (percentuais na escala 0–100)

- `payout = dividend_yield * preco_lucro` (payout estimado; DY 6 × P/L 10 = 60%).
- `p_vp_por_roe = preco_valor_patrimonial / NULLIF(roe, 0)`.
- `earnings_yield = 100.0 / NULLIF(preco_lucro, 0)`.

## 3. Limitações

1. O **Rank Valor** é uma versão simplificada da Magic Formula, não a metodologia original de
   Joel Greenblatt.
2. O **Rank Proventos** usa payout estimado e não comprova a sustentabilidade futura dos
   dividendos, a recorrência dos pagamentos nem a geração de caixa.
3. O **Rank Operacional** não contempla geração de caixa operacional: o dado não existe na Silver
   e o EBITDA não é usado como substituto.
4. Não há cálculo de **Dívida Líquida/EBITDA** nesta entrega.
5. O **Rank Seguro** não representa análise completa de solvência ou risco de crédito.
6. Os rankings individuais são **classificações relativas entre empresas elegíveis**.
7. As recomendações de `marts_50_rank_recomendacoes.sql` (seção 4) são um **sinal relativo e mecà¢nico** derivado
   dos 10 rankings sobre uma única fotografia do Fundamentus. Não consideram preço-alvo, valor
   intrínseco, histórico, governança, contexto setorial nem o perfil do investidor, e **não
   constituem recomendação de investimento**.

Observações de dados:

- Classes de ação da mesma emissora (ex.: ON/PN) compartilham os fundamentos do Fundamentus e
  aparecem empatadas nos rankings lexicográficos.
- Zeros do Fundamentus podem representar ausência de dado na origem; os critérios `> 0` dos
  rankings os excluem naturalmente, sem conversão para NULL.
- Há valores extremos na origem (ex.: margens acima de 1.000%) preservados sem filtro, pois a
  spec não define limites máximos.

## 4. Recomendações consolidadas (`marts_50_rank_recomendacoes.sql`)

Consolida os 10 rankings em `Compra`, `Manter` ou `Venda` por ticker (spec §7).

1. **Ranks**: cada ranking é reproduzido dentro da consulta, com a mesma elegibilidade e o mesmo
   `DENSE_RANK` do arquivo individual, sobre a consulta-base completa.
2. **Faixa por ranking**, pela posição relativa do rank (aritmética inteira; empates ficam na
   mesma faixa):

   | Faixa | Regra | Pontos |
   |---|---|---|
   | Superior | `(rank - 1) * 3 < max_rank - 1` (terço melhor) | +1 |
   | Intermediário | terço do meio | 0 |
   | Inferior | `(rank - 1) * 3 > 2 * (max_rank - 1)` (terço pior) | âˆ’1 |
   | Não elegível | reprovado na elegibilidade do ranking | âˆ’1 |

   Não elegível conta como pior classificação: a elegibilidade exclui justamente os casos
   desfavoráveis (rentabilidade ou múltiplos não positivos, DL/PL > 1,5, sem dividendos etc.).
3. **Saldo** = superiores âˆ’ inferiores âˆ’ não elegíveis (âˆ’10 a +10, pesos iguais).
   `saldo > 0` → **Compra**, `saldo = 0` → **Manter**, `saldo < 0` → **Venda**.
4. **Saída**: somente tickers com `liquidez_2_meses > 0`, ordenados por `saldo` ↓ e
   `qtd_superior` ↓ (`posicao`), o que coloca Compra no topo, Manter no meio e Venda no fim.
   As colunas `faixa_*` mostram a faixa em cada ranking, para auditoria.

Validação (2026-11-02): 391 linhas = 391 tickers negociados (150 sem liquidez ficam fora); os 10
ranks reproduzidos coincidem 100% com os arquivos individuais; faixas somam 10 em todas as linhas.

| Recomendação | Tickers | Saldo |
|---|---|---|
| Compra | 89 | +1 a +10 |
| Manter | 22 | 0 |
| Venda | 280 | âˆ’10 a âˆ’1 |

A predominà¢ncia de Venda decorre de a maioria das empresas ser reprovada na elegibilidade de vários
rankings (ex.: Proventos tem apenas 200 elegíveis entre os 541 tickers da consulta-base).

## 5. Execução

```python
import duckdb
from pathlib import Path

con = duckdb.connect("fundamentalistas.duckdb", read_only=True)
df = con.execute(Path("sql/marts/marts_01_rank_valor.sql").read_text(encoding="utf-8")).df()
```
