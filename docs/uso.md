# Instalação e uso

## Requisitos

- Python ≥ 3.13
- [uv](https://docs.astral.sh/uv/) — gerencia o ambiente e as dependências. Não use `pip`.

## Instalação

```powershell
uv sync   # cria a .venv conforme o uv.lock (inclui o grupo dev)
```

## Executar o pipeline

As etapas rodam em ordem: cada uma lê apenas a camada anterior.

```powershell
uv run python -m pipeline.ingestao        # 1. Bronze  (raw)
uv run python -m pipeline.transformacao   # 2. Silver  (refined)
uv run python -m pipeline.materializacao  # 3. Gold    (marts)
uv run streamlit run app.py               # painel
```

Todas terminam com código `0` em sucesso e `1` em falha. Em falha, nenhuma tabela da camada de
destino é alterada.

O banco fica em `fundamentalistas.duckdb`, na raiz do projeto. Para usar outro arquivo (ex.: uma
cópia de homologação), defina `VALUATIONB3_DB`; um caminho relativo é resolvido a partir da raiz
do projeto. Pipeline, painel e `ui.py` passam a usar o mesmo arquivo:

```powershell
$env:VALUATIONB3_DB = "D:\dados\homologacao.duckdb"
uv run python -m pipeline.transformacao
Remove-Item Env:VALUATIONB3_DB   # volta ao padrão
```

Progresso e relatórios saem em `stdout`; avisos e erros, em `stderr`.

!!! note "Arquivo bloqueado"
    O DuckDB aceita um único processo gravando. Feche a DuckDB UI (`uv run python ui.py`) antes
    das etapas 1 a 3. O painel pode ficar aberto: cada leitura abre e fecha uma conexão
    `read_only`. Depois de materializar, clique em **Recarregar dados**.

No VS Code, as mesmas etapas estão em **Terminal → Executar Tarefa** (`.vscode/tasks.json`),
inclusive **Pipeline: completo**, que roda as três em sequência.

## Ferramentas auxiliares

```powershell
uv run python ui.py   # DuckDB UI em http://localhost:4213 (Ctrl+C encerra)
```

O `.mcp.json` registra um servidor MCP de leitura apontando para o banco, para consultas por
assistentes de IA.

## Desenvolvimento

```powershell
uv run ruff check .            # lint
uv run ruff format . --check   # formatação
uv run pytest                  # testes, sempre com cobertura (mínimo 60%)
uv run mkdocs serve            # esta documentação em http://127.0.0.1:8000
uv run mkdocs build --strict   # falha com link quebrado ou página fora da navegação
```

Os testes nunca tocam o banco real nem a rede: usam DuckDB em pasta temporária e substituem as
chamadas HTTP e o yfinance por respostas mínimas.
