r"""Transformação da camada Refined (Silver): B3, Fundamentus, yfinance e Minha Receita.

Execução: uv run python -m pipeline.transformacao

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
import json
import re
import sys
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

import duckdb
import pyarrow as pa

from pipeline import db
from pipeline.db import _ident

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


TABELAS_SQL = (
    TabelaSql(
        "b3_empresas",
        "b3_empresas",
        (
            Coluna("codeCVM", "codigo_cvm"),
            Coluna("issuingCompany", "empresa_emissora"),
            Coluna("companyName", "razao_social"),
            Coluna("tradingName", "nome_pregao"),
            Coluna("cnpj", "cnpj", CNPJ),
            Coluna("marketIndicator", "indicador_mercado"),
            Coluna("typeBDR", "tipo_bdr"),
            Coluna("dateListing", "data_listagem", DATA_BR),
            Coluna("status", "situacao"),
            Coluna("segment", "segmento"),
            Coluna("segmentEng", "segmento_ingles"),
            Coluna("type", "tipo_empresa"),
            Coluna("market", "mercado"),
            Coluna("_timestamp_ingestao", "_timestamp_ingestao"),
            Coluna("_source_origin", "_source_origin"),
        ),
        ("codigo_cvm",),
    ),
    TabelaSql(
        "fundamentus_acoes",
        "fundamentus_acoes",
        (
            Coluna("Papel", "ticker"),
            Coluna("Cotação", "cotacao", NUMERO_BR),
            Coluna("P/L", "preco_lucro", NUMERO_BR),
            Coluna("P/VP", "preco_valor_patrimonial", NUMERO_BR),
            Coluna("PSR", "preco_vendas", NUMERO_BR),
            Coluna("Div.Yield", "dividend_yield", NUMERO_BR),
            Coluna("P/Ativo", "preco_ativo", NUMERO_BR),
            Coluna("P/Cap.Giro", "preco_capital_giro", NUMERO_BR),
            Coluna("P/EBIT", "preco_ebit", NUMERO_BR),
            Coluna("P/Ativ Circ.Liq", "preco_ativo_circulante_liquido", NUMERO_BR),
            Coluna("EV/EBIT", "enterprise_value_ebit", NUMERO_BR),
            Coluna("EV/EBITDA", "enterprise_value_ebitda", NUMERO_BR),
            Coluna("Mrg Bruta", "margem_bruta", NUMERO_BR),
            Coluna("Mrg Ebit", "margem_ebit", NUMERO_BR),
            Coluna("Mrg. Líq.", "margem_liquida", NUMERO_BR),
            Coluna("Liq. Corr.", "liquidez_corrente", NUMERO_BR),
            Coluna("ROIC", "roic", NUMERO_BR),
            Coluna("ROE", "roe", NUMERO_BR),
            Coluna("Liq.2meses", "liquidez_2_meses", NUMERO_BR),
            Coluna("Patrim. Líq", "patrimonio_liquido", NUMERO_BR),
            Coluna(
                "Dív.Líq/ Patrim.",
                "divida_liquida_patrimonio",
                NUMERO_BR,
                LIMPEZA_EXTREMIDADES,
            ),
            Coluna("Cresc. Rec.5a", "crescimento_receita_5_anos", NUMERO_BR),
            Coluna("_timestamp_ingestao", "_timestamp_ingestao"),
            Coluna("_source_origin", "_source_origin"),
        ),
        ("ticker",),
    ),
    TabelaSql(
        "yfinance_cotacoes",
        "yfinance_cotacoes",
        (
            Coluna("ticker", "ticker"),
            Coluna("Date", "data", TIMESTAMP_TZ),
            Coluna("Open", "abertura", DOUBLE),
            Coluna("High", "maxima", DOUBLE),
            Coluna("Low", "minima", DOUBLE),
            Coluna("Close", "fechamento", DOUBLE),
            Coluna("Adj Close", "fechamento_ajustado", DOUBLE),
            Coluna("Volume", "volume", BIGINT),
            Coluna("Dividends", "dividendos", DOUBLE),
            Coluna("Stock Splits", "desdobramentos", DOUBLE),
            Coluna("_source_origin", "_source_origin"),
            Coluna("_timestamp_ingestao", "_timestamp_ingestao"),
            Coluna("Capital Gains", "ganhos_capital", DOUBLE),
        ),
        ("ticker", "data"),
    ),
)

# --------------------------------------------------------------------------- contrato Minha Receita

TEXTO_JSON = "texto"
INTEIRO_JSON = "inteiro"
DECIMAL_JSON = "decimal"
BOOLEANO_JSON = "booleano"
DATA_JSON = "data"
CNPJ_JSON = "cnpj"

TIPOS_ARROW = {
    TEXTO_JSON: pa.string(),
    CNPJ_JSON: pa.string(),
    INTEIRO_JSON: pa.int64(),
    BOOLEANO_JSON: pa.bool_(),
    DATA_JSON: pa.date32(),
}

ORIGEM_MINHARECEITA = "minhareceita_empresas"
COLUNAS_BRONZE_MINHARECEITA = (
    "cnpj",
    "payload_json",
    "_timestamp_ingestao",
    "_source_origin",
)
METADADOS = ("_timestamp_ingestao", "_source_origin")

ESCALARES_EMPRESA = {
    "cnpj": CNPJ_JSON,
    "uf": TEXTO_JSON,
    "cep": TEXTO_JSON,
    "pais": TEXTO_JSON,
    "email": TEXTO_JSON,
    "porte": TEXTO_JSON,
    "bairro": TEXTO_JSON,
    "numero": TEXTO_JSON,
    "ddd_fax": TEXTO_JSON,
    "municipio": TEXTO_JSON,
    "logradouro": TEXTO_JSON,
    "cnae_fiscal": INTEIRO_JSON,
    "codigo_pais": INTEIRO_JSON,
    "complemento": TEXTO_JSON,
    "codigo_porte": INTEIRO_JSON,
    "razao_social": TEXTO_JSON,
    "nome_fantasia": TEXTO_JSON,
    "capital_social": DECIMAL_JSON,
    "ddd_telefone_1": TEXTO_JSON,
    "ddd_telefone_2": TEXTO_JSON,
    "opcao_pelo_mei": BOOLEANO_JSON,
    "codigo_municipio": INTEIRO_JSON,
    "natureza_juridica": TEXTO_JSON,
    "situacao_especial": TEXTO_JSON,
    "opcao_pelo_simples": BOOLEANO_JSON,
    "situacao_cadastral": INTEIRO_JSON,
    "data_opcao_pelo_mei": DATA_JSON,
    "data_exclusao_do_mei": DATA_JSON,
    "cnae_fiscal_descricao": TEXTO_JSON,
    "codigo_municipio_ibge": INTEIRO_JSON,
    "data_inicio_atividade": DATA_JSON,
    "data_situacao_especial": DATA_JSON,
    "data_opcao_pelo_simples": DATA_JSON,
    "data_situacao_cadastral": DATA_JSON,
    "nome_cidade_no_exterior": TEXTO_JSON,
    "codigo_natureza_juridica": INTEIRO_JSON,
    "data_exclusao_do_simples": DATA_JSON,
    "motivo_situacao_cadastral": INTEIRO_JSON,
    "ente_federativo_responsavel": TEXTO_JSON,
    "identificador_matriz_filial": INTEIRO_JSON,
    "qualificacao_do_responsavel": INTEIRO_JSON,
    "descricao_situacao_cadastral": TEXTO_JSON,
    "descricao_tipo_de_logradouro": TEXTO_JSON,
    "descricao_motivo_situacao_cadastral": TEXTO_JSON,
    "descricao_identificador_matriz_filial": TEXTO_JSON,
}


@dataclass(frozen=True)
class ArrayJson:
    propriedade: str
    destino: str
    sequencia: str | None  # coluna com a posição original (1, 2, ...) no array
    propriedades: dict  # propriedade JSON -> (coluna Silver, tipo)
    chave: tuple


ARRAYS_EMPRESA = (
    ArrayJson(
        "qsa",
        "minhareceita_qsa",
        "sequencia_socio",
        {
            "pais": ("pais", TEXTO_JSON),
            "nome_socio": ("nome_socio", TEXTO_JSON),
            "codigo_pais": ("codigo_pais", INTEIRO_JSON),
            "faixa_etaria": ("faixa_etaria", TEXTO_JSON),
            "cnpj_cpf_do_socio": ("cnpj_cpf_do_socio", TEXTO_JSON),
            "qualificacao_socio": ("qualificacao_socio", TEXTO_JSON),
            "codigo_faixa_etaria": ("codigo_faixa_etaria", INTEIRO_JSON),
            "data_entrada_sociedade": ("data_entrada_sociedade", DATA_JSON),
            "identificador_de_socio": ("identificador_de_socio", INTEIRO_JSON),
            "cpf_representante_legal": ("cpf_representante_legal", TEXTO_JSON),
            "nome_representante_legal": ("nome_representante_legal", TEXTO_JSON),
            "codigo_qualificacao_socio": ("codigo_qualificacao_socio", INTEIRO_JSON),
            "qualificacao_representante_legal": (
                "qualificacao_representante_legal",
                TEXTO_JSON,
            ),
            "codigo_qualificacao_representante_legal": (
                "codigo_qualificacao_representante_legal",
                INTEIRO_JSON,
            ),
        },
        ("cnpj", "sequencia_socio"),
    ),
    ArrayJson(
        "regime_tributario",
        "minhareceita_regime_tributario",
        "sequencia_regime",
        {
            "ano": ("ano", INTEIRO_JSON),
            "cnpj_da_scp": ("cnpj_da_scp", CNPJ_JSON),
            "forma_de_tributacao": ("forma_de_tributacao", TEXTO_JSON),
            "quantidade_de_escrituracoes": (
                "quantidade_de_escrituracoes",
                INTEIRO_JSON,
            ),
        },
        ("cnpj", "sequencia_regime"),
    ),
    ArrayJson(
        "cnaes_secundarios",
        "minhareceita_cnaes_secundarios",
        None,
        {
            "codigo": ("codigo_cnae", INTEIRO_JSON),
            "descricao": ("descricao", TEXTO_JSON),
        },
        ("cnpj", "codigo_cnae"),
    ),
)
CHAVE_EMPRESA = ("cnpj",)

TABELAS_BRONZE = tuple(t.origem for t in TABELAS_SQL) + (ORIGEM_MINHARECEITA,)

_FORMATO_DATA_JSON = re.compile(r"\d{4}-\d{2}-\d{2}")
_FORMATO_CNPJ = re.compile(r"\d{0,14}")


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
    return f"{_ident(SCHEMA_ORIGEM)}.{_ident(tabela)}"


def _silver(tabela):
    return f"{_ident(SCHEMA_DESTINO)}.{_ident(tabela)}"


def _rotulo_bronze(tabela):
    return f"{SCHEMA_ORIGEM}.{tabela}"


def _rotulo_silver(tabela):
    return f"{SCHEMA_DESTINO}.{tabela}"


def _temporaria(destino, sufixo):
    return f"temp.main.{_ident(f'_silver_{destino}_{sufixo}')}"


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
    return [dict(zip(nomes, linha, strict=False)) for linha in cursor.fetchall()]


def _formatar_registros(registros):
    return "\n" + "\n".join(f"    {r}" for r in registros)


# --------------------------------------------------------------------------- verificação Bronze


def verificar_bronze(con):
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
    chave_sql = ", ".join(_ident(c) for c in chave)
    with _contexto("deduplicação", destino=rotulo):
        antes = _contar(con, staging)
        con.execute(
            f"CREATE OR REPLACE TEMP TABLE {final} AS "
            f"SELECT DISTINCT * FROM {staging} ORDER BY ALL"
        )
        con.execute(f"DROP TABLE {staging}")
        depois = _contar(con, final)

    with _contexto("validação de chave", destino=rotulo, coluna=", ".join(chave)):
        filtro_nulo = " OR ".join(f"{_ident(c)} IS NULL" for c in chave)
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


# ------------------------------------------------- tabelas SQL (B3, Fundamentus, yfinance)


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
    bruto = _ident(coluna.origem)
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


def preparar_tabela_sql(con, tabela):
    rotulo_origem = _rotulo_bronze(tabela.origem)
    with _contexto("leitura", rotulo_origem, _rotulo_silver(tabela.destino)):
        _validar_colunas_bronze(
            con, tabela.origem, [c.origem for c in tabela.colunas], tabela.destino
        )
        origem = _contar(con, _bronze(tabela.origem))

    selecao = ", ".join(
        f"{_expressao_coluna(con, tabela, c)} AS {_ident(c.destino)}"
        for c in tabela.colunas
    )
    staging = _temporaria(tabela.destino, "staging")
    with _contexto("conversão de tipo", rotulo_origem, _rotulo_silver(tabela.destino)):
        con.execute(
            f"CREATE OR REPLACE TEMP TABLE {staging} AS "
            f"SELECT {selecao} FROM {_bronze(tabela.origem)}"
        )
    return _deduplicar_e_validar(con, tabela.destino, staging, tabela.chave, origem)


# --------------------------------------------------------------------------- Minha Receita (JSON)


def _erro_json(motivo, destino, coluna, exemplo):
    return ErroTransformacao(
        "validação estrutural JSON",
        motivo,
        origem=f"{_rotulo_bronze(ORIGEM_MINHARECEITA)}.payload_json",
        destino=_rotulo_silver(destino),
        coluna=coluna,
        exemplo=exemplo,
    )


def _decodificar(cnpj, payload):
    def sem_duplicatas(pares):
        objeto = {}
        for chave, valor in pares:
            if chave in objeto:
                raise ValueError(f"propriedade duplicada no objeto JSON: {chave!r}")
            objeto[chave] = valor
        return objeto

    def rejeitar_constante(nome):
        raise ValueError(f"constante numérica não suportada: {nome}")

    if payload is None:
        raise _erro_json(
            "payload_json nulo", ORIGEM_MINHARECEITA, "payload_json", f"cnpj {cnpj}"
        )
    try:
        # Decimal mantém exatamente a representação dos números não inteiros.
        return json.loads(
            payload,
            parse_float=Decimal,
            parse_constant=rejeitar_constante,
            object_pairs_hook=sem_duplicatas,
        )
    except ValueError as exc:
        raise _erro_json(
            f"JSON inválido: {exc}", ORIGEM_MINHARECEITA, "payload_json", f"cnpj {cnpj}"
        ) from exc


def _validar_objeto(objeto, esperadas, destino, caminho, cnpj):
    if not isinstance(objeto, dict):
        raise _erro_json(
            f"esperado objeto JSON, encontrado {type(objeto).__name__}",
            destino,
            caminho,
            f"{objeto!r} (cnpj {cnpj})",
        )
    faltando = [p for p in esperadas if p not in objeto]
    if faltando:
        raise _erro_json(
            f"propriedade(s) obrigatória(s) ausente(s): {faltando}",
            destino,
            caminho,
            f"cnpj {cnpj}",
        )
    sobrando = [p for p in objeto if p not in esperadas]
    if sobrando:
        raise _erro_json(
            f"propriedade(s) não prevista(s) no contrato da Silver: {sobrando}",
            destino,
            caminho,
            f"cnpj {cnpj}",
        )


def _valor(valor, tipo, destino, coluna, cnpj):
    """Valida o tipo JSON e devolve o valor Python correspondente; nulo continua nulo."""
    if valor is None:
        return None
    if tipo == TEXTO_JSON and isinstance(valor, str):
        return valor
    if tipo == CNPJ_JSON and isinstance(valor, str):
        if not _FORMATO_CNPJ.fullmatch(valor):
            raise _erro_json(
                "CNPJ deve conter somente dígitos, no máximo 14",
                destino,
                coluna,
                f"{valor!r} (cnpj {cnpj})",
            )
        return valor.zfill(14) if valor else valor  # 7.8: string vazia permanece vazia
    if tipo == INTEIRO_JSON and type(valor) is int:
        return valor
    if tipo == DECIMAL_JSON and type(valor) in (int, Decimal):
        return Decimal(valor)
    if tipo == BOOLEANO_JSON and type(valor) is bool:
        return valor
    if tipo == DATA_JSON and isinstance(valor, str):
        try:
            if not _FORMATO_DATA_JSON.fullmatch(valor):
                raise ValueError("formato diferente de YYYY-MM-DD")
            return datetime.strptime(valor, "%Y-%m-%d").date()
        except ValueError as exc:
            raise _erro_json(
                f"data inválida: {exc}", destino, coluna, f"{valor!r} (cnpj {cnpj})"
            ) from exc
    raise _erro_json(
        f"tipo JSON {type(valor).__name__} incompatível com o tipo esperado ({tipo})",
        destino,
        coluna,
        f"{valor!r} (cnpj {cnpj})",
    )


def _precisao_escala(valores):
    inteiros = escala = 0
    for valor in valores:
        if valor is None:
            continue
        _, digitos, expoente = valor.as_tuple()
        escala = max(escala, -expoente)
        inteiros = max(inteiros, len(digitos) + expoente)
    return max(inteiros, 1) + escala, escala


def _tabela_arrow(destino, colunas, linhas):
    """colunas: [(nome, tipo JSON)]; DECIMAL recebe precisão calculada sobre todos os valores."""
    arrays, campos = [], []
    for nome, tipo in colunas:
        valores = [linha[nome] for linha in linhas]
        if tipo == DECIMAL_JSON:
            precisao, escala = _precisao_escala(valores)
            if precisao > LIMITE_PRECISAO_DECIMAL:
                raise ErroTransformacao(
                    "cálculo de precisão DECIMAL",
                    f"precisão necessária DECIMAL({precisao},{escala}) ultrapassa o limite "
                    f"do DuckDB ({LIMITE_PRECISAO_DECIMAL} dígitos)",
                    origem=f"{_rotulo_bronze(ORIGEM_MINHARECEITA)}.payload_json",
                    destino=_rotulo_silver(destino),
                    coluna=nome,
                )
            tipo_arrow = pa.decimal128(precisao, escala)
        else:
            tipo_arrow = TIPOS_ARROW[tipo]
        with _contexto(
            "conversão de tipo",
            _rotulo_bronze(ORIGEM_MINHARECEITA),
            _rotulo_silver(destino),
            nome,
        ):
            arrays.append(pa.array(valores, type=tipo_arrow))
        campos.append(pa.field(nome, tipo_arrow))
    return pa.Table.from_arrays(arrays, schema=pa.schema(campos))


def _carregar_staging(con, destino, tabela_arrow):
    staging = _temporaria(destino, "staging")
    visao = f"_arrow_{uuid.uuid4().hex}"
    with _contexto("conversão de tipo", destino=_rotulo_silver(destino)):
        con.register(visao, tabela_arrow)
        try:
            con.execute(
                f"CREATE OR REPLACE TEMP TABLE {staging} AS "
                f"SELECT * FROM {_ident(visao)}"
            )
        finally:
            con.unregister(visao)
    return staging


def preparar_minhareceita(con):
    """Valida o contrato JSON em todos os registros e prepara as quatro tabelas da Minha Receita."""
    rotulo = _rotulo_bronze(ORIGEM_MINHARECEITA)
    with _contexto("leitura", rotulo, _rotulo_silver(ORIGEM_MINHARECEITA)):
        _validar_colunas_bronze(
            con, ORIGEM_MINHARECEITA, COLUNAS_BRONZE_MINHARECEITA, ORIGEM_MINHARECEITA
        )
        linhas_bronze = con.execute(
            f"SELECT cnpj, payload_json, _timestamp_ingestao, _source_origin "
            f"FROM {_bronze(ORIGEM_MINHARECEITA)} ORDER BY cnpj"
        ).fetchall()

    esperadas_empresa = list(ESCALARES_EMPRESA) + [
        a.propriedade for a in ARRAYS_EMPRESA
    ]
    empresas = []
    derivadas = {a.destino: [] for a in ARRAYS_EMPRESA}
    for cnpj, payload, timestamp, origem in linhas_bronze:
        dados = _decodificar(cnpj, payload)
        _validar_objeto(
            dados, esperadas_empresa, ORIGEM_MINHARECEITA, "payload_json", cnpj
        )
        metadados = {"_timestamp_ingestao": timestamp, "_source_origin": origem}
        empresa = {
            p: _valor(dados[p], tipo, ORIGEM_MINHARECEITA, p, cnpj)
            for p, tipo in ESCALARES_EMPRESA.items()
        }
        # A correspondência é verificada entre os valores já padronizados com 14 dígitos (7.8).
        cnpj_bronze = _valor(
            cnpj, CNPJ_JSON, ORIGEM_MINHARECEITA, "cnpj (linha Bronze)", cnpj
        )
        if empresa["cnpj"] != cnpj_bronze:
            raise _erro_json(
                "CNPJ da linha Bronze diverge da propriedade cnpj do JSON",
                ORIGEM_MINHARECEITA,
                "cnpj",
                f"linha Bronze {cnpj!r} x JSON {dados['cnpj']!r}",
            )
        empresas.append(empresa | metadados)

        for array in ARRAYS_EMPRESA:
            itens = dados[array.propriedade]
            if itens is None:  # array nulo não gera linhas (7.7)
                continue
            if not isinstance(itens, list):
                raise _erro_json(
                    f"esperado array JSON, encontrado {type(itens).__name__}",
                    array.destino,
                    array.propriedade,
                    f"{itens!r} (cnpj {cnpj})",
                )
            for posicao, item in enumerate(itens, start=1):
                caminho = f"{array.propriedade}[{posicao}]"
                _validar_objeto(
                    item, list(array.propriedades), array.destino, caminho, cnpj
                )
                linha = {"cnpj": empresa["cnpj"]}
                if array.sequencia:
                    linha[array.sequencia] = posicao
                for propriedade, (coluna, tipo) in array.propriedades.items():
                    linha[coluna] = _valor(
                        item[propriedade],
                        tipo,
                        array.destino,
                        f"{caminho}.{propriedade}",
                        cnpj,
                    )
                derivadas[array.destino].append(linha | metadados)

    preparadas = []
    colunas_empresa = list(ESCALARES_EMPRESA.items()) + [
        (m, TEXTO_JSON) for m in METADADOS
    ]
    staging = _carregar_staging(
        con,
        ORIGEM_MINHARECEITA,
        _tabela_arrow(ORIGEM_MINHARECEITA, colunas_empresa, empresas),
    )
    preparadas.append(
        _deduplicar_e_validar(
            con, ORIGEM_MINHARECEITA, staging, CHAVE_EMPRESA, len(linhas_bronze)
        )
    )

    for array in ARRAYS_EMPRESA:
        linhas = derivadas[array.destino]
        colunas = (
            [("cnpj", TEXTO_JSON)]
            + ([(array.sequencia, INTEIRO_JSON)] if array.sequencia else [])
            + list(array.propriedades.values())
            + [(m, TEXTO_JSON) for m in METADADOS]
        )
        staging = _carregar_staging(
            con, array.destino, _tabela_arrow(array.destino, colunas, linhas)
        )
        preparadas.append(
            _deduplicar_e_validar(con, array.destino, staging, array.chave, len(linhas))
        )
    return preparadas


# --------------------------------------------------------------------------- publicação atômica


def publicar(con, preparadas):
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
        print(f"{' ' * recuo}{rotulo:<{largura - recuo}}{_fmt(n):>{numeros}}")

    for r in relatorio:
        print()
        print(r["tabela"])
        print("-" * (largura + numeros))
        linha("Registros de origem", r["origem"])
        linha("Registros antes da deduplicação", r["antes_dedup"])
        linha("Duplicatas idênticas removidas", r["duplicatas"])
        linha("Registros gravados", r["gravados"])
        linha("Total de registros processados", r["processados"])
        print("  Valores nulos por coluna:")
        for coluna, n in r["nulos"].items():
            linha(coluna, n, recuo=4)
    total = sum(r["gravados"] for r in relatorio)
    print()
    print("=" * (largura + numeros))
    print(f"{'TOTAL GRAVADO NAS SETE TABELAS':<{largura}}{_fmt(total):>{numeros}}")


# --------------------------------------------------------------------------- orquestração


def executar(con):
    """Prepara e valida as sete tabelas e só então as publica atomicamente."""
    with _contexto("verificação da Bronze"):
        verificar_bronze(con)
    preparadas = [preparar_tabela_sql(con, t) for t in TABELAS_SQL]
    preparadas += preparar_minhareceita(con)
    publicar(con, preparadas)
    return _coletar_relatorio(con, preparadas)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    try:
        con = db.conectar()
    except duckdb.Error as exc:
        print(
            f"\nERRO DE TRANSFORMAÇÃO\n  Etapa:   conexão\n  Motivo:  {exc}",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        relatorio = executar(con)
    except ErroTransformacao as exc:
        print(f"\nERRO DE TRANSFORMAÇÃO\n{exc}", file=sys.stderr)
        print("Nenhuma tabela Silver foi alterada.", file=sys.stderr)
        sys.exit(1)
    finally:
        con.close()
    _imprimir_relatorio(relatorio)


if __name__ == "__main__":
    main()
