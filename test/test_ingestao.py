"""Testes de pipeline/ingestao.py. Sem rede: `_sessao` e `yfinance` são substituídos por
respostas mínimas, e o banco é um DuckDB temporário em tmp_path."""

import base64
import json

import duckdb
import pandas as pd
import pytest
import requests
from yfinance.exceptions import YFRateLimitError

from pipeline import db
from pipeline import ingestao as ing


class RespostaFalsa:
    def __init__(self, status_code=200, texto="", dados=None):
        self.status_code = status_code
        self.text = texto
        self._dados = dados

    def json(self):
        return self._dados

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class SessaoFalsa:
    """Devolve a resposta de `rotas(url)` e registra as URLs pedidas."""

    def __init__(self, rotas):
        self.rotas = rotas
        self.urls = []

    def get(self, url, timeout):
        self.urls.append(url)
        return self.rotas(url)


def usar_sessao(monkeypatch, rotas):
    sessao = SessaoFalsa(rotas)
    monkeypatch.setattr(ing, "_sessao", lambda: sessao)
    monkeypatch.setattr(ing, "BACKOFF_BASE", 0)  # retry sem espera
    return sessao


def parametros_b3(url):
    """Decodifica o JSON em base64 do final da URL da API da B3."""
    return json.loads(base64.b64decode(url.rsplit("/", 1)[1]))


# --------------------------------------------------------------------------- utilitários


def test_com_retry_repete_erro_transitorio_ate_conseguir(monkeypatch):
    monkeypatch.setattr(ing, "BACKOFF_BASE", 0)
    chamadas = []

    def operacao():
        chamadas.append(1)
        if len(chamadas) < ing.TENTATIVAS:
            raise requests.ConnectionError("queda")
        return "ok"

    assert ing._com_retry(operacao, "teste") == "ok"
    assert len(chamadas) == ing.TENTATIVAS


def test_com_retry_desiste_depois_da_ultima_tentativa(monkeypatch):
    monkeypatch.setattr(ing, "BACKOFF_BASE", 0)
    chamadas = []

    def operacao():
        chamadas.append(1)
        raise requests.ConnectionError("fora do ar")

    with pytest.raises(requests.ConnectionError):
        ing._com_retry(operacao, "teste")
    assert len(chamadas) == ing.TENTATIVAS


def test_com_retry_nao_repete_erro_definitivo():
    chamadas = []

    def operacao():
        chamadas.append(1)
        raise ing._ErroDefinitivo("HTTP 404", 404)

    with pytest.raises(ing._ErroDefinitivo):
        ing._com_retry(operacao, "teste")
    assert len(chamadas) == 1


@pytest.mark.parametrize("status", [404, 403])
def test_get_trata_4xx_como_erro_definitivo(monkeypatch, status):
    usar_sessao(monkeypatch, lambda url: RespostaFalsa(status))
    with pytest.raises(ing._ErroDefinitivo) as erro:
        ing._get("https://exemplo")
    assert erro.value.status == status


@pytest.mark.parametrize("status", [429, 503])
def test_get_trata_429_e_5xx_como_transitorio(monkeypatch, status):
    usar_sessao(monkeypatch, lambda url: RespostaFalsa(status))
    with pytest.raises(requests.HTTPError):
        ing._get("https://exemplo")


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        (None, None),
        (float("nan"), None),
        (pd.NaT, None),
        ("6,91%", "6,91%"),
        (12.345678901234, "12.345678901234"),  # sem arredondamento
        (True, "true"),
        ({"a": "ç"}, '{"a": "ç"}'),
        ([1, 2], "[1, 2]"),
    ],
)
def test_texto_preserva_valor_sem_arredondar_e_nulo_como_nulo(valor, esperado):
    assert ing._texto(valor) == esperado


# --------------------------------------------------------------------------- validação prévia


def test_validar_fontes_aceita_app_de_listados_no_ar(monkeypatch):
    usar_sessao(
        monkeypatch, lambda url: RespostaFalsa(texto="<html><app-root></app-root>")
    )
    ing.validar_fontes()


def test_validar_fontes_falha_se_o_app_de_listados_nao_responde(monkeypatch):
    usar_sessao(monkeypatch, lambda url: RespostaFalsa(texto="<html>Erro | B3</html>"))
    with pytest.raises(ing.FalhaExtracao, match="b3_empresas"):
        ing.validar_fontes()


# --------------------------------------------------------------------------- fontes


def test_extrair_b3_percorre_todas_as_paginas(monkeypatch):
    def rotas(url):
        pagina = parametros_b3(url)["pageNumber"]
        return RespostaFalsa(
            dados={
                "page": {"totalPages": 2},
                "results": [{"codeCVM": str(pagina), "cnpj": f"0{pagina}", "x": None}],
            }
        )

    sessao = usar_sessao(monkeypatch, rotas)
    df = ing.extrair_b3()
    assert len(sessao.urls) == 2
    assert df["codeCVM"].tolist() == ["1", "2"]
    assert df["x"].isna().all()  # nulo continua nulo
    assert {"_timestamp_ingestao", "_source_origin"} <= set(df.columns)


def test_extrair_b3_sem_registros_e_falha(monkeypatch):
    usar_sessao(
        monkeypatch,
        lambda url: RespostaFalsa(dados={"page": {"totalPages": 1}, "results": []}),
    )
    with pytest.raises(ing.FalhaExtracao, match="não retornou registros"):
        ing.extrair_b3()


def test_identificar_cnpjs_remove_vazios_e_repetidos_sem_alterar_valor():
    # dtype=object como em extrair_b3: None continua None
    df_b3 = pd.DataFrame({"cnpj": ["123", "", None, "123", "00456"]}, dtype=object)
    assert ing.identificar_cnpjs(df_b3) == ["123", "00456"]


def test_identificar_tickers_usa_other_codes_de_cada_codigo_cvm(monkeypatch):
    detalhes = {
        "1": {"otherCodes": [{"code": "AAAA3"}, {"code": "AAAA4"}]},
        "2": {"otherCodes": [{"code": "AAAA3"}, {"code": None}]},
        "3": {"otherCodes": None},
    }
    usar_sessao(
        monkeypatch,
        lambda url: RespostaFalsa(dados=detalhes[parametros_b3(url)["codeCVM"]]),
    )
    df_b3 = pd.DataFrame({"codeCVM": ["1", "2", "3", "1", None]}, dtype=object)
    assert sorted(ing.identificar_tickers(df_b3)) == ["AAAA3", "AAAA4"]


HTML_FUNDAMENTUS = """
<html><body><table>
  <thead><tr><th>Papel</th><th>Cotação</th><th>Div.Yield</th></tr></thead>
  <tbody>
    <tr><td>AAAA3</td><td>10,50</td><td>6,91%</td></tr>
    <tr><td>BBBB4</td><td>1.234,00</td><td>0,00%</td></tr>
  </tbody>
</table></body></html>
"""


def test_extrair_fundamentus_le_a_tabela_como_texto(monkeypatch):
    usar_sessao(monkeypatch, lambda url: RespostaFalsa(texto=HTML_FUNDAMENTUS))
    df = ing.extrair_fundamentus()
    assert df[["Papel", "Cotação", "Div.Yield"]].values.tolist() == [
        ["AAAA3", "10,50", "6,91%"],
        ["BBBB4", "1.234,00", "0,00%"],
    ]
    assert (df["_source_origin"] == ing.URL_FUNDAMENTUS).all()


@pytest.mark.parametrize(
    "html",
    ["<html><body>sem tabela</body></html>", "<table><thead></thead></table>"],
)
def test_extrair_fundamentus_sem_tabela_ou_vazia_e_falha(monkeypatch, html):
    usar_sessao(monkeypatch, lambda url: RespostaFalsa(texto=html))
    with pytest.raises(ing.FalhaExtracao, match="fundamentus_acoes"):
        ing.extrair_fundamentus()


def test_extrair_minhareceita_completa_cnpj_so_na_url_e_ignora_rejeitados(monkeypatch):
    def rotas(url):
        if url.endswith("99999999999999"):
            return RespostaFalsa(404)
        return RespostaFalsa(texto='{"razao_social": "EMPRESA FICTICIA"}')

    sessao = usar_sessao(monkeypatch, rotas)
    df = ing.extrair_minhareceita(["123", "99999999999999"])
    assert f"{ing.URL_MINHARECEITA}00000000000123" in sessao.urls
    assert df["cnpj"].tolist() == ["123"]  # valor gravado como veio da B3
    assert df["_source_origin"].tolist() == [f"{ing.URL_MINHARECEITA}00000000000123"]


def test_extrair_minhareceita_com_consulta_falha_aborta(monkeypatch):
    def rotas(url):
        if url.endswith("2"):
            return RespostaFalsa(503)
        return RespostaFalsa(texto="{}")

    usar_sessao(monkeypatch, rotas)
    with pytest.raises(ing.FalhaExtracao, match="1 consultas falharam"):
        ing.extrair_minhareceita(["1", "2"])


def test_extrair_minhareceita_sem_nenhum_payload_e_falha(monkeypatch):
    usar_sessao(monkeypatch, lambda url: RespostaFalsa(404))
    with pytest.raises(ing.FalhaExtracao, match="nenhuma consulta concluída"):
        ing.extrair_minhareceita(["1"])


def historico_ficticio():
    indice = pd.DatetimeIndex(
        ["2026-10-29", "2026-10-30"], tz="America/Sao_Paulo", name="Date"
    )
    return pd.DataFrame({"Close": [10.5, None], "Volume": [100, 200]}, index=indice)


class TickerFalso:
    historicos = {}

    def __init__(self, simbolo):
        self.simbolo = simbolo

    def history(self, **_):
        resultado = self.historicos[self.simbolo]
        if isinstance(resultado, Exception):
            raise resultado
        return resultado


def usar_yfinance(monkeypatch, historicos):
    monkeypatch.setattr(TickerFalso, "historicos", historicos)
    monkeypatch.setattr(ing.yf, "Ticker", TickerFalso)
    monkeypatch.setattr(ing, "BACKOFF_BASE", 0)


def test_extrair_yfinance_grava_historico_como_texto_e_ignora_falhas(monkeypatch):
    usar_yfinance(
        monkeypatch,
        {
            "AAAA3.SA": historico_ficticio(),
            "VAZI3.SA": pd.DataFrame(),
            "ERRO3.SA": YFRateLimitError(),
        },
    )
    df = ing.extrair_yfinance(["AAAA3", "VAZI3", "ERRO3"])
    assert df["ticker"].tolist() == ["AAAA3", "AAAA3"]
    assert df["Close"].tolist()[0] == "10.5"
    assert pd.isna(df["Close"].tolist()[1])
    assert df["_source_origin"].unique().tolist() == [
        f"{ing.ORIGEM_YFINANCE}: AAAA3.SA"
    ]
    assert df.columns[-2:].tolist() == ["_timestamp_ingestao", "_source_origin"]


def test_extrair_yfinance_sem_nenhum_historico_e_falha(monkeypatch):
    usar_yfinance(monkeypatch, {"VAZI3.SA": pd.DataFrame()})
    with pytest.raises(ing.FalhaExtracao, match="yfinance_cotacoes"):
        ing.extrair_yfinance(["VAZI3"])


# --------------------------------------------------------------------------- orquestração


def apontar_banco(tmp_path, monkeypatch):
    arquivo = tmp_path / "teste.duckdb"
    monkeypatch.setattr(db, "_ARQUIVO_DB", arquivo)
    return arquivo


def tabelas_raw(arquivo):
    con = duckdb.connect(str(arquivo))
    try:
        return sorted(
            n
            for (n,) in con.execute(
                "SELECT table_name FROM duckdb_tables() WHERE schema_name = 'raw'"
            ).fetchall()
        )
    finally:
        con.close()


def test_main_grava_as_tabelas_raw_numa_transacao(tmp_path, monkeypatch):
    arquivo = apontar_banco(tmp_path, monkeypatch)
    tabelas = {
        "b3_empresas": pd.DataFrame({"codeCVM": ["1"]}),
        "fundamentus_acoes": pd.DataFrame({"Papel": ["AAAA3", "BBBB4"]}),
    }
    monkeypatch.setattr(ing, "_extrair_tudo", lambda: tabelas)
    ing.main()
    assert tabelas_raw(arquivo) == ["b3_empresas", "fundamentus_acoes"]


def test_main_com_falha_de_extracao_sai_com_1_sem_gravar(tmp_path, monkeypatch, capsys):
    arquivo = apontar_banco(tmp_path, monkeypatch)

    def falhar():
        raise ing.FalhaExtracao("fundamentus_acoes: tabela vazia")

    monkeypatch.setattr(ing, "_extrair_tudo", falhar)
    with pytest.raises(SystemExit) as saida:
        ing.main()
    assert saida.value.code == 1
    assert "Nenhuma tabela foi gravada" in capsys.readouterr().err
    assert not arquivo.exists()


def test_main_com_falha_de_gravacao_desfaz_tudo(tmp_path, monkeypatch, capsys):
    arquivo = apontar_banco(tmp_path, monkeypatch)
    monkeypatch.setattr(
        ing, "_extrair_tudo", lambda: {"b3_empresas": pd.DataFrame({"x": ["1"]})}
    )
    ing.main()  # versão anterior publicada

    gravar_original = db.gravar

    def gravar_e_falhar(con, df, schema, tabela):
        if tabela == "fundamentus_acoes":
            raise duckdb.IOException("disco cheio")
        return gravar_original(con, df, schema, tabela)

    monkeypatch.setattr(db, "gravar", gravar_e_falhar)
    monkeypatch.setattr(
        ing,
        "_extrair_tudo",
        lambda: {
            "b3_empresas": pd.DataFrame({"x": ["2", "3"]}),
            "fundamentus_acoes": pd.DataFrame({"Papel": ["AAAA3"]}),
        },
    )
    with pytest.raises(SystemExit) as saida:
        ing.main()
    assert saida.value.code == 1
    assert "Rollback executado" in capsys.readouterr().err
    con = duckdb.connect(str(arquivo))
    assert con.execute("SELECT x FROM raw.b3_empresas").fetchall() == [("1",)]
    con.close()
    assert tabelas_raw(arquivo) == ["b3_empresas"]
