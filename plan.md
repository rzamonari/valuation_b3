# Plano do projeto — B3 Valuation (`valuationb3`)

Plano de construção e evolução do pipeline de indicadores fundamentalistas de ações da B3, em
arquitetura Medallion (Bronze → Silver → Gold) sobre DuckDB, com painel somente leitura em
Streamlit.

Fontes deste plano: [doc_api.md](doc_api.md) (o que o sistema faz) e
[.claude/skills/python-engenharia-dados/SKILL.md](.claude/skills/python-engenharia-dados/SKILL.md)
(como o time desenvolve). Estado do repositório conferido em **04/11/2026**.

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
- 11 marts de indicadores (9 do Fundamentus + retorno/risco + cotação), 10 rankings temáticos,
  1 recomendação consolidada e 8 marts do painel — 30 marts no total.
- Painel Streamlit com cinco seções e filtros.

**Fora do escopo (limitações aceitas)**

- Dívida Líquida/EBITDA, Sharpe, valor justo por Gordon e comparação setorial.
- Setor econômico (o `segmento` disponível é o de listagem da B3).
- Execução agendada, banco remoto e múltiplos processos gravando.

---

## 2. Princípios de arquitetura

| Camada | Schema | Artefato | Regra |
|---|---|---|---|
| Bronze | `raw` | `pipeline/ingestao.py` | Dado como veio, tudo `VARCHAR`, com `_timestamp_ingestao` e `_source_origin` |
| Silver | `refined` | `pipeline/transformacao/` | Tipagem estrita, deduplicação, validação de chave; **sem cálculo, sem preencher ausentes** |
| Gold | `marts` | `sql/marts/*.sql` + `pipeline/materializacao.py` | Um `SELECT` puro por mart, lendo `refined` e, quando agrega outro mart, `marts.<nome>`; o `.sql` é a fonte da verdade |
| Apresentação | — | `painel.py` + `app.py` | Só lê, filtra, ordena e formata; **número novo exige mart novo** |

Garantias transversais, válidas para todas as etapas:

- **Atomicidade:** cada etapa publica numa única transação; falha → `ROLLBACK` e versão anterior preservada.
- **Idempotência:** reexecutar produz o mesmo estado (`CREATE OR REPLACE`, `IF NOT EXISTS`).
- **Isolamento entre camadas:** cada etapa lê apenas a camada anterior e grava só no seu schema.
  Na Gold, um mart pode ler outro mart da mesma execução (`marts.<nome>`, resolvido em ordem
  topológica pela materialização), nunca a versão publicada anterior.
- **Banco único:** `fundamentalistas.duckdb` na raiz, caminho derivado de `Path(__file__)`;
  `VALUATIONB3_DB` aponta outro arquivo (ex.: homologação) para pipeline e painel.
- **Nulos preservados:** nunca viram zero; divisão por zero resulta em `NULL`.
- **Código de saída:** `0` em sucesso, `1` em falha (mensagem em `stderr`, sem traceback).

Dependências entre módulos: `db` não importa nada de `pipeline`; `ingestao`, `transformacao` e
`materializacao` importam `db`; `painel` lê só `marts.*`; `app` usa só `painel`.

---

## 3. Fases de construção (entregues)

### Fase 0 — Fundação ✅

- [x] `pyproject.toml` (`valuationb3`, Python ≥ 3.13) gerenciado por `uv`, com `uv.lock` versionado.
- [x] Dependências: `duckdb`, `pandas`, `pyarrow`, `plotly`, `streamlit`, `yfinance`; grupo `dev`: `pytest`, `pytest-cov`, `ruff`.
- [x] `[tool.pytest.ini_options]` (`testpaths = ["test"]`, `pythonpath = ["."]`) e `[tool.coverage]` com `fail_under = 60`.
- [x] `pipeline/db.py`: `conectar`, `criar_schema`, `gravar` (recria tabela com colunas `VARCHAR`), `_ident`.
- [x] `ui.py` (DuckDB UI em `localhost:4213`) e `.mcp.json` (servidor MCP de leitura).

**Pronto:** `uv sync` e `uv run pytest test/test_db.py` passam.

### Fase 1 — Bronze: ingestão (`raw`) ✅

- [x] `validar_fontes()` antes de qualquer extração.
- [x] `extrair_b3()` (paginação de 120) → `raw.b3_empresas`.
- [x] `extrair_fundamentus()` → `raw.fundamentus_acoes`.
- [x] `identificar_cnpjs()` + `extrair_minhareceita()` → `raw.minhareceita_empresas` (HTTP 400/404 = CNPJ rejeitado e listado).
- [x] `identificar_tickers()` + `extrair_yfinance()` → `raw.yfinance_cotacoes`.
- [x] Retry com backoff (`TENTATIVAS = 3`, `BACKOFF_BASE = 2`, `TIMEOUT = 30`); 429/5xx repetidos, demais 4xx definitivos.
- [x] Paralelismo limitado (`WORKERS_HTTP = 8`, `WORKERS_YFINANCE = 4`).
- [x] `FalhaExtracao`: qualquer fonte inteira falhou → nenhuma tabela é gravada.

**Pronto:** `uv run python -m pipeline.ingestao` grava as 4 tabelas `raw.*` numa transação.

### Fase 2 — Silver: transformação (`refined`) ✅

- [x] `verificar_bronze()` orienta rodar a ingestão se faltar tabela.
- [x] Conversões estritas (`Conversao`): `TEXTO`, `DATA_BR`, `NUMERO_BR`, `TIMESTAMP_TZ`, `DOUBLE`, `BIGINT`, `CNPJ`; valor inválido gera `ErroTransformacao` com etapa, origem, destino, coluna e exemplo.
- [x] Toda coluna Bronze mapeada (nenhuma descartada em silêncio); nomes em `snake_case` português.
- [x] JSON da Minha Receita validado contra contrato e decomposto em tabela principal + `qsa`, `regime_tributario`, `cnaes_secundarios`.
- [x] Deduplicação de linhas idênticas; chave nula ou duplicada com conteúdo diferente → erro.
- [x] `publicar()` substitui as 7 tabelas `refined.*` numa transação.

**Pronto:** `uv run python -m pipeline.transformacao` produz as 7 tabelas; `test/test_transformacao.py` verde.

### Fase 3 — Gold: marts (`marts`) ✅

- **3.1 Indicadores:** `marts_roic`, `marts_roe`, `marts_ev_ebit`, `marts_alavancagem`,
  `marts_preco_lucro`, `marts_margens`, `marts_crescimento_receita_5_anos`,
  `marts_dividend_yield_payout`, `marts_p_vp`, `marts_retorno_total_risco` (janela de 5 anos),
  `marts_cotacao`.
- **3.2 Rankings temáticos** (`marts_01` … `marts_10`): Valor, Proventos, Eficiência, Retorno,
  Pechincha, Patrimônio, Crescimento, Operacional, Seguro, Rentabilidade —
  `fundamentus_acoes` ⨝ `b3_empresas` (emissora = 4 primeiros caracteres) ⟕
  `minhareceita_empresas`, com `DENSE_RANK`.
- **3.3 Recomendação** (`marts_50_rank_recomendacoes`): faixas por terço,
  `saldo = superiores − inferiores − não elegíveis`, Compra/Manter/Venda, só
  `liquidez_2_meses > 0`, colunas `faixa_<tema>` para auditoria.
- **3.4 Marts do painel:** `marts_card_01` … `marts_card_05`, `marts_card_02_acoes_semindicacao`,
  `marts_painel_indicadores`, `marts_painel_data_referencia`.
- **3.5 Materialização** (`pipeline/materializacao.py`):
  - [x] `MARTS` com `Mart(nome, chave, natureza)`; `inventariar()` exige 1:1 com os `.sql`.
  - [x] `preparar()` em tabela temporária, validando colunas, tipos e chave.
  - [x] Conferência pré-`COMMIT` (contagem, colunas, tipos, chave, `EXCEPT ALL` nos dois sentidos).
  - [x] Só o schema `marts` é alterado; órfãs são reportadas, nunca apagadas.

**Pronto:** `uv run python -m pipeline.materializacao` publica os 30 marts;
`test/test_sql_marts.py` e `test/test_marts.py` verdes.

### Fase 4 — Apresentação ✅

- [x] `painel.py` sem dependência de Streamlit: `ler`, `ler_cotacao` (parâmetro vinculado), `tabelas_faltando`, `filtrar`; exceções `BancoBloqueado` e `ErroMart`; conexão `read_only` por leitura.
- [x] Formatação brasileira independente de locale (`numero`, `reais`, `reais_compacto`, `pct`, `multiplo`, `data_br`).
- [x] Gráficos Plotly (template `b3`, escuro): valor × qualidade, rankings temáticos, radar, cotação, tabela consolidada, cartões e termômetro.
- [x] `app.py`: pulso do mercado, ranking de oportunidades, valor × qualidade, rankings temáticos e ficha da ação; `st.cache_data` + **Recarregar dados**.
- [x] Tabela faltando, banco bloqueado ou erro de leitura → mensagem clara e página interrompida.

**Pronto:** `uv run streamlit run app.py` abre o painel; `test/test_painel.py` verde.

**Testes hoje:** 163 casos em 8 arquivos (`test_db` 10, `test_ingestao` 38,
`test_transformacao` 49, `test_sql_marts` 12, `test_marts` 18, `test_painel` 25, `test_log` 4,
`test_docs_hooks` 6); cobertura 91,8% com `uv run pytest`.

---

## 4. Pendências no que já existe ✅

Todas resolvidas em 04/11/2026, cada uma num commit pequeno, sem mudança de comportamento do
pipeline. A P6 foi resolvida pela própria Etapa E (a pasta virou o subpacote).

| # | Pendência (observada no repositório) | Ação | Verificação |
|---|---|---|---|
| ✅ P1 | `pipeline/ingestao.py` importa `requests` e `lxml`, não declarados no `pyproject.toml` | `uv add requests lxml`; `pyproject.toml` + `uv.lock` no mesmo commit | `uv sync` limpo + `uv run python -m pipeline.ingestao` |
| ✅ P2 | `.vscode/tasks.json` só tem tarefas pontuais de renomear specs em `.venv/.specs/`, chamando `python` direto | Remover as tarefas obsoletas; se quiser tarefas, criar as do pipeline com `uv run ...` | Executar as tarefas no VS Code |
| ✅ P3 | `_ident` duplicado em `db.py`, `materializacao.py` e `transformacao.py` | Reaproveitar `db._ident` | `uv run pytest --cov` |
| ✅ P4 | Specs em `.venv/.specs/` (pasta descartável, fora do git), citadas em `painel.py`, `app.py`, `materializacao.py`, `sql/marts/README.md` e `RANKINGS.md` — e os nomes citados (`marts_agregacao_*.md`) não batem com os arquivos reais (`marts_sql_*.md`) | Mover para `docs/specs/`, versionar e corrigir as referências | Busca por `.venv/.specs` sem resultados |
| ✅ P5 | `doc_api.md` e `.claude/` não versionados | Revisar e commitar | `git status` |
| ✅ P6 | `pipeline/transformacao/` existia vazia (só `__pycache__`) ao lado de `transformacao.py` | Apagar até a Etapa E começar de fato | `uv run python -m pipeline.transformacao` |
| ✅ P7 | Comentários de 5 `.sql` com mojibake (`âˆ’`, `mecà¢nico`); correção está no working tree, não commitada | Commitar a correção (junto com o texto novo de Proventos em `painel.py`) | `rg "Ã|â€|âˆ" sql/` sem resultados |
| ✅ P8 | Cards e `marts_painel_indicadores` contêm **cópia literal** da consulta de `marts_50`; a mudança da P7 já teve de ser feita em 5 arquivos | Teste de consistência: contagens dos cards = `COUNT(*)` por `recomendacao` em `marts_50`; recomendação de `marts_painel_indicadores` = a de `marts_50` | Novo teste em `test/test_sql_marts.py` |

---

## 5. Roadmap de evolução 📋

Cada etapa é um PR dedicado, com testes verdes antes e depois. Refatoração e formatação em massa
nunca se misturam com mudança de comportamento. Ordem sugerida: A → B → C → D → E; F só após
decisão; G conforme demanda.

**Estado em 04/11/2026:** A–E e H ✅ entregues (branch `evolucao/pendencias-e-roadmap`);
F 📋 aguarda decisão; G 📋 backlog.

### Etapa A — Qualidade de código (Ruff) ✅

> Entregue. Além do `select`, `[tool.ruff.lint.pycodestyle] max-line-length = 100`: o formatter
> mantém o código em 88 colunas e o E501 vale a 100 para docstrings, comentários e SQL em
> strings (margem já usada no projeto). A cópia da spec Silver na docstring de
> `transformacao.py` deu lugar a uma referência a `docs/specs/refined_transformacao.md`.

1. Acrescentar ao `pyproject.toml` (sem reescrevê-lo):
   ```toml
   [tool.ruff]
   target-version = "py313"

   [tool.ruff.lint]
   select = ["E", "F", "W", "I", "B", "UP", "SIM"]
   ```
2. Commit só de formatação: `uv run ruff check . --fix` e `uv run ruff format .`.
3. Corrigir à mão o restante; `# noqa` só com código da regra e motivo.

**Pronto quando:** `uv run ruff check .` e `uv run ruff format . --check` passam.

### Etapa B — Testes obrigatórios ✅

> Entregue: `addopts = "--cov"`, `htmlcov/` ignorado, `test/test_ingestao.py` (38 casos,
> ingestão de 0% para 89%). Cobertura total 91,8%.

1. `addopts = "--cov"` em `[tool.pytest.ini_options]`, tornando os 60% obrigatórios.
2. `htmlcov/` no `.gitignore`.
3. `test/test_ingestao.py` sem rede (`monkeypatch` em `_get`, `_sessao` e `yfinance`): sucesso,
   `FalhaExtracao`, retry em 429/5xx, erro definitivo em 4xx, CNPJ rejeitado, `ROLLBACK` na gravação.
4. Teste de consistência cards × `marts_50` (P8), se ainda não feito.

**Pronto quando:** `uv run pytest` aplica a cobertura e fica ≥ 60% sem ampliar `omit` nem reduzir `fail_under`.

### Etapa C — Documentação com MkDocs Material ✅

> Entregue. A Referência não copia `doc_api.md`, `README.md` e `RANKINGS.md`: o hook
> `docs/hooks.py` inclui o arquivo de origem e reescreve os links (código vira texto), para
> o `--strict` validar sem afrouxar a checagem de links.

1. `uv add --dev mkdocs-material` (hoje está no `.venv`, mas não declarado).
2. `mkdocs.yml` (`language: pt-BR`) e `docs/`: Início, Instalação e uso, Arquitetura,
   Referência (API de `doc_api.md`; Marts de `sql/marts/README.md`; Rankings de `RANKINGS.md`),
   Decisões, Specs (de `docs/specs/`, P4).
3. Toda página na `nav`.
4. Com o build reproduzível, tirar `site/` do git (61 arquivos versionados hoje) e incluí-lo no `.gitignore`.

**Pronto quando:** `uv run mkdocs build --strict` passa e `site/` não está mais versionado.

### Etapa D — Robustez e observabilidade ✅

> Entregue: `pipeline/log.py`, type hints nas funções públicas, `VALUATIONB3_DB`
> (`db.caminho_banco()`, reutilizado pelo painel). Silver e Gold rodaram com a variável
> presente sobre uma cópia do banco. Com a variável ausente, a resolução para
> `fundamentalistas.duckdb` foi verificada, mas o pipeline completo não rodou no banco real.

1. Type hints nas funções públicas, começando por `pipeline/db.py`.
2. Migrar `print` para `logging` (`ingestao.py` já importa `logging`, mas imprime): etapa, fonte,
   contagens e falhas por item; nunca headers, tokens ou payloads.
3. Caminho do banco configurável por variável de ambiente, mantendo `fundamentalistas.duckdb` como padrão.

**Pronto quando:** testes verdes e o pipeline completo roda com a variável ausente e presente.

### Etapa E — Modularização da Silver ✅

> Entregue, com um módulo a mais: `comum.py` (erros, conversões, deduplicação e preparo SQL
> compartilhados) e `__main__.py` (mantém `python -m`). `refined.*` idêntico antes e depois:
> EXCEPT ALL nos dois sentidos nas 7 tabelas e as 130 colunas com os mesmos tipos.

1. Dividir `pipeline/transformacao.py` (1.033 linhas após a Etapa A) em
   `pipeline/transformacao/{__init__,b3,fundamentus,minhareceita,yfinance}.py`, mantendo a
   interface pública (`executar`, `main`, `ErroTransformacao`, …) e `python -m pipeline.transformacao`.
2. Sem mudança de comportamento: mesmas tabelas `refined.*`, mesmos testes.

**Pronto quando:** `refined.*` idêntico antes e depois (`EXCEPT ALL` nos dois sentidos).

### Etapa F — Layout `src/` (decisão pendente) 📋

Diverge do padrão `pipeline/` adotado na skill; **decidir antes de executar**. Se aprovada:

1. `[build-system]` com `uv_build`.
2. `git mv pipeline src/valuationb3`, `git mv test tests`; imports `from valuationb3 import db`.
3. Ajustar `testpaths`, remover `pythonpath = ["."]`, ajustar `[tool.coverage.run]`.
4. Atualizar comandos em docstrings, `doc_api.md`, `painel.py` e MkDocs.

**Pronto quando:** pipeline completo, painel e `uv run pytest` funcionam com os novos caminhos.

### Etapa H — Publicação e confiabilidade ✅

> Entregue em 04/11/2026, um commit por item.

1. `marts_50` lê os rankings `marts_01` … `marts_10`, e cards e `marts_painel_indicadores` leem
   `marts_50`; a materialização resolve as dependências `marts.<nome>` em ordem topológica.
   As 30 tabelas `marts.*` ficaram iguais sobre o banco real (`EXCEPT ALL` nos dois sentidos).
2. CI no GitHub Actions (`ruff check`, `ruff format --check`, `pytest` em Ubuntu e Windows) e
   `fail_under` de 60 para 85.
3. `pipeline/qualidade.py`: 71 verificações (reconciliação raw → refined → marts e regras de
   domínio, como `cotacao > 0` e percentuais em faixas plausíveis); erro = código 1.
4. `pipeline/fotografia.py`: `fotografia/` versionada (Parquet + manifesto com data de
   referência e SHA-256), gerada só com qualidade aprovada; o painel a lê quando não há banco
   local (Streamlit Community Cloud).
5. `README.md` na raiz com objetivo, diagrama, execução, capturas do painel e resultados.

Correções encontradas no caminho: o termômetro falhava em empate no máximo (subconsulta escalar
com duas linhas) e `total` era `HUGEINT`, sem equivalente em Parquet.

**Pendente fora do repositório:** criar o app no Streamlit Community Cloud (conta do usuário),
depois do merge na `main`.

### Etapa G — Novos indicadores (backlog de produto) 📋

Candidatos: Dívida Líquida/EBITDA, Sharpe, valor justo por Gordon, comparação setorial (exige
fonte de setor econômico). Para cada um:

1. `sql/marts/marts_<nome>.sql` com `SELECT` puro e comentário `Grão:`.
2. Declaração em `MARTS` (`materializacao.py`).
3. Teste em `test/test_sql_marts.py` com dados fictícios conferíveis à mão (inclui nulos e divisão por zero).
4. Se exibido: `MARTS_CARREGAR` / `MARTS_OBRIGATORIOS` em `painel.py` e `doc_api.md`.

Se o indicador depender de dado ausente na Silver, a mudança começa na Bronze (nova fonte) e segue
camada a camada. Rankings e regra de recomendação têm uma única fonte (`marts_01`…`10` e
`marts_50`); cards e painel os leem como dependência.

---

## 6. Ordem de execução do pipeline

```powershell
uv sync
uv run python -m pipeline.ingestao        # 1. Bronze  (raw)
uv run python -m pipeline.transformacao   # 2. Silver  (refined)
uv run python -m pipeline.materializacao  # 3. Gold    (marts)
uv run python -m pipeline.qualidade       # 4. Qualidade (só leitura; erro = código 1)
uv run python -m pipeline.fotografia      # 5. Fotografia versionada (commit de fotografia/)
uv run streamlit run app.py               # painel
```

Feche a DuckDB UI (`ui.py`) antes das etapas 1 a 3: o DuckDB aceita um único processo gravando.
O painel pode ficar aberto; depois de materializar, clique em **Recarregar dados**.

---

## 7. Definição de pronto (todo PR)

```powershell
uv run ruff check .
uv run ruff format . --check
uv run pytest                  # cobertura obrigatória (addopts = --cov)
uv run mkdocs build --strict
```

O CI (`.github/workflows/ci.yml`) repete as três primeiras e confere `requirements.txt` e a
fotografia versionada.

- [ ] Mudança na camada correta (seção 2); sem cálculo fora da Gold.
- [ ] Testes de sucesso, erro e bordas (nulos, duplicatas, tabela vazia, divisão por zero, zeros do Fundamentus); sem rede e sem banco real.
- [ ] Cobertura ≥ 85% sem mexer em `fail_under`/`omit`.
- [ ] `pyproject.toml` + `uv.lock` no mesmo commit quando houver dependência nova; nunca `pip install`.
- [ ] `doc_api.md`, docstrings e `sql/marts/README.md`/`RANKINGS.md` atualizados se a interface mudou.
- [ ] Comandos executados e resultado real (incluindo % de cobertura) relatados no PR.

---

## 8. Riscos

| Risco | Impacto | Mitigação |
|---|---|---|
| Fonte muda formato ou sai do ar | Ingestão aborta | `validar_fontes`, `FalhaExtracao`, conversões estritas na Silver |
| Rate limit do Yahoo Finance | Extração lenta ou falha | Paralelismo 4, retry com backoff |
| Regra de recomendação repetida em vários `.sql` | Números divergentes entre seções | Resolvido: `marts_50` lê os rankings e cards/painel leem `marts_50`; teste de consistência mantido (P8 ✅) |
| Zeros do Fundamentus significando ausência | Rankings distorcidos | Preservados e excluídos pelos critérios `> 0` |
| Payout estimado (`DY × P/L`) acima de 100% | Proventos favorece pagadora insustentável | Desempate por menor payout; documentado (56 de 256 elegíveis) |
| `fechamento_ajustado` negativo (8 tickers) | Métricas de risco erradas | Tratado como inválido no mart e no gráfico |
| 454 tickers sem emissora na B3 | Ficam fora dos rankings | Explicado por motivo em `marts_exclusoes_universo` e no painel; join alternativo avaliado e descartado (cadastro só de ativas; `otherCodes` não recupera nenhum) |
| Classes ON/PN da mesma emissora | Aparecem empatadas | Documentado como limitação |
| Arquivo DuckDB bloqueado | Etapa não grava | Fechar a UI; painel usa `read_only` |
| Volume de `marts_cotacao` (~1,9 mi linhas) | Memória no painel | Filtro no banco por ticker com parâmetro vinculado |
| Specs fora do git | Perda de decisões ao recriar o `.venv` | Resolvido: versionadas em `docs/specs/` (P4 ✅) |
