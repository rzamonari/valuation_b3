"""Infraestrutura de conexão e persistência genérica no DuckDB."""

import uuid
from pathlib import Path

import duckdb

# Raiz do projeto = pasta imediatamente acima de pipeline/ (independe do cwd).
_RAIZ = Path(__file__).resolve().parent.parent
PASTA_RAW = _RAIZ / "raw"
_ARQUIVO_DB = _RAIZ / "fundamentalistas.duckdb"


def _ident(nome):
    return '"' + str(nome).replace('"', '""') + '"'


def conectar():
    """Abre (criando se preciso) o banco. Quem chama é responsável por fechar."""
    return duckdb.connect(str(_ARQUIVO_DB))


def criar_schema(con, nome):
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {_ident(nome)}")


def gravar(con, df, schema, tabela):
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
