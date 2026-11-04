"""Infraestrutura de conexão e persistência genérica no DuckDB.

O banco padrão é fundamentalistas.duckdb na raiz do projeto. A variável de ambiente
VALUATIONB3_DB sobrescreve o caminho; um caminho relativo é resolvido a partir da raiz do
projeto (nunca do diretório corrente), para que todas as etapas e o painel abram o mesmo
arquivo de onde quer que sejam executados.
"""

import os
import uuid
from pathlib import Path

import duckdb
import pandas as pd

# Raiz do projeto = pasta imediatamente acima de pipeline/ (independe do cwd).
_RAIZ = Path(__file__).resolve().parent.parent
PASTA_RAW = _RAIZ / "raw"
VARIAVEL_DB = "VALUATIONB3_DB"
_PADRAO_DB = "fundamentalistas.duckdb"


def caminho_banco() -> Path:
    """Caminho do banco: VALUATIONB3_DB, se definida e não vazia, ou o padrão na raiz."""
    valor = os.environ.get(VARIAVEL_DB, "").strip()
    # Um caminho absoluto em VALUATIONB3_DB prevalece sobre _RAIZ no operador "/".
    return _RAIZ / (valor or _PADRAO_DB)


_ARQUIVO_DB = caminho_banco()


def _ident(nome: object) -> str:
    return '"' + str(nome).replace('"', '""') + '"'


def conectar() -> duckdb.DuckDBPyConnection:
    """Abre (criando se preciso) o banco. Quem chama é responsável por fechar."""
    return duckdb.connect(str(_ARQUIVO_DB))


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
