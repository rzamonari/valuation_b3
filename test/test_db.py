"""Testes de pipeline/db.py. Banco DuckDB temporário em tmp_path: o banco real não é tocado."""

import duckdb
import pandas as pd

from pipeline import db


def apontar_banco(tmp_path, monkeypatch):
    arquivo = tmp_path / "teste.duckdb"
    monkeypatch.setattr(db, "_ARQUIVO_DB", arquivo)
    return arquivo


def test_conectar_abre_o_banco_do_caminho_configurado(tmp_path, monkeypatch):
    arquivo = apontar_banco(tmp_path, monkeypatch)
    con = db.conectar()
    con.execute("CREATE TABLE t AS SELECT 1 AS x")
    con.close()
    # o arquivo foi criado no caminho configurado e guarda o que foi gravado
    assert arquivo.exists()
    outra = duckdb.connect(str(arquivo))
    assert outra.execute("SELECT x FROM t").fetchall() == [(1,)]
    outra.close()


def test_criar_schema_duas_vezes_nao_falha(tmp_path, monkeypatch):
    apontar_banco(tmp_path, monkeypatch)
    con = db.conectar()
    db.criar_schema(con, "raw")
    db.criar_schema(con, "raw")  # segunda chamada: idempotente
    schemas = con.execute(
        "SELECT schema_name FROM duckdb_schemas() WHERE schema_name = 'raw'"
    ).fetchall()
    con.close()
    assert schemas == [("raw",)]


def test_gravar_converte_todas_as_colunas_para_varchar_e_preserva_nulo(
    tmp_path, monkeypatch
):
    apontar_banco(tmp_path, monkeypatch)
    con = db.conectar()
    db.criar_schema(con, "raw")
    df = pd.DataFrame(
        {
            "ticker": ["ABCD3", "WXYZ4"],
            "preco": [10.5, None],  # segunda linha: preço ausente vira NULL, não "nan"
            "volume": [100, 200],  # inteiro também vira texto
        },
        dtype=object,
    )
    gravados = db.gravar(con, df, "raw", "cotacoes")
    tipos = con.execute(
        "SELECT column_name, column_type FROM (DESCRIBE raw.cotacoes)"
    ).fetchall()
    linhas = con.execute("SELECT * FROM raw.cotacoes ORDER BY ticker").fetchall()
    con.close()
    assert gravados == 2
    assert tipos == [("ticker", "VARCHAR"), ("preco", "VARCHAR"), ("volume", "VARCHAR")]
    assert linhas == [("ABCD3", "10.5", "100"), ("WXYZ4", None, "200")]


def test_gravar_de_novo_substitui_a_tabela_sem_acumular(tmp_path, monkeypatch):
    apontar_banco(tmp_path, monkeypatch)
    con = db.conectar()
    db.criar_schema(con, "raw")
    db.gravar(con, pd.DataFrame({"x": ["a", "b", "c"]}), "raw", "t")
    gravados = db.gravar(
        con, pd.DataFrame({"x": ["d"]}), "raw", "t"
    )  # segunda carga, 1 linha
    linhas = con.execute("SELECT x FROM raw.t").fetchall()
    con.close()
    assert gravados == 1
    assert linhas == [("d",)]


def test_gravar_aceita_nome_de_coluna_com_aspas_e_espacos(tmp_path, monkeypatch):
    apontar_banco(tmp_path, monkeypatch)
    con = db.conectar()
    db.criar_schema(con, "raw")
    # cabeçalhos como os do Fundamentus: espaço, ponto e aspas
    df = pd.DataFrame({'Div. "Yield"': ["6,91%"], "Patrim. Líq": ["1.000,00"]})
    db.gravar(con, df, "raw", "fundamentus")
    colunas = [c[0] for c in con.execute("DESCRIBE raw.fundamentus").fetchall()]
    con.close()
    assert colunas == ['Div. "Yield"', "Patrim. Líq"]


def test_caminho_banco_sem_variavel_usa_o_arquivo_padrao_na_raiz(monkeypatch):
    monkeypatch.delenv(db.VARIAVEL_DB, raising=False)
    assert db.caminho_banco() == db._RAIZ / "fundamentalistas.duckdb"


def test_caminho_banco_vazio_e_tratado_como_ausente(monkeypatch):
    monkeypatch.setenv(db.VARIAVEL_DB, "  ")
    assert db.caminho_banco() == db._RAIZ / "fundamentalistas.duckdb"


def test_caminho_banco_relativo_e_resolvido_a_partir_da_raiz(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # o diretório corrente não influencia
    monkeypatch.setenv(db.VARIAVEL_DB, "dados/outro.duckdb")
    assert db.caminho_banco() == db._RAIZ / "dados" / "outro.duckdb"


def test_caminho_banco_absoluto_e_usado_como_veio(monkeypatch, tmp_path):
    arquivo = tmp_path / "homologacao.duckdb"
    monkeypatch.setenv(db.VARIAVEL_DB, str(arquivo))
    assert db.caminho_banco() == arquivo
