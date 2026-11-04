"""Infraestrutura de conexão e persistência genérica no DuckDB."""

import os
import uuid
from pathlib import Path

import duckdb
import pandas as pd

# Raiz do projeto = pasta imediatamente acima de pipeline/ (independe do cwd).
_RAIZ = Path(__file__).resolve().parent.parent
PASTA_RAW = _RAIZ / "raw"
_ARQUIVO_DB = _RAIZ / "fundamentalistas.duckdb"
# Outro arquivo de banco (ex.: cópia de homologação); relativo = a partir da raiz do projeto.
VARIAVEL_DB = "VALUATIONB3_DB"


def _ident(nome: object) -> str:
    return '"' + str(nome).replace('"', '""') + '"'


def caminho_banco() -> Path:
    """Arquivo do banco: o de VALUATIONB3_DB, se definida e não vazia; senão o padrão."""
    valor = os.environ.get(VARIAVEL_DB, "").strip()
    if not valor:
        return _ARQUIVO_DB
    caminho = Path(valor)
    return caminho if caminho.is_absolute() else _RAIZ / caminho


def conectar() -> duckdb.DuckDBPyConnection:
    """Abre (criando se preciso) o banco. Quem chama é responsável por fechar."""
    return duckdb.connect(str(caminho_banco()))


def criar_schema(con: duckdb.DuckDBPyConnection, nome: str) -> None:
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {_ident(nome)}")


def gravar(
    con: duckdb.DuckDBPyConnection, df: pd.DataFrame, schema: str, tabela: str
) -> int:
    """Recria schema.tabela com todas as colunas como VARCHAR e devolve o COUNT(*) do banco.

    Não inicia nem confirma transações: o controle é de quem chama.
    """
    destino = f"{_ident(schema)}.{_ident(tabela)}"
    visao = f"_gravar_{uuid.uuid4().hex}"
    colunas = ", ".join(
        f"CAST({_ident(c)} AS VARCHAR) AS {_ident(c)}" for c in df.columns
    )
    con.register(visao, df)
    try:
        con.execute(
            f"CREATE OR REPLACE TABLE {destino} AS SELECT {colunas} FROM {_ident(visao)}"
        )
    finally:
        con.unregister(visao)
    return con.execute(f"SELECT COUNT(*) FROM {destino}").fetchall()[0][0]
