# B3 Valuation — Documentação da API

Referência dos módulos, funções públicas, tabelas e comandos do projeto **valuationb3**: um
pipeline de indicadores fundamentalistas de ações da B3 em arquitetura Medallion
(Bronze → Silver → Gold) sobre DuckDB, com um painel em Streamlit.

> Os sinais de Compra/Manter/Venda são relativos e mecânicos, derivados de 10 rankings sobre uma
> fotografia de dados. **Não constituem recomendação de investimento.**

---

## 1. Visão geral

| Camada | Schema | Módulo / artefato | Papel |
|---|---|---|---|
| Bronze | `raw` | `pipeline/ingestao.py` | Extração das fontes externas, tudo como `VARCHAR` |
| Silver | `refined` | `pipeline/transformacao/` | Tipagem, padronização, deduplicação e validação de chaves |
| Gold | `marts` | `sql/marts/*.sql` + `pipeline/materializacao.py` | Indicadores, rankings e agregados do painel |
| Apresentação | — | `painel.py` + `app.py` | Leitura somente leitura dos marts e visualização |

Banco único: `fundamentalistas.duckdb`, na raiz do projeto (sobrescrevível pela variável de
ambiente `VALUATIONB3_DB`; ver seção 3).

### Fontes externas

| Fonte | Endpoint | Tabela Bronze |
|---|---|---|
| B3 — empresas listadas | `sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall` | `raw.b3_empresas` |
| Fundamentus | `https://www.fundamentus.com.br/resultado.php` | `raw.fundamentus_acoes` |
| Minha Receita (CNPJ) | `https://minhareceita.org/` | `raw.minhareceita_empresas` |
| Yahoo Finance | biblioteca `yfinance` | `raw.yfinance_cotacoes` |

---

## 2. Instalação e execução

Requisitos: Python ≥ 3.13 e [uv](https://docs.astral.sh/uv/).

```bash
uv sync                                    # instala dependências (inclui grupo dev)

uv run python -m pipeline.ingestao         # 1. Bronze  (raw)
uv run python -m pipeline.transformacao    # 2. Silver  (refined)
uv run python -m pipeline.materializacao   # 3. Gold    (marts)

uv run streamlit run app.py                # painel web
uv run python ui.py                        # DuckDB UI em http://localhost:4213
uv run pytest                              # testes, sempre com cobertura (mínimo 60%)
uv run mkdocs serve                        # documentação em http://127.0.0.1:8000
```

A ordem das etapas importa: cada uma lê apenas a camada anterior.

> **Bloqueio do arquivo.** O DuckDB permite um único processo gravando. Feche a DuckDB UI
> (`ui.py`) antes de rodar ingestão, transformação ou materialização. O painel pode ficar
> aberto: ele abre e fecha uma conexão `read_only` a cada leitura.

### Códigos de saída

Todos os comandos do pipeline terminam com código `0` em sucesso e `1` em falha. Em falha, a
gravação é desfeita por `ROLLBACK` e nenhuma tabela da camada de destino muda.

### Saída e logging

As etapas registram por `logging` no logger `pipeline` (configurado por
`pipeline.log.configurar()`): progresso e relatório em **stdout**; retries, falhas por item,
avisos e erros em **stderr**. Logs de bibliotecas (ex.: `yfinance`) não são exibidos.

---

## 3. `pipeline.db` — infraestrutura

| Símbolo | Assinatura | Descrição |
|---|---|---|
| `PASTA_RAW` | `Path` | Pasta `raw/` na raiz do projeto |
| `VARIAVEL_DB` | `str` | Nome da variável de ambiente do banco: `VALUATIONB3_DB` |
| `caminho_banco` | `caminho_banco() -> Path` | `VALUATIONB3_DB`, se definida e não vazia; senão `fundamentalistas.duckdb` na raiz |
| `conectar` | `conectar() -> duckdb.DuckDBPyConnection` | Abre (criando se preciso) o banco em modo leitura/escrita. Quem chama fecha. |
| `criar_schema` | `criar_schema(con, nome) -> None` | `CREATE SCHEMA IF NOT EXISTS` |
| `gravar` | `gravar(con, df, schema, tabela) -> int` | Recria `schema.tabela` a partir de um DataFrame, com todas as colunas `VARCHAR`; devolve o `COUNT(*)`. Não controla transação. |

Os caminhos são resolvidos a partir do arquivo do módulo, independentemente do diretório atual.
Um `VALUATIONB3_DB` relativo também é resolvido a partir da raiz do projeto. O caminho é lido na
importação; o pipeline e o painel (`painel.ARQUIVO_DB`) usam o mesmo valor. O `.mcp.json`
continua apontando para `fundamentalistas.duckdb`.

```powershell
$env:VALUATIONB3_DB = "D:\dados\homologacao.duckdb"   # PowerShell
uv run python -m pipeline.transformacao
```

---

## 4. `pipeline.ingestao` — camada Bronze

Execução: `uv run python -m pipeline.ingestao`

| Função | Retorno | Descrição |
|---|---|---|
| `validar_fontes()` | — | Verifica se as fontes estão acessíveis antes de extrair |
| `extrair_b3()` | `DataFrame` | Empresas listadas na B3 (paginação de 120) |
| `identificar_cnpjs(df_b3)` | lista | CNPJs a consultar na Minha Receita |
| `identificar_tickers(df_b3)` | lista | Tickers a consultar no yfinance (detalhe por código CVM) |
| `extrair_fundamentus()` | `DataFrame` | Tabela de indicadores do Fundamentus |
| `extrair_minhareceita(cnpjs)` | `DataFrame` | Payload JSON de cada CNPJ |
| `extrair_yfinance(tickers)` | `DataFrame` | Histórico de cotações por ticker |
| `main()` | — | Orquestra tudo e grava as 4 tabelas `raw.*` numa transação |

**Comportamento**

- Retry com backoff exponencial: `TENTATIVAS = 3`, `BACKOFF_BASE = 2` s, `TIMEOUT = 30` s.
- Paralelismo: `WORKERS_HTTP = 8`, `WORKERS_YFINANCE = 4`.
- Metadados em cada linha: `_timestamp_ingestao` (UTC) e `_source_origin`.
- Exceção `FalhaExtracao`: qualquer falha de fonte aborta antes de gravar ("Nenhuma tabela foi
  gravada").

---

## 5. `pipeline.transformacao` — camada Silver

Execução: `uv run python -m pipeline.transformacao`

A Silver padroniza nomes, converte e valida tipos, normaliza JSON, valida chaves e trata
duplicidades. **Não** faz cálculos financeiros nem preenche dados ausentes.

O pacote é dividido por fonte; as funções abaixo são expostas por `pipeline.transformacao`.

| Módulo | Conteúdo |
|---|---|
| `comum` | Tipos (`Conversao`, `Coluna`, `TabelaSql`, `Preparada`), `ErroTransformacao`, deduplicação, validação de chave e o motor de conversão de tabelas Bronze |
| `b3`, `fundamentus`, `yfinance` | `TABELA`: mapeamento coluna Bronze → coluna/conversão Silver da fonte |
| `minhareceita` | Contrato JSON (`ESCALARES_EMPRESA`, `ARRAYS_EMPRESA`) e `preparar_minhareceita` |
| `__init__` | Verificação da Bronze, publicação, relatório, `executar` e `main` |

Para mudar o mapeamento de uma fonte, altere só o módulo dela.

| Função | Descrição |
|---|---|
| `verificar_bronze(con)` | Confere se todas as tabelas `raw` existem; senão orienta rodar a ingestão |
| `preparar_tabela_sql(con, tabela)` | Converte uma tabela Bronze tabular para staging tipado |
| `preparar_minhareceita(con)` | Decodifica o JSON da Minha Receita em tabela principal + tabelas de arrays |
| `publicar(con, preparadas)` | Substitui as tabelas `refined.*` numa única transação |
| `executar(con)` | Fluxo completo: verificar → preparar → publicar → relatório |
| `main()` | Ponto de entrada CLI |

**Tabelas produzidas**

| Tabela | Chave |
|---|---|
| `refined.b3_empresas` | `codigo_cvm` |
| `refined.fundamentus_acoes` | `ticker` |
| `refined.yfinance_cotacoes` | `(ticker, data)` |
| `refined.minhareceita_empresas` | `cnpj` |
| `refined.minhareceita_qsa` | array do JSON por `cnpj` |
| `refined.minhareceita_regime_tributario` | array do JSON por `cnpj` |
| `refined.minhareceita_cnaes_secundarios` | array do JSON por `cnpj` |

**Conversões** (`Conversao`): `TEXTO`, `DATA_BR`, `NUMERO_BR` (milhar `.`, decimal `,`, `%`
removido), `TIMESTAMP_TZ`, `DOUBLE`, `BIGINT`, `CNPJ`. As conversões são estritas: um valor que
não casa com o formato esperado gera `ErroTransformacao` (com etapa, origem, destino, coluna e
exemplo), em vez de virar `NULL` sem aviso.

---

## 6. Camada Gold — `sql/marts/`

Cada arquivo `.sql` é uma consulta `SELECT` pura, sem efeito colateral, e é a fonte da verdade do
seu mart. Detalhes completos em `sql/marts/README.md` (indicadores) e
`sql/marts/RANKINGS.md` (rankings).

### 6.1 Indicadores

| Arquivo | Colunas principais | Origem |
|---|---|---|
| `marts_roic.sql` | `roic` | Fundamentus |
| `marts_roe.sql` | `roe` | Fundamentus |
| `marts_ev_ebit.sql` | `enterprise_value_ebit` | Fundamentus |
| `marts_alavancagem.sql` | `divida_liquida_patrimonio` | Fundamentus |
| `marts_preco_lucro.sql` | `preco_lucro`, `earnings_yield` | Fundamentus |
| `marts_margens.sql` | `margem_ebit`, `margem_liquida`, `margem_bruta` | Fundamentus |
| `marts_crescimento_receita_5_anos.sql` | `crescimento_receita_5_anos` | Fundamentus |
| `marts_dividend_yield_payout.sql` | `dividend_yield`, `payout` | Fundamentus |
| `marts_p_vp.sql` | `preco_valor_patrimonial`, `roe`, `p_vp_por_roe` | Fundamentus |
| `marts_retorno_total_risco.sql` | `cagr`, `volatilidade_anualizada`, `max_drawdown` | yfinance |
| `marts_cotacao.sql` | série histórica por `(ticker, data)` | yfinance |

**Fórmulas derivadas** (percentuais na escala 0–100):

- `earnings_yield = 100 / preco_lucro`; P/L 0 → `NULL`
- `payout = dividend_yield × preco_lucro`
- `p_vp_por_roe = preco_valor_patrimonial / roe`; ROE 0 → `NULL`
- `cagr = ((P_final / P_inicial)^(1/anos) − 1) × 100`, janela de 5 anos
- `volatilidade_anualizada = stddev_samp(ln(P_t / P_t−1)) × √252 × 100`
- `max_drawdown = min(P_t / max(P_0..P_t) − 1) × 100`

Nulos são preservados (nunca viram zero) e toda divisão por zero resulta em `NULL`.

### 6.2 Rankings

Todos partem de `refined.fundamentus_acoes` ⨝ `refined.b3_empresas` (pela emissora, 4 primeiros
caracteres do ticker) ⟕ `refined.minhareceita_empresas`, e classificam com `DENSE_RANK`.

| Arquivo | Tema | Critério |
|---|---|---|
| `marts_01_rank_valor.sql` | Valor | ROIC ↓ + EV/EBIT ↑ (Magic Formula simplificada) |
| `marts_02_rank_proventos.sql` | Proventos | DY ↓, payout ↑ (0 ≤ payout ≤ 100) |
| `marts_03_rank_eficiencia.sql` | Eficiência | Margem EBIT ↓, margem líquida ↓ |
| `marts_04_rank_retorno.sql` | Retorno | ROE ↓, DL/PL ↑ (DL/PL ≤ 1,5) |
| `marts_05_rank_pechincha.sql` | Pechincha | P/L ↑ + EV/EBIT ↑ |
| `marts_06_rank_patrimonio.sql` | Patrimônio | P/VP ÷ ROE ↑ |
| `marts_07_rank_crescimento.sql` | Crescimento | Cresc. receita 5a ↓ (ROIC > 10) |
| `marts_08_rank_operacional.sql` | Operacional | Margem EBIT ↓ |
| `marts_09_rank_seguro.sql` | Seguro | Menor alavancagem com rentabilidade |
| `marts_10_rank_rentabilidade.sql` | Rentabilidade | Earnings yield ↓ |

### 6.3 Recomendação consolidada — `marts_50_rank_recomendacoes.sql`

1. Em cada um dos 10 rankings o ticker cai numa faixa: **Superior** (terço melhor, +1),
   **Intermediário** (0), **Inferior** (terço pior, −1) ou **Não elegível** (−1).
2. `saldo = superiores − inferiores − não elegíveis` (de −10 a +10).
3. `saldo > 0` → **Compra**; `saldo = 0` → **Manter**; `saldo < 0` → **Venda**.
4. Só entram tickers com `liquidez_2_meses > 0`. As colunas `faixa_<tema>` permitem auditar.

### 6.4 Marts do painel

| Arquivo | Conteúdo |
|---|---|
| `marts_card_01_acoes_analisadas.sql` | Total de ações analisadas |
| `marts_card_02_acoes_compra.sql` | Total em Compra |
| `marts_card_02_acoes_semindicacao.sql` | Total sem indicação |
| `marts_card_03_acoes_manter.sql` | Total em Manter |
| `marts_card_04_acoes_venda.sql` | Total em Venda |
| `marts_card_05_termometro_mercado.sql` | Termômetro do mercado (empate → Manter) |
| `marts_painel_indicadores.sql` | Indicadores consolidados por ticker |
| `marts_painel_data_referencia.sql` | Data de referência dos dados |

### 6.5 Executar uma consulta diretamente

```python
import duckdb
from pathlib import Path

con = duckdb.connect("fundamentalistas.duckdb", read_only=True)
df = con.execute(Path("sql/marts/marts_roic.sql").read_text(encoding="utf-8")).df()
```

---

## 7. `pipeline.materializacao` — persistência da Gold

Execução: `uv run python -m pipeline.materializacao` (depois da transformação).

Cada `sql/marts/<nome>.sql` vira a tabela `marts.<nome>` (ex.: `marts_roic.sql` →
`marts.marts_roic`).

| Símbolo | Descrição |
|---|---|
| `Mart(nome, chave, natureza)` | Declaração de um mart: chave lógica (`()` = linha única) e natureza |
| `MARTS` | Registro de todos os marts. **Todo `.sql` novo precisa ser declarado aqui.** |
| `inventariar(pasta, marts)` | Confere a correspondência 1:1 entre arquivos `.sql` e `MARTS` |
| `preparar(con, mart, pasta)` | Executa a consulta numa tabela temporária e valida colunas, tipos e chave |
| `publicar(con, preparadas)` | `CREATE OR REPLACE TABLE` de todos os marts numa única transação |
| `executar(con, pasta, marts)` | Fluxo completo com relatório |
| `ErroMaterializacao` | Erro com etapa, motivo, arquivo, destino e exemplo |

**Naturezas e estratégia** (sempre substituição integral):

| Natureza | Chave | Exemplos |
|---|---|---|
| Fotografia por ticker | `ticker` | indicadores, rankings, `marts_50`, `marts_painel_indicadores` |
| Agregado de linha única | — (exatamente 1 linha) | `marts_card_*`, `marts_painel_data_referencia` |
| Série histórica | `(ticker, data)` | `marts_cotacao` |

**Garantias**

- A chave não pode ter nulos nem duplicatas.
- Antes do `COMMIT`, cada tabela é comparada com a temporária (contagem, colunas, tipos e
  `EXCEPT ALL` nos dois sentidos). Qualquer divergência faz `ROLLBACK`.
- Só o schema `marts` é alterado. Tabelas de `marts` sem `.sql` correspondente não são apagadas;
  aparecem no relatório como órfãs.

### Como adicionar um mart

1. Crie `sql/marts/<nome>.sql` com um `SELECT` puro e um comentário `Grão:` indicando a chave.
2. Declare `Mart("<nome>", (<chave>), <NATUREZA>)` em `MARTS`.
3. Rode `uv run python -m pipeline.materializacao`.
4. Se o painel for usar o mart, inclua-o nas listas de `painel.py` (`MARTS_CARREGAR` /
   `MARTS_OBRIGATORIOS`).

---

## 8. `painel.py` — leitura e visualização

Biblioteca sem dependência de Streamlit (reaproveitável e testável). **Não faz cálculos:** só
ordena, filtra, renomeia e formata. Todo número novo exige um `.sql` novo na Gold.

### 8.1 Leitura

| Função | Descrição |
|---|---|
| `ler(nomes) -> dict[str, DataFrame]` | `SELECT * FROM marts."<nome>"` para cada nome |
| `ler_cotacao(ticker) -> DataFrame` | Histórico de um ticker em `marts.marts_cotacao`, filtrado no banco com parâmetro vinculado |
| `tabelas_faltando() -> list[str]` | Tabelas obrigatórias ausentes (ou o próprio arquivo do banco) |
| `filtrar(df, recomendacoes, segmentos, liquidez_minima)` | Filtra linhas por recomendação, segmento e liquidez mínima |

Cada leitura abre e fecha a própria conexão `read_only`.

**Exceções**

| Exceção | Quando |
|---|---|
| `BancoBloqueado` | O arquivo está bloqueado por outro processo (UI, ingestão, materialização) |
| `ErroMart(tabela, mensagem)` | Falha ao ler uma tabela `marts.*` |

### 8.2 Formatação (funções puras)

Formato brasileiro sem depender do locale: milhar com `.` e decimal com `,`. Nulo vira `—`.

| Função | Exemplo |
|---|---|
| `numero(v, casas=0)` | `1234567` → `1.234.567` |
| `reais(v, casas=2)` | `1234.5` → `R$ 1.234,50` |
| `reais_compacto(v)` | `2500000` → `R$ 2,5 mi` |
| `pct(v, casas=1)` | `12.34` → `12,3%` (não multiplica por 100) |
| `multiplo(v, casas=1)` | `8.5` → `8,5x` |
| `data_br(v)` | `2026-11-03` → `03/11/2026` |

### 8.3 Gráficos e componentes

| Função | Saída |
|---|---|
| `fig_valor_qualidade(ind)` | Dispersão ROIC × EV/EBIT, com linhas de referência ROIC 15% e EV/EBIT 10 |
| `fig_ranking_tematico(df, ranking, n=15)` | Barras do top N de um ranking temático |
| `tabela_ranking_tematico(df, ranking, n=15)` | Tabela do top N |
| `fig_radar(linha)` | Radar das faixas de um ticker nos 10 rankings |
| `fig_cotacao(cot)` | Série de cotação (ignora preços nulos ou ≤ 0) |
| `tabela_consolidado(rec)` | Tabela do ranking consolidado |
| `html_cartao(...)`, `html_termometro(...)` | Componentes HTML dos cartões e do termômetro |

### 8.4 Constantes úteis

| Constante | Conteúdo |
|---|---|
| `RANKINGS` | Metadados dos 10 rankings temáticos (chave, mart, aba, colunas de barras/tooltip/tabela) |
| `INDICADORES` | Coluna → (rótulo, formatador) |
| `REC`, `BADGE` | Ícone, rótulo e cor de Compra/Manter/Venda |
| `FAIXAS` | Superior / Intermediário / Inferior / Não elegível |
| `LIQUIDEZ_MINIMA` | Opções de filtro: Todas, R$ 100 mil, R$ 1 mi, R$ 10 mi |

---

## 9. `app.py` — painel Streamlit

Execução: `uv run streamlit run app.py`

Cinco seções: **pulso do mercado** (cartões e termômetro), **ranking de oportunidades**,
**valor × qualidade**, **rankings temáticos** (abas) e **ficha da ação** (radar e cotação).

- Os dados ficam em cache (`st.cache_data`); o botão **Recarregar dados** relê os marts após
  uma nova materialização.
- Filtros (recomendação, segmento, liquidez) afetam só o ranking consolidado, a dispersão e a
  lista da ficha. Cartões e rankings temáticos sempre mostram o mercado inteiro.
- Tabela faltando, banco bloqueado ou erro de leitura mostram uma mensagem clara e interrompem
  a página, sem traceback.
- Tema escuro definido em `.streamlit/config.toml`.

---

## 10. Ferramentas auxiliares

- **`ui.py`** — abre o banco na DuckDB UI (`http://localhost:4213`). Ctrl+C encerra. Mantém o
  arquivo bloqueado enquanto estiver aberta.
- **`.mcp.json`** — servidor MCP `mcp-server-motherduck` apontando para `fundamentalistas.duckdb`,
  para consultas via assistentes de IA.

---

## 11. Testes

```bash
uv run pytest                  # todos os testes, sempre com cobertura (mínimo 60%; app.py e ui.py fora)
uv run ruff check .            # lint
uv run ruff format . --check   # formatação
```

| Arquivo | Cobre |
|---|---|
| `test/test_db.py` | Conexão, caminho do banco (`VALUATIONB3_DB`), schema e gravação |
| `test/test_ingestao.py` | Retry, extração de cada fonte e atomicidade da ingestão (sem rede) |
| `test/test_log.py` | Destino das mensagens por nível (stdout/stderr) e reconfiguração |
| `test/test_transformacao.py` | Conversões, chaves, deduplicação e publicação da Silver |
| `test/test_sql_marts.py` | Execução e resultados das consultas `.sql` |
| `test/test_marts.py` | Inventário, validação e atomicidade da materialização |
| `test/test_painel.py` | Leitura, formatação, filtros e gráficos do painel |

---

## 12. Limitações conhecidas

- **Zeros do Fundamentus** podem significar ausência de dado; são preservados (os critérios
  `> 0` dos rankings os excluem).
- **Cotações**: algumas séries têm `fechamento_ajustado` negativo, tratado como inválido.
- O join Fundamentus ↔ B3 pela emissora deixa de fora os tickers sem emissora correspondente.
- `segmento` é o segmento de **listagem** da B3, não o setor econômico.
- Não calculados: Dívida Líquida/EBITDA, Sharpe, valor justo por Gordon e comparação setorial.
