# Plano do projeto — B3 Valuation (`valuationb3`)

Plano de construção e evolução do pipeline de indicadores fundamentalistas de ações da B3, em
arquitetura Medallion (Bronze → Silver → Gold) sobre DuckDB, com painel em Streamlit.

Fontes deste plano: [doc_api.md](doc_api.md) (o que o sistema faz) e
[.claude/skills/python-engenharia-dados/SKILL.md](.claude/skills/python-engenharia-dados/SKILL.md)
(como o time desenvolve).

> Os sinais de Compra/Manter/Venda são relativos e mecânicos, derivados de 10 rankings sobre uma
> fotografia de dados. **Não constituem recomendação de investimento.**

**Legenda de status:** ✅ entregue · 🔧 pendência no que já existe · 📋 proposta (ainda não ativa)

---

## 1. Objetivo e escopo

**Objetivo:** consolidar dados públicos de quatro fontes num banco DuckDB local, calcular
indicadores e rankings fundamentalistas e exibi-los num painel somente leitura.

**Dentro do escopo**

- Extração de B3 (empresas listadas), Fundamentus, Minha Receita (CNPJ) e Yahoo Finance.
- Tipagem, padronização e validação de chaves (Silver), sem cálculo financeiro.
- 11 marts de indicadores, 10 rankings temáticos, 1 recomendação consolidada e marts do painel.
- Painel Streamlit com cinco seções e filtros.

**Fora do escopo (limitações aceitas)**

- Dívida Líquida/EBITDA, Sharpe, valor justo por Gordon e comparação setorial.
- Setor econômico (o `segmento` disponível é o de listagem da B3).
- Execução agendada, banco remoto e múltiplos usuários gravando.

---

## 2. Princípios de arquitetura

| Camada | Schema | Artefato | Regra |
|---|---|---|---|
| Bronze | `raw` | `pipeline/ingestao.py` | Dado como veio, tudo `VARCHAR`, com `_timestamp_ingestao` e `_source_origin` |
| Silver | `refined` | `pipeline/transformacao.py` | Tipagem estrita, deduplicação, validação de chave; **sem cálculo, sem preencher ausentes** |
| Gold | `marts` | `sql/marts/*.sql` + `pipeline/materializacao.py` | Um `SELECT` puro por mart; o `.sql` é a fonte da verdade |
| Apresentação | — | `painel.py` + `app.py` | Só lê, filtra, ordena e formata; **número novo exige mart novo** |

Garantias transversais, válidas para todas as etapas:

- **Atomicidade:** cada etapa publica numa única transação; falha → `ROLLBACK` e versão anterior preservada.
- **Idempotência:** reexecutar produz o mesmo estado (`CREATE OR REPLACE`, `IF NOT EXISTS`).
- **Isolamento entre camadas:** cada etapa lê apenas a camada anterior.
- **Banco único:** `fundamentalistas.duckdb` na raiz, caminho derivado de `Path(__file__)`.
- **Nulos preservados:** nunca viram zero; divisão por zero resulta em `NULL`.
- **Código de saída:** `0` em sucesso, `1` em falha.

---

## 3. Fases de construção

### Fase 0 — Fundação do projeto ✅

- [x] `pyproject.toml` (`valuationb3`, Python ≥ 3.13) gerenciado por `uv`, com `uv.lock` versionado.
- [x] Dependências: `duckdb`, `pandas`, `pyarrow`, `plotly`, `streamlit`, `yfinance`.
- [x] Grupo `dev`: `pytest`, `pytest-cov`, `ruff`.
- [x] `[tool.pytest.ini_options]` e `[tool.coverage]` com `fail_under = 60`.
- [x] `pipeline/db.py`: `conectar`, `criar_schema`, `gravar` (recria tabela com colunas `VARCHAR`).
- [x] `ui.py` (DuckDB UI em `localhost:4213`) e `.mcp.json` (servidor MCP de leitura).

**Critério de pronto:** `uv sync` e `uv run pytest test/test_db.py` passam.

### Fase 1 — Bronze: ingestão (`raw`) ✅

- [x] `validar_fontes()` antes de qualquer extração.
- [x] `extrair_b3()` com paginação de 120 → `raw.b3_empresas`.
- [x] `extrair_fundamentus()` → `raw.fundamentus_acoes`.
- [x] `identificar_cnpjs()` + `extrair_minhareceita()` → `raw.minhareceita_empresas`.
- [x] `identificar_tickers()` + `extrair_yfinance()` → `raw.yfinance_cotacoes`.
- [x] Retry com backoff (`TENTATIVAS = 3`, `BACKOFF_BASE = 2`, `TIMEOUT = 30`), sem retry para erro definitivo.
- [x] Paralelismo limitado (`WORKERS_HTTP = 8`, `WORKERS_YFINANCE = 4`).
- [x] `FalhaExtracao`: qualquer fonte falhou → nenhuma tabela é gravada.

**Critério de pronto:** `uv run python -m pipeline.ingestao` grava as 4 tabelas `raw.*` numa transação.

### Fase 2 — Silver: transformação (`refined`) ✅

- [x] `verificar_bronze()` orienta rodar a ingestão se faltar tabela.
- [x] Conversões estritas (`Conversao`): `TEXTO`, `DATA_BR`, `NUMERO_BR`, `TIMESTAMP_TZ`, `DOUBLE`, `BIGINT`, `CNPJ`; valor inválido gera `ErroTransformacao` com etapa, origem, destino, coluna e exemplo.
- [x] Decodificação do JSON da Minha Receita em tabela principal + arrays (`qsa`, `regime_tributario`, `cnaes_secundarios`).
- [x] Validação de chaves: `codigo_cvm`, `ticker`, `(ticker, data)`, `cnpj`.
- [x] `publicar()` substitui todas as tabelas `refined.*` numa transação.

**Critério de pronto:** `uv run python -m pipeline.transformacao` produz as 7 tabelas `refined.*`; `test/test_transformacao.py` verde.

### Fase 3 — Gold: marts (`marts`) ✅

**3.1 Indicadores** — `marts_roic`, `marts_roe`, `marts_ev_ebit`, `marts_alavancagem`,
`marts_preco_lucro`, `marts_margens`, `marts_crescimento_receita_5_anos`,
`marts_dividend_yield_payout`, `marts_p_vp`, `marts_retorno_total_risco`, `marts_cotacao`.

**3.2 Rankings temáticos** (`marts_01` a `marts_10`): Valor, Proventos, Eficiência, Retorno,
Pechincha, Patrimônio, Crescimento, Operacional, Seguro, Rentabilidade — todos a partir de
`fundamentus_acoes` ⨝ `b3_empresas` (emissora = 4 primeiros caracteres) ⟕ `minhareceita_empresas`,
com `DENSE_RANK`.

**3.3 Recomendação consolidada** (`marts_50_rank_recomendacoes`): faixas por terço,
`saldo = superiores − inferiores − não elegíveis`, sinal Compra/Manter/Venda, apenas
`liquidez_2_meses > 0`, colunas `faixa_<tema>` para auditoria.

**3.4 Marts do painel:** `marts_card_01` a `marts_card_05`, `marts_painel_indicadores`,
`marts_painel_data_referencia`.

**3.5 Materialização** (`pipeline/materializacao.py`):

- [x] Registro `MARTS` com `Mart(nome, chave, natureza)` e `inventariar()` 1:1 com os `.sql`.
- [x] `preparar()` em tabela temporária, validando colunas, tipos e chave (sem nulos/duplicatas).
- [x] Conferência pré-`COMMIT` (contagem, colunas, tipos, `EXCEPT ALL` nos dois sentidos).
- [x] Só o schema `marts` é alterado; órfãs são reportadas, não apagadas.

**Critério de pronto:** `uv run python -m pipeline.materializacao` publica todos os marts;
`test/test_sql_marts.py` e `test/test_marts.py` verdes.

### Fase 4 — Apresentação ✅

- [x] `painel.py` sem dependência de Streamlit: `ler`, `ler_cotacao` (parâmetro vinculado), `tabelas_faltando`, `filtrar`.
- [x] Exceções `BancoBloqueado` e `ErroMart`; cada leitura abre e fecha conexão `read_only`.
- [x] Formatação brasileira independente de locale (`numero`, `reais`, `reais_compacto`, `pct`, `multiplo`, `data_br`).
- [x] Gráficos: valor × qualidade, rankings temáticos, radar, cotação, tabela consolidada, cartões e termômetro.
- [x] `app.py`: pulso do mercado, ranking de oportunidades, valor × qualidade, rankings temáticos (abas) e ficha da ação; cache com botão **Recarregar dados**; tema escuro.
- [x] Erros (tabela faltando, banco bloqueado, falha de leitura) exibem mensagem clara sem traceback.

**Critério de pronto:** `uv run streamlit run app.py` abre o painel; `test/test_painel.py` verde.

---

## 4. Pendências no que já existe ✅

Itens observados no repositório que devem ser corrigidos antes das propostas da seção 5.
Todos resolvidos (P2: as tarefas antigas eram renomeações pontuais de specs e foram
substituídas pelas etapas do pipeline, testes e Ruff via `uv run`).

| # | Pendência | Ação | Verificação |
|---|---|---|---|
| P1 | `pipeline/ingestao.py` importa `requests` e `lxml` sem declará-los | `uv add requests lxml`; commitar `pyproject.toml` + `uv.lock` juntos | `uv sync` limpo + `uv run python -m pipeline.ingestao` |
| P2 | `.vscode/tasks.json` chama `python` direto | Trocar por `uv run ...` | Executar as tarefas no VS Code |
| P3 | `_ident` repetido em `db.py`, `materializacao.py` e `transformacao.py` | Reaproveitar o de `db` | `uv run pytest --cov` |
| P4 | Specs em `.venv/.specs/` (pasta descartável) | Mover para `docs/specs/` e atualizar referências | Busca por `.venv/.specs` sem resultados |
| P5 | `doc_api.md` ainda não versionado | Revisar e commitar | `git status` |

---

## 5. Roadmap de evolução 📋

Cada etapa é um PR dedicado, com testes verdes antes e depois. Refatoração e formatação em massa
nunca se misturam com mudança de comportamento.

### Etapa A — Qualidade de código (Ruff) ✅

> `E501` ignorado: o comprimento de linha fica a cargo do `ruff format`; o que ele não quebra
> (strings, SQL, URLs) não justifica reescrita manual.

1. Adicionar `[tool.ruff]` no `pyproject.toml` (`target-version = "py313"`; regras `E`, `F`, `W`, `I`, `B`, `UP`, `SIM`).
2. Commit só de formatação: `uv run ruff check . --fix` e `uv run ruff format .`.
3. Corrigir à mão o que o `--fix` não resolver.

**Pronto quando:** `uv run ruff check .` e `uv run ruff format . --check` passam sem erros.

### Etapa B — Testes obrigatórios ✅

1. `addopts = "--cov"` em `[tool.pytest.ini_options]`, tornando o limite de 60% obrigatório.
2. `htmlcov/` no `.gitignore`.
3. Criar `test/test_ingestao.py` (sem rede: `monkeypatch` em `_get`, `_sessao` e `yfinance`), cobrindo sucesso, `FalhaExtracao` e retry.

**Pronto quando:** `uv run pytest` aplica a cobertura e fica ≥ 60% sem ampliar `omit`.

### Etapa C — Documentação com MkDocs Material ✅

> `doc_api.md` e `sql/marts/*.md` são incluídos no site via `pymdownx.snippets` (fonte única).

1. `uv add --dev mkdocs-material`; criar `mkdocs.yml` (`language: pt-BR`).
2. Páginas: Início, Instalação e uso, Arquitetura, Referência da API (de `doc_api.md`), Marts (de `sql/marts/README.md` e `RANKINGS.md`), Decisões (specs da P4).
3. Toda página na `nav`.

**Pronto quando:** `uv run mkdocs build --strict` passa.

### Etapa D — Robustez e observabilidade ✅

> Logging em `pipeline/log.py`; variável `VALUATIONB3_DB` em `db.caminho_banco()`.

1. Type hints nas funções públicas, começando por `pipeline/db.py`.
2. Migrar `print` para `logging` (etapa, fonte, contagens, falhas por item; nunca headers, tokens ou payloads).
3. Caminho do banco configurável por variável de ambiente, mantendo `fundamentalistas.duckdb` como padrão.

**Pronto quando:** testes verdes e o pipeline completo roda com a variável ausente e presente.

### Etapa E — Modularização da Silver ✅

1. Extrair `pipeline/transformacao.py` (~1.800 linhas) por fonte: `pipeline/transformacao/{b3,fundamentus,minhareceita,yfinance}.py`.
2. Sem mudança de comportamento: mesmas tabelas `refined.*`, mesmos testes.

**Pronto quando:** `refined.*` idêntico antes e depois (comparação por `EXCEPT ALL`).

### Etapa F — Layout `pipeline/` (opcional, último)

1. `[build-system]` com `uv_build`.
2. `git mv painel.py pipeline/painel.py`, `git mv test tests`; imports continuam `from pipeline import db`.
3. Ajustar `testpaths`, remover `pythonpath = ["."]`, ajustar `[tool.coverage.run] source`.
4. Atualizar comandos em docstrings, `doc_api.md`, `painel.py` e MkDocs.

**Pronto quando:** pipeline completo, painel e `uv run pytest` funcionam com os novos caminhos.

### Etapa G — Novos indicadores (backlog de produto)

Candidatos hoje fora do escopo: Dívida Líquida/EBITDA, Sharpe, valor justo por Gordon,
comparação setorial (exige fonte de setor econômico). Para cada um:

1. Novo `sql/marts/marts_<nome>.sql` com `SELECT` puro e comentário `Grão:`.
2. Declaração em `MARTS` (`materializacao.py`).
3. Teste em `test/test_sql_marts.py` com dados fictícios conferíveis à mão.
4. Se exibido: incluir em `MARTS_CARREGAR` / `MARTS_OBRIGATORIOS` (`painel.py`) e atualizar `doc_api.md`.

Se o indicador depender de dado que a Silver não tem, a mudança começa na Bronze (nova fonte) e
segue camada a camada.

---

## 6. Ordem de execução do pipeline

```powershell
uv sync
uv run python -m pipeline.ingestao        # 1. Bronze  (raw)
uv run python -m pipeline.transformacao   # 2. Silver  (refined)
uv run python -m pipeline.materializacao  # 3. Gold    (marts)
uv run streamlit run app.py               # painel
```

Feche a DuckDB UI (`ui.py`) antes das etapas 1 a 3: o DuckDB aceita um único processo gravando.

---

## 7. Definição de pronto (todo PR)

```powershell
uv run ruff check .
uv run ruff format . --check
uv run pytest --cov
uv run mkdocs build --strict   # a partir da Etapa C
```

- [ ] Mudança na camada correta (tabela da seção 2).
- [ ] Testes cobrindo sucesso, erro e bordas (nulos, duplicatas, tabela vazia); sem banco real e sem rede.
- [ ] `doc_api.md`, docstrings e `sql/marts/README.md` atualizados se a interface mudou.
- [ ] `pyproject.toml` e `uv.lock` no mesmo commit quando houver dependência nova.
- [ ] Comandos executados e resultado real (incluindo cobertura) relatados no PR.

---

## 8. Riscos

| Risco | Impacto | Mitigação |
|---|---|---|
| Fonte muda formato ou sai do ar | Ingestão aborta | `validar_fontes`, `FalhaExtracao`, conversões estritas na Silver |
| Rate limit do Yahoo Finance | Extração lenta ou falha | Paralelismo limitado (4), retry com backoff |
| Zeros do Fundamentus significando ausência | Rankings distorcidos | Preservados e excluídos pelos critérios `> 0` |
| `fechamento_ajustado` negativo | Métricas de risco erradas | Tratado como inválido no mart e no gráfico |
| Tickers sem emissora na B3 | Ficam fora dos rankings | Documentado; avaliar join alternativo |
| Arquivo DuckDB bloqueado | Etapa não grava | Fechar a UI; painel usa `read_only` |
| Volume de `marts_cotacao` (~1,9 mi linhas) | Memória no painel | Filtrar no banco por ticker com parâmetro vinculado |
