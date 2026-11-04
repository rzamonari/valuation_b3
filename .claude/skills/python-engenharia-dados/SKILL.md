---
name: python-engenharia-dados
description: Regras e boas práticas de desenvolvimento Python para o time de Engenharia de Dados no projeto b3_valuation (pacote valuationb3) — estrutura e modularidade, uv, Ruff, pytest com cobertura mínima de 60%, MkDocs Material e práticas de pipelines DuckDB (Bronze/Silver/Gold). Use ao criar, alterar, revisar ou testar código Python, SQL de marts, dependências ou documentação deste repositório.
---

# Python para Engenharia de Dados — b3_valuation

Guia de consulta rápida. Cada regra indica se reflete o **estado atual** do repositório ou é
**[PROPOSTA]** — algo recomendado que ainda não está configurado. Nunca trate uma proposta como
já ativa, e não a aplique fora do escopo da tarefa em andamento.

## 0. Estado atual do repositório (referência)

```text
b3_valuation/
├── pyproject.toml            # projeto "valuationb3", Python >=3.13, sem [build-system]
├── uv.lock
├── app.py                    # interface Streamlit (layout)
├── painel.py                 # leitura dos marts, formatação e gráficos (apresentação)
├── ui.py                     # abre o banco na DuckDB UI
├── pipeline/
│   ├── db.py                 # conexão e persistência genérica no DuckDB
│   ├── ingestao.py           # Bronze  (schema raw)
│   ├── transformacao.py      # Silver  (schema refined) — ~1.800 linhas
│   └── materializacao.py     # Gold    (schema marts)
├── sql/marts/*.sql           # uma consulta por mart + README.md / RANKINGS.md
├── test/                     # test_db, test_transformacao, test_marts, test_sql_marts, test_painel
├── doc_api.md                # referência da API (ainda não versionado)
└── fundamentalistas.duckdb   # banco local, fora do git
```

Já configurado: `uv` + `uv.lock`; grupo `dev` com `pytest`, `pytest-cov`, `ruff`;
`[tool.pytest.ini_options]` (`testpaths = ["test"]`, `pythonpath = ["."]`);
`[tool.coverage]` com `fail_under = 60`, `show_missing = true`, omitindo `test/*`, `app.py`, `ui.py`.

Não configurado: `[tool.ruff]`, MkDocs, layout `src/`, type hints, `logging` estruturado.

## 1. Estrutura e modularidade

**Responsabilidade de cada camada (respeite ao localizar uma mudança):**

| Mudança | Lugar |
|---|---|
| Nova fonte ou extração | `pipeline/ingestao.py` → `raw`, tudo como `VARCHAR` via `db.gravar` |
| Tipagem, padronização, deduplicação | `pipeline/transformacao.py` → `refined` |
| Novo indicador/ranking/agregado | novo `sql/marts/marts_*.sql` + declaração em `MARTS` (`materializacao.py`) |
| Conexão/persistência genérica | `pipeline/db.py` |
| Exibição | `painel.py` (leitura/formatação) e `app.py` (layout) — **sem cálculo**: número novo na tela exige um mart |

Regras:
- Um módulo, uma responsabilidade. Regra de negócio não entra em `db.py`; acesso a banco não entra em `app.py`.
- Sem dependências circulares: `pipeline.*` importa `pipeline.db`, nunca `painel`/`app`.
- Não duplique lógica: reutilize `db.conectar`, `db.gravar`, `db.criar_schema` e os helpers existentes antes de criar outros (ex.: há `_ident` duplicado em `db.py` e `materializacao.py` — ao tocar nesses trechos, prefira reaproveitar o de `db`).
- Módulos grandes (`transformacao.py`): ao adicionar algo significativo, considere extrair por fonte (ex.: `pipeline/transformacao/b3.py`, `.../yfinance.py`) **em PR separado**, sem mudar comportamento.
- Notebooks só para exploração. Código reutilizável vai para o pacote e ganha teste; nenhum notebook é etapa do pipeline.
- Siga o idioma e a nomenclatura do repositório: identificadores em português, `snake_case`, funções privadas com `_`, docstring de módulo com linha `Execução: uv run ...` e decisões de implementação.

**[PROPOSTA] Padrão `src/` e `tests/`** — orientação para a evolução, não renomeie automaticamente:

```text
src/valuationb3/{__init__.py, db.py, ingestao.py, transformacao.py, materializacao.py, painel.py}
tests/{test_db.py, test_ingestao.py, test_transformacao.py, ...}   # espelha src/valuationb3/
app.py                                                              # entrypoint fino
```

Migração incremental (um PR dedicado, testes verdes antes e depois):
1. Adicionar `[build-system]` (ex.: `uv_build`) ao `pyproject.toml` para o projeto ser instalável.
2. `git mv pipeline src/valuationb3` e `git mv test tests`; atualizar imports (`from valuationb3 import db`).
3. Ajustar `testpaths`, remover `pythonpath = ["."]`, ajustar `[tool.coverage.run] source`.
4. Atualizar comandos `uv run python -m ...` em docstrings, `doc_api.md` e `painel.py`.

Até lá, código novo segue a estrutura existente (`pipeline/`, `test/`).

## 2. Ambiente e dependências com `uv`

Nunca use `pip` (nem `uv pip install` como atalho). Toda dependência fica no `pyproject.toml` + `uv.lock`.

```powershell
uv sync                         # cria/atualiza .venv conforme o lockfile (inclui grupo dev)
uv add duckdb                   # dependência de runtime
uv add --dev pytest-mock        # dependência de desenvolvimento
uv remove plotly                # remove e atualiza o lock
uv lock --upgrade-package pandas
uv run python -m pipeline.ingestao        # Bronze
uv run python -m pipeline.transformacao   # Silver
uv run python -m pipeline.materializacao  # Gold
uv run streamlit run app.py               # painel
uv run python ui.py                       # DuckDB UI
```

- Sempre execute ferramentas com `uv run` (inclusive em tarefas do VS Code: hoje `.vscode/tasks.json` chama `python` diretamente).
- Declare todo import direto. **Pendência observada:** `pipeline/ingestao.py` importa `requests` e `lxml`, que só chegam como dependências transitivas — corrigir com `uv add requests lxml`.
- Versione `pyproject.toml` e `uv.lock` juntos, no mesmo commit.
- **Atenção:** as specs referenciadas no código ficam em `.venv/.specs/`. `.venv` é descartável e ignorado pelo git; recriar o ambiente apaga as specs. [PROPOSTA] movê-las para `docs/specs/` e atualizar as referências.

## 3. Estilo, lint e imports com Ruff

Ruff é o único linter/formatador/organizador de imports. Não adicione black, isort ou flake8.

```powershell
uv run ruff check .          # lint
uv run ruff check . --fix    # corrige o que for seguro (inclui ordenação de imports se "I" estiver ativo)
uv run ruff format .         # formata
uv run ruff format . --check # verifica sem alterar (CI)
```

Hoje não há `[tool.ruff]`: valem os padrões (regras `E4`, `E7`, `E9`, `F`; linha 88). Os
imports já seguem a ordem stdlib → terceiros → locais, mas isso **não** é verificado.

**[PROPOSTA]** configuração centralizada no `pyproject.toml`:

```toml
[tool.ruff]
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP", "SIM"]
```

Ao ativar: rode `uv run ruff check . --fix` e `uv run ruff format .` em um commit só de
formatação, separado de mudanças de comportamento. Não crie `ruff.toml` paralelo.

## 4. Testes com pytest e cobertura (mínimo 60%)

```powershell
uv run pytest                                      # todos os testes
uv run pytest test/test_db.py -k gravar            # recorte
uv run pytest --cov                                # cobertura no terminal + fail_under=60
uv run pytest --cov --cov-report=term-missing      # linhas não cobertas
uv run pytest --cov --cov-report=html              # relatório em htmlcov/index.html
```

- O limite de 60% está em `[tool.coverage.report]` e só é aplicado quando `--cov` é passado. [PROPOSTA] `addopts = "--cov"` em `[tool.pytest.ini_options]` para torná-lo obrigatório em toda execução, e `htmlcov/` no `.gitignore`.
- Nunca reduza `fail_under`, amplie `omit` ou adicione `# pragma: no cover` para passar. Se a cobertura cair, escreva testes.
- Arquivo de teste por módulo: `test/test_<modulo>.py`. Nome do teste descreve o comportamento: `test_gravar_de_novo_substitui_a_tabela_sem_acumular`.
- **Nunca toque o banco real.** Padrão do projeto: banco em `tmp_path` e `monkeypatch.setattr(db, "_ARQUIVO_DB", arquivo)` (ver `test/test_db.py`); `painel` usa `ARQUIVO_DB`.
- Sem rede em teste unitário: substitua `_get`, `_sessao` ou chamadas ao `yfinance` com `monkeypatch`, devolvendo payloads mínimos.
- SQL de marts é testado executando o `.sql` real sobre tabelas `refined` pequenas e inventadas (`test/test_sql_marts.py`), com valores escolhidos para o resultado ser conferível à mão.
- Cubra sucesso, erro (ex.: `FalhaExtracao`, `ErroMaterializacao`, rollback preservando a versão anterior) e bordas (nulos, duplicatas, chave vazia, nomes com aspas, tabela vazia).
- Teste comportamento, não implementação: verifique o que foi gravado/devolvido, não a sequência de chamadas internas.
- Dados de teste fictícios: sem CNPJs, e-mails ou dados pessoais reais copiados de produção.

## 5. Documentação com MkDocs Material

Hoje **não há** `mkdocs.yml` nem `docs/`; a documentação está em `doc_api.md`, nas docstrings
de módulo e em `sql/marts/README.md` / `RANKINGS.md`.

**[PROPOSTA]** adoção:

```powershell
uv add --dev mkdocs-material
uv run mkdocs serve           # pré-visualização em http://127.0.0.1:8000
uv run mkdocs build --strict  # build falha com link quebrado ou página fora da nav
```

```yaml
# mkdocs.yml
site_name: B3 Valuation
theme:
  name: material
  language: pt-BR
nav:
  - Início: index.md
  - Instalação e uso: uso.md
  - Arquitetura: arquitetura.md        # Medallion raw → refined → marts, banco único
  - Referência da API: referencia/api.md   # conteúdo atual de doc_api.md
  - Marts: referencia/marts.md         # a partir de sql/marts/README.md e RANKINGS.md
  - Decisões: decisoes/index.md        # specs e decisões de implementação
```

- Toda página nova entra na `nav`. Instalação, configuração, execução do pipeline, arquitetura e decisões relevantes devem estar cobertas.
- Exemplos de código usam a API e os comandos reais (`uv run python -m pipeline.<etapa>`); atualize-os no mesmo PR que mudar a interface.
- Plugins (ex.: `mkdocstrings`) só quando houver necessidade concreta.

## 6. Boas práticas de Python e Engenharia de Dados

**Código**
- Type hints em funções públicas novas ou alteradas (hoje praticamente inexistentes; adote de forma incremental): `def gravar(con: duckdb.DuckDBPyConnection, df: pd.DataFrame, schema: str, tabela: str) -> int:`.
- Funções curtas e coesas; nomes que dizem o que fazem.
- Exceções específicas (`YFRateLimitError`, `duckdb.IOException`, exceções do domínio como `FalhaExtracao`). Nada de `except Exception: pass`.
- Sem efeitos colaterais no import; execução só sob `if __name__ == "__main__":` / `main()`.

**Configuração, caminhos e segredos**
- Caminhos derivados de `Path(__file__)` (padrão de `db._RAIZ`), nunca do diretório corrente nem absolutos.
- [PROPOSTA] permitir sobrescrever o caminho do banco por variável de ambiente, com o valor atual como padrão, para não fixar `fundamentalistas.duckdb` no código.
- Segredos (tokens de API, se surgirem) via variável de ambiente ou `.env` ignorado pelo git — nunca no código, em fixtures, logs ou docs.

**Observabilidade**
- Registre contexto útil: etapa, fonte, contagens lidas/gravadas, falhas por item. Hoje o pipeline usa `print`; [PROPOSTA] migrar para `logging` ao tocar os módulos. Nunca registre headers, tokens ou payloads completos.

**Dados**
- Bronze grava o dado como veio (`VARCHAR`); tipagem e regras na Silver; cálculo na Gold.
- Conversões estritas: valor inválido gera erro ou é reportado, não vira nulo silenciosamente. Não descarte colunas/registros sem registrar.
- Valide chave lógica (sem nulos e sem duplicatas), colunas e tipos antes de publicar — como `materializacao.py` já faz.
- Idempotência: reexecutar uma etapa produz o mesmo estado (`CREATE OR REPLACE`, `CREATE SCHEMA IF NOT EXISTS`).
- Atomicidade: publique em transação; qualquer falha faz `ROLLBACK` e mantém a versão anterior. Extração falhou → nada é gravado.
- Conexões: abra, use e feche (`try/finally`). Leitura com `read_only=True`. O arquivo DuckDB fica bloqueado enquanto há conexão de escrita (ou a DuckDB UI) aberta.
- SQL: valores por parâmetro vinculado (`WHERE ticker = ?`); identificadores via `_ident`. Nunca interpole entrada externa.
- Volume e memória: filtre e agregue no DuckDB, não no pandas. `marts.marts_cotacao` tem ~1,9 milhão de linhas — leia só o recorte necessário; para varreduras grandes use `fetch_record_batch`/`fetch_df_chunk` ou `COPY ... TO` em vez de `fetchdf()` completo.
- Chamadas externas: retry com backoff para erros transitórios, sem retry para erros definitivos (padrão `_com_retry` / `_ErroDefinitivo`), paralelismo limitado.

**Evite** abstrações prematuras (camadas genéricas para uma única fonte) e dependências novas para o que a stdlib, o DuckDB ou o pandas já resolvem.

## 7. Fluxo de trabalho para alterações

1. **Entenda antes de editar:** leia a docstring do módulo (decisões de implementação), a spec citada e os testes da área. Localize a camada correta (tabela da seção 1).
2. **Mudança pequena e coesa**, compatível com nomes, schemas (`raw`/`refined`/`marts`) e interfaces existentes. Refatorações e formatação em massa vão em PRs separados.
3. **Atualize testes e documentação** (`doc_api.md`, docstrings, `sql/marts/README.md`) no mesmo PR quando comportamento ou interface mudar. Mart novo: `.sql` com comentário `Grão:` + entrada em `MARTS` + teste.
4. **Verifique antes de concluir**, executando de fato:

   ```powershell
   uv run ruff check .
   uv run ruff format . --check
   uv run pytest --cov
   uv run mkdocs build --strict   # somente depois que MkDocs estiver configurado
   ```

5. **Relate** os comandos executados e o resultado real (incluindo a cobertura obtida). Se algo falhou ou não foi executado, diga isso explicitamente — nunca afirme que uma verificação passou sem rodá-la.
