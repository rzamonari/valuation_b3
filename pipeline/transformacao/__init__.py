r"""Transformação da camada Refined (Silver): B3, Fundamentus, yfinance e Minha Receita.

Execução: uv run python -m pipeline.transformacao

Módulos: comum (erros, conversões, deduplicação e preparo SQL), b3, fundamentus e
yfinance (mapeamento de cada tabela), minhareceita (contrato JSON). Este módulo
orquestra a verificação da Bronze, a publicação atômica e o relatório.

Spec: docs/specs/refined_transformacao.md (fonte da verdade das regras da Silver; as
seções citadas abaixo e nos comentários referem-se a ela).

# DECISÕES DE IMPLEMENTAÇÃO (confirmadas após a inspeção dos dados reais)

1. refined.minhareceita_regime_tributario usa a chave (cnpj, sequencia_regime), e não
   (cnpj, ano): a mesma empresa tem vários regimes no mesmo ano (um por cnpj_da_scp e,
   em alguns casos, formas de tributação distintas com cnpj_da_scp nulo). sequencia_regime
   é a posição original do objeto no array, como sequencia_socio no QSA.
2. As três tabelas auxiliares herdam _timestamp_ingestao e _source_origin da linha Bronze
   da empresa de origem.
3. sequencia_socio e sequencia_regime começam em 1 (posição ordinal no array).
4. Tipagem da Minha Receita (contrato validado em todos os registros a cada execução):
   strings JSON -> VARCHAR; inteiros JSON -> BIGINT; capital_social (inteiros e decimais)
   -> DECIMAL(p,s) com precisão calculada sobre todos os valores; booleanos -> BOOLEAN;
   propriedades data_* (YYYY-MM-DD) -> DATE; email (sempre nulo na inspeção) -> VARCHAR.
   Propriedades ausentes, não previstas, duplicadas ou com tipo incompatível geram erro.
5. A deduplicação compara os registros já tipados (todas as colunas, incluindo metadados).
6. Publicação: as sete tabelas são preparadas e validadas em tabelas temporárias da conexão
   e substituídas em uma única transação (CREATE OR REPLACE TABLE é transacional no DuckDB:
   ROLLBACK restaura a versão anterior das tabelas).
7. Fundamentus: o valor exatamente igual a '-' (após a limpeza das extremidades, quando
   houver) é o marcador de "sem valor" da própria fonte e vira NULL nas 21 colunas
   numéricas. Qualquer outro texto não numérico continua gerando erro de conversão.
8. CNPJ (seção 7.8): b3_empresas.cnpj, o cnpj da Minha Receita (linha Bronze e JSON),
   o cnpj das tabelas auxiliares e cnpj_da_scp são completados com zeros à esquerda até
   14 dígitos. NULL e string vazia são preservados; valor não numérico ou com mais de
   14 dígitos gera erro.
"""

import contextlib
import logging
import sys

import duckdb

from pipeline import db, execucao
from pipeline.db import _ident
from pipeline.log import configurar as configurar_logging
from pipeline.transformacao import b3, fundamentus, yfinance
from pipeline.transformacao.comum import (
    BIGINT,
    CNPJ,
    DATA_BR,
    DOUBLE,
    NUMERO_BR,
    ORIENTACAO_BRONZE,
    SCHEMA_DESTINO,
    SCHEMA_ORIGEM,
    TEXTO,
    TIMESTAMP_TZ,
    Coluna,
    Conversao,
    ErroTransformacao,
    Preparada,
    TabelaSql,
    _contexto,
    _fmt,
    _rotulo_bronze,
    _rotulo_silver,
    _silver,
    preparar_tabela_sql,
)
from pipeline.transformacao.minhareceita import (
    ARRAYS_EMPRESA,
    COLUNAS_BRONZE_MINHARECEITA,
    ESCALARES_EMPRESA,
    METADADOS,
    ORIGEM_MINHARECEITA,
    ArrayJson,
    preparar_minhareceita,
)

__all__ = [
    "ARRAYS_EMPRESA",
    "BIGINT",
    "CNPJ",
    "COLUNAS_BRONZE_MINHARECEITA",
    "DATA_BR",
    "DOUBLE",
    "ESCALARES_EMPRESA",
    "METADADOS",
    "NUMERO_BR",
    "ORIGEM_MINHARECEITA",
    "SCHEMA_DESTINO",
    "SCHEMA_ORIGEM",
    "TABELAS_BRONZE",
    "TABELAS_SQL",
    "TEXTO",
    "TIMESTAMP_TZ",
    "ArrayJson",
    "Coluna",
    "Conversao",
    "ErroTransformacao",
    "Preparada",
    "TabelaSql",
    "executar",
    "main",
    "preparar_minhareceita",
    "preparar_tabela_sql",
    "publicar",
    "verificar_bronze",
]

log = logging.getLogger(__name__)

TABELAS_SQL = (b3.TABELA, fundamentus.TABELA, yfinance.TABELA)
TABELAS_BRONZE = tuple(t.origem for t in TABELAS_SQL) + (ORIGEM_MINHARECEITA,)


# --------------------------------------------------------------------------- verificação Bronze


def verificar_bronze(con: duckdb.DuckDBPyConnection) -> None:
    existentes = {
        nome
        for (nome,) in con.execute(
            "SELECT table_name FROM duckdb_tables() "
            "WHERE database_name = current_database() AND schema_name = ?",
            [SCHEMA_ORIGEM],
        ).fetchall()
    }
    ausentes = [t for t in TABELAS_BRONZE if t not in existentes]
    if ausentes:
        raise ErroTransformacao(
            "verificação da Bronze",
            f"tabela(s) Bronze ausente(s): {', '.join(map(_rotulo_bronze, ausentes))}. "
            f"{ORIENTACAO_BRONZE}",
            origem=", ".join(map(_rotulo_bronze, ausentes)),
        )


# --------------------------------------------------------------------------- publicação atômica


def publicar(con: duckdb.DuckDBPyConnection, preparadas: list[Preparada]) -> None:
    """Substitui as tabelas Silver em uma única transação; falha faz rollback (seção 13)."""
    con.begin()
    try:
        db.criar_schema(con, SCHEMA_DESTINO)
        for p in preparadas:
            con.execute(
                f"CREATE OR REPLACE TABLE {_silver(p.destino)} AS SELECT * FROM {p.temporaria}"
            )
        con.commit()
    except Exception as exc:
        # a transação pode já ter sido abortada pelo próprio DuckDB
        with contextlib.suppress(duckdb.Error):
            con.rollback()
        raise ErroTransformacao(
            "publicação",
            f"{exc} — rollback executado: nenhuma tabela Silver foi alterada",
            destino=SCHEMA_DESTINO,
        ) from exc


# --------------------------------------------------------------------------- relatório


def _coletar_relatorio(con, preparadas):
    relatorio = []
    for p in preparadas:
        with _contexto("relatório", destino=_rotulo_silver(p.destino)):
            colunas = [
                nome
                for (nome,) in con.execute(
                    "SELECT column_name FROM duckdb_columns() WHERE database_name = "
                    "current_database() "
                    "AND schema_name = ? AND table_name = ? ORDER BY column_index",
                    [SCHEMA_DESTINO, p.destino],
                ).fetchall()
            ]
            contagens = con.execute(
                "SELECT COUNT(*), "
                + ", ".join(f"COUNT(*) - COUNT({_ident(c)})" for c in colunas)
                + f" FROM {_silver(p.destino)}"
            ).fetchall()[0]
        relatorio.append(
            {
                "tabela": _rotulo_silver(p.destino),
                "origem": p.origem,
                "antes_dedup": p.antes_dedup,
                "duplicatas": p.duplicatas,
                "gravados": contagens[0],
                "processados": p.antes_dedup,
                "nulos": dict(zip(colunas, contagens[1:], strict=False)),
            }
        )
    return relatorio


def _imprimir_relatorio(relatorio):
    largura = 44
    numeros = max([len(_fmt(r["gravados"])) for r in relatorio] + [12])

    def linha(rotulo, n, recuo=2):
        log.info(f"{' ' * recuo}{rotulo:<{largura - recuo}}{_fmt(n):>{numeros}}")

    for r in relatorio:
        log.info("")
        log.info(r["tabela"])
        log.info("-" * (largura + numeros))
        linha("Registros de origem", r["origem"])
        linha("Registros antes da deduplicação", r["antes_dedup"])
        linha("Duplicatas idênticas removidas", r["duplicatas"])
        linha("Registros gravados", r["gravados"])
        linha("Total de registros processados", r["processados"])
        log.info("  Valores nulos por coluna:")
        for coluna, n in r["nulos"].items():
            linha(coluna, n, recuo=4)
    total = sum(r["gravados"] for r in relatorio)
    log.info("")
    log.info("=" * (largura + numeros))
    log.info(f"{'TOTAL GRAVADO NAS SETE TABELAS':<{largura}}{_fmt(total):>{numeros}}")


# --------------------------------------------------------------------------- orquestração


def executar(con: duckdb.DuckDBPyConnection) -> list[dict]:
    """Prepara e valida as sete tabelas e só então as publica atomicamente."""
    with _contexto("verificação da Bronze"):
        verificar_bronze(con)
    preparadas = [preparar_tabela_sql(con, t) for t in TABELAS_SQL]
    preparadas += preparar_minhareceita(con)
    publicar(con, preparadas)
    return _coletar_relatorio(con, preparadas)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    configurar_logging()

    with execucao.registrada("transformacao") as registro:
        try:
            con = db.conectar()
        except duckdb.Error as exc:
            log.error(f"\nERRO DE TRANSFORMAÇÃO\n  Etapa:   conexão\n  Motivo:  {exc}")
            sys.exit(1)
        try:
            relatorio = executar(con)
        except ErroTransformacao as exc:
            log.error(f"\nERRO DE TRANSFORMAÇÃO\n{exc}")
            log.error("Nenhuma tabela Silver foi alterada.")
            sys.exit(1)
        finally:
            con.close()
        registro.tabelas = {r["tabela"]: r["gravados"] for r in relatorio}
        _imprimir_relatorio(relatorio)
