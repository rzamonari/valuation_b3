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
uv run python -m pipeline.qualidade       # 4. Qualidade (só leitura)
uv run python -m pipeline.fotografia      # 5. Fotografia versionada (fotografia/)
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
inclusive **Pipeline: completo**, que roda materialização e qualidade em sequência.

## Qualidade e fotografia

`pipeline.qualidade` reconcilia raw → refined → marts e aplica regras de domínio; termina com
código `1` se alguma verificação de erro falhar (avisos só aparecem no relatório).

`pipeline.fotografia` exige a qualidade sem erros e grava `marts.*` em `fotografia/` (um Parquet
por mart + `manifesto.json` com data de referência, contagens e SHA-256). A pasta é versionada no
git; para publicar dados novos, gere a fotografia e faça commit dela.

```powershell
uv run python -m pipeline.fotografia --verificar   # confere os hashes da fotografia versionada
```

## Painel sobre a fotografia (Streamlit Cloud)

O painel lê o banco local se `fundamentalistas.duckdb` existir; senão, lê a fotografia versionada.
`VALUATIONB3_FONTE=fotografia` (ou `banco`) fixa a fonte. O cabeçalho do painel mostra qual fonte
está em uso e, na fotografia, a data de referência e o início do hash.

```powershell
$env:VALUATIONB3_FONTE = "fotografia"; uv run streamlit run app.py
```

O painel está publicado em
[valuationb3-zamonari.streamlit.app](https://valuationb3-zamonari.streamlit.app/).

Configuração no [Streamlit Community Cloud](https://share.streamlit.io): repositório
`rzamonari/valuation_b3`, branch `main`, arquivo principal `app.py`, Python 3.13 em
**Advanced settings**, sem secrets. No Cloud não há `fundamentalistas.duckdb` (o banco não é
versionado), então o painel lê a fotografia sem precisar de `VALUATIONB3_FONTE`. As dependências
vêm do `uv.lock` / `requirements.txt`, exportado dele (o CI falha se os dois divergirem):

```powershell
uv export --no-dev --no-hashes --no-emit-project --locked -o requirements.txt
```

### Atualizar a fotografia publicada

Gerar → verificar → commit → o Cloud faz o redeploy sozinho a cada push na `main`:

```powershell
uv run python -m pipeline.fotografia              # gerar (exige a qualidade sem erros)
uv run python -m pipeline.fotografia --verificar  # verificar os hashes do manifesto
git add fotografia/
git commit -m "data: fotografia de <data de referência>"
git push origin main
```

Confira no cabeçalho do painel publicado a nova data de referência e o início do hash.

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
uv run pytest                  # testes, sempre com cobertura (mínimo 85%)
uv run python -m pipeline.fotografia --verificar   # integridade da fotografia
uv run mkdocs serve            # esta documentação em http://127.0.0.1:8000
uv run mkdocs build --strict   # falha com link quebrado ou página fora da navegação
```

O GitHub Actions (`.github/workflows/ci.yml`) roda `ruff check`, `ruff format --check`, a
conferência de `requirements.txt` e da fotografia e o `pytest` (Ubuntu e Windows) a cada push na
`main` e em todo pull request.

Os testes nunca tocam o banco real nem a rede: usam DuckDB em pasta temporária e substituem as
chamadas HTTP e o yfinance por respostas mínimas.
