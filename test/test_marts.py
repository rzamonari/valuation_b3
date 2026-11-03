"""Testes da materialização Gold. Usam banco DuckDB e pasta SQL temporários: o banco real não é tocado."""

import duckdb
import pytest

from pipeline import db
from pipeline import materializacao as m

SQL = {
    "marts_roic": "-- Grão: uma linha por ticker.\nSELECT ticker, roic FROM refined.fundamentus_acoes ORDER BY ticker;",
    "marts_card": "SELECT COUNT(*) AS quantidade FROM refined.fundamentus_acoes;",
    "marts_cotacao": "SELECT ticker, data, fechamento FROM refined.yfinance_cotacoes ORDER BY ticker, data;",
}
MARTS = [
    m.Mart("marts_roic", ("ticker",), m.FOTOGRAFIA),
    m.Mart("marts_card", (), m.LINHA_UNICA),
    m.Mart("marts_cotacao", ("ticker", "data"), m.SERIE),
]
TABELAS_GOLD = sorted(n for n in SQL)


def nova_pasta(tmp_path):
    destino = tmp_path / "marts"
    destino.mkdir()
    for nome, texto in SQL.items():
        # BOM como nos arquivos reais gravados pelo editor
        (destino / f"{nome}.sql").write_text(texto, encoding="utf-8-sig")
    return destino


def novo_banco(tmp_path):
    conexao = duckdb.connect(str(tmp_path / "teste.duckdb"))
    conexao.execute("CREATE SCHEMA raw")
    conexao.execute("CREATE TABLE raw.origem AS SELECT 1 AS x")
    conexao.execute("CREATE SCHEMA refined")
    conexao.execute(
        "CREATE TABLE refined.fundamentus_acoes (ticker VARCHAR, roic DECIMAL(6,2))"
    )
    conexao.execute(
        "INSERT INTO refined.fundamentus_acoes VALUES ('AAAA3', 10.5), ('BBBB4', NULL), ('CCCC3', -2.25)"
    )
    conexao.execute(
        "CREATE TABLE refined.yfinance_cotacoes (ticker VARCHAR, data TIMESTAMPTZ, fechamento DOUBLE)"
    )
    conexao.execute(
        "INSERT INTO refined.yfinance_cotacoes VALUES "
        "('AAAA3', '2026-10-29 00:00:00-03', 1.5), ('AAAA3', '2026-10-30 00:00:00-03', NULL), "
        "('BBBB4', '2026-10-29 00:00:00-03', 0.1)"
    )
    return conexao


def consultar(con, sql):
    return con.execute(sql).fetchall()


def foto(con, schema, tabelas):
    return {
        tab: consultar(con, f"SELECT * FROM {schema}.{db._ident(tab)} ORDER BY ALL")
        for tab in tabelas
    }


def tabelas_gold(con):
    return [
        n
        for (n,) in consultar(
            con,
            "SELECT table_name FROM duckdb_tables() WHERE schema_name = 'marts' ORDER BY 1",
        )
    ]


# --------------------------------------------------------------------------- inventário


def test_inventario_real_cobre_todos_os_arquivos():
    nomes = [mart.nome for mart in m.inventariar()]
    assert nomes == sorted(f.stem for f in m.PASTA_MARTS.glob("*.sql"))
    assert len(nomes) == len(set(nomes))


def test_sql_sem_chave_declarada_interrompe(tmp_path):
    con = novo_banco(tmp_path)
    pasta = nova_pasta(tmp_path)
    (pasta / "marts_novo.sql").write_text("SELECT 1 AS x", encoding="utf-8")
    with pytest.raises(m.ErroMaterializacao, match="sem chave lógica") as erro:
        m.executar(con, pasta, MARTS)
    assert "marts_novo.sql" in erro.value.exemplo
    assert tabelas_gold(con) == []


def test_mart_declarado_sem_arquivo_interrompe(tmp_path):
    con = novo_banco(tmp_path)
    pasta = nova_pasta(tmp_path)
    (pasta / "marts_card.sql").unlink()
    with pytest.raises(m.ErroMaterializacao, match="sem arquivo SQL"):
        m.executar(con, pasta, MARTS)


# --------------------------------------------------------------------------- materialização


def test_materializa_resultado_identico_a_consulta(tmp_path):
    con = novo_banco(tmp_path)
    pasta = nova_pasta(tmp_path)
    relatorio = m.executar(con, pasta, MARTS)
    assert tabelas_gold(con) == TABELAS_GOLD
    for nome, texto in SQL.items():
        consulta = texto.strip().removesuffix(";")
        assert consultar(con, f"DESCRIBE marts.{nome}") == consultar(
            con, f"DESCRIBE ({consulta})"
        )
        assert consultar(con, f"SELECT * FROM marts.{nome} ORDER BY ALL") == consultar(
            con, f"SELECT * FROM ({consulta}) ORDER BY ALL"
        )
    registros = {r["tabela"]: r["registros"] for r in relatorio["tabelas"]}
    assert registros == {
        "marts.marts_roic": 3,
        "marts.marts_card": 1,
        "marts.marts_cotacao": 3,
    }
    assert relatorio["orfas"] == []


def test_nulos_e_tipos_preservados(tmp_path):
    con = novo_banco(tmp_path)
    pasta = nova_pasta(tmp_path)
    m.executar(con, pasta, MARTS)
    assert consultar(
        con, "SELECT roic FROM marts.marts_roic WHERE ticker = 'BBBB4'"
    ) == [(None,)]
    tipos = {c[0]: c[1] for c in consultar(con, "DESCRIBE marts.marts_cotacao")}
    assert tipos == {
        "ticker": "VARCHAR",
        "data": "TIMESTAMP WITH TIME ZONE",
        "fechamento": "DOUBLE",
    }


def test_nova_execucao_substitui_sem_duplicar(tmp_path):
    con = novo_banco(tmp_path)
    pasta = nova_pasta(tmp_path)
    m.executar(con, pasta, MARTS)
    foto1 = foto(con, "marts", TABELAS_GOLD)
    m.executar(con, pasta, MARTS)
    assert foto(con, "marts", TABELAS_GOLD) == foto1
    con.execute("DELETE FROM refined.fundamentus_acoes WHERE ticker = 'CCCC3'")
    m.executar(con, pasta, MARTS)
    assert consultar(con, "SELECT ticker FROM marts.marts_roic ORDER BY 1") == [
        ("AAAA3",),
        ("BBBB4",),
    ]
    assert consultar(con, "SELECT * FROM marts.marts_card") == [(2,)]


def test_temporarias_removidas(tmp_path):
    con = novo_banco(tmp_path)
    pasta = nova_pasta(tmp_path)
    m.executar(con, pasta, MARTS)
    assert (
        consultar(con, "SELECT table_name FROM duckdb_tables() WHERE temporary") == []
    )


def test_raw_e_refined_permanecem_inalterados(tmp_path):
    con = novo_banco(tmp_path)
    pasta = nova_pasta(tmp_path)
    antes = foto(con, "raw", ["origem"]) | foto(
        con, "refined", ["fundamentus_acoes", "yfinance_cotacoes"]
    )
    m.executar(con, pasta, MARTS)
    depois = foto(con, "raw", ["origem"]) | foto(
        con, "refined", ["fundamentus_acoes", "yfinance_cotacoes"]
    )
    assert depois == antes


def test_tabela_orfa_reportada_e_mantida(tmp_path):
    con = novo_banco(tmp_path)
    pasta = nova_pasta(tmp_path)
    con.execute("CREATE SCHEMA marts")
    con.execute("CREATE TABLE marts.antiga AS SELECT 1 AS x")
    relatorio = m.executar(con, pasta, MARTS)
    assert relatorio["orfas"] == ["antiga"]
    assert consultar(con, "SELECT * FROM marts.antiga") == [(1,)]


# --------------------------------------------------------------------------- chave lógica


def test_chave_duplicada_interrompe(tmp_path):
    con = novo_banco(tmp_path)
    pasta = nova_pasta(tmp_path)
    con.execute("INSERT INTO refined.fundamentus_acoes VALUES ('AAAA3', 1)")
    with pytest.raises(m.ErroMaterializacao, match="duplicada") as erro:
        m.executar(con, pasta, MARTS)
    assert erro.value.destino == "marts.marts_roic"
    assert "AAAA3" in erro.value.exemplo


def test_chave_duplicada_deixa_o_schema_marts_como_estava(tmp_path):
    con = novo_banco(tmp_path)
    pasta = nova_pasta(tmp_path)
    m.executar(con, pasta, MARTS)
    antes = foto(con, "marts", TABELAS_GOLD)
    # AAAA3 repetido na refined: o grão de marts_roic (ticker) deixa de ser único
    con.execute("INSERT INTO refined.fundamentus_acoes VALUES ('AAAA3', 1)")
    with pytest.raises(m.ErroMaterializacao):
        m.executar(con, pasta, MARTS)
    assert foto(con, "marts", TABELAS_GOLD) == antes


def test_chave_nula_interrompe(tmp_path):
    con = novo_banco(tmp_path)
    pasta = nova_pasta(tmp_path)
    con.execute("INSERT INTO refined.yfinance_cotacoes VALUES ('AAAA3', NULL, 1)")
    with pytest.raises(m.ErroMaterializacao, match="nula"):
        m.executar(con, pasta, MARTS)


def test_linha_unica_com_mais_de_uma_linha_interrompe(tmp_path):
    con = novo_banco(tmp_path)
    pasta = nova_pasta(tmp_path)
    (pasta / "marts_card.sql").write_text(
        "SELECT 1 AS q UNION ALL SELECT 2", encoding="utf-8"
    )
    with pytest.raises(m.ErroMaterializacao, match="linha única"):
        m.executar(con, pasta, MARTS)


def test_coluna_da_chave_ausente_interrompe(tmp_path):
    con = novo_banco(tmp_path)
    pasta = nova_pasta(tmp_path)
    (pasta / "marts_roic.sql").write_text(
        "SELECT roic FROM refined.fundamentus_acoes", encoding="utf-8"
    )
    with pytest.raises(m.ErroMaterializacao, match="ausente"):
        m.executar(con, pasta, MARTS)


# --------------------------------------------------------------------------- atomicidade


def test_erro_de_sql_preserva_versao_anterior(tmp_path):
    con = novo_banco(tmp_path)
    pasta = nova_pasta(tmp_path)
    m.executar(con, pasta, MARTS)
    antes = foto(con, "marts", TABELAS_GOLD)
    con.execute(
        "INSERT INTO refined.fundamentus_acoes VALUES ('DDDD3', 7)"
    )  # mudaria marts_roic...
    (pasta / "marts_cotacao.sql").write_text(
        "SELECT * FROM refined.nao_existe", encoding="utf-8"
    )
    with pytest.raises(m.ErroMaterializacao) as erro:  # ...mas outro mart falha
        m.executar(con, pasta, MARTS)
    assert erro.value.arquivo == "sql/marts/marts_cotacao.sql"
    assert foto(con, "marts", TABELAS_GOLD) == antes


def test_rollback_quando_publicacao_falha(tmp_path):
    con = novo_banco(tmp_path)
    pasta = nova_pasta(tmp_path)
    m.executar(con, pasta, MARTS)
    antes = foto(con, "marts", TABELAS_GOLD)
    con.execute("INSERT INTO refined.fundamentus_acoes VALUES ('DDDD3', 7)")
    preparadas = [m.preparar(con, mart, pasta) for mart in MARTS]
    preparadas[
        -1
    ].temporaria = "temp.main.nao_existe"  # a 3ª falha depois de 2 substituídas
    with pytest.raises(m.ErroMaterializacao, match="rollback executado"):
        m.publicar(con, preparadas)
    assert foto(con, "marts", TABELAS_GOLD) == antes


def test_divergencia_na_validacao_faz_rollback(tmp_path):
    con = novo_banco(tmp_path)
    pasta = nova_pasta(tmp_path)
    m.executar(con, pasta, MARTS)
    antes = foto(con, "marts", TABELAS_GOLD)
    preparadas = [m.preparar(con, mart, pasta) for mart in MARTS]
    preparadas[0].registros += 1  # simula contagem divergente da consulta
    with pytest.raises(m.ErroMaterializacao, match="registros gravados") as erro:
        m.publicar(con, preparadas)
    assert erro.value.etapa == "validação da publicação"
    assert foto(con, "marts", TABELAS_GOLD) == antes


def test_falha_encerra_com_codigo_1(tmp_path, monkeypatch):
    con = novo_banco(tmp_path)
    pasta = nova_pasta(tmp_path)
    # consulta quebrada: tabela inexistente
    (pasta / "marts_roic.sql").write_text(
        "SELECT * FROM refined.nao_existe", encoding="utf-8"
    )
    with pytest.raises(m.ErroMaterializacao) as erro:
        m.executar(con, pasta, MARTS)
    assert erro.value.arquivo == "sql/marts/marts_roic.sql"

    class SemFechar:
        def __getattr__(self, nome):
            return getattr(con, nome)

        def close(self):
            pass

    monkeypatch.setattr(db, "conectar", lambda: SemFechar())
    monkeypatch.setattr(m, "PASTA_MARTS", pasta)
    monkeypatch.setattr(m, "MARTS", MARTS)
    monkeypatch.setattr(m.executar, "__defaults__", (pasta, MARTS))
    with pytest.raises(SystemExit) as saida:
        m.main()
    assert saida.value.code == 1
    assert tabelas_gold(con) == []
