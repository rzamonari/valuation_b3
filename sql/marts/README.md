# Camada Gold (Marts) — Indicadores Fundamentalistas

Especificação de origem: `docs/specs/marts_sql_indicadores.md` (v1.0).

## 1. Objetivo e escopo

Disponibilizar consultas SQL independentes (DuckDB) para os indicadores fundamentalistas e de
retorno/risco, usando **somente leitura** da camada Silver (`refined`) do banco
`fundamentalistas.duckdb`.

As camadas Bronze (`raw`) e Silver (`refined`) **não foram modificadas**: nenhuma tabela, coluna,
registro ou arquivo de ingestão/transformação foi alterado. Nenhuma fonte externa foi usada.

## 2. Arquitetura

| Camada | Schema | Papel |
|---|---|---|
| Bronze | `raw` | Dados brutos ingeridos (`pipeline/ingestao.py`) |
| Silver | `refined` | Dados tipados e deduplicados (`pipeline/transformacao.py`) |
| Gold | `marts` | Indicadores analíticos: consultas em `sql/marts/`, materializadas por `pipeline/materializacao.py` |

Os arquivos `.sql` continuam sendo consultas `SELECT` puras e a fonte da verdade de cada mart.
A persistência é feita à parte pelo módulo de materialização (seção 12), sem alterar o texto
das consultas.

## 3. Fontes Silver utilizadas

| Tabela | Chave lógica | Uso |
|---|---|---|
| `refined.fundamentus_acoes` | `ticker` (995 linhas, 995 distintos) | Marts 1–9 |
| `refined.yfinance_cotacoes` | `(ticker, data)` (1.920.774 linhas, 609 tickers, sem duplicatas) | Mart 10 |

`refined.b3_empresas` e as tabelas `refined.minhareceita_*` não são usadas: nenhum indicador
definido depende delas e não há relacionamento comprovado ticker → setor econômico.

Nenhum mart faz join entre tabelas diferentes; o único join (mart 10) é da tabela com seu próprio
agregado por `ticker` (1:N sobre chave única), sem multiplicação de registros.

## 4. Mapeamento de colunas

| Arquivo | Coluna de saída | Origem | Tipo | Unidade | Natureza |
|---|---|---|---|---|---|
| `marts_roic.sql` | `roic` | `fundamentus_acoes.roic` | DECIMAL(6,2) | % (0–100) | Pronto |
| `marts_ev_ebit.sql` | `enterprise_value_ebit` | `fundamentus_acoes.enterprise_value_ebit` | DECIMAL(6,2) | vezes | Pronto |
| `marts_alavancagem.sql` | `divida_liquida_patrimonio` | `fundamentus_acoes.divida_liquida_patrimonio` | DECIMAL(7,2) | vezes | Pronto |
| `marts_roe.sql` | `roe` | `fundamentus_acoes.roe` | DECIMAL(9,2) | % (0–100) | Pronto |
| `marts_preco_lucro.sql` | `preco_lucro` | `fundamentus_acoes.preco_lucro` | DECIMAL(7,2) | vezes | Pronto |
| `marts_preco_lucro.sql` | `earnings_yield` | `100.0 / preco_lucro` | DOUBLE | % (0–100) | Derivado |
| `marts_margens.sql` | `margem_ebit`, `margem_liquida`, `margem_bruta` | colunas homônimas | DECIMAL | % (0–100) | Pronto |
| `marts_crescimento_receita_5_anos.sql` | `crescimento_receita_5_anos` | coluna homônima | DECIMAL(6,2) | % (0–100) | Pronto |
| `marts_dividend_yield_payout.sql` | `dividend_yield` | `fundamentus_acoes.dividend_yield` | DECIMAL(6,2) | % (0–100) | Pronto |
| `marts_dividend_yield_payout.sql` | `payout` | `dividend_yield * preco_lucro` | DECIMAL(13,4) | % (0–100) | Derivado |
| `marts_p_vp.sql` | `preco_valor_patrimonial`, `roe` | colunas homônimas | DECIMAL | vezes / % | Pronto |
| `marts_p_vp.sql` | `p_vp_por_roe` | `preco_valor_patrimonial / roe` | DOUBLE | vezes por p.p. de ROE | Derivado |
| `marts_retorno_total_risco.sql` | `cagr` | `fechamento_ajustado` | DOUBLE | % (0–100) | Derivado |
| `marts_retorno_total_risco.sql` | `volatilidade_anualizada` | `fechamento_ajustado` | DOUBLE | % (0–100) | Derivado |
| `marts_retorno_total_risco.sql` | `max_drawdown` | `fechamento_ajustado` | DOUBLE | % (0–100, ≤ 0) | Derivado |

O mart 10 também expõe colunas de rastreabilidade: `data_inicial`, `data_final`, `anos`,
`qtd_precos_validos`, `qtd_retornos`, `preco_inicial`, `preco_final`.

## 5. Fórmulas

- **Earnings Yield** = `100.0 / preco_lucro`; P/L zero ou NULL → NULL.
- **Payout** = `dividend_yield * preco_lucro` (ex.: DY 6 × P/L 10 = 60%); componente NULL → NULL;
  P/L zero → 0 (sem divisão).
- **P/VP ÷ ROE** = `preco_valor_patrimonial / roe`; ROE zero ou NULL → NULL.
- **Retorno total e risco** (metodologia aprovada em 2026-11-02):
  - Janela: 5 anos até a última cotação de cada ticker (`data >= MAX(data) - INTERVAL 5 YEAR`).
  - Preço válido: `fechamento_ajustado > 0`; NULL ou ≤ 0 é inválido e não gera retorno.
  - `cagr = ((preco_final / preco_inicial) ^ (1 / anos) - 1) * 100`, com primeiro/último preço
    válido da janela e `anos = dias entre eles / 365.25`; NULL quando `anos = 0`.
  - `volatilidade_anualizada = stddev_samp(ln(P_t / P_t-1)) * sqrt(252) * 100`; o retorno é NULL
    se qualquer dos dois preços for inválido; NULL com menos de 2 retornos.
  - `max_drawdown = min(P_t / max(P_0..P_t) - 1) * 100`.

## 6. Tratamento de nulos e divisões

- Valores do Fundamentus são devolvidos sem arredondamento, troca de escala ou filtro.
- Nulos são preservados e nunca substituídos por zero; negativos são preservados.
- Toda divisão é protegida por `CASE WHEN denominador = 0 THEN NULL`; o registro da empresa é
  mantido, apenas o indicador derivado fica NULL.
- Datas ausentes nas cotações não são preenchidas.

## 7. Indicadores desconsiderados

| Indicador | Justificativa |
|---|---|
| Dívida líquida/EBITDA | Silver não possui dívida líquida nem EBITDA em valores monetários |
| Sharpe | Sem taxa livre de risco nem metodologia aprovada |
| Comparação setorial de margens | `b3_empresas.segmento` é segmento de listagem, não setor econômico |
| Valor justo por Gordon | Ke e crescimento perpétuo sem parâmetros aprovados |

## 8. Dependências

Nenhum arquivo SQL depende de outro. Cada um depende apenas de uma tabela Silver:
marts 1–9 → `refined.fundamentus_acoes`; mart 10 → `refined.yfinance_cotacoes`.

## 9. Execução

Com o projeto (`pipeline/db.py` fornece `conectar()`; para consulta use somente leitura):

```python
import duckdb
from pathlib import Path

con = duckdb.connect("fundamentalistas.duckdb", read_only=True)
df = con.execute(Path("sql/marts/marts_roic.sql").read_text(encoding="utf-8")).df()
```

Ou pela CLI do DuckDB: `duckdb -readonly fundamentalistas.duckdb < sql/marts/marts_roic.sql`.

## 10. Validação realizada (2026-11-02, conexão `read_only`)

- Todos os 10 SQLs executam no DuckDB; todas as tabelas/colunas referenciadas existem.
- Marts 1–9: 995 linhas = 995 tickers distintos (sem multiplicação nem perda de registros).
- Mart 10: 609 linhas = 609 tickers distintos da Silver.
- Fórmulas derivadas recalculadas linha a linha: 0 divergências; 0 valores infinitos/NaN;
  `earnings_yield` NULL em exatamente os 90 casos de P/L = 0; `p_vp_por_roe` NULL nos 31 casos
  de ROE = 0; exemplo de payout DY 6 × P/L 10 = 60.
- Mart 10 conferido contra implementação independente em pandas (VALE3, PETR4, ITUB4 e PPAR3,
  este com preços inválidos): CAGR, volatilidade e drawdown idênticos até 6 casas decimais.
- Integridade da Silver: contagem e hash determinístico de `refined.yfinance_cotacoes`
  idênticos antes e depois; `git status` só mostra `sql/` como novo.

## 11. Observações e pendências

- **Zeros no Fundamentus**: as colunas do Fundamentus quase não têm NULL (apenas 9 em
  `divida_liquida_patrimonio`), mas têm muitos zeros (ex.: 90 P/L, 31 ROE, 698 DY), e alguns
  tickers têm `cotacao = 0`. O zero pode representar ausência de dado na origem. Por regra
  (§5.2/§5.3) os zeros foram preservados; tratá-los como NULL exige regra aprovada.
- **Qualidade das cotações**: 18.350 linhas de 8 tickers têm `fechamento_ajustado < 0` e 1 linha é
  NULL; são tratadas como inválidas. Há volatilidades extremas (máx. ≈ 2.110% a.a.) que indicam
  séries ajustadas anômalas na origem — preservadas, sem filtro não especificado.
- 160 tickers têm `cagr` e `volatilidade_anualizada` NULL: todos possuem no máximo uma cotação
  válida na Silver, portanto não há intervalo nem retornos para calcular.

## 12. Materialização no schema `marts`

Spec: `docs/specs/marts_materializacao.md` (ajuste "Materialização dos resultados na camada Gold").

```
uv run python -m pipeline.materializacao
```

Executar depois de `pipeline.transformacao`. Feche a DuckDB UI (`ui.py`) antes, porque o arquivo do
banco fica bloqueado enquanto ela está aberta. O painel (`app.py`) pode continuar de pé: ele abre
e fecha a conexão a cada leitura.

O painel lê diretamente estas tabelas (`SELECT * FROM marts."<nome>"`) e não executa os `.sql`
(spec `dashboard_apresentacao.md` v1.5). Depois de materializar, clique em "Recarregar dados".

**Inventário e nomes.** Cada `sql/marts/<nome>.sql` vira a tabela `marts.<nome>` (ex.:
`marts_roic.sql` → `marts.marts_roic`). A chave lógica de cada arquivo está declarada em
`pipeline/materializacao.py` (`MARTS`), conforme o comentário "Grão:" do próprio SQL. Um `.sql`
novo sem chave declarada, ou uma chave declarada sem `.sql`, interrompe a execução.

| Tabelas | Natureza | Chave lógica | Estratégia |
|---|---|---|---|
| `marts_01` … `marts_10_rank_*`, `marts_50_rank_recomendacoes` | fotografia por ticker | `ticker` | substituição integral |
| `marts_alavancagem`, `marts_crescimento_receita_5_anos`, `marts_dividend_yield_payout`, `marts_ev_ebit`, `marts_margens`, `marts_p_vp`, `marts_preco_lucro`, `marts_roe`, `marts_roic` | fotografia por ticker | `ticker` | substituição integral |
| `marts_retorno_total_risco`, `marts_painel_indicadores` | fotografia por ticker | `ticker` | substituição integral |
| `marts_card_01` … `marts_card_05`, `marts_card_02_acoes_semindicacao`, `marts_painel_data_referencia` | agregado de linha única | — (exatamente 1 linha) | substituição integral |
| `marts_cotacao` | série histórica | `(ticker, data)` | substituição integral |

**Por que a cotação também é substituída por inteiro.** A consulta devolve o histórico completo de
`refined.yfinance_cotacoes`, sem filtro incremental, e a própria Silver é recriada por inteiro a
cada transformação. O `fechamento_ajustado` é recalculado retroativamente pelo YFinance a cada
provento ou desdobramento. Acrescentar só as datas novas deixaria preços antigos desatualizados e
manteria linhas que já saíram da Silver.

**Fluxo e atomicidade.**
1. Cada consulta é executada uma vez para uma tabela temporária da conexão. As colunas e os tipos
   precisam bater com o `DESCRIBE` da consulta, e a chave não pode ter nulos nem duplicatas.
2. Todas as tabelas `marts.*` são substituídas (`CREATE OR REPLACE TABLE … AS SELECT * FROM
   <temporária>`) em uma única transação.
3. Antes do `COMMIT`, cada tabela é comparada com a temporária: quantidade de registros, colunas,
   tipos, chave e `EXCEPT ALL` nos dois sentidos (multiconjunto, com NULL igual a NULL). Isso
   cobre valores, nulos e duplicações.
4. Qualquer falha (erro de SQL, chave, divergência) dispara um `ROLLBACK`. Nesse caso nenhuma
   tabela Gold muda, o erro informa a etapa, o arquivo e a tabela, e o processo sai com código 1.

Só o schema `marts` é criado ou alterado. Tabelas em `marts` sem `.sql` correspondente não são
apagadas: aparecem no relatório como órfãs, para decisão manual.

**Validação realizada (2026-11-03, banco real).** 30/30 consultas inventariadas, executadas e
materializadas, num total de 1.934.482 registros (1.920.774 em `marts_cotacao`). Duas execuções
seguidas resultaram no mesmo conteúdo, sem duplicações. A contagem e o hash de todas as tabelas
`raw` e `refined` ficaram idênticos antes e depois. Em uma conexão nova, 29 de 30 tabelas são
idênticas à consulta reexecutada. A exceção é `marts_retorno_total_risco`: o
`stddev_samp` da volatilidade, executado em paralelo, varia no último bit entre execuções da
*própria consulta* (|Δ| ≤ 3e-14 em 3 tickers). Por isso a validação compara a tabela com o resultado
capturado na mesma execução, e não com uma nova execução.
