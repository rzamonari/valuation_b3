"""Testes de pipeline/ingestao.py sem rede: HTTP e yfinance são substituídos por respostas fixas.

O banco é um DuckDB temporário em tmp_path; o banco real não é tocado.
"""

import base64
import json

import duckdb
import pandas as pd
import pytest
import requests
from yfinance.exceptions import YFRateLimitError

from pipeline import db
from pipeline import ingestao as ing


class Resposta:
    def __init__(self, status=200, texto="", dados=None):
        self.status_code = status
        self.text = texto
        self._dados = dados

    def json(self):
        return self._dados

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class Sessao:
    """Responde pela função `rotas(url) -> Resposta` e registra as URLs pedidas."""

    def __init__(self, rotas):
        self.rotas = rotas
        self.urls = []

    def get(self, url, timeout):
        self.urls.append(url)
        resposta = self.rotas(url)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta


@pytest.fixture(autouse=True)
def sem_espera(monkeypatch):
    esperas = []
    monkeypatch.setattr(ing.time, "sleep", esperas.append)
    return esperas


def usar_sessao(monkeypatch, rotas):
    sessao = Sessao(rotas)
    monkeypatch.setattr(ing, "_sessao", lambda: sessao)
    return sessao


def parametros_b3(url):
    return json.loads(base64.b64decode(url.rsplit("/", 1)[1]))


# --------------------------------------------------------------------------- _get e _com_retry


def test_get_devolve_a_resposta_quando_status_e_2xx(monkeypatch):
    usar_sessao(monkeypatch, lambda url: Resposta(200, "ok"))
    assert ing._get("https://x").text == "ok"


def test_get_4xx_e_erro_definitivo_com_o_status(monkeypatch):
    usar_sessao(monkeypatch, lambda url: Resposta(404))
    with pytest.raises(ing._ErroDefinitivo) as erro:
        ing._get("https://x")
    assert erro.value.status == 404


@pytest.mark.parametrize("status", [429, 500, 503])
def test_get_429_e_5xx_sao_erros_transitorios(monkeypatch, status):
    usar_sessao(monkeypatch, lambda url: Resposta(status))
    with pytest.raises(requests.HTTPError):
        ing._get("https://x")


def test_retry_repete_erro_transitorio_com_backoff_e_devolve_o_sucesso(
    monkeypatch, sem_espera
):
    respostas = iter([Resposta(503), Resposta(429), Resposta(200, "ok")])
    sessao = usar_sessao(monkeypatch, lambda url: next(respostas))
    resultado = ing._com_retry(lambda: ing._get("https://x").text, "teste")
    assert resultado == "ok"
    assert len(sessao.urls) == 3
    assert sem_espera == [2, 4]


def test_retry_desiste_apos_as_tentativas_e_repassa_o_erro(monkeypatch, sem_espera):
    sessao = usar_sessao(monkeypatch, lambda url: Resposta(500))
    with pytest.raises(requests.HTTPError):
        ing._com_retry(lambda: ing._get("https://x"), "teste")
    assert len(sessao.urls) == ing.TENTATIVAS
    assert len(sem_espera) == ing.TENTATIVAS - 1


def test_retry_nao_repete_erro_definitivo(monkeypatch, sem_espera):
    sessao = usar_sessao(monkeypatch, lambda url: Resposta(400))
    with pytest.raises(ing._ErroDefinitivo):
        ing._com_retry(lambda: ing._get("https://x"), "teste")
    assert len(sessao.urls) == 1
    assert sem_espera == []


# --------------------------------------------------------------------------- utilitários


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        (None, None),
        (float("nan"), None),
        (pd.NA, None),
        ("", ""),
        ("texto", "texto"),
        (0.1, "0.1"),
        (0, "0"),
        (True, "true"),
        ({"a": "ç"}, '{"a": "ç"}'),
        ([1, 2], "[1, 2]"),
    ],
)
def test_texto_preserva_nulos_e_nao_arredonda(valor, esperado):
    assert ing._texto(valor) == esperado


def test_url_minhareceita_completa_zeros_so_quando_o_cnpj_e_numerico():
    assert ing._url_minhareceita("191").endswith("/00000000000191")
    assert ing._url_minhareceita("33000167000101").endswith("/33000167000101")
    assert ing._url_minhareceita("12.345").endswith("/12.345")


def test_em_paralelo_registra_falhas_sem_interromper_os_demais():
    def dobrar(n):
        if n == 2:
            raise ValueError("falhou")
        return n * 2

    resultados, falhas = ing._em_paralelo(dobrar, [1, 2, 3], 2, "teste")
    assert sorted(resultados) == [(1, 2), (3, 6)]
    assert falhas == [2]


# --------------------------------------------------------------------------- validar_fontes


def test_validar_fontes_passa_quando_pagina_e_app_respondem(monkeypatch):
    usar_sessao(
        monkeypatch,
        lambda url: Resposta(200, "<app-root></app-root>" if "listados" in url else ""),
    )
    ing.validar_fontes()


def test_validar_fontes_sem_o_app_vira_falha_de_extracao(monkeypatch):
    usar_sessao(monkeypatch, lambda url: Resposta(200, "Erro | B3"))
    with pytest.raises(ing.FalhaExtracao, match="b3_empresas"):
        ing.validar_fontes()


# --------------------------------------------------------------------------- B3


def empresa(codigo, cnpj):
    return {"codeCVM": codigo, "issuingCompany": f"E{codigo}", "cnpj": cnpj}


def test_extrair_b3_percorre_todas_as_paginas_e_marca_a_origem(monkeypatch):
    paginas = {
        1: [empresa("1", "191"), empresa("2", "")],
        2: [empresa("3", None)],
    }

    def rotas(url):
        pagina = parametros_b3(url)["pageNumber"]
        return Resposta(dados={"page": {"totalPages": 2}, "results": paginas[pagina]})

    usar_sessao(monkeypatch, rotas)
    df = ing.extrair_b3()
    assert df["codeCVM"].tolist() == ["1", "2", "3"]
    assert df["cnpj"].tolist() == ["191", "", None]  # vazio e nulo continuam distintos
    assert df["_source_origin"].unique().tolist() == [
        f"{ing.URL_B3_API}/GetInitialCompanies"
    ]
    assert df["_timestamp_ingestao"].notna().all()


def test_extrair_b3_sem_registros_e_falha_de_extracao(monkeypatch):
    usar_sessao(
        monkeypatch,
        lambda url: Resposta(dados={"page": {"totalPages": 1}, "results": []}),
    )
    with pytest.raises(ing.FalhaExtracao, match="não retornou registros"):
        ing.extrair_b3()


def test_identificar_cnpjs_ignora_vazios_e_repetidos():
    # dtype=object como em extrair_b3: None continua None
    df = pd.DataFrame({"cnpj": ["191", "", None, "191", "0001"]}, dtype=object)
    assert ing.identificar_cnpjs(df) == ["191", "0001"]


def test_identificar_tickers_junta_os_codigos_dos_detalhes_sem_repetir(monkeypatch):
    detalhes = {
        "1": {"otherCodes": [{"code": "AAAA3"}, {"code": "AAAA4"}]},
        "2": {"otherCodes": [{"code": "AAAA3"}, {"code": ""}]},
        "3": {"otherCodes": None},
    }
    usar_sessao(
        monkeypatch,
        lambda url: Resposta(dados=detalhes[parametros_b3(url)["codeCVM"]]),
    )
    df = pd.DataFrame({"codeCVM": ["1", "2", "3", "1", None]})
    assert sorted(ing.identificar_tickers(df)) == ["AAAA3", "AAAA4"]


# --------------------------------------------------------------------------- Fundamentus

HTML_FUNDAMENTUS = """
<html><body><table>
  <thead><tr><th>Papel</th><th>Cotação</th><th>P/L</th></tr></thead>
  <tbody>
    <tr><td>AAAA3</td><td>10,50</td><td>-3,20</td></tr>
    <tr><td>BBBB4</td><td>0,00</td><td>-</td></tr>
  </tbody>
</table></body></html>
"""


def test_extrair_fundamentus_le_a_tabela_como_texto(monkeypatch):
    usar_sessao(monkeypatch, lambda url: Resposta(200, HTML_FUNDAMENTUS))
    df = ing.extrair_fundamentus()
    assert df[["Papel", "Cotação", "P/L"]].values.tolist() == [
        ["AAAA3", "10,50", "-3,20"],
        ["BBBB4", "0,00", "-"],
    ]
    assert (df["_source_origin"] == ing.URL_FUNDAMENTUS).all()


@pytest.mark.parametrize(
    "pagina",
    ["<html><body><p>sem tabela</p></body></html>", "<table><thead></thead></table>"],
)
def test_extrair_fundamentus_sem_tabela_ou_vazia_e_falha(monkeypatch, pagina):
    usar_sessao(monkeypatch, lambda url: Resposta(200, pagina))
    with pytest.raises(ing.FalhaExtracao, match="fundamentus_acoes"):
        ing.extrair_fundamentus()


# --------------------------------------------------------------------------- Minha Receita


def test_minhareceita_grava_cnpj_original_e_lista_os_rejeitados(monkeypatch, capsys):
    def rotas(url):
        if url.endswith("/00000000000191"):
            return Resposta(200, '{"cnpj": "00000000000191"}')
        return Resposta(404)

    usar_sessao(monkeypatch, rotas)
    df = ing.extrair_minhareceita(["191", "999"])
    assert df["cnpj"].tolist() == ["191"]  # valor gravado como veio da B3
    assert df["payload_json"].tolist() == ['{"cnpj": "00000000000191"}']
    assert df["_source_origin"].tolist() == [f"{ing.URL_MINHARECEITA}00000000000191"]
    assert "1 CNPJs rejeitados" in capsys.readouterr().out


def test_minhareceita_com_consulta_falhando_e_falha_de_extracao(monkeypatch):
    usar_sessao(monkeypatch, lambda url: Resposta(500))
    with pytest.raises(ing.FalhaExtracao, match="1 consultas falharam"):
        ing.extrair_minhareceita(["191"])


def test_minhareceita_com_todos_rejeitados_e_falha_de_extracao(monkeypatch):
    usar_sessao(monkeypatch, lambda url: Resposta(400))
    with pytest.raises(ing.FalhaExtracao, match="nenhuma consulta concluída"):
        ing.extrair_minhareceita(["191"])


# --------------------------------------------------------------------------- yfinance


class TickerFalso:
    """Substitui yf.Ticker: `historicos[simbolo]` é um DataFrame ou uma exceção."""

    historicos = {}
    chamadas = []

    def __init__(self, simbolo):
        self.simbolo = simbolo

    def history(self, **kwargs):
        TickerFalso.chamadas.append(self.simbolo)
        resultado = self.historicos[self.simbolo]
        if callable(resultado):
            resultado = resultado()
        if isinstance(resultado, Exception):
            raise resultado
        return resultado


def usar_yfinance(monkeypatch, historicos):
    TickerFalso.historicos = historicos
    TickerFalso.chamadas = []
    monkeypatch.setattr(ing.yf, "Ticker", TickerFalso)


def historico(*fechamentos):
    indice = pd.DatetimeIndex(
        pd.date_range("2026-01-02", periods=len(fechamentos), tz="America/Sao_Paulo"),
        name="Date",
    )
    return pd.DataFrame({"Close": list(fechamentos)}, index=indice)


def test_yfinance_grava_texto_com_ticker_da_b3_e_origem_com_sa(monkeypatch):
    usar_yfinance(
        monkeypatch,
        {"AAAA3.SA": historico(10.25, None), "BBBB4.SA": historico()},
    )
    df = ing.extrair_yfinance(["AAAA3", "BBBB4"])
    assert df["ticker"].tolist() == ["AAAA3", "AAAA3"]  # histórico vazio é ignorado
    assert df["Close"].tolist()[0] == "10.25"
    assert pd.isna(df["Close"].tolist()[1])
    assert df["Date"].tolist()[0].startswith("2026-01-02 00:00:00-03:00")
    assert df["_source_origin"].unique().tolist() == [
        f"{ing.ORIGEM_YFINANCE}: AAAA3.SA"
    ]
    assert list(df.columns)[-2:] == ["_timestamp_ingestao", "_source_origin"]


def test_yfinance_repete_rate_limit(monkeypatch, sem_espera):
    tentativas = iter([YFRateLimitError(), historico(1.0)])
    usar_yfinance(monkeypatch, {"AAAA3.SA": lambda: next(tentativas)})
    df = ing.extrair_yfinance(["AAAA3"])
    assert len(df) == 1
    assert TickerFalso.chamadas == ["AAAA3.SA", "AAAA3.SA"]


def test_yfinance_sem_nenhum_historico_e_falha_de_extracao(monkeypatch):
    usar_yfinance(monkeypatch, {"AAAA3.SA": historico()})
    with pytest.raises(ing.FalhaExtracao, match="yfinance_cotacoes"):
        ing.extrair_yfinance(["AAAA3"])


# --------------------------------------------------------------------------- main


def tabelas_extraidas(valor="1"):
    return {
        "b3_empresas": pd.DataFrame({"codeCVM": [valor]}, dtype=object),
        "fundamentus_acoes": pd.DataFrame({"Papel": ["AAAA3", "BBBB4"]}, dtype=object),
        "minhareceita_empresas": pd.DataFrame({"cnpj": ["191"]}, dtype=object),
        "yfinance_cotacoes": pd.DataFrame({"ticker": ["AAAA3"]}, dtype="string"),
    }


def ler_raw(arquivo):
    con = duckdb.connect(str(arquivo), read_only=True)
    try:
        return {
            tabela: con.execute(f"SELECT * FROM raw.{tabela} ORDER BY ALL").fetchall()
            for (tabela,) in con.execute(
                "SELECT table_name FROM duckdb_tables() WHERE schema_name = 'raw' "
                "ORDER BY table_name"
            ).fetchall()
        }
    finally:
        con.close()


def preparar_main(tmp_path, monkeypatch, extrair):
    arquivo = tmp_path / "teste.duckdb"
    monkeypatch.setattr(db, "_ARQUIVO_DB", arquivo)
    monkeypatch.setattr(ing, "_extrair_tudo", extrair)
    return arquivo


def test_main_grava_as_quatro_tabelas_raw(tmp_path, monkeypatch, capsys):
    arquivo = preparar_main(tmp_path, monkeypatch, tabelas_extraidas)
    ing.main()
    assert ler_raw(arquivo) == {
        "b3_empresas": [("1",)],
        "fundamentus_acoes": [("AAAA3",), ("BBBB4",)],
        "minhareceita_empresas": [("191",)],
        "yfinance_cotacoes": [("AAAA3",)],
    }
    assert "TOTAL" in capsys.readouterr().out


def test_main_com_falha_de_extracao_sai_com_1_sem_gravar(tmp_path, monkeypatch, capsys):
    def falhar():
        raise ing.FalhaExtracao("fundamentus_acoes: tabela vazia")

    arquivo = preparar_main(tmp_path, monkeypatch, falhar)
    with pytest.raises(SystemExit) as saida:
        ing.main()
    assert saida.value.code == 1
    assert "Nenhuma tabela foi gravada" in capsys.readouterr().err
    assert not arquivo.exists()


def test_main_com_falha_na_gravacao_faz_rollback_e_preserva_a_versao_anterior(
    tmp_path, monkeypatch, capsys
):
    arquivo = preparar_main(tmp_path, monkeypatch, tabelas_extraidas)
    ing.main()
    antes = ler_raw(arquivo)

    gravar_original = db.gravar

    def gravar_falhando_na_ultima(con, df, schema, tabela):
        if tabela == "yfinance_cotacoes":
            raise duckdb.IOException("disco cheio")
        return gravar_original(con, df, schema, tabela)

    monkeypatch.setattr(ing, "_extrair_tudo", lambda: tabelas_extraidas("2"))
    monkeypatch.setattr(db, "gravar", gravar_falhando_na_ultima)
    with pytest.raises(SystemExit) as saida:
        ing.main()
    assert saida.value.code == 1
    assert "Rollback executado" in capsys.readouterr().err
    assert ler_raw(arquivo) == antes
