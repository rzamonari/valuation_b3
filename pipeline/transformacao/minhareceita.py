"""Minha Receita — contrato JSON e as quatro tabelas derivadas de payload_json
(seções 7.4 a 7.8)."""

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

import duckdb
import pyarrow as pa

from pipeline.db import _ident
from pipeline.transformacao.comum import (
    LIMITE_PRECISAO_DECIMAL,
    ErroTransformacao,
    Preparada,
    _bronze,
    _contexto,
    _deduplicar_e_validar,
    _rotulo_bronze,
    _rotulo_silver,
    _temporaria,
    _validar_colunas_bronze,
)

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

_FORMATO_DATA_JSON = re.compile(r"\d{4}-\d{2}-\d{2}")
_FORMATO_CNPJ = re.compile(r"\d{0,14}")


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


def preparar_minhareceita(con: duckdb.DuckDBPyConnection) -> list[Preparada]:
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
