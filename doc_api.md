# Referência da API — B3 Valuation (`valuationb3`)

Pipeline de indicadores fundamentalistas de ações da B3 em arquitetura Medallion
(Bronze → Silver → Gold) sobre DuckDB, com painel somente leitura em Streamlit.

> Os sinais Compra/Manter/Venda são relativos e mecânicos, derivados de 10 rankings sobre uma
> fotografia de dados. **Não constituem recomendação de investimento.**

Números de linhas citados abaixo vêm do banco `fundamentalistas.duckdb` com data de referência
**02/11/2026**; mudam a cada ingestão.

---

## 1. Visão geral

| Camada | Schema | Módulo | Comando | Regra principal |
|---|---|---|---|---|
| Bronze | `raw` | [pipeline/ingestao.py](pipeline/ingestao.py) | `uv run python -m pipeline.ingestao` | Dado como veio, tudo `VARCHAR` |
| Silver | `refined` | [pipeline/transformacao/](pipeline/transformacao/__init__.py) | `uv run python -m pipeline.transformacao` | Tipagem estrita, deduplicação, chaves; sem cálculo |
| Gold | `marts` | [sql/marts/](sql/marts/) + [pipeline/materializacao.py](pipeline/materializacao.py) | `uv run python -m pipeline.materializacao` | Um `SELECT` puro por mart |
| Qualidade | — | [pipeline/qualidade.py](pipeline/qualidade.py) | `uv run python -m pipeline.qualidade` | Reconciliação raw → refined → marts e regras de domínio (só leitura) |
| Fotografia | — | [pipeline/fotografia.py](pipeline/fotografia.py) | `uv run python -m pipeline.fotografia` | `marts.*` em Parquet + manifesto com data de referência e hash |
| Apresentação | — | [painel.py](painel.py) + [app.py](app.py) | `uv run streamlit run app.py` | Só lê, filtra, ordena e formata |

Utilitários: [ui.py](ui.py) abre o banco na DuckDB UI (`http://localhost:4213`);
[.mcp.json](.mcp.json) expõe o banco a um servidor MCP de leitura (`mcp-server-motherduck`).

### Garantias transversais

- **Atomicidade:** cada etapa publica tudo numa única transação; falha → `ROLLBACK`, versão anterior preservada.
- **Idempotência:** `CREATE OR REPLACE` / `IF NOT EXISTS`; reexecutar produz o mesmo estado.
- **Isolamento:** cada etapa lê só a camada anterior e grava só no seu schema.
- **Nulos preservados:** nunca viram zero; divisão por zero resulta em `NULL`.
- **Código de saída:** `0` em sucesso, `1` em falha (mensagem em `stderr`, sem traceback).
- **Banco único:** `fundamentalistas.duckdb` na raiz, caminho derivado de `Path(__file__)` (independe do cwd);
  `VALUATIONB3_DB` aponta outro arquivo para pipeline e painel.

---

## 2. Instalação e execução

Requisitos: Python ≥ 3.13 e [uv](https://docs.astral.sh/uv/).

```powershell
uv sync
uv run python -m pipeline.ingestao        # 1. Bronze  (raw)
uv run python -m pipeline.transformacao   # 2. Silver  (refined)
uv run python -m pipeline.materializacao  # 3. Gold    (marts)
uv run python -m pipeline.qualidade       # 4. Qualidade (reconciliação e regras de domínio)
uv run python -m pipeline.fotografia      # 5. Fotografia versionada (fotografia/)
uv run streamlit run app.py               # painel
```

Feche a DuckDB UI (`ui.py`) antes das etapas 1 a 3: o DuckDB aceita um único processo gravando.
O painel pode ficar aberto (abre e fecha conexão `read_only` a cada leitura); depois de
materializar, clique em **Recarregar dados**.

Dependências (`pyproject.toml`): `duckdb`, `lxml`, `pandas`, `plotly`, `pyarrow`, `requests`,
`streamlit`, `yfinance`. Grupo `dev`: `mkdocs-material`, `pytest`, `pytest-cov`, `ruff`.

**Outro arquivo de banco.** Defina `VALUATIONB3_DB` (ex.: uma cópia de homologação); um caminho
relativo é resolvido a partir da raiz do projeto. Pipeline, painel e `ui.py` passam a usar o
mesmo arquivo. Vazia ou ausente, vale `fundamentalistas.duckdb`.

```powershell
$env:VALUATIONB3_DB = "D:\dados\homologacao.duckdb"
uv run python -m pipeline.transformacao
Remove-Item Env:VALUATIONB3_DB   # volta ao padrão
```

**Saída.** Os módulos registram em `logging` (`pipeline.log.configurar()` no `main()`):
progresso e relatórios vão para `stdout`; avisos (retry, falha por item, tabelas órfãs) e erros,
para `stderr`.

---

## 3. `pipeline.db` — infraestrutura

| Símbolo | Descrição |
|---|---|
| `PASTA_RAW` | `<raiz>/raw` |
| `VARIAVEL_DB` | `"VALUATIONB3_DB"`: nome da variável de ambiente com outro arquivo de banco. |
| `caminho_banco()` | Arquivo do banco: o de `VALUATIONB3_DB` (relativo = a partir da raiz) ou `fundamentalistas.duckdb`. |
| `conectar()` | Abre (criando se preciso) o banco de `caminho_banco()`. Quem chama fecha. |
| `criar_schema(con, nome)` | `CREATE SCHEMA IF NOT EXISTS`. |
| `gravar(con, df, schema, tabela)` | Recria `schema.tabela` a partir do DataFrame com **todas as colunas `VARCHAR`** e devolve o `COUNT(*)`. Não abre nem confirma transação. |
| `_ident(nome)` | Cita identificador SQL com aspas duplas (escapando `"`). |

---

## 4. `pipeline.ingestao` — Bronze (`raw`)

### Fontes

| Tabela | Fonte | Como |
|---|---|---|
| `raw.b3_empresas` | API de empresas listadas da B3 (`listedCompaniesProxy/CompanyCall/GetInitialCompanies`) | Paginação de 120; parâmetros em JSON codificado em Base64 na URL |
| `raw.fundamentus_acoes` | `https://www.fundamentus.com.br/resultado.php` | Primeira `<table>` do HTML (via `lxml`) |
| `raw.minhareceita_empresas` | `https://minhareceita.org/<cnpj>` | Um GET por CNPJ da B3; payload JSON guardado inteiro em `payload_json` |
| `raw.yfinance_cotacoes` | Yahoo Finance (`yfinance`), símbolo `<ticker>.SA` | `history(period="max", interval="1d", auto_adjust=False)` |

Toda tabela recebe `_timestamp_ingestao` (UTC, ISO-8601) e `_source_origin` (URL ou símbolo consultado).

### Funções públicas

| Função | Retorno | Observação |
|---|---|---|
| `validar_fontes()` | — | Confere a página oficial da B3 e o app de listados (`<app-root>`); falha → `FalhaExtracao` |
| `extrair_b3()` | `DataFrame` | Todas as páginas; vazio → `FalhaExtracao` |
| `identificar_cnpjs(df_b3)` | `list[str]` | CNPJs distintos e não vazios, exatamente como vieram |
| `identificar_tickers(df_b3)` | `list[str]` | `GetDetail` por `codeCVM`, coletando `otherCodes[].code` (detalhes não são persistidos) |
| `extrair_fundamentus()` | `DataFrame` | Tabela sem linhas/colunas → `FalhaExtracao` |
| `extrair_minhareceita(cnpjs)` | `DataFrame` | CNPJ completado com zeros **só na URL**; HTTP 400/404 = CNPJ rejeitado (ignorado e listado); outra falha → `FalhaExtracao` |
| `extrair_yfinance(tickers)` | `DataFrame` | Falha por ticker é registrada e ignorada; nenhum histórico → `FalhaExtracao` |
| `main()` | — | Extrai tudo, depois grava as 4 tabelas numa transação e imprime o relatório |

### Resiliência

| Constante | Valor | Uso |
|---|---|---|
| `TENTATIVAS` | 3 | Execuções por operação |
| `BACKOFF_BASE` | 2 | Espera exponencial: 2 s, 4 s |
| `TIMEOUT` | 30 | Segundos por requisição |
| `WORKERS_HTTP` | 8 | Paralelismo B3 detalhe / Minha Receita |
| `WORKERS_YFINANCE` | 4 | Paralelismo yfinance (rate limit) |

- HTTP 429 e 5xx são repetidos; outros 4xx viram `_ErroDefinitivo` (sem retry).
- `FalhaExtracao`: qualquer fonte inteira falhou → **nenhuma tabela é gravada**, saída 1.
- Falha de gravação → `ROLLBACK`, nenhuma tabela `raw.*` alterada, saída 1.

---

## 5. `pipeline.transformacao` — Silver (`refined`)

Lê só `raw`, grava só `refined`. Regras: [spec da Silver](docs/specs/refined_transformacao.md);
a docstring do pacote registra as decisões de implementação.

| Módulo | Conteúdo |
|---|---|
| `__init__` | Orquestração: `verificar_bronze`, `publicar`, relatório, `executar`, `main`; reexporta a interface pública |
| `comum` | `ErroTransformacao`, conversões (`Conversao`), utilitários, deduplicação e chave, `preparar_tabela_sql` |
| `b3`, `fundamentus`, `yfinance` | `TABELA`: mapeamento de colunas, conversões e chave de cada fonte |
| `minhareceita` | Contrato JSON (`ESCALARES_EMPRESA`, `ARRAYS_EMPRESA`) e `preparar_minhareceita` |
| `__main__` | `python -m pipeline.transformacao` |

### Tabelas produzidas (7)

| Tabela | Origem | Chave lógica | Linhas |
|---|---|---|---|
| `refined.b3_empresas` | `raw.b3_empresas` | `codigo_cvm` | 3.548 |
| `refined.fundamentus_acoes` | `raw.fundamentus_acoes` | `ticker` | 995 |
| `refined.yfinance_cotacoes` | `raw.yfinance_cotacoes` | `(ticker, data)` | 1.920.774 |
| `refined.minhareceita_empresas` | escalares de `payload_json` | `cnpj` | 3.220 |
| `refined.minhareceita_qsa` | array `qsa` | `(cnpj, sequencia_socio)` | 14.704 |
| `refined.minhareceita_regime_tributario` | array `regime_tributario` | `(cnpj, sequencia_regime)` | 24.903 |
| `refined.minhareceita_cnaes_secundarios` | array `cnaes_secundarios` | `(cnpj, codigo_cnae)` | 17.929 |

Os nomes das colunas são padronizados em `snake_case` português (ex.: `P/L` → `preco_lucro`,
`Adj Close` → `fechamento_ajustado`, `codeCVM` → `codigo_cvm`). O mapeamento completo está em
`TABELAS_SQL`, `ESCALARES_EMPRESA` e `ARRAYS_EMPRESA`.

### Conversões estritas (`Conversao`)

| Conversão | Formato aceito | Destino |
|---|---|---|
| `TEXTO` | qualquer | `VARCHAR` |
| `DATA_BR` | `DD/MM/YYYY` | `DATE` |
| `NUMERO_BR` | `-1.234,56` ou `12,3%`; `-` = ausente | `DECIMAL(p,s)` calculado sobre os dados (sem dividir `%` por 100) |
| `TIMESTAMP_TZ` | `YYYY-MM-DD HH:MM:SS[.f]±HH:MM` | `TIMESTAMPTZ` |
| `DOUBLE` | decimal/científico | `DOUBLE` |
| `BIGINT` | inteiro | `BIGINT` |
| `CNPJ` | até 14 dígitos | `VARCHAR` com zeros à esquerda; `''` permanece `''` |

Valor que não casa com o formato **interrompe** a transformação (nada de conversão tolerante).

### Regras

- Toda coluna Bronze precisa estar mapeada e vice-versa (nenhuma descartada em silêncio).
- Duplicatas **integralmente idênticas** são removidas; chave nula ou duplicada com conteúdo diferente → erro.
- JSON da Minha Receita é validado contra o contrato (propriedades e tipos esperados).
- Percentuais do Fundamentus ficam na escala 0–100.

### API

| Símbolo | Descrição |
|---|---|
| `ErroTransformacao(etapa, motivo, *, origem, destino, coluna, exemplo)` | Erro com contexto formatado; nenhuma tabela Silver é publicada |
| `verificar_bronze(con)` | Exige as 4 tabelas `raw.*`; orienta rodar a ingestão |
| `preparar_tabela_sql(con, tabela)` | Converte, deduplica e valida uma `TabelaSql` em tabela temporária → `Preparada` |
| `preparar_minhareceita(con)` | Decodifica o JSON em tabela principal + 3 arrays → `list[Preparada]` |
| `publicar(con, preparadas)` | Substitui todas as `refined.*` numa transação |
| `executar(con)` | Orquestra tudo e devolve o relatório (origem, duplicatas, gravados, nulos por coluna) |
| `main()` | Ponto de entrada CLI |

---

## 6. Camada Gold (`marts`)

Cada `sql/marts/<nome>.sql` é um `SELECT` puro (fonte da verdade) e vira a tabela
`marts.<nome>`. Os marts leem apenas `refined`. Documentação detalhada:
[sql/marts/README.md](sql/marts/README.md) (indicadores) e
[sql/marts/RANKINGS.md](sql/marts/RANKINGS.md) (rankings e recomendação).

### 6.1 Indicadores (fonte: `refined.fundamentus_acoes`, 995 linhas, chave `ticker`)

| Mart | Colunas | Natureza |
|---|---|---|
| `marts_roic` | `roic` (%) | Pronto |
| `marts_roe` | `roe` (%) | Pronto |
| `marts_ev_ebit` | `enterprise_value_ebit` (x) | Pronto |
| `marts_alavancagem` | `divida_liquida_patrimonio` (x) | Pronto |
| `marts_preco_lucro` | `preco_lucro`, `earnings_yield = 100 / P/L` | Derivado |
| `marts_margens` | `margem_ebit`, `margem_liquida`, `margem_bruta` (%) | Pronto |
| `marts_crescimento_receita_5_anos` | `crescimento_receita_5_anos` (%) | Pronto |
| `marts_dividend_yield_payout` | `dividend_yield`, `payout = DY × P/L` | Derivado |
| `marts_p_vp` | `preco_valor_patrimonial`, `roe`, `p_vp_por_roe` | Derivado |

### 6.2 Retorno e risco (fonte: `refined.yfinance_cotacoes`)

| Mart | Chave | Linhas | Conteúdo |
|---|---|---|---|
| `marts_retorno_total_risco` | `ticker` | 609 | `cagr`, `volatilidade_anualizada`, `max_drawdown` + rastreabilidade (`data_inicial`, `data_final`, `anos`, `qtd_precos_validos`, `qtd_retornos`, `preco_inicial`, `preco_final`) |
| `marts_cotacao` | `(ticker, data)` | 1.920.774 | Histórico OHLC, `fechamento_ajustado`, `volume`, `dividendos`, `desdobramentos`, `ganhos_capital` |

Metodologia: janela de 5 anos até a última cotação; preço válido = `fechamento_ajustado > 0`;
`cagr = ((final/inicial)^(1/anos) − 1) × 100` com `anos = dias / 365,25`;
`volatilidade = stddev_samp(ln(Pt/Pt−1)) × √252 × 100`; `max_drawdown = min(Pt / max(P0..Pt) − 1) × 100`.

### 6.3 Rankings temáticos (`marts_01` … `marts_10`, chave `ticker`)

Consulta-base comum:

```sql
FROM refined.fundamentus_acoes a
INNER JOIN refined.b3_empresas b ON b.empresa_emissora = SUBSTRING(a.ticker, 1, 4)
LEFT JOIN refined.minhareceita_empresas c ON c.cnpj = b.cnpj
```

Classificação por `DENSE_RANK` (empates recebem o mesmo rank).

| Mart | Tema | Elegibilidade | Ordem | Linhas |
|---|---|---|---|---|
| `marts_01_rank_valor` | Valor (Magic Formula simplificada) | ROIC > 0, EV/EBIT > 0 | soma de rank ROIC ↓ + rank EV/EBIT ↑ | 387 |
| `marts_02_rank_proventos` | Proventos | DY > 0, P/L > 0, payout ≥ 0 | DY ↓, payout ↑ | 256 |
| `marts_03_rank_eficiencia` | Eficiência | margem EBIT > 0, margem líquida > 0 | margem EBIT ↓, margem líquida ↓ | 335 |
| `marts_04_rank_retorno` | Retorno | ROE > 0, DL/PL não nula e ≤ 1,5 | ROE ↓, DL/PL ↑ | 367 |
| `marts_05_rank_pechincha` | Pechincha | P/L > 0, EV/EBIT > 0 | soma de rank P/L ↑ + rank EV/EBIT ↑ | 336 |
| `marts_06_rank_patrimonio` | Patrimônio | P/VP > 0, ROE > 0 | P/VP ÷ ROE ↑ | 384 |
| `marts_07_rank_crescimento` | Crescimento | cresc. 5a não nulo, ROIC > 10 | cresc. receita ↓ | 222 |
| `marts_08_rank_operacional` | Operacional | margem EBIT > 0 | margem EBIT ↓ | 394 |
| `marts_09_rank_seguro` | Seguro | DL/PL não nula e ≤ 1,5, ROIC > 0, ROE > 0 | DL/PL ↑, ROIC ↓, ROE ↓ | 277 |
| `marts_10_rank_rentabilidade` | Rentabilidade | P/L > 0 | earnings yield ↓ | 397 |

Proventos não tem teto de payout: 56 dos 256 elegíveis têm payout estimado acima de 100%.

### 6.4 Recomendação consolidada — `marts_50_rank_recomendacoes`

1. Cada um dos 10 rankings é reproduzido dentro da consulta.
2. Faixa por ranking (aritmética inteira, terços):

   | Faixa | Regra | Pontos |
   |---|---|---|
   | Superior | `(rank − 1) × 3 < max_rank − 1` (ou `max_rank = 1`) | +1 |
   | Intermediário | demais elegíveis | 0 |
   | Inferior | `(rank − 1) × 3 > 2 × (max_rank − 1)` | −1 |
   | Não elegível | reprovado na elegibilidade | −1 |

3. `saldo = qtd_superior − qtd_inferior − qtd_nao_elegivel` (−10 a +10):
   `> 0` → **Compra**, `= 0` → **Manter**, `< 0` → **Venda**.
4. Só tickers com `liquidez_2_meses > 0`; `posicao` = `DENSE_RANK` por `saldo` ↓ e `qtd_superior` ↓.

Colunas: `posicao`, `recomendacao`, `ticker`, `empresa`, `razao_social`, `segmento`, `atividade`,
`mercado`, `municipio`, `uf`, `natureza_juridica`, `data_inicio_atividade`, `situacao`, `cotacao`,
`liquidez_2_meses`, `saldo`, `qtd_superior`, `qtd_intermediario`, `qtd_inferior`,
`qtd_nao_elegivel` e `faixa_<tema>` para os 10 temas (auditoria).

Fotografia atual: 391 tickers — 95 Compra, 20 Manter, 276 Venda.

### 6.5 Marts do painel

| Mart | Grão | Colunas |
|---|---|---|
| `marts_card_01_acoes_analisadas` | 1 linha | `quantidade` (tickers com liquidez > 0) |
| `marts_card_02_acoes_compra` | 1 linha | `quantidade` |
| `marts_card_03_acoes_manter` | 1 linha | `quantidade` |
| `marts_card_04_acoes_venda` | 1 linha | `quantidade` |
| `marts_card_02_acoes_semindicacao` | 1 linha | `quantidade` (liquidez nula ou ≤ 0, sobre todo o Fundamentus) |
| `marts_card_05_termometro_mercado` | 1 linha | `recomendacao` predominante (empate → Manter), `quantidade`, `total`, `percentual` |
| `marts_painel_data_referencia` | 1 linha | `data_referencia` (`MAX(_timestamp_ingestao)` em `America/Sao_Paulo`) |
| `marts_painel_indicadores` | `ticker` | recomendação + indicadores do Fundamentus, `payout`, `earnings_yield` |

Dependências entre marts: `marts_50` lê `marts.marts_01` … `marts_10` (ticker e rank), e os cards
01–05 e `marts_painel_indicadores` leem `marts.marts_50_rank_recomendacoes`. A elegibilidade e o
`DENSE_RANK` de cada tema vivem só no arquivo do ranking, e a regra de recomendação só no
`marts_50`. A materialização extrai as referências `marts.<nome>` do `.sql`, prepara os marts em
ordem topológica e troca cada referência pela temporária da mesma execução (`dependencias`,
`ordenar`).

### 6.6 Tratamento de dados

- Valores do Fundamentus sem arredondamento nem troca de escala; negativos e nulos preservados.
- Divisões protegidas (`CASE WHEN … = 0 THEN NULL` / `NULLIF`).
- Zeros do Fundamentus podem significar ausência na origem; os critérios `> 0` dos rankings os excluem.
- 454 tickers do Fundamentus não têm emissora na B3 e ficam fora dos rankings (`INNER JOIN`).
- `segmento` é o segmento de **listagem** da B3, não setor econômico.

---

## 7. `pipeline.materializacao` — publicação da Gold

| Símbolo | Descrição |
|---|---|
| `Mart(nome, chave, natureza)` | Declaração de um mart; `chave=()` = resultado de linha única |
| `MARTS` | Registro dos 30 marts com a chave do comentário `Grão:` de cada `.sql` |
| `ErroMaterializacao(etapa, motivo, *, arquivo, destino, exemplo)` | Erro com contexto; nenhuma tabela Gold muda |
| `inventariar(pasta, marts)` | Exige correspondência 1:1 entre `.sql` e `MARTS` |
| `dependencias(sql)` | Marts lidos pela consulta (`marts.<nome>` fora de comentários) |
| `ordenar(marts, pasta)` | Ordem topológica pelas dependências (empate alfabético); dependência não declarada ou ciclo interrompem |
| `preparar(con, mart, pasta, temporarias)` | Executa o `.sql` uma vez para tabela temporária; valida colunas/tipos contra `DESCRIBE` e a chave (sem nulos/duplicatas; linha única = exatamente 1) |
| `publicar(con, preparadas)` | `CREATE OR REPLACE TABLE marts.<nome>` de todos numa transação; antes do `COMMIT` confere contagem, colunas, tipos, chave e `EXCEPT ALL` nos dois sentidos |
| `executar(con, pasta, marts)` | Orquestra e devolve relatório (tabelas + órfãs) |

Naturezas: **fotografia por ticker**, **agregado de linha única** e **série histórica**
(`marts_cotacao`); todas com **substituição integral**. Tabelas em `marts` sem `.sql`
correspondente são reportadas como órfãs, nunca apagadas.

---

## 8. `pipeline.qualidade` — reconciliação e regras de domínio

Só lê o banco (`read_only`). Cada verificação é um `SELECT` das linhas que violam a regra
(zero linhas = ok); as primeiras viram exemplo no relatório. Código de saída `1` se alguma
verificação de **erro** falhar.

| Símbolo | Descrição |
|---|---|
| `Verificacao(nome, camada, severidade, sql)` | Regra declarada; `severidade` = `ERRO` ou `AVISO` |
| `Resultado` | `violacoes`, `exemplos`, `falha` (consulta não executou) e `status` (`OK`, `AVISO`, `ERRO`) |
| `verificacoes()` | Catálogo completo (71 verificações) |
| `executar(con, catalogo=None)` / `erros(resultados)` | Executa e filtra os erros |
| `exigir(con)` | Executa e levanta `ErroQualidade` se houver erro (portão da fotografia) |

| Camada | O que confere | Severidade |
|---|---|---|
| raw → refined | chaves distintas da Bronze = registros da Silver; mesma `_timestamp_ingestao` (4 fontes) | erro |
| refined → marts | marts do Fundamentus com os mesmos tickers; `marts_cotacao` com as mesmas chaves; rankings dentro do universo; `marts_50` = universo negociado; painel e cards = `marts_50` | erro |
| domínio refined | DY ≥ 0, liquidez ≥ 0, crescimento ≥ −100%, fechamento > 0, volume/dividendos/desdobramentos ≥ 0 | erro |
| domínio refined | cotação > 0 (zero = ausência), percentuais em faixas plausíveis (`FAIXAS_PLAUSIVEIS`), máxima ≥ mínima, fechamento ajustado > 0 | aviso |
| domínio marts | `marts_50`: cotação > 0, saldo em [−10, 10], faixas somam 10, recomendação coerente com o saldo, faixas válidas; rank ≥ 1; termômetro em [0, 100]; data de referência informada | erro |

As faixas plausíveis são aviso porque o Fundamentus publica extremos reais (ROE acima de
1.000.000%, margem líquida de 144.637%) e a Silver preserva o dado como veio. Nulo não viola
regra de domínio. Na base de 02/11/2026: 61 ok, 10 avisos, 0 erros.

---

## 9. `pipeline.fotografia` — fotografia versionada da Gold

| Símbolo | Descrição |
|---|---|
| `exportar(con, pasta)` | Exige qualidade sem erros; grava cada mart de `MARTS` em `<mart>.parquet` (zstd, ordenado pela chave) e `manifesto.json`; troca a pasta por renomeação (falha preserva a anterior) |
| `verificar(pasta)` | Confere arquivos e SHA-256 contra o manifesto; `ErroFotografia` se divergir |
| `conectar(pasta)` | DuckDB em memória com views `marts."<mart>"` sobre os Parquet |
| `ler_manifesto(pasta)` | Lê e valida o formato do manifesto |

Manifesto: `data_referencia`, `gerada_em`, versão do `duckdb`, resumo da qualidade e, por tabela,
`arquivo`, `registros`, `bytes` e `sha256`. `hash` = SHA-256 das linhas `"<mart> <sha256>"` em
ordem alfabética: identifica a fotografia inteira e só muda quando os dados mudam (a escrita é
determinística para a mesma versão do DuckDB). Tipos sem equivalente em Parquet (ex.: `HUGEINT`)
interrompem a exportação. `uv run python -m pipeline.fotografia --verificar` confere a fotografia
versionada (também no CI).

---

## 10. `painel` — leitura, formatação e gráficos

Módulo sem dependência de Streamlit (testável e reaproveitável).

### Leitura

| Símbolo | Descrição |
|---|---|
| `MARTS_CARREGAR` | Cards, marts do painel, 10 rankings, `marts_50` e `marts_retorno_total_risco` |
| `MARTS_OBRIGATORIOS` | `MARTS_CARREGAR` + `marts_cotacao` |
| `tabelas_faltando()` | Lista `marts.<nome>` obrigatórias ausentes (ou o arquivo do banco) |
| `ler(nomes)` | `SELECT * FROM marts."<nome>"` para cada nome → `{nome: DataFrame}` |
| `ler_cotacao(ticker)` | `marts_cotacao` filtrada com `WHERE ticker = ?` (parâmetro vinculado) |
| `filtrar(df, recomendacoes, segmentos, liquidez_minima)` | Recorte por recomendação, segmento e liquidez mínima |
| `BancoBloqueado` | Arquivo em uso por outro processo (UI, ingestão, materialização) |
| `ErroMart(tabela, mensagem)` | Falha ao ler uma tabela |

Cada leitura abre e fecha uma conexão `read_only`. Não há cálculo no painel: **número novo exige
mart novo**.

### Formatação (padrão brasileiro, independente do locale)

| Função | Exemplo | Nulo |
|---|---|---|
| `numero(v, casas=0)` | `1.234` | `—` |
| `reais(v, casas=2)` | `R$ 1.234,56` | `—` |
| `reais_compacto(v)` | `R$ 1,2 mi` / `R$ 3,4 bi` / `R$ 12 mil` | `—` |
| `pct(v, casas=1)` | `12,3%` (não multiplica por 100) | `—` |
| `multiplo(v, casas=1)` | `8,5x` | `—` |
| `data_br(v)` | `02/11/2026` | `—` |

### Gráficos e tabelas (Plotly, template `b3` em modo escuro)

`tabela_consolidado`, `fig_valor_qualidade` (linhas de referência ROIC 15% e EV/EBIT 10x),
`fig_ranking_tematico`, `tabela_ranking_tematico`, `fig_radar` (faixa nos 10 rankings),
`fig_cotacao` (fechamento ajustado + volume + 💰 proventos; preços ≤ 0 ficam fora),
`html_cartao`, `html_termometro`.

Constantes visuais: `REC` (ícone + rótulo + cor por recomendação, para acessibilidade),
`FAIXAS`, `INDICADORES`, `RANKINGS`, `LIQUIDEZ_MINIMA` (Todas, R$ 100 mil, R$ 1 mi, R$ 10 mi).

---

## 11. `app.py` — painel Streamlit

Cinco seções:

1. **Pulso do mercado** — seis cartões (analisadas, Compra, Manter, Venda, sem indicação, termômetro).
2. **Ranking de oportunidades** — tabela consolidada com saldo e faixas por tema.
3. **Valor × qualidade** — dispersão EV/EBIT × ROIC, tamanho = liquidez.
4. **Rankings temáticos** — uma aba por tema (top 15 em gráfico e tabela).
5. **Ficha da ação** — indicadores, CAGR/volatilidade/drawdown, radar e cotação histórica.

Filtros na barra lateral (recomendação, segmento, liquidez mínima) recortam só as seções 2, 3 e a
lista da ficha; cartões e rankings temáticos valem para o mercado inteiro. Dados em
`st.cache_data`, com botão **Recarregar dados**. Tabela faltando, banco bloqueado ou erro de
leitura mostram mensagem clara e param a página. Tema escuro em
[.streamlit/config.toml](.streamlit/config.toml).

---

## 12. Testes

```powershell
uv run pytest   # testpaths = test, pythonpath = .; addopts = --cov, fail_under = 85
```

Cobertura medida sem `test/*`, `app.py`, `ui.py` e `.venv/*`. `test/conftest.py` remove
`VALUATIONB3_DB` e `VALUATIONB3_FONTE` do ambiente de cada teste e aponta a fotografia do painel
para uma pasta vazia: nenhum teste toca o banco real, a fotografia versionada nem a rede.

| Arquivo | Testes | Cobre |
|---|---|---|
| [test/test_db.py](test/test_db.py) | 10 | conexão, `caminho_banco` (`VALUATIONB3_DB`), schema, `gravar` |
| [test/test_ingestao.py](test/test_ingestao.py) | 38 | retry/backoff, 4xx definitivo, cada fonte, `FalhaExtracao`, rollback da gravação |
| [test/test_transformacao.py](test/test_transformacao.py) | 50 | conversões, deduplicação, chaves, JSON, publicação |
| [test/test_sql_marts.py](test/test_sql_marts.py) | 14 | SQLs dos marts com dados fictícios; `marts_50` sobre os rankings; cards × `marts_50`; empate do termômetro |
| [test/test_marts.py](test/test_marts.py) | 24 | inventário, dependências entre marts, preparação, publicação e rollback |
| [test/test_qualidade.py](test/test_qualidade.py) | 16 | pipeline de ponta a ponta + cada tipo de violação; código de saída |
| [test/test_fotografia.py](test/test_fotografia.py) | 22 | exportação, determinismo do hash, portão de qualidade, adulteração, painel sobre a fotografia |
| [test/test_painel.py](test/test_painel.py) | 25 | leitura, filtros, formatação e gráficos |
| [test/test_log.py](test/test_log.py) | 4 | destino das mensagens (`stdout`/`stderr`) e configuração idempotente |
| [test/test_docs_hooks.py](test/test_docs_hooks.py) | 6 | hook do MkDocs: inclusão de documentos e reescrita de links |

---

## 13. Limitações conhecidas

- Fora do escopo: Dívida Líquida/EBITDA, Sharpe, valor justo por Gordon e comparação setorial.
- Rank Valor é uma versão simplificada da Magic Formula; payout é estimado (`DY × P/L`).
- Classes da mesma emissora (ON/PN) compartilham fundamentos e aparecem empatadas.
- 8 tickers têm `fechamento_ajustado < 0` em parte do histórico (tratado como inválido).
- `marts_retorno_total_risco` pode variar no último bit da volatilidade entre execuções
  (`stddev_samp` paralelo); por isso a materialização compara com a temporária, não com uma reexecução.

Pendências e roadmap: [plan.md](plan.md).
