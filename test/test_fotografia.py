"""Testes da fotografia versionada (exportação, verificação, leitura) e do painel sobre ela.

O banco de origem é o pipeline de ponta a ponta de test_qualidade, em tmp_path.
"""

import json
import shutil

import duckdb
import pytest
from test_qualidade import novo_banco

import painel as p
from pipeline import db, qualidade
from pipeline import fotografia as f
from pipeline import materializacao as m


@pytest.fixture(scope="module")
def modelo(tmp_path_factory):
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


@pytest.fixture
def foto(con, tmp_path):
    """Fotografia exportada em tmp_path/fotografia e o seu manifesto."""
    pasta = tmp_path / "fotografia"
    return pasta, f.exportar(con, pasta)


def colunas(con, relacao):
    return con.execute(f"DESCRIBE {relacao}").fetchall()


# --------------------------------------------------------------------------- exportação


def test_exporta_todos_os_marts_com_manifesto(con, foto):
    pasta, manifesto = foto
    assert sorted(manifesto["tabelas"]) == sorted(mart.nome for mart in m.MARTS)
    assert sorted(a.name for a in pasta.iterdir()) == sorted(
        [f.MANIFESTO] + [f"{mart.nome}.parquet" for mart in m.MARTS]
    )
    assert (
        manifesto["data_referencia"] == "2026-11-01"
    )  # 18:43 UTC = 15:43 em São Paulo
    assert manifesto["tabelas"]["marts_cotacao"]["registros"] == 2
    assert manifesto["qualidade"]["verificacoes"] == len(qualidade.verificacoes())
    assert json.loads((pasta / f.MANIFESTO).read_text(encoding="utf-8")) == manifesto
    assert not list(pasta.parent.glob(".fotografia.*"))  # temporárias removidas


def test_leitura_da_fotografia_e_identica_as_tabelas(con, foto):
    pasta, manifesto = foto
    leitura = f.conectar(pasta)
    try:
        for nome in manifesto["tabelas"]:
            consulta = f'SELECT {f.selecao(nome)} FROM marts."{nome}" ORDER BY ALL'
            tabela = con.execute(consulta).fetchall()
            assert leitura.execute(consulta).fetchall() == tabela, nome
            assert colunas(leitura, f'marts."{nome}"') == colunas(con, f"({consulta})")
    finally:
        leitura.close()


def test_cotacao_vai_so_com_as_colunas_do_painel(con, foto):
    pasta, manifesto = foto
    esperadas = list(f.COLUNAS["marts_cotacao"])
    assert manifesto["tabelas"]["marts_cotacao"]["colunas"] == esperadas
    assert "colunas" not in manifesto["tabelas"]["marts_roic"]
    leitura = f.conectar(pasta)
    try:
        lidas = [c[0] for c in colunas(leitura, "marts.marts_cotacao")]
    finally:
        leitura.close()
    assert lidas == esperadas
    assert len(colunas(con, "marts.marts_cotacao")) > len(
        esperadas
    )  # banco segue completo


def test_coluna_do_recorte_ausente_no_mart_interrompe_sem_alterar(con, foto):
    pasta, manifesto = foto
    con.execute("ALTER TABLE marts.marts_cotacao DROP COLUMN dividendos")
    with pytest.raises(duckdb.BinderException, match="dividendos"):
        f.exportar(con, pasta)
    assert f.verificar(pasta)["hash"] == manifesto["hash"]
    assert not list(pasta.parent.glob(".fotografia.*"))


def test_mesmos_dados_geram_o_mesmo_hash(con, foto, tmp_path):
    _, primeiro = foto
    segundo = f.exportar(con, tmp_path / "outra")
    assert segundo["hash"] == primeiro["hash"]
    assert {n: t["sha256"] for n, t in segundo["tabelas"].items()} == {
        n: t["sha256"] for n, t in primeiro["tabelas"].items()
    }


def test_dado_novo_muda_o_hash_e_substitui_a_fotografia(con, foto):
    pasta, primeiro = foto
    con.execute("UPDATE marts.marts_roic SET roic = roic + 1")
    segundo = f.exportar(con, pasta)
    assert segundo["hash"] != primeiro["hash"]
    assert f.verificar(pasta)["hash"] == segundo["hash"]


def test_qualidade_reprovada_nao_altera_a_fotografia(con, foto):
    pasta, manifesto = foto
    con.execute("UPDATE marts.marts_50_rank_recomendacoes SET cotacao = 0")
    with pytest.raises(qualidade.ErroQualidade):
        f.exportar(con, pasta)
    assert f.verificar(pasta)["hash"] == manifesto["hash"]


def test_tipo_sem_equivalente_em_parquet_interrompe_sem_alterar(con, foto):
    pasta, manifesto = foto
    con.execute(
        "CREATE OR REPLACE TABLE marts.marts_card_01_acoes_analisadas AS "
        "SELECT CAST(quantidade AS HUGEINT) AS quantidade FROM marts.marts_card_01_acoes_analisadas"
    )
    with pytest.raises(f.ErroFotografia, match="HUGEINT"):
        f.exportar(con, pasta)
    assert f.verificar(pasta)["hash"] == manifesto["hash"]
    assert not list(pasta.parent.glob(".fotografia.*"))


# --------------------------------------------------------------------------- verificação


def test_arquivo_alterado_e_detectado(foto):
    pasta, _ = foto
    with open(pasta / "marts_roic.parquet", "ab") as arquivo:
        arquivo.write(b"\0")
    with pytest.raises(
        f.ErroFotografia, match="marts_roic.parquet com hash divergente"
    ):
        f.verificar(pasta)


def test_arquivo_ausente_e_detectado(foto):
    pasta, _ = foto
    (pasta / "marts_cotacao.parquet").unlink()
    with pytest.raises(f.ErroFotografia, match="marts_cotacao.parquet ausente"):
        f.verificar(pasta)


def test_manifesto_adulterado_e_detectado(foto):
    pasta, manifesto = foto
    manifesto["tabelas"]["marts_roic"]["sha256"] = "0" * 64
    (pasta / f.MANIFESTO).write_text(json.dumps(manifesto), encoding="utf-8")
    with pytest.raises(f.ErroFotografia, match="hash total divergente"):
        f.verificar(pasta)


@pytest.mark.parametrize(
    ("conteudo", "motivo"),
    [(None, "não encontrado"), ("{", "inválido"), ('{"formato": 99}', "não suportado")],
)
def test_manifesto_ausente_ou_invalido(tmp_path, conteudo, motivo):
    if conteudo is not None:
        (tmp_path / f.MANIFESTO).write_text(conteudo, encoding="utf-8")
    with pytest.raises(f.ErroFotografia, match=motivo):
        f.verificar(tmp_path)


# --------------------------------------------------------------------------- comando


def _main(monkeypatch, argv):
    with pytest.raises(SystemExit) as saida:
        f.main(argv)
        raise SystemExit(0)
    return saida.value.code


def test_main_exporta_e_verifica(banco, tmp_path, monkeypatch, caplog):
    monkeypatch.setenv(db.VARIAVEL_DB, str(banco))
    monkeypatch.setattr(f, "PASTA_FOTOGRAFIA", tmp_path / "fotografia")
    with caplog.at_level("INFO", logger="pipeline.fotografia"):
        assert _main(monkeypatch, []) == 0
        assert _main(monkeypatch, ["--verificar"]) == 0
    assert "Fotografia gerada" in caplog.text
    assert "Fotografia íntegra" in caplog.text


def test_main_reprova_qualidade_com_codigo_1(banco, tmp_path, monkeypatch, caplog):
    conexao = duckdb.connect(str(banco))
    conexao.execute("UPDATE marts.marts_50_rank_recomendacoes SET saldo = 99")
    conexao.close()
    monkeypatch.setenv(db.VARIAVEL_DB, str(banco))
    monkeypatch.setattr(f, "PASTA_FOTOGRAFIA", tmp_path / "fotografia")
    assert _main(monkeypatch, []) == 1
    assert not (tmp_path / "fotografia").exists()
    assert "Qualidade reprovada" in caplog.text


def test_main_verificar_sem_fotografia_encerra_com_codigo_1(tmp_path, monkeypatch):
    monkeypatch.setattr(f, "PASTA_FOTOGRAFIA", tmp_path / "fotografia")
    assert _main(monkeypatch, ["--verificar"]) == 1


def test_main_sem_banco_encerra_com_codigo_1(tmp_path, monkeypatch):
    monkeypatch.setenv(db.VARIAVEL_DB, str(tmp_path / "nao_existe.duckdb"))
    assert _main(monkeypatch, []) == 1


# --------------------------------------------------------------------------- painel


@pytest.fixture
def painel_na_fotografia(foto, tmp_path, monkeypatch):
    pasta, manifesto = foto
    monkeypatch.setattr(p, "ARQUIVO_DB", tmp_path / "sem_banco.duckdb")
    monkeypatch.setattr(p, "PASTA_FOTOGRAFIA", pasta)
    return pasta, manifesto


def test_sem_banco_o_painel_le_a_fotografia(painel_na_fotografia):
    _, manifesto = painel_na_fotografia
    assert p.fonte() == p.FOTOGRAFIA
    assert p.tabelas_faltando() == []
    d = p.ler(p.MARTS_CARREGAR)
    assert d["marts_card_01_acoes_analisadas"]["quantidade"].tolist() == [2]
    cotacao = p.ler_cotacao("BOAS3")
    assert cotacao.columns.tolist() == list(f.COLUNAS["marts_cotacao"])
    assert len(cotacao) == 2
    assert p.fig_cotacao(cotacao).data  # o gráfico da ficha monta só com o recorte
    assert p.ler_cotacao("ZZZZ3").empty
    assert manifesto["hash"][:12] in p.origem()
    assert "01/11/2026" in p.origem()
    assert p.mensagem_faltando() == p.MSG_FOTOGRAFIA


def test_banco_presente_tem_prioridade_sobre_a_fotografia(
    painel_na_fotografia, banco, monkeypatch
):
    monkeypatch.setattr(p, "ARQUIVO_DB", banco)
    assert p.fonte() == p.BANCO
    assert "teste.duckdb" in p.origem()
    assert p.mensagem_faltando() == p.MSG_MATERIALIZAR


def test_variavel_de_ambiente_fixa_a_fonte(painel_na_fotografia, banco, monkeypatch):
    monkeypatch.setattr(p, "ARQUIVO_DB", banco)
    monkeypatch.setenv(p.VARIAVEL_FONTE, "Fotografia")
    assert p.fonte() == p.FOTOGRAFIA
    monkeypatch.setenv(p.VARIAVEL_FONTE, "nuvem")
    with pytest.raises(ValueError, match="nuvem"):
        p.fonte()


def test_fotografia_corrompida_interrompe_o_painel(painel_na_fotografia):
    pasta, _ = painel_na_fotografia
    with open(pasta / "marts_cotacao.parquet", "ab") as arquivo:
        arquivo.write(b"\0")
    with pytest.raises(p.FotografiaInvalida, match="hash divergente"):
        p.tabelas_faltando()


def test_fotografia_sem_mart_obrigatorio_aparece_como_faltando(painel_na_fotografia):
    pasta, manifesto = painel_na_fotografia
    del manifesto["tabelas"]["marts_cotacao"]
    manifesto["hash"] = f._hash_total(manifesto["tabelas"])
    (pasta / f.MANIFESTO).write_text(json.dumps(manifesto), encoding="utf-8")
    assert p.tabelas_faltando() == ["marts.marts_cotacao"]


def test_fotografia_sem_manifesto_na_leitura_vira_erro_do_painel(
    painel_na_fotografia, monkeypatch
):
    pasta, _ = painel_na_fotografia
    monkeypatch.setenv(p.VARIAVEL_FONTE, p.FOTOGRAFIA)
    (pasta / f.MANIFESTO).unlink()
    with pytest.raises(p.FotografiaInvalida, match="manifesto"):
        p.ler(p.MARTS_CARDS)
