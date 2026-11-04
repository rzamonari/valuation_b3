"""Testes da qualidade: reconciliação raw → refined → marts e regras de domínio.

O banco é montado de ponta a ponta em tmp_path: Bronze sintética (mesmos helpers de
test_transformacao), transformação e materialização reais. O banco real não é tocado.
"""

import shutil

import duckdb
import pytest
from test_transformacao import (
    empresa,
    gravar_bronze,
    linha_b3,
    linha_fundamentus,
    linha_minhareceita,
    linha_yfinance,
)

from pipeline import db
from pipeline import materializacao as m
from pipeline import qualidade as q
from pipeline import transformacao as t

CNPJ = "11111111000111"


def acao(ticker, **valores):
    """Linha do Fundamentus elegível em todos os rankings, com liquidez e cotação."""
    base = {
        "Papel": ticker,
        "Cotação": "10,50",
        "P/L": "10,00",
        "P/VP": "2,00",
        "Div.Yield": "6,00%",
        "EV/EBIT": "5,00",
        "Mrg Bruta": "40,00%",
        "Mrg Ebit": "30,00%",
        "Mrg. Líq.": "20,00%",
        "ROIC": "30,00%",
        "ROE": "25,00%",
        "Liq.2meses": "1.000,00",
        "Dív.Líq/ Patrim.": "0,50",
        "Cresc. Rec.5a": "10,00%",
    }
    return linha_fundamentus(**(base | valores))


def novo_banco(tmp_path):
    con = duckdb.connect(str(tmp_path / "teste.duckdb"))
    gravar_bronze(
        con,
        "b3_empresas",
        [
            linha_b3(codeCVM="1", issuingCompany="BOAS", cnpj=CNPJ),
            linha_b3(codeCVM="2", issuingCompany="RUIM", cnpj="22222222000122"),
        ],
    )
    gravar_bronze(
        con,
        "fundamentus_acoes",
        [
            acao("BOAS3"),
            # ROE fora da faixa plausível, como os extremos reais do Fundamentus
            acao(
                "RUIM3",
                **{
                    "ROIC": "-5,00%",
                    "ROE": "-5.000,00%",
                    "Mrg Ebit": "-1,00%",
                    "Div.Yield": "0,00%",
                },
            ),
            # sem emissora na B3 e sem liquidez
            acao("PARA3", **{"Liq.2meses": "0,00"}),
        ],
    )
    gravar_bronze(
        con,
        "yfinance_cotacoes",
        [
            linha_yfinance(ticker="BOAS3", Date="2026-10-29 00:00:00-03:00"),
            linha_yfinance(
                ticker="BOAS3", Date="2026-10-30 00:00:00-03:00", Close="1.6"
            ),
        ],
    )
    gravar_bronze(con, "minhareceita_empresas", [linha_minhareceita(empresa(CNPJ))])
    t.executar(con)
    m.executar(con)
    return con


def por_nome(resultados):
    return {r.verificacao.nome: r for r in resultados}


@pytest.fixture(scope="module")
def modelo(tmp_path_factory):
    """Pipeline completo uma vez por módulo; cada teste recebe uma cópia do arquivo."""
    pasta = tmp_path_factory.mktemp("modelo")
    novo_banco(pasta).close()
    return pasta / "teste.duckdb"


@pytest.fixture
def banco(tmp_path, modelo):
    destino = tmp_path / "teste.duckdb"
    shutil.copyfile(modelo, destino)
    return destino


@pytest.fixture
def con(banco):
    conexao = duckdb.connect(str(banco))
    yield conexao
    conexao.close()


# --------------------------------------------------------------------------- caminho feliz


def test_pipeline_consistente_passa_sem_erros(con):
    resultados = q.executar(con)
    assert q.erros(resultados) == []
    reconciliacoes = [
        r
        for r in resultados
        if r.verificacao.camada in (q.RAW_REFINED, q.REFINED_MARTS)
    ]
    assert reconciliacoes and all(r.ok for r in reconciliacoes)
    assert q.exigir(con) == resultados


def test_catalogo_cobre_as_quatro_fontes_e_as_quatro_camadas():
    catalogo = q.verificacoes()
    camadas = {v.camada for v in catalogo}
    assert camadas == {
        q.RAW_REFINED,
        q.REFINED_MARTS,
        q.DOMINIO_REFINED,
        q.DOMINIO_MARTS,
    }
    nomes = " ".join(v.nome for v in catalogo)
    for fonte in (
        "b3_empresas",
        "fundamentus_acoes",
        "yfinance_cotacoes",
        "minhareceita_empresas",
    ):
        assert f"{fonte}: chaves distintas" in nomes
    assert len({v.nome for v in catalogo}) == len(catalogo)


# --------------------------------------------------------------------------- reconciliação


def test_linha_a_mais_na_bronze_quebra_a_reconciliacao_raw_refined(con):
    con.execute("INSERT INTO raw.fundamentus_acoes (Papel) VALUES ('NOVA3')")
    r = por_nome(q.executar(con))[
        "fundamentus_acoes: chaves distintas da Bronze = registros da Silver"
    ]
    assert r.status == "ERRO"
    assert r.exemplos == ((4, 3),)


def test_ingestao_diferente_entre_camadas_e_erro(con):
    con.execute(
        "UPDATE raw.b3_empresas SET _timestamp_ingestao = '2030-01-01T00:00:00+00:00'"
    )
    r = por_nome(q.executar(con))["b3_empresas: mesma ingestão nas duas camadas"]
    assert r.status == "ERRO"


def test_cotacao_perdida_na_gold_aparece_do_lado_esperado(con):
    con.execute(
        "DELETE FROM marts.marts_cotacao WHERE data = (SELECT MAX(data) FROM marts.marts_cotacao)"
    )
    r = por_nome(q.executar(con))[
        "marts_cotacao: mesmas chaves (ticker, data) da Silver"
    ]
    assert r.status == "ERRO"
    assert r.violacoes == 1
    assert r.exemplos[0][:2] == ("só no esperado", "BOAS3")


def test_card_divergente_de_marts_50_e_erro(con):
    con.execute(
        "UPDATE marts.marts_card_02_acoes_compra SET quantidade = quantidade + 1"
    )
    r = por_nome(q.executar(con))[
        "marts_card_02_acoes_compra: contagem de Compra em marts_50"
    ]
    assert r.status == "ERRO"


def test_ranking_com_ticker_fora_do_universo_e_erro(con):
    con.execute(
        "INSERT INTO marts.marts_01_rank_valor (rank, ticker) VALUES (1, 'PARA3')"
    )
    r = por_nome(q.executar(con))[
        "marts_01_rank_valor: tickers dentro do universo da consulta-base"
    ]
    assert r.status == "ERRO"
    assert r.exemplos == (("PARA3",),)


# --------------------------------------------------------------------------- domínio


def test_cotacao_zero_nas_recomendacoes_e_erro(con):
    con.execute("UPDATE marts.marts_50_rank_recomendacoes SET cotacao = 0")
    falhas = {r.verificacao.nome for r in q.erros(q.executar(con))}
    assert "marts_50: cotação > 0" in falhas


def test_recomendacao_incoerente_com_saldo_e_erro(con):
    con.execute(
        "UPDATE marts.marts_50_rank_recomendacoes SET recomendacao = 'Venda' WHERE saldo > 0"
    )
    falhas = {r.verificacao.nome for r in q.erros(q.executar(con))}
    assert "marts_50: recomendação coerente com o sinal do saldo" in falhas


def test_percentual_fora_da_faixa_plausivel_e_aviso_sem_bloquear(con):
    resultados = q.executar(con)
    r = por_nome(resultados)["Fundamentus: roe entre -100 e 100"]
    assert r.status == "AVISO"
    assert [e[0] for e in r.exemplos] == ["RUIM3"]
    assert q.erros(resultados) == []


def test_nulo_nao_viola_regra_de_dominio(con):
    con.execute("UPDATE refined.fundamentus_acoes SET dividend_yield = NULL")
    r = por_nome(q.executar(con))["Fundamentus: dividend yield não negativo"]
    assert r.ok


def test_dividend_yield_negativo_e_erro(con):
    con.execute(
        "UPDATE refined.fundamentus_acoes SET dividend_yield = -1 WHERE ticker = 'RUIM3'"
    )
    with pytest.raises(q.ErroQualidade) as erro:
        q.exigir(con)
    assert "dividend yield não negativo" in str(erro.value)


def test_tabela_ausente_e_erro_mesmo_em_verificacao_de_aviso(con):
    v = q.Verificacao(
        "aviso sobre tabela inexistente",
        q.DOMINIO_MARTS,
        q.AVISO,
        "SELECT * FROM marts.nao_existe",
    )
    [r] = q.executar(con, [v])
    assert r.status == "ERRO"
    assert "nao_existe" in r.falha


# --------------------------------------------------------------------------- comando


def _main(tmp_path, monkeypatch):
    monkeypatch.setenv(db.VARIAVEL_DB, str(tmp_path / "teste.duckdb"))
    with pytest.raises(SystemExit) as saida:
        q.main()
        raise SystemExit(0)
    return saida.value.code


def test_main_aprova_e_relata_avisos(banco, tmp_path, monkeypatch, caplog):
    with caplog.at_level("INFO", logger="pipeline.qualidade"):
        assert _main(tmp_path, monkeypatch) == 0
    assert "0 erro(s)" in caplog.text


def test_main_reprova_com_codigo_1(banco, tmp_path, monkeypatch, caplog):
    conexao = duckdb.connect(str(banco))
    conexao.execute("UPDATE marts.marts_50_rank_recomendacoes SET saldo = 99")
    conexao.close()
    with caplog.at_level("INFO", logger="pipeline.qualidade"):
        assert _main(tmp_path, monkeypatch) == 1
    assert "saldo entre -10 e +10" in caplog.text
    assert "Qualidade reprovada" in caplog.text


def test_main_sem_banco_encerra_com_codigo_1(tmp_path, monkeypatch):
    # read_only não cria o arquivo: banco inexistente é erro de conexão
    assert _main(tmp_path, monkeypatch) == 1
