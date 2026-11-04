"""Ingestão da camada Raw (Bronze): B3, Fundamentus, Minha Receita e yfinance.

Execução: uv run python -m pipeline.ingestao
"""

import base64
import json
import logging
import sys
import threading
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pandas as pd
import requests
import yfinance as yf
from lxml import html
from yfinance.exceptions import YFException, YFRateLimitError

from pipeline import db

SCHEMA = "raw"

URL_B3_PAGINA = "https://www.b3.com.br/pt_br/produtos-e-servicos/negociacao/renda-variavel/empresas-listadas.htm"
URL_B3_APP = "sistemaswebb3-listados.b3.com.br/listedCompaniesPage"
URL_B3_API = "https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall"
URL_FUNDAMENTUS = "https://www.fundamentus.com.br/resultado.php"
URL_MINHARECEITA = "https://minhareceita.org/"
ORIGEM_YFINANCE = "Yahoo Finance via yfinance"

B3_PAGE_SIZE = 120
TENTATIVAS = 3
BACKOFF_BASE = 2  # segundos: 2, 4
TIMEOUT = 30
WORKERS_HTTP = 8
WORKERS_YFINANCE = 4
HEADERS = {"User-Agent": "Mozilla/5.0"}

_local = threading.local()


class FalhaExtracao(Exception):
    """Falha permanente de uma fonte inteira (aborta a execução)."""


class _ErroDefinitivo(Exception):
    """Erro que não adianta repetir (ex.: HTTP 4xx diferente de 429)."""

    def __init__(self, mensagem, status=None):
        super().__init__(mensagem)
        self.status = status


# --------------------------------------------------------------------------- utilitários


def _agora_utc():
    return datetime.now(UTC).isoformat()


def _sessao():
    if not hasattr(_local, "sessao"):
        _local.sessao = requests.Session()
        _local.sessao.headers.update(HEADERS)
    return _local.sessao


def _com_retry(operacao, descricao):
    """Até TENTATIVAS execuções com backoff exponencial (E1)."""
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            return operacao()
        except _ErroDefinitivo:
            raise
        except Exception as exc:
            if tentativa == TENTATIVAS:
                raise
            espera = BACKOFF_BASE**tentativa
            print(
                f"  [retry {tentativa}/{TENTATIVAS - 1}] {descricao}: {exc} — aguardando {espera}s"
            )
            time.sleep(espera)


def _get(url):
    resposta = _sessao().get(url, timeout=TIMEOUT)
    if resposta.status_code == 429 or resposta.status_code >= 500:
        resposta.raise_for_status()
    if resposta.status_code >= 400:
        raise _ErroDefinitivo(f"HTTP {resposta.status_code}", resposta.status_code)
    return resposta


def _texto(valor):
    """Representação textual sem arredondamento; nulos continuam nulos (I3, Y11, Y12)."""
    if valor is None or (not isinstance(valor, (str, list, dict)) and pd.isna(valor)):
        return None
    if isinstance(valor, str):
        return valor
    if isinstance(valor, (list, dict, bool)):
        return json.dumps(valor, ensure_ascii=False)
    return str(valor)


def _b3_url(endpoint, parametros):
    codificado = base64.b64encode(json.dumps(parametros).encode()).decode()
    return f"{URL_B3_API}/{endpoint}/{codificado}"


def _em_paralelo(funcao, itens, workers, rotulo):
    """Aplica funcao a cada item; falhas individuais são registradas e ignoradas."""
    resultados, falhas = [], []
    total = len(itens)

    def executar(item):
        try:
            return item, funcao(item), None
        except Exception as exc:  # noqa: BLE001 — falha por item é tolerada
            return item, None, exc

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, (item, resultado, erro) in enumerate(pool.map(executar, itens), start=1):
            if erro is not None:
                falhas.append(item)
                print(f"  [falha] {rotulo} {item}: {erro}")
            else:
                resultados.append((item, resultado))
            if i % 250 == 0 or i == total:
                print(f"  {rotulo}: {i}/{total} processados ({len(falhas)} falhas)")
    return resultados, falhas


# --------------------------------------------------------------------------- validação prévia


def validar_fontes():
    """Confirma que a página oficial da B3 e o app de listados (iframe dela) estão no ar.

    O conteúdo da página oficial não é exigido: o CDN da B3 devolve com frequência HTTP 200
    com uma página "Erro | B3" no lugar do iframe, sem relação com indisponibilidade da listagem.
    """

    def verificar_app():
        if "<app-root>" not in _get(f"https://{URL_B3_APP}/?language=pt-br").text:
            raise RuntimeError("app de listados não respondeu com a aplicação esperada")

    try:
        _com_retry(lambda: _get(URL_B3_PAGINA), "página B3")
        _com_retry(verificar_app, "app de listados B3")
    except Exception as exc:
        raise FalhaExtracao(f"b3_empresas: {exc}") from exc


# --------------------------------------------------------------------------- fontes


def extrair_b3():
    timestamp = _agora_utc()
    registros, pagina, total_paginas = [], 1, 1
    while pagina <= total_paginas:
        url = _b3_url(
            "GetInitialCompanies",
            {"language": "pt-br", "pageNumber": pagina, "pageSize": B3_PAGE_SIZE},
        )
        dados = _com_retry(lambda u=url: _get(u).json(), f"B3 página {pagina}")
        total_paginas = dados["page"]["totalPages"]
        registros.extend(dados["results"])
        pagina += 1
    if not registros:
        raise FalhaExtracao("b3_empresas: a API não retornou registros")

    df = pd.DataFrame(
        [{k: _texto(v) for k, v in r.items()} for r in registros], dtype=object
    )
    df["_timestamp_ingestao"] = timestamp
    df["_source_origin"] = f"{URL_B3_API}/GetInitialCompanies"
    return df


def identificar_cnpjs(df_b3):
    # Valores exatamente como vieram da B3 (M6); a repetição de consultas idênticas é evitada.
    # Vazio não identifica CNPJ: consultá-lo retornaria a página inicial da Minha Receita.
    return list(dict.fromkeys(c for c in df_b3["cnpj"] if c))


def identificar_tickers(df_b3):
    """Tickers negociáveis via GetDetail (otherCodes) de cada codeCVM.

    Os detalhes não são persistidos.
    """
    codigos_cvm = list(dict.fromkeys(c for c in df_b3["codeCVM"] if c is not None))

    def detalhe(codigo_cvm):
        url = _b3_url("GetDetail", {"codeCVM": codigo_cvm, "language": "pt-br"})
        return _com_retry(lambda: _get(url).json(), f"B3 detalhe {codigo_cvm}")

    resultados, _ = _em_paralelo(
        detalhe, codigos_cvm, WORKERS_HTTP, "B3 detalhe codeCVM"
    )
    tickers = []
    for _, dados in resultados:
        for outro in (dados or {}).get("otherCodes") or []:
            if outro.get("code"):
                tickers.append(outro["code"])
    return list(dict.fromkeys(tickers))


def extrair_fundamentus():
    timestamp = _agora_utc()
    resposta = _com_retry(lambda: _get(URL_FUNDAMENTUS), "Fundamentus")
    tabelas = html.fromstring(resposta.text).xpath("//table")
    if not tabelas:
        raise FalhaExtracao("fundamentus_acoes: nenhuma tabela encontrada no HTML")
    tabela = tabelas[0]
    colunas = [th.text_content() for th in tabela.xpath(".//thead//th")]
    linhas = [
        [td.text_content() for td in tr.xpath("./td")]
        for tr in tabela.xpath(".//tbody/tr")
    ]
    if not colunas or not linhas:
        raise FalhaExtracao("fundamentus_acoes: tabela vazia")

    df = pd.DataFrame(linhas, columns=colunas, dtype=object)
    df["_timestamp_ingestao"] = timestamp
    df["_source_origin"] = URL_FUNDAMENTUS
    return df


def _url_minhareceita(cnpj):
    # A API exige 14 dígitos; o complemento vale só para a URL, nunca para o valor gravado (M6.1).
    consulta = cnpj.zfill(14) if cnpj.isdigit() else cnpj
    return f"{URL_MINHARECEITA}{consulta}"


def extrair_minhareceita(cnpjs):
    timestamp = _agora_utc()

    def consultar(cnpj):
        url = _url_minhareceita(cnpj)
        try:
            return url, _com_retry(lambda: _get(url).text, f"Minha Receita {cnpj}")
        except _ErroDefinitivo as exc:
            if exc.status in (400, 404):  # identificador rejeitado pela API (M6.4)
                return url, None
            raise

    resultados, falhas = _em_paralelo(
        consultar, cnpjs, WORKERS_HTTP, "Minha Receita CNPJ"
    )
    if falhas:
        raise FalhaExtracao(
            f"minhareceitaorg_dadosempresas: {len(falhas)} consultas falharam: {falhas}"
        )

    rejeitados = [cnpj for cnpj, (_, payload) in resultados if payload is None]
    if rejeitados:
        print(
            f"  {len(rejeitados)} CNPJs rejeitados pela API (HTTP 400/404): {rejeitados}"
        )
    registros = [
        {
            "cnpj": cnpj,
            "payload_json": payload,
            "_timestamp_ingestao": timestamp,
            "_source_origin": url,
        }
        for cnpj, (url, payload) in resultados
        if payload is not None
    ]
    if not registros:
        raise FalhaExtracao("minhareceitaorg_dadosempresas: nenhuma consulta concluída")
    return pd.DataFrame(registros, dtype=object)


def extrair_yfinance(tickers):
    timestamp = _agora_utc()

    def historico(ticker):
        simbolo = f"{ticker}.SA"

        def baixar():
            try:
                return yf.Ticker(simbolo).history(
                    period="max", interval="1d", auto_adjust=False
                )
            except YFException as exc:
                if isinstance(exc, YFRateLimitError):
                    raise
                raise _ErroDefinitivo(str(exc)) from exc
            except Exception as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status and 400 <= status < 500 and status != 429:
                    raise _ErroDefinitivo(str(exc)) from exc
                raise

        df = _com_retry(baixar, f"yfinance {simbolo}").reset_index()
        df = pd.DataFrame(
            {c: [_texto(v) for v in df[c]] for c in df.columns}, dtype="string"
        )
        # ticker como veio da B3; o símbolo consultado (com .SA) fica só na origem.
        df.insert(0, "ticker", ticker)
        df["_source_origin"] = f"{ORIGEM_YFINANCE}: {simbolo}"
        return df

    resultados, _ = _em_paralelo(
        historico, tickers, WORKERS_YFINANCE, "yfinance ticker"
    )
    frames = [df for _, df in resultados if not df.empty]
    if not frames:
        raise FalhaExtracao("yfinance_cotacoes: nenhum histórico obtido")

    df = pd.concat(frames, ignore_index=True)
    df.insert(len(df.columns) - 1, "_timestamp_ingestao", timestamp)
    return df


# --------------------------------------------------------------------------- orquestração


def _extrair_tudo():
    print("Validando fontes...")
    validar_fontes()
    print("Extraindo B3...")
    df_b3 = extrair_b3()
    print(f"  {len(df_b3)} registros")
    print("Extraindo Fundamentus...")
    df_fundamentus = extrair_fundamentus()
    print(f"  {len(df_fundamentus)} registros")
    print("Identificando CNPJs e tickers da B3...")
    cnpjs = identificar_cnpjs(df_b3)
    tickers = identificar_tickers(df_b3)
    print(f"  {len(cnpjs)} CNPJs, {len(tickers)} tickers")
    print("Consultando Minha Receita...")
    df_minhareceita = extrair_minhareceita(cnpjs)
    print("Consultando yfinance...")
    df_yfinance = extrair_yfinance(tickers)
    return {
        "b3_empresas": df_b3,
        "fundamentus_acoes": df_fundamentus,
        "minhareceita_empresas": df_minhareceita,
        "yfinance_cotacoes": df_yfinance,
    }


def _imprimir_relatorio(contagens):

    def fmt(n):
        return f"{n:,}".replace(",", ".")

    largura = 33
    total = sum(contagens.values())
    numeros = max(len(fmt(total)), 15)
    print()
    for tabela, n in contagens.items():
        print(f"{f'{SCHEMA}.{tabela}':<{largura}}{fmt(n):>{numeros}}")
    print("-" * (largura + numeros))
    print(f"{'TOTAL':<{largura}}{fmt(total):>{numeros}}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    warnings.filterwarnings(
        "ignore", module=r"yfinance\."
    )  # avisos internos do yfinance com pandas 3
    yf.config.debug.hide_exceptions = (
        False  # erros do yfinance viram exceções tratadas pelo retry
    )

    try:
        tabelas = _extrair_tudo()
    except Exception as exc:  # noqa: BLE001 — qualquer falha de fonte aborta (E2)
        print(f"\nERRO DE EXTRAÇÃO — {exc}", file=sys.stderr)
        print("Nenhuma tabela foi gravada.", file=sys.stderr)
        sys.exit(1)

    con = db.conectar()
    try:
        db.criar_schema(con, SCHEMA)
        con.begin()
        try:
            contagens = {
                nome: db.gravar(con, df, SCHEMA, nome) for nome, df in tabelas.items()
            }
            con.commit()
        except Exception as exc:  # noqa: BLE001 — qualquer falha de gravação faz rollback (E3)
            con.rollback()
            print(f"\nERRO DE PERSISTÊNCIA — {exc}", file=sys.stderr)
            print(
                "Rollback executado: nenhuma das tabelas foi alterada.", file=sys.stderr
            )
            sys.exit(1)
        _imprimir_relatorio(contagens)
    finally:
        con.close()


if __name__ == "__main__":
    main()
