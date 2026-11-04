---
name: python-engenharia-dados
description: Regras e boas práticas de desenvolvimento Python do projeto b3_valuation (pacote valuationb3) — estrutura do pacote pipeline/, uv, Ruff, pytest com cobertura mínima de 85%, MkDocs Material e engenharia de dados sobre DuckDB (Bronze/Silver/Gold). Use ao criar, alterar, revisar ou testar código Python, SQL de marts, dependências ou documentação deste repositório.
---

# Python para Engenharia de Dados — b3_valuation

Guia de consulta rápida para quem altera este repositório. Fontes complementares:
[plan.md](../../../plan.md) (fases, pendências P1–P8 e roadmap A–G) e
[doc_api.md](../../../doc_api.md) (o que cada módulo faz).

**Legenda:** ✅ já configurado no repositório · 📋 recomendação/proposta (ainda não ativa).
Nunca trate um item 📋 como se já estivesse em vigor.

---

## 1. Estrutura e modularidade

### Estrutura observada

```text
b3_valuation/
├── pyproject.toml          ✅ projeto "valuationb3", Python >= 3.13
├── uv.lock                 ✅
├── pipeline/               ✅ pacote Python
│   ├── db.py               conexão, caminho do banco e persistência genérica no DuckDB
│   ├── log.py              logging dos comandos (stdout até INFO, stderr avisos/erros)
│   ├── ingestao.py         Bronze  → schema raw      (python -m pipeline.ingestao)
│   ├── transformacao/      Silver  → schema refined  (subpacote: comum, b3, fundamentus,
│   │                       yfinance, minhareceita; orquestração no __init__)
│   └── materializacao.py   Gold    → schema marts    (executa sql/marts/*.sql)
├── sql/marts/*.sql         ✅ um SELECT puro por mart (fonte da verdade da Gold)
├── painel.py               ✅ lógica do painel (leitura, filtros, formatação)
├── app.py                  ✅ interface Streamlit (apenas layout/interação)
├── ui.py                   ✅ abre a DuckDB UI
├── test/                   ✅ testes pytest (nome atual: test/, não tests/)
├── mkdocs.yml + docs/      ✅ documentação MkDocs Material (specs em docs/specs/)
└── site/                   gerado por `uv run mkdocs build` (fora do git)
```

### Responsabilidade por camada

| Camada | Onde mexer | Regra |
|---|---|---|
| Acesso a dados | `pipeline/db.py` | Conexão, schema, gravação genérica. Sem regra de negócio |
| Ingestão (Bronze) | `pipeline/ingestao.py` | Dado como veio, tudo `VARCHAR`, com `_timestamp_ingestao` e `_source_origin` |
| Transformação (Silver) | `pipeline/transformacao/` | Tipagem, deduplicação, chaves. **Sem cálculo financeiro, sem preencher ausentes** |
| Regras de negócio (Gold) | `sql/marts/*.sql` + `MARTS` em `materializacao.py` | Indicador novo = mart novo |
| Orquestração/CLI | `main()` + `if __name__ == "__main__"` de cada módulo | Código de saída `0` sucesso, `1` falha |
| Apresentação | `painel.py` (lógica) e `app.py` (Streamlit) | Só lê, filtra, ordena e formata. **Número novo exige mart novo** |

### Regras

- Código novo vai em `pipeline/`. Quando um módulo crescer demais, divida-o em subpacote
  `pipeline/<nome_do_pacote>/` mantendo a interface pública (ex.: Etapa E do plano:
  `pipeline/transformacao/{comum,b3,fundamentus,minhareceita,yfinance}.py`, com
  `__main__.py` para manter `python -m`).
- Cada etapa lê apenas a camada anterior. Nada de `painel.py` lendo `raw.*`.
- Sem dependência circular: `db` não importa nada de `pipeline`; os demais importam `db`.
- Não duplique utilitários: `_ident` e `caminho_banco()` vivem em `db` e são reaproveitados
  (inclusive pelo painel).
- Notebooks (se usados) são só para exploração; funções reutilizáveis vão para `pipeline/`
  com teste. Nenhum passo do pipeline pode depender de notebook.
- Mantenha nomes em português e o padrão existente (`extrair_*`, `preparar`, `publicar`,
  `marts_<nome>.sql`, `marts_card_NN_*`, `marts_NN_rank_*`).

### 📋 Propostas incrementais (não renomear automaticamente)

- **`test/` → `tests/`**: em PR próprio, `git mv test tests` e ajustar `testpaths` e
  `[tool.coverage.run] omit`. Até lá, testes novos vão em `test/`.
- **Espelhar módulos nos testes**: `test/test_<modulo>.py` por módulo; ao virar subpacote,
  `test/<subpacote>/test_<modulo>.py`.
- A Etapa F do plano (layout `src/valuationb3`) diverge do padrão `pipeline/` adotado aqui;
  decidir antes de executá-la.

---

## 2. Projeto com `uv`

Sempre `uv`. **Nunca `pip install`** (nem `uv pip install` para dependências do projeto):
o que não está no `pyproject.toml` + `uv.lock` não existe para o time.

```powershell
uv sync                              # cria/atualiza .venv a partir do uv.lock
uv add <pacote>                      # dependência de execução
uv add --dev <pacote>                # grupo dev (pytest, ruff, mkdocs...)
uv remove <pacote>
uv lock --upgrade-package <pacote>   # atualização pontual
uv run python -m pipeline.ingestao   # qualquer comando roda via uv run
```

- `pyproject.toml` e `uv.lock` sempre no **mesmo commit**.
- Dependência importada precisa estar declarada, mesmo que já venha transitiva
  (`requests` e `lxml` da ingestão e `mkdocs-material` do grupo dev já estão).
- Tarefas do VS Code (`.vscode/tasks.json`) chamam sempre `uv run`, nunca `python` direto.
- Mudanças de configuração são incrementais: acrescente seções ao `pyproject.toml`, não reescreva o arquivo.

### Comandos do dia a dia

```powershell
# pipeline completo (feche a DuckDB UI antes: um único processo grava no arquivo)
uv run python -m pipeline.ingestao        # Bronze  (raw)
uv run python -m pipeline.transformacao   # Silver  (refined)
uv run python -m pipeline.materializacao  # Gold    (marts)
uv run streamlit run app.py               # painel

# qualidade
uv run ruff check .
uv run ruff check . --fix
uv run ruff format .
uv run pytest                             # sempre com cobertura (addopts = --cov)
uv run mkdocs serve                       # documentação em http://127.0.0.1:8000

# atalhos taskipy ([tool.taskipy.tasks] no pyproject.toml; lista: uv run task --list)
uv run task test     # pytest com cobertura
uv run task lint     # ruff check . && ruff format . --check
uv run task format   # ruff check . --fix && ruff format .
uv run task docs     # mkdocs serve
```

---

## 3. Estilo, lint e imports — Ruff

Estado ✅: `ruff` no grupo `dev` e configurado no `pyproject.toml` (Etapa A):

```powershell
uv run ruff check .            # lint
uv run ruff check . --fix      # correções automáticas, inclusive ordenação de imports (regra I)
uv run ruff format .           # formatação
uv run ruff format . --check   # verificação sem alterar (CI / definição de pronto)
```

```toml
[tool.ruff]
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP", "SIM"]

[tool.ruff.lint.pycodestyle]
max-line-length = 100   # E501 em prosa/SQL; o formatter mantém o código em 88
```

- Configuração só no `pyproject.toml`; não crie `ruff.toml`/`.ruff.toml`.
- Ruff já formata e organiza imports: **não** adicione black, isort ou flake8.
- Formatação em massa vai em commit/PR só de formatação, separado de mudança de comportamento.
- `# noqa` só com o código da regra e um motivo: `# noqa: E501  URL longa`.

---

## 4. Testes — pytest e cobertura

Estado ✅: `pytest`, `pytest-cov`; `testpaths = ["test"]`, `pythonpath = ["."]`,
`addopts = "--cov"`; `[tool.coverage.report] fail_under = 85`, `show_missing = true`.
Todo `uv run pytest` aplica o limite. `htmlcov/` está no `.gitignore`.

```powershell
uv run pytest                                  # todos os testes + cobertura (fail_under 85)
uv run pytest test/test_db.py -k gravar --no-cov   # recorte rápido, sem cobertura
uv run pytest --cov-report=html                # relatório em htmlcov/index.html
```

### Regras

- **Nunca** reduza `fail_under`, amplie `omit` ou marque `skip` para fazer a execução passar.
- Sem rede e sem banco real: use `tmp_path` + `monkeypatch` como em `test/test_db.py`
  (`monkeypatch.setattr(db, "_ARQUIVO_DB", tmp_path / "teste.duckdb")`);
  `test/conftest.py` remove `VALUATIONB3_DB` do ambiente de cada teste.
  Para ingestão, substitua `_sessao` e `yf.Ticker` (ver `test/test_ingestao.py`).
- Dados de teste pequenos, fictícios e conferíveis à mão (DataFrames ou `INSERT` inline).
- Cubra sucesso, erro (`FalhaExtracao`, `ErroMaterializacao`, `ROLLBACK`) e bordas do domínio:
  nulos, duplicatas, tabela vazia, divisão por zero → `NULL`, zeros do Fundamentus.
- Teste comportamento observável (tabela publicada, contagem, valor calculado), não a
  implementação (não reescreva o SQL no teste para comparar com ele mesmo).
- Nome descreve a regra: `test_gravar_de_novo_substitui_a_tabela_sem_acumular`.
- Testes determinísticos: sem dependência de data atual, ordem de linhas ou aleatoriedade
  (ordene com `ORDER BY`, fixe datas).

```python
# Ilustrativo: banco_temporario e executar_mart são helpers a definir no próprio arquivo de teste.
def test_mart_retorna_null_quando_divisor_e_zero(tmp_path, monkeypatch):
    con = banco_temporario(tmp_path, monkeypatch)
    con.execute("CREATE TABLE refined.x AS SELECT 10.0 AS lucro, 0.0 AS pl")
    resultado = executar_mart(con, "marts_exemplo")
    assert resultado["indicador"].isna().all()
```

---

## 5. Documentação — MkDocs Material

Estado ✅ (Etapa C): `mkdocs-material` no grupo dev, `mkdocs.yml` (`strict: true`) e `docs/`;
specs versionadas em `docs/specs/`; `site/` fora do git. As páginas da Referência publicam
`doc_api.md`, `sql/marts/README.md` e `RANKINGS.md` sem cópia: o hook `docs/hooks.py`
inclui o arquivo de origem e reescreve os links (código vira texto).

```powershell
uv run mkdocs serve            # pré-visualização em http://127.0.0.1:8000
uv run mkdocs build --strict   # falha em link quebrado ou página fora da nav
```

```text
docs/
├── index.md
├── uso.md            instalação (uv sync), execução do pipeline, painel
├── arquitetura.md    camadas raw/refined/marts, garantias (atomicidade, idempotência)
├── decisoes.md       decisões e limitações aceitas
├── referencia/       marcadores preenchidos pelo hook (api, marts, rankings)
├── specs/            specs de cada camada
└── hooks.py          hook do MkDocs (fora do site via exclude_docs)
```

- Toda página entra na `nav`; `--strict` deve passar.
- Exemplos de código e comandos na doc devem ser os reais (`uv run python -m pipeline.<modulo>`)
  e atualizados no mesmo PR que muda a interface — inclusive `doc_api.md`, docstrings e
  `sql/marts/README.md`.

---

## 6. Boas práticas de Python e Engenharia de Dados

### Código

- Tipagem explícita em funções públicas (✅ em `db`, `ingestao`, `transformacao` e
  `materializacao`; mantenha em código novo):
  ```python
  def gravar(con: duckdb.DuckDBPyConnection, df: pd.DataFrame, schema: str, tabela: str) -> int:
  ```
- Funções coesas, nomes claros, docstring curta dizendo contrato e efeitos (como `gravar`:
  "não inicia nem confirma transações").
- Exceções específicas do domínio (`FalhaExtracao`, `ErroMaterializacao`); nada de
  `except Exception: pass`. Capture o mínimo e repasse contexto.
- Caminhos derivados de `Path(__file__)` (padrão atual), nunca do diretório de trabalho
  nem absolutos fixos. O banco vem de `db.caminho_banco()`: `VALUATIONB3_DB` (relativo =
  a partir da raiz) ou `fundamentalistas.duckdb`.
- Sem efeitos colaterais no import: conexão, leitura e escrita só dentro de funções.
- SQL dinâmico: identificadores via `_ident`; valores via parâmetro vinculado (`?`), nunca f-string.
- Sem abstração ou dependência nova sem necessidade concreta.

### Configuração, segredos e logs

- As fontes atuais são públicas e o projeto não usa segredos. Se surgir algum: variável de
  ambiente, nunca no código, no `.mcp.json`, em fixtures ou na doc.
- Saída via `logging` (✅ Etapa D): logger `pipeline.<modulo>` com nome explícito (sob
  `python -m`, `__name__` é `__main__`) e `pipeline.log.configurar()` só no `main()`.
  Registre etapa, fonte, contagens e falhas por item — **nunca** headers, tokens ou
  payloads completos.

### Dados

- **Atomicidade:** cada etapa publica numa transação; falha → `ROLLBACK`, versão anterior preservada.
- **Idempotência:** reexecutar produz o mesmo estado (`CREATE OR REPLACE`, `IF NOT EXISTS`).
- **Schema explícito:** Bronze tudo `VARCHAR`; tipagem estrita só na Silver; conversão
  inválida é tratada explicitamente, não silenciada.
- **Nulos preservados:** nunca viram zero; divisão por zero → `NULL`. Zeros do Fundamentus que
  significam ausência são excluídos pelos critérios `> 0`, não reescritos.
- **Chaves:** valide unicidade da chave lógica (como `_validar_chave` em `materializacao.py`)
  e deduplique na Silver.
- **Rastreabilidade:** mantenha `_timestamp_ingestao` e `_source_origin`; relate contagens por tabela.
- **Volume e memória:** filtre e agregue no DuckDB, não no pandas. Ex.: `marts_cotacao`
  (~1,9 mi linhas) é lida no painel filtrada por ticker com parâmetro vinculado; use
  `read_only=True` para leitura.
- **Fontes externas:** paralelismo limitado e retry com backoff (`_com_retry`, `_em_paralelo`);
  valide disponibilidade antes de extrair (`validar_fontes`).
- Arquivos `*.duckdb` e `*.parquet` não vão para o git (já no `.gitignore`); fixtures não
  contêm dados reais de pessoas (ex.: dados de sócios da Minha Receita).

---

## 7. Fluxo de trabalho para alterações

1. **Entender antes de editar:** ler o módulo, os testes correspondentes, `doc_api.md` e a
   seção relevante do `plan.md`. Identificar a camada certa (tabela da seção 1).
2. **Mudança pequena e coesa**, compatível com nomes, interfaces e convenções atuais.
   Refatoração/formatação em massa nunca junto com mudança de comportamento.
3. **Indicador novo** (receita da Etapa G):
   `sql/marts/marts_<nome>.sql` (SELECT puro, comentário `Grão:`) → declaração em `MARTS`
   (`materializacao.py`) → teste em `test/test_sql_marts.py` → se exibido, `MARTS_CARREGAR`/
   `MARTS_OBRIGATORIOS` em `painel.py` e `doc_api.md`.
4. **Atualizar testes e documentação** sempre que comportamento ou interface mudar.
5. **Verificar ao concluir** (o que estiver configurado):
   ```powershell
   uv run ruff check .
   uv run ruff format . --check
   uv run pytest
   uv run mkdocs build --strict
   ```
6. **Relatar** os comandos executados e o resultado real (incluindo % de cobertura e falhas).
   Não afirme que algo passou sem ter executado; se uma verificação não pôde rodar, diga qual e por quê.

### Checklist de PR

- [ ] Mudança na camada correta; sem lógica de cálculo fora da Gold.
- [ ] Testes de sucesso, erro e bordas; sem rede e sem banco real.
- [ ] `uv run pytest` ≥ 85% sem mexer em `fail_under`/`omit`.
- [ ] `pyproject.toml` + `uv.lock` juntos quando houver dependência nova.
- [ ] `doc_api.md`, docstrings e `sql/marts/README.md` atualizados se a interface mudou.
