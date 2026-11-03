"""Testes do painel (sem streamlit): leitura, formato, filtros e gráficos.

A leitura usa um banco DuckDB temporário: o real não é tocado.
"""

import subprocess
import sys
from datetime import date, datetime
from decimal import Decimal

import duckdb
import pandas as pd
import pytest

import painel as p


def novo_banco(tmp_path, monkeypatch):
    arquivo = tmp_path / "teste.duckdb"
    con = duckdb.connect(str(arquivo))
    con.execute("CREATE SCHEMA marts")
    for nome in p.MARTS_OBRIGATORIOS:
        con.execute(f'CREATE TABLE marts."{nome}" AS SELECT 1 AS quantidade')
    con.execute(
        'CREATE OR REPLACE TABLE marts."marts_cotacao" AS '
        "SELECT * FROM (VALUES ('AAAA3', DATE '2026-10-30', 2.0), "
        "('AAAA3', DATE '2026-10-29', 1.0), ('BBBB4', DATE '2026-10-29', 9.0)) "
        "t(ticker, data, fechamento_ajustado)"
    )
    con.execute(
        'CREATE OR REPLACE TABLE marts."marts_card_02_acoes_compra" AS SELECT 95 AS quantidade'
    )
    # mesma coluna em raw/refined com valor diferente: o painel não pode lê-las
    con.execute("CREATE SCHEMA refined")
    con.execute(
        "CREATE TABLE refined.marts_card_02_acoes_compra AS SELECT -1 AS quantidade"
    )
    con.close()
    monkeypatch.setattr(p, "ARQUIVO_DB", arquivo)
    return arquivo


def test_ler_devolve_tabelas_marts(tmp_path, monkeypatch):
    novo_banco(tmp_path, monkeypatch)
    d = p.ler(p.MARTS_CARREGAR)
    assert set(d) == set(p.MARTS_CARREGAR)
    assert d["marts_card_02_acoes_compra"]["quantidade"].tolist() == [95]


def test_tabelas_faltando_vazio_quando_completo(tmp_path, monkeypatch):
    novo_banco(tmp_path, monkeypatch)
    assert p.tabelas_faltando() == []


def test_tabelas_faltando_lista_ausentes(tmp_path, monkeypatch):
    banco = novo_banco(tmp_path, monkeypatch)
    con = duckdb.connect(str(banco))
    con.execute('DROP TABLE marts."marts_cotacao"')
    con.execute('DROP TABLE marts."marts_01_rank_valor"')
    con.close()
    assert p.tabelas_faltando() == ["marts.marts_01_rank_valor", "marts.marts_cotacao"]


def test_tabelas_faltando_sem_schema_marts(tmp_path, monkeypatch):
    arquivo = tmp_path / "vazio.duckdb"
    duckdb.connect(str(arquivo)).close()
    monkeypatch.setattr(p, "ARQUIVO_DB", arquivo)
    assert p.tabelas_faltando() == [f"marts.{n}" for n in p.MARTS_OBRIGATORIOS]


def test_tabelas_faltando_sem_banco(tmp_path, monkeypatch):
    monkeypatch.setattr(p, "ARQUIVO_DB", tmp_path / "nao_existe.duckdb")
    assert p.tabelas_faltando() == ["nao_existe.duckdb"]
    assert not (tmp_path / "nao_existe.duckdb").exists()


def test_ler_cotacao_filtra_ticker(tmp_path, monkeypatch):
    novo_banco(tmp_path, monkeypatch)
    cot = p.ler_cotacao("AAAA3")
    assert sorted(cot["fechamento_ajustado"].tolist()) == [1.0, 2.0]
    assert set(cot["ticker"]) == {"AAAA3"}
    assert p.ler_cotacao("ZZZZ3").empty


def test_erro_de_leitura_informa_tabela(tmp_path, monkeypatch):
    banco = novo_banco(tmp_path, monkeypatch)
    con = duckdb.connect(str(banco))
    con.execute('DROP TABLE marts."marts_retorno_total_risco"')
    con.close()
    with pytest.raises(p.ErroMart) as erro:
        p.ler([p.MART_RISCO])
    assert erro.value.tabela == "marts.marts_retorno_total_risco"


def test_banco_bloqueado_por_outro_processo(tmp_path, monkeypatch):
    banco = novo_banco(tmp_path, monkeypatch)
    dono = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import duckdb, sys, time; c = duckdb.connect(sys.argv[1]); "
                "print('ok', flush=True); time.sleep(60)"
            ),
            str(banco),
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert dono.stdout.readline().strip() == "ok"
        with pytest.raises(p.BancoBloqueado):
            p.tabelas_faltando()
        with pytest.raises(p.BancoBloqueado):
            p.ler(p.MARTS_CARDS)
    finally:
        dono.kill()
        dono.wait()


# --------------------------------------------------------------------------- formato


def test_reais_usa_ponto_no_milhar_e_virgula_no_decimal():
    assert p.reais(1003862.14) == "R$ 1.003.862,14"
    assert p.reais(Decimal("12.5")) == "R$ 12,50"  # DECIMAL vindo do DuckDB
    assert p.reais(-3.2) == "R$ -3,20"  # negativo preservado


def test_reais_compacto_escolhe_bi_mi_e_mil():
    assert p.reais_compacto(1_200_000_000) == "R$ 1,2 bi"
    assert p.reais_compacto(12_340_000) == "R$ 12,3 mi"
    assert p.reais_compacto(850_000) == "R$ 850 mil"
    assert p.reais_compacto(999) == "R$ 999,00"  # abaixo de mil: valor cheio


def test_pct_nao_multiplica_por_100():
    assert p.pct(6.91) == "6,9%"  # percentual já está na escala 0–100
    assert p.pct(Decimal("70.5")) == "70,5%"
    assert p.pct(12.345, casas=2) == "12,35%"


def test_multiplo_e_numero_formatam_no_padrao_brasileiro():
    assert p.multiplo(8.42) == "8,4x"
    assert p.numero(1234567) == "1.234.567"
    assert p.numero(0.125, casas=3) == "0,125"


def test_data_br_aceita_date_datetime_texto_e_timestamp():
    assert p.data_br(date(2026, 1, 5)) == "05/01/2026"
    assert p.data_br(datetime(2026, 1, 5, 23, 59)) == "05/01/2026"
    assert p.data_br("2026-01-05") == "05/01/2026"
    assert p.data_br(pd.Timestamp("2026-01-05")) == "05/01/2026"


def test_valor_nulo_vira_traco_e_nunca_zero():
    funcoes = [p.reais, p.reais_compacto, p.pct, p.multiplo, p.numero, p.data_br]
    for nulo in (None, float("nan"), pd.NA, pd.NaT):
        assert [f(nulo) for f in funcoes] == ["—"] * len(funcoes)


# --------------------------------------------------------------------------- filtros


def ranking_inventado():
    return pd.DataFrame(
        {
            "ticker": ["AAAA3", "BBBB3", "CCCC3", "DDDD3"],
            "recomendacao": ["Compra", "Manter", "Venda", "Compra"],
            "segmento": ["Novo Mercado", "Nível 1", "Novo Mercado", "Nível 2"],
            # DDDD3 abaixo de R$ 100 mil; os demais acima de R$ 1 mi
            "liquidez_2_meses": [5_000_000, 2_000_000, 1_500_000, 50_000],
        }
    )


def test_filtrar_por_recomendacao_segmento_e_liquidez():
    df = ranking_inventado()
    assert p.filtrar(df, ["Compra"], [], None)["ticker"].tolist() == ["AAAA3", "DDDD3"]
    so_novo_mercado = p.filtrar(df, p.RECS_ANALISADAS, ["Novo Mercado"], None)
    assert so_novo_mercado["ticker"].tolist() == ["AAAA3", "CCCC3"]
    liquidas = p.filtrar(df, p.RECS_ANALISADAS, [], 100_000)
    assert liquidas["ticker"].tolist() == ["AAAA3", "BBBB3", "CCCC3"]


def test_filtrar_sem_recomendacao_selecionada_nao_deixa_linha():
    assert p.filtrar(ranking_inventado(), [], [], None).empty


# --------------------------------------------------------------------------- gráficos


def pontos(fig):
    return sum(len(trace.x) for trace in fig.data if trace.x is not None)


def indicadores_inventados():
    return pd.DataFrame(
        {
            "ticker": ["AAAA3", "BBBB3", "CCCC3", "DDDD3", "EEEE3"],
            "empresa": ["A", "B", "C", "D", "E"],
            "recomendacao": ["Compra", "Manter", "Venda", "Compra", "Venda"],
            # CCCC3: EV/EBIT negativo; DDDD3: ROIC zero → fora do desenho
            "enterprise_value_ebit": [5.0, 8.0, -2.0, 6.0, 12.0],
            "roic": [20.0, 12.0, 15.0, 0.0, 9.0],
            "preco_lucro": [8.0, 10.0, None, 7.0, 20.0],
            "dividend_yield": [6.0, 4.0, 2.0, None, 1.0],
            "roe": [18.0, 11.0, 5.0, 3.0, 7.0],
            "liquidez_2_meses": [1e6, 2e6, 3e6, 4e6, 5e6],
        }
    )


def test_valor_qualidade_desenha_so_ev_ebit_e_roic_positivos():
    fig = p.fig_valor_qualidade(indicadores_inventados())
    desenhados = sorted(t for trace in fig.data for t in trace.customdata[:, 0])
    assert pontos(fig) == 3
    assert desenhados == ["AAAA3", "BBBB3", "EEEE3"]


def rank_inventado(n):
    return pd.DataFrame(
        {
            "rank": list(
                range(n, 0, -1)
            ),  # chega fora de ordem: a função ordena por rank
            "ticker": [f"T{i:03d}3" for i in range(n)],
            "empresa": [f"Empresa {i}" for i in range(n)],
            "roic": [10.0 + i for i in range(n)],
            "enterprise_value_ebit": [5.0] * n,
            "margem_ebit": [30.0] * n,
            "margem_liquida": [10.0] * n,
        }
    )


def test_ranking_tematico_desenha_uma_barra_por_linha_ate_o_top_n():
    valor = p.RANKINGS[0]  # Valor: uma série (ROIC)
    assert pontos(p.fig_ranking_tematico(rank_inventado(4), valor)) == 4
    fig = p.fig_ranking_tematico(rank_inventado(20), valor)  # 20 linhas, top 15
    assert pontos(fig) == 15
    assert fig.data[0].y[0] == "T0193"  # rank 1 no topo


def test_ranking_tematico_de_eficiencia_tem_duas_series_por_ticker():
    eficiencia = next(r for r in p.RANKINGS if r["chave"] == "eficiencia")
    fig = p.fig_ranking_tematico(rank_inventado(3), eficiencia)
    assert [trace.name for trace in fig.data] == ["Margem EBIT", "Margem líquida"]
    assert pontos(fig) == 6  # 3 tickers × 2 margens


def test_tabela_ranking_tematico_ordena_por_rank_e_formata():
    vista = p.tabela_ranking_tematico(rank_inventado(3), p.RANKINGS[0])
    assert vista["rank"].tolist() == [1, 2, 3]
    assert vista["ROIC"].tolist() == ["12,0%", "11,0%", "10,0%"]
    assert vista["EV/EBIT"].tolist() == ["5,0x"] * 3


def test_radar_desenha_um_ponto_por_ranking():
    faixas = ["Superior", "Inferior", "Intermediário", "Não elegível", "Superior"] * 2
    linha = pd.Series({"recomendacao": "Compra", **dict(zip(p.FAIXA_COLUNAS, faixas))})
    radar = p.fig_radar(linha).data[0]
    # o polígono repete o primeiro ponto para fechar: 10 rankings distintos
    assert len(set(radar.theta)) == 10
    assert list(radar.r[:10]) == [p.FAIXA_CODIGO[f] for f in faixas]


def cotacao_inventada():
    return pd.DataFrame(
        {
            "data": pd.to_datetime(
                ["2026-01-05", "2026-01-02", "2026-01-06", "2026-01-07", "2026-01-08"]
            ),
            # 06/01 nulo e 07/01 negativo: inválidos, fora do desenho
            "fechamento_ajustado": [11.0, 10.0, None, -1.0, 12.0],
            "volume": [100, 200, 300, 400, 500],
            # provento em 05/01 (preço válido) e em 07/01 (preço inválido: não marca)
            "dividendos": [0.5, 0.0, 0.0, 0.3, 0.0],
        }
    )


def test_cotacao_omite_preco_nulo_ou_negativo_e_ordena_por_data():
    linha, proventos, volume = p.fig_cotacao(cotacao_inventada()).data
    assert list(linha.y) == [10.0, 11.0, 12.0]
    assert len(volume.x) == 3
    assert list(proventos.y) == [11.0]  # só o provento com preço válido


# --------------------------------------------------------------------------- cartões e tabela


def test_cartao_mostra_numero_formatado_e_dica():
    html = p.html_cartao(
        "Ações analisadas", 1234, "tickers negociados", p.AZUL, dica="ajuda"
    )
    assert ">1.234<" in html
    assert 'title="ajuda"' in html


def test_termometro_assume_a_cor_da_recomendacao_predominante():
    termometro = pd.DataFrame(
        {
            "recomendacao": ["Venda"],
            "quantidade": [6],
            "total": [10],
            "percentual": [60.0],
        }
    )
    html = p.html_termometro(termometro, compra=3, manter=1, venda=6)
    assert p.REC["Venda"]["cor"] in html
    assert "🔴 Venda / Risco" in html
    assert "60,0% das ações analisadas" in html
    assert "flex:6 1 0" in html  # barra da Venda proporcional à própria quantidade


def test_tabela_consolidado_ordena_por_posicao_e_traduz_faixas():
    faixas = {coluna: ["Superior", "Não elegível"] for coluna in p.FAIXA_COLUNAS}
    rec = pd.DataFrame(
        {
            "posicao": [2, 1],  # chega fora de ordem
            "recomendacao": ["Venda", "Compra"],
            "ticker": ["BBBB3", "AAAA3"],
            "empresa": ["B", "A"],
            "segmento": ["Nível 1", "Novo Mercado"],
            "cotacao": [10.0, 25.5],
            "liquidez_2_meses": [850_000, 12_340_000],
            "saldo": [-3, 4],
            **faixas,
        }
    )
    vista = p.tabela_consolidado(rec)
    assert vista["ticker"].tolist() == ["AAAA3", "BBBB3"]
    assert vista["recomendacao"].tolist() == [
        "🟢 Compra / Oportunidade",
        "🔴 Venda / Risco",
    ]
    assert vista["cotacao"].tolist() == ["R$ 25,50", "R$ 10,00"]
    assert vista["liquidez_2_meses"].tolist() == ["R$ 12,3 mi", "R$ 850 mil"]
    assert vista["faixa_valor"].tolist() == ["⚪ N/E", "🟢 Sup."]
