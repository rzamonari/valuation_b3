"""Base comum da camada Silver: tipos, conversões, validações e conversão de tabelas Bronze.

Usado pelos módulos de cada fonte (b3, fundamentus, yfinance, minhareceita) e pela
orquestração em pipeline/transformacao/__init__.py, onde estão as decisões de implementação.
"""

from contextlib import contextmanager
from dataclasses import dataclass

import duckdb
import pyarrow as pa

from pipeline import db

SCHEMA_ORIGEM = "raw"
SCHEMA_DESTINO = "refined"
LIMITE_PRECISAO_DECIMAL = 38  # maior largura de DECIMAL aceita pelo DuckDB
AMOSTRA = 5  # chaves/registros exibidos em mensagens de erro

ORIENTACAO_BRONZE = "Execute a ingestão Bronze: uv run python -m pipeline.ingestao"


class ErroTransformacao(Exception):
    """Falha que interrompe a transformação sem publicar nenhuma tabela Silver."""

    def __init__(
        self, etapa, motivo, *, origem=None, destino=None, coluna=None, exemplo=None
    ):
        super().__init__(motivo)
        self.etapa = etapa
        self.motivo = motivo
        self.origem = origem
        self.destino = destino
        self.coluna = coluna
        self.exemplo = exemplo

    def __str__(self):
        campos = [
            ("Etapa", self.etapa),
            ("Origem", self.origem),
            ("Destino", self.destino),
            ("Coluna", self.coluna),
            ("Exemplo", self.exemplo),
            ("Motivo", self.motivo),
        ]
        return "\n".join(
            f"  {rotulo + ':':<9}{valor}" for rotulo, valor in campos if valor
        )


@dataclass(frozen=True)
class Conversao:
    descricao: str
    formato: str | None = (
        None  # regex (RE2) que todo valor não nulo deve casar por inteiro
    )
    expressao: str = "{v}"  # SQL que leva o texto validado ao tipo de destino
    decimal: bool = False  # DECIMAL(p,s) calculado sobre todos os valores
    ausente: str | None = None  # marcador exato que a fonte usa para "sem valor"


TEXTO = Conversao("VARCHAR")
DATA_BR = Conversao(
    "DATE (DD/MM/YYYY)", r"\d{2}/\d{2}/\d{4}", "CAST(strptime({v}, '%d/%m/%Y') AS DATE)"
)
NUMERO_BR = Conversao(
    "DECIMAL (notação brasileira)",
    r"-?\d{1,3}(\.\d{3})*(,\d+)?%?",
    decimal=True,
    ausente="-",
)
TIMESTAMP_TZ = Conversao(
    "TIMESTAMP WITH TIME ZONE",
    r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)?[+-]\d{2}:\d{2}",
    "CAST({v} AS TIMESTAMPTZ)",
)
DOUBLE = Conversao("DOUBLE", r"-?\d+(\.\d+)?([eE][+-]?\d+)?", "CAST({v} AS DOUBLE)")
BIGINT = Conversao("BIGINT", r"-?\d+", "CAST({v} AS BIGINT)")
# 7.8: até 14 dígitos, completados com zeros à esquerda; string vazia permanece vazia.
CNPJ = Conversao(
    "CNPJ (somente dígitos, no máximo 14)",
    r"\d{0,14}",
    "CASE WHEN {v} = '' THEN {v} ELSE lpad({v}, 14, '0') END",
)

# Texto canônico 'NNNN.DD': sem separador de milhar, ponto decimal e sem % (sem dividir por 100).
NORMALIZACAO_BR = "replace(replace(regexp_replace({v}, '%$', ''), '.', ''), ',', '.')"
# Só as quebras de linha e tabulações externas observadas em Dív.Líq/ Patrim.
LIMPEZA_EXTREMIDADES = r"regexp_replace({v}, '^[\n\t]+|[\n\t]+$', '', 'g')"


@dataclass(frozen=True)
class Coluna:
    origem: str
    destino: str
    conversao: Conversao = TEXTO
    limpeza: str | None = None  # SQL aplicado antes da validação de formato


@dataclass(frozen=True)
class TabelaSql:
    origem: str
    destino: str
    colunas: tuple
    chave: tuple


@dataclass(frozen=True)
class Preparada:
    """Tabela Silver já convertida, deduplicada e validada, aguardando publicação."""

    destino: str
    temporaria: str
    origem: int  # registros Bronze (ou elementos de array extraídos)
    antes_dedup: int
    duplicatas: int


# --------------------------------------------------------------------------- utilitários


def _bronze(tabela):
    return f"{db._ident(SCHEMA_ORIGEM)}.{db._ident(tabela)}"


def _silver(tabela):
    return f"{db._ident(SCHEMA_DESTINO)}.{db._ident(tabela)}"


def _rotulo_bronze(tabela):
    return f"{SCHEMA_ORIGEM}.{tabela}"


def _rotulo_silver(tabela):
    return f"{SCHEMA_DESTINO}.{tabela}"


def _temporaria(destino, sufixo):
    return f"temp.main.{db._ident(f'_silver_{destino}_{sufixo}')}"


def _fmt(n):
    return f"{n:,}".replace(",", ".")


@contextmanager
def _contexto(etapa, origem=None, destino=None, coluna=None):
    """Converte falhas do DuckDB/Arrow em ErroTransformacao com etapa, tabela e coluna."""
    try:
        yield
    except ErroTransformacao:
        raise
    except (duckdb.Error, pa.ArrowException) as exc:
        raise ErroTransformacao(
            etapa, str(exc), origem=origem, destino=destino, coluna=coluna
        ) from exc


def _contar(con, tabela):
    return con.execute(f"SELECT COUNT(*) FROM {tabela}").fetchall()[0][0]


def _registros(con, sql, parametros=None):
    cursor = con.execute(sql, parametros or [])
    nomes = [d[0] for d in cursor.description]
    return [dict(zip(nomes, linha, strict=True)) for linha in cursor.fetchall()]


def _formatar_registros(registros):
    return "\n" + "\n".join(f"    {r}" for r in registros)


def _validar_colunas_bronze(con, tabela, esperadas, destino):
    """Nenhuma coluna Bronze pode ser descartada em silêncio nem faltar ao mapeamento."""
    reais = [
        nome
        for (nome,) in con.execute(
            "SELECT column_name FROM duckdb_columns() WHERE database_name = current_database() "
            "AND schema_name = ? AND table_name = ? ORDER BY column_index",
            [SCHEMA_ORIGEM, tabela],
        ).fetchall()
    ]
    faltando = [c for c in esperadas if c not in reais]
    sobrando = [c for c in reais if c not in esperadas]
    if faltando or sobrando:
        partes = []
        if faltando:
            partes.append(f"colunas mapeadas ausentes na Bronze: {faltando}")
        if sobrando:
            partes.append(f"colunas Bronze sem mapeamento na Silver: {sobrando}")
        raise ErroTransformacao(
            "validação de estrutura",
            "; ".join(partes),
            origem=_rotulo_bronze(tabela),
            destino=_rotulo_silver(destino),
            coluna=", ".join(faltando + sobrando),
        )


# --------------------------------------------------------------------------- deduplicação e chaves


def _deduplicar_e_validar(con, destino, staging, chave, origem):
    """Remove duplicatas integralmente idênticas e valida a chave lógica (seção 9)."""
    rotulo = _rotulo_silver(destino)
    final = _temporaria(destino, "final")
    chave_sql = ", ".join(db._ident(c) for c in chave)
    with _contexto("deduplicação", destino=rotulo):
        antes = _contar(con, staging)
        con.execute(
            f"CREATE OR REPLACE TEMP TABLE {final} AS "
            f"SELECT DISTINCT * FROM {staging} ORDER BY ALL"
        )
        con.execute(f"DROP TABLE {staging}")
        depois = _contar(con, final)

    with _contexto("validação de chave", destino=rotulo, coluna=", ".join(chave)):
        filtro_nulo = " OR ".join(f"{db._ident(c)} IS NULL" for c in chave)
        n_nulas = con.execute(
            f"SELECT COUNT(*) FROM {final} WHERE {filtro_nulo}"
        ).fetchall()[0][0]
        nulas = _registros(
            con, f"SELECT * FROM {final} WHERE {filtro_nulo} LIMIT {AMOSTRA}"
        )
    if n_nulas:
        raise ErroTransformacao(
            "validação de chave",
            f"{_fmt(n_nulas)} registro(s) com chave lógica nula ({', '.join(chave)})",
            destino=rotulo,
            coluna=", ".join(chave),
            exemplo=_formatar_registros(nulas),
        )

    with _contexto("validação de chave", destino=rotulo, coluna=", ".join(chave)):
        repetidas = f"SELECT {chave_sql} FROM {final} GROUP BY ALL HAVING COUNT(*) > 1"
        n_conflitos = con.execute(f"SELECT COUNT(*) FROM ({repetidas})").fetchall()[0][
            0
        ]
        conflitos = _registros(
            con,
            f"SELECT f.* FROM {final} f SEMI JOIN "
            f"({repetidas} ORDER BY ALL LIMIT {AMOSTRA}) r USING ({chave_sql}) "
            f"ORDER BY ALL",
        )
    if n_conflitos:
        raise ErroTransformacao(
            "validação de chave",
            f"{_fmt(n_conflitos)} chave(s) ({', '.join(chave)}) com conteúdos divergentes; "
            "nenhum registro foi escolhido arbitrariamente",
            destino=rotulo,
            coluna=", ".join(chave),
            exemplo=_formatar_registros(conflitos),
        )

    return Preparada(destino, final, origem, antes, antes - depois)


# --------------------------------------------------------------------------- tabelas SQL (B3, Fundamentus, yfinance)


def _tipo_decimal(con, tabela, coluna, normalizado):
    """Menor DECIMAL(p,s) que representa exatamente todos os valores da coluna (7.2)."""
    with _contexto(
        "cálculo de precisão DECIMAL",
        _rotulo_bronze(tabela.origem),
        _rotulo_silver(tabela.destino),
        coluna.origem,
    ):
        inteiros, escala = con.execute(
            f"""
            SELECT
                COALESCE(MAX(length(ltrim(split_part(ltrim(n, '-'), '.', 1), '0'))), 0),
                COALESCE(MAX(length(split_part(n, '.', 2))), 0)
            FROM (SELECT {normalizado} AS n FROM {_bronze(tabela.origem)})
            WHERE n IS NOT NULL
            """
        ).fetchall()[0]
    precisao = max(inteiros, 1) + escala
    if precisao > LIMITE_PRECISAO_DECIMAL:
        raise ErroTransformacao(
            "cálculo de precisão DECIMAL",
            f"precisão necessária DECIMAL({precisao},{escala}) ultrapassa o limite do DuckDB "
            f"({LIMITE_PRECISAO_DECIMAL} dígitos)",
            origem=_rotulo_bronze(tabela.origem),
            destino=_rotulo_silver(tabela.destino),
            coluna=coluna.origem,
        )
    return f"DECIMAL({precisao}, {escala})"


def _expressao_coluna(con, tabela, coluna):
    """Valida o formato de todos os valores e devolve a expressão SQL de conversão estrita."""
    origem_sql = _bronze(tabela.origem)
    bruto = db._ident(coluna.origem)
    valor = coluna.limpeza.replace("{v}", bruto) if coluna.limpeza else bruto
    conversao = coluna.conversao
    if conversao.ausente is not None:
        valor = f"NULLIF({valor}, '{conversao.ausente}')"
    contexto = (
        _rotulo_bronze(tabela.origem),
        _rotulo_silver(tabela.destino),
        coluna.origem,
    )
    if conversao.formato is None:
        return valor

    with _contexto("validação de formato", *contexto):
        invalidos = con.execute(
            f"SELECT {bruto} FROM {origem_sql} "
            f"WHERE {valor} IS NOT NULL AND NOT regexp_full_match({valor}, ?) LIMIT 1",
            [conversao.formato],
        ).fetchall()
    if invalidos:
        raise ErroTransformacao(
            "validação de formato",
            f"valor incompatível com o tipo de destino {conversao.descricao}",
            origem=contexto[0],
            destino=contexto[1],
            coluna=coluna.origem,
            exemplo=repr(invalidos[0][0]),
        )

    if conversao.decimal:
        normalizado = NORMALIZACAO_BR.replace("{v}", valor)
        expressao = (
            f"CAST({normalizado} AS {_tipo_decimal(con, tabela, coluna, normalizado)})"
        )
    else:
        expressao = conversao.expressao.replace("{v}", valor)

    # A conversão é executada por coluna para que a falha identifique a coluna envolvida.
    with _contexto("conversão de tipo", *contexto):
        con.execute(f"SELECT MAX({expressao}) FROM {origem_sql}").fetchall()
    return expressao


def preparar_tabela_sql(con: duckdb.DuckDBPyConnection, tabela: TabelaSql) -> Preparada:
    rotulo_origem = _rotulo_bronze(tabela.origem)
    with _contexto("leitura", rotulo_origem, _rotulo_silver(tabela.destino)):
        _validar_colunas_bronze(
            con, tabela.origem, [c.origem for c in tabela.colunas], tabela.destino
        )
        origem = _contar(con, _bronze(tabela.origem))

    selecao = ", ".join(
        f"{_expressao_coluna(con, tabela, c)} AS {db._ident(c.destino)}"
        for c in tabela.colunas
    )
    staging = _temporaria(tabela.destino, "staging")
    with _contexto("conversão de tipo", rotulo_origem, _rotulo_silver(tabela.destino)):
        con.execute(
            f"CREATE OR REPLACE TEMP TABLE {staging} AS "
            f"SELECT {selecao} FROM {_bronze(tabela.origem)}"
        )
    return _deduplicar_e_validar(con, tabela.destino, staging, tabela.chave, origem)
