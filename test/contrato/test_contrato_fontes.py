"""Testes de contrato das fontes: uma chamada real e pequena por fonte, contra o formato que a
ingestão e a Silver esperam.

Execução: uv run pytest test/contrato -m contrato --no-cov
(fora do pytest padrão: addopts traz -m "not contrato"; o workflow contrato-fontes.yml roda
toda semana e abre uma issue quando algum falha).

# DECISÕES

1. O contrato é o da própria Silver: colunas de pipeline/transformacao/{b3,fundamentus,yfinance}
   e propriedades de minhareceita.ESCALARES_EMPRESA/ARRAYS_EMPRESA, com os formatos de cada
   Conversao. Coluna a mais também quebra a Silver (colunas Bronze sem mapeamento), por isso é
   reportada como mudança, não ignorada.
2. Cada teste junta todas as diferenças da fonte e falha uma vez, com a mensagem
   "[<fonte>] <o que mudou>": é o texto que vai para a issue automática.
3. Fonte fora do ar ou HTTP de erro também falha ("indisponível"): o aviso vale do mesmo jeito,
   e a mensagem separa mudança de formato de indisponibilidade.
4. Minha Receita: as mensagens citam só nomes de propriedade e tipos JSON, nunca valores (o QSA
   traz nomes de pessoas, e a issue é pública).
"""

import json
import math
import re

import pytest
import yfinance as yf

from pipeline import ingestao as ing
from pipeline.transformacao import b3, fundamentus, minhareceita, yfinance
from pipeline.transformacao.comum import NUMERO_BR

pytestmark = pytest.mark.contrato

METADADOS = {"_timestamp_ingestao", "_source_origin"}
PAGINA = 20  # registros por página na chamada de contrato da B3
CODIGO_CVM_PETROBRAS = "9512"
CNPJ_PETROBRAS = "33000167000101"
TICKERS_YAHOO = ["PETR4", "VALE3"]
# Só aparece quando algum ticker do lote tem ganho de capital (fundos); ação comum não traz.
OPCIONAIS_YAHOO = {"Capital Gains"}
MINIMO_FUNDAMENTUS = 500  # linhas da tabela (998 em 11/2026)
EXEMPLOS = 3


def falhar(fonte, problemas):
    if problemas:
        pytest.fail(f"[{fonte}] " + "; ".join(problemas), pytrace=False)


def _obter(fonte, operacao):
    try:
        return operacao()
    except Exception as exc:  # noqa: BLE001 — qualquer falha de rede vira "indisponível"
        pytest.fail(
            f"[{fonte}] indisponível: {type(exc).__name__}: {exc}", pytrace=False
        )


def colunas_esperadas(tabela, ignorar=()):
    return [
        c.origem for c in tabela.colunas if c.origem not in METADADOS | set(ignorar)
    ]


def diferenca_de_colunas(esperadas, recebidas, opcionais=()):
    faltando = [c for c in esperadas if c not in recebidas and c not in opcionais]
    sobrando = [c for c in recebidas if c not in esperadas]
    problemas = []
    if faltando:
        problemas.append(f"campos obrigatórios ausentes: {faltando}")
    if sobrando:
        problemas.append(f"campos novos, sem mapeamento na Silver: {sobrando}")
    return problemas


def formatos_invalidos(tabela, linhas, limpar=None):
    """Valores fora do formato da Conversao de cada coluna (o mesmo que a Silver exige)."""
    problemas = []
    for coluna in tabela.colunas:
        formato = coluna.conversao.formato
        if formato is None or coluna.origem in METADADOS:
            continue
        ruins = []
        for linha in linhas:
            valor = linha.get(coluna.origem)
            if valor is None:
                continue
            if not isinstance(valor, str):
                ruins.append(f"{type(valor).__name__} {valor!r}")
                continue
            texto = limpar(valor) if limpar else valor
            if texto == coluna.conversao.ausente:
                continue
            if not re.fullmatch(formato, texto):
                ruins.append(repr(valor))
        if ruins:
            problemas.append(
                f"{coluna.origem}: {len(ruins)} valor(es) fora do formato "
                f"{coluna.conversao.descricao} (ex.: {', '.join(ruins[:EXEMPLOS])})"
            )
    return problemas


# --------------------------------------------------------------------------- B3


def _pagina_b3(numero):
    url = ing._b3_url(
        "GetInitialCompanies",
        {"language": "pt-br", "pageNumber": numero, "pageSize": PAGINA},
    )
    return _obter("B3", lambda: ing._com_retry(lambda: ing._get(url).json(), "B3"))


def test_b3_listagem_paginada_com_os_campos_da_silver():
    primeira, segunda = _pagina_b3(1), _pagina_b3(2)
    problemas = []
    for chave in ("page", "results"):
        if chave not in primeira:
            problemas.append(
                f"resposta sem a chave {chave!r} (chaves: {sorted(primeira)})"
            )
    falhar("B3", problemas)

    pagina = primeira["page"]
    for campo in ("pageNumber", "pageSize", "totalRecords", "totalPages"):
        if not isinstance(pagina.get(campo), int):
            problemas.append(
                f"page.{campo} ausente ou não inteiro: {pagina.get(campo)!r}"
            )
    falhar("B3", problemas)
    if pagina["pageNumber"] != 1 or pagina["pageSize"] != PAGINA:
        problemas.append(
            f"paginação não respeita pageNumber/pageSize pedidos: {pagina!r}"
        )
    if pagina["totalPages"] != math.ceil(pagina["totalRecords"] / PAGINA):
        problemas.append(f"totalPages incoerente com totalRecords/pageSize: {pagina!r}")
    if pagina["totalPages"] < 2:
        problemas.append(f"menos de 2 páginas com pageSize={PAGINA}: {pagina!r}")
    if len(primeira["results"]) != PAGINA:
        problemas.append(
            f"página 1 com {len(primeira['results'])} registros, não {PAGINA}"
        )
    codigos = [{r.get("codeCVM") for r in p["results"]} for p in (primeira, segunda)]
    if codigos[0] & codigos[1]:
        problemas.append(
            f"páginas 1 e 2 repetem codeCVM: {sorted(codigos[0] & codigos[1])}"
        )

    registros = primeira["results"] + segunda["results"]
    recebidas = list(dict.fromkeys(k for r in registros for k in r))
    problemas += diferenca_de_colunas(colunas_esperadas(b3.TABELA), recebidas)
    problemas += formatos_invalidos(
        b3.TABELA, [{k: ing._texto(v) for k, v in r.items()} for r in registros]
    )
    emissoras = [r.get("issuingCompany") for r in registros]
    invalidas = [e for e in emissoras if not re.fullmatch(r"[A-Z0-9]{4}", e or "")]
    if invalidas:
        problemas.append(
            f"issuingCompany fora de 4 letras/dígitos: {invalidas[:EXEMPLOS]}"
        )
    sem_codigo = [
        r for r in registros if not re.fullmatch(r"\d+", r.get("codeCVM") or "")
    ]
    if sem_codigo:
        problemas.append(f"{len(sem_codigo)} registro(s) com codeCVM não numérico")
    falhar("B3", problemas)


def test_b3_detalhe_traz_os_tickers_em_other_codes():
    url = ing._b3_url(
        "GetDetail", {"codeCVM": CODIGO_CVM_PETROBRAS, "language": "pt-br"}
    )
    dados = _obter("B3", lambda: ing._com_retry(lambda: ing._get(url).json(), "B3"))
    outros = dados.get("otherCodes") if isinstance(dados, dict) else None
    if not isinstance(outros, list) or not outros:
        falhar(
            "B3", [f"GetDetail sem lista otherCodes (chaves: {sorted(dados or {})})"]
        )
    codigos = [o.get("code") for o in outros if isinstance(o, dict)]
    problemas = []
    # a ingestão aceita qualquer code não vazio (inclui debêntures, ex.: PETR-DEB62)
    if not all(isinstance(c, str) and c for c in codigos):
        problemas.append(f"otherCodes[].code ausente ou não textual: {codigos}")
    if "PETR4" not in codigos:
        problemas.append(f"otherCodes da Petrobras sem PETR4: {codigos}")
    falhar("B3", problemas)


# --------------------------------------------------------------------------- Fundamentus


def _limpar_fundamentus(valor):
    return valor.strip("\n\t")


def test_fundamentus_cabecalho_e_formato_numerico_brasileiro():
    df = _obter("Fundamentus", ing.extrair_fundamentus)
    recebidas = [c for c in df.columns if c not in METADADOS]
    problemas = diferenca_de_colunas(colunas_esperadas(fundamentus.TABELA), recebidas)
    if len(df) < MINIMO_FUNDAMENTUS:
        problemas.append(f"tabela com {len(df)} linhas, menos que {MINIMO_FUNDAMENTUS}")
    linhas = df.to_dict("records")
    problemas += formatos_invalidos(fundamentus.TABELA, linhas, _limpar_fundamentus)
    papeis = [linha.get("Papel") for linha in linhas]
    invalidos = [
        p for p in papeis if not re.fullmatch(r"[A-Z0-9]{4}\d{1,2}[A-Z]?", p or "")
    ]
    if invalidos:
        problemas.append(
            f"Papel fora do formato de ticker: {len(invalidos)} (ex.: {invalidos[:EXEMPLOS]})"
        )
    numericas = sum(c.conversao is NUMERO_BR for c in fundamentus.TABELA.colunas)
    if numericas != 21:  # a decisão 7 da Silver cita as 21 colunas numéricas
        problemas.append(f"mapeamento da Silver mudou: {numericas} colunas numéricas")
    falhar("Fundamentus", problemas)


# --------------------------------------------------------------------------- Minha Receita


def _tipo_json(valor):
    return "null" if valor is None else type(valor).__name__


def _confere(valor, tipo):
    if valor is None:
        return True
    if tipo in (minhareceita.TEXTO_JSON,):
        return isinstance(valor, str)
    if tipo == minhareceita.CNPJ_JSON:
        return isinstance(valor, str) and re.fullmatch(r"\d{0,14}", valor) is not None
    if tipo == minhareceita.INTEIRO_JSON:
        return type(valor) is int
    if tipo == minhareceita.DECIMAL_JSON:
        return type(valor) in (int, float)
    if tipo == minhareceita.BOOLEANO_JSON:
        return type(valor) is bool
    if tipo == minhareceita.DATA_JSON:
        return (
            isinstance(valor, str)
            and re.fullmatch(r"\d{4}-\d{2}-\d{2}", valor) is not None
        )
    raise AssertionError(f"tipo de contrato desconhecido: {tipo}")


def _diferencas_objeto(objeto, tipos, caminho):
    problemas = diferenca_de_colunas(list(tipos), list(objeto))
    problemas = [f"{caminho}: {p}" for p in problemas]
    for propriedade, tipo in tipos.items():
        if propriedade in objeto and not _confere(objeto[propriedade], tipo):
            problemas.append(
                f"{caminho}.{propriedade}: esperado {tipo}, "
                f"recebido {_tipo_json(objeto[propriedade])}"
            )
    return problemas


def test_minhareceita_propriedades_e_tipos_do_contrato_json():
    url = ing._url_minhareceita(CNPJ_PETROBRAS)
    texto = _obter(
        "Minha Receita",
        lambda: ing._com_retry(lambda: ing._get(url).text, "Minha Receita"),
    )
    try:
        dados = json.loads(texto)
    except json.JSONDecodeError as exc:
        falhar("Minha Receita", [f"resposta não é JSON: {exc}"])
    if not isinstance(dados, dict):
        falhar("Minha Receita", [f"esperado objeto JSON, recebido {_tipo_json(dados)}"])

    tipos_empresa = dict(minhareceita.ESCALARES_EMPRESA)
    arrays = {a.propriedade: a for a in minhareceita.ARRAYS_EMPRESA}
    problemas = diferenca_de_colunas(list(tipos_empresa) + list(arrays), list(dados))
    for propriedade, tipo in tipos_empresa.items():
        if propriedade in dados and not _confere(dados[propriedade], tipo):
            problemas.append(
                f"{propriedade}: esperado {tipo}, recebido {_tipo_json(dados[propriedade])}"
            )
    if dados.get("cnpj") != CNPJ_PETROBRAS:
        problemas.append("cnpj do JSON diferente do consultado")
    for propriedade, array in arrays.items():
        itens = dados.get(propriedade)
        if itens is None:
            continue
        if not isinstance(itens, list):
            problemas.append(
                f"{propriedade}: esperado array, recebido {_tipo_json(itens)}"
            )
            continue
        tipos = {p: tipo for p, (_, tipo) in array.propriedades.items()}
        for posicao, item in enumerate(itens, start=1):
            caminho = f"{propriedade}[{posicao}]"
            if not isinstance(item, dict):
                problemas.append(
                    f"{caminho}: esperado objeto, recebido {_tipo_json(item)}"
                )
                continue
            problemas += _diferencas_objeto(item, tipos, caminho)
    if not dados.get("qsa"):
        problemas.append(
            "qsa vazio ou ausente para a Petrobras (array esperado com sócios)"
        )
    falhar("Minha Receita", list(dict.fromkeys(problemas)))


# --------------------------------------------------------------------------- Yahoo Finance


def test_yahoo_historico_com_as_colunas_e_tipos_da_silver():
    yf.config.debug.hide_exceptions = False  # como no main da ingestão
    df = _obter("Yahoo", lambda: ing.extrair_yfinance(TICKERS_YAHOO))
    recebidas = [c for c in df.columns if c not in METADADOS]
    problemas = diferenca_de_colunas(
        colunas_esperadas(yfinance.TABELA), recebidas, OPCIONAIS_YAHOO
    )
    obtidos = sorted(df["ticker"].unique()) if "ticker" in df else []
    if obtidos != sorted(TICKERS_YAHOO):
        problemas.append(f"histórico obtido só para {obtidos} de {TICKERS_YAHOO}")
    if len(df) < 1000:
        problemas.append(f"histórico com só {len(df)} linhas (period=max)")
    linhas = df.astype(object).where(df.notna(), None).to_dict("records")
    problemas += formatos_invalidos(yfinance.TABELA, linhas)
    falhar("Yahoo", problemas)
