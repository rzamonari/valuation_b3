"""Testes do registro de execução (meta.execucoes), do mart de saúde e da idade dos dados.

Banco DuckDB em tmp_path; o mart é o sql/marts/marts_painel_saude_pipeline.sql real,
publicado por materializacao.atualizar como no pipeline. O banco real não é tocado.
"""

import logging
import sys
from datetime import date, datetime

import duckdb
import pandas as pd
import pytest

from pipeline import db
from pipeline import execucao as e
from pipeline import materializacao as m

SAUDE = f"marts.{e.MART_SAUDE}"


@pytest.fixture
def arquivo(tmp_path, monkeypatch):
    """Banco vazio em tmp_path como banco padrão do pipeline."""
    caminho = tmp_path / "teste.duckdb"
    duckdb.connect(str(caminho)).close()
    monkeypatch.setattr(db, "_ARQUIVO_DB", caminho)
    return caminho


def ler(arquivo, sql):
    con = duckdb.connect(str(arquivo), read_only=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def saude(arquivo):
    """{etapa: linha do mart como dict}."""
    con = duckdb.connect(str(arquivo), read_only=True)
    try:
        df = con.execute(f"SELECT * FROM {SAUDE} ORDER BY ordem").df()
    finally:
        con.close()
    return {linha["etapa"]: linha for linha in df.to_dict("records")}


def execucao(etapa, inicio, status=e.SUCESSO, tabelas=None, avisos=(), erro=None):
    """Execução concluída com início fixo (testes determinísticos)."""
    registro = e.Execucao(etapa, inicio_utc=inicio)
    registro.tabelas = dict(tabelas or {})
    registro.concluir(status, list(avisos), erro)
    registro.fim_utc = inicio.replace(second=inicio.second + 30)
    registro.duracao_s = 30.0
    return registro


# --------------------------------------------------------------------------- registrada


def test_etapa_com_sucesso_grava_linhas_por_tabela_e_avisos_do_log(arquivo):
    with e.registrada("transformacao") as registro:
        logging.getLogger("pipeline.transformacao").warning("  [retry 1/2] fonte lenta")
        registro.tabelas = {"refined.a": 3, "refined.b": 4}
    [linha] = ler(
        arquivo,
        "SELECT etapa, status, linhas_por_tabela, avisos, erro, duracao_s >= 0, "
        "fim_utc >= inicio_utc FROM meta.execucoes",
    )
    assert linha == (
        "transformacao",
        "sucesso",
        [{"tabela": "refined.a", "linhas": 3}, {"tabela": "refined.b", "linhas": 4}],
        ["[retry 1/2] fonte lenta"],
        None,
        True,
        True,
    )


def test_sys_exit_1_registra_falha_com_o_erro_do_log_e_mantem_o_codigo(arquivo):
    with pytest.raises(SystemExit) as saida, e.registrada("materializacao"):
        logging.getLogger("pipeline.materializacao").error("\nERRO DE MATERIALIZAÇÃO")
        sys.exit(1)
    assert saida.value.code == 1
    assert ler(
        arquivo, "SELECT status, erro, linhas_por_tabela FROM meta.execucoes"
    ) == [("falha", "ERRO DE MATERIALIZAÇÃO", [])]


def test_excecao_sem_log_registra_tipo_e_mensagem_e_segue_adiante(arquivo):
    with pytest.raises(ValueError), e.registrada("ingestao"):
        raise ValueError("payload inesperado")
    assert ler(arquivo, "SELECT status, erro FROM meta.execucoes") == [
        ("falha", "ValueError: payload inesperado")
    ]


def test_sys_exit_0_e_sucesso(arquivo):
    with pytest.raises(SystemExit), e.registrada("qualidade"):
        sys.exit(0)
    assert ler(arquivo, "SELECT status FROM meta.execucoes") == [("sucesso",)]


def test_avisos_informados_pela_etapa_prevalecem_sobre_o_log(arquivo):
    with e.registrada("qualidade") as registro:
        logging.getLogger("pipeline.qualidade").warning("linha do relatório")
        registro.avisos = ["roe plausível: 2 violação(ões)"]
    assert ler(arquivo, "SELECT avisos FROM meta.execucoes") == [
        (["roe plausível: 2 violação(ões)"],)
    ]


def test_avisos_acima_do_limite_viram_resumo_e_erro_e_truncado():
    registro = e.Execucao("ingestao")
    registro.concluir(
        e.FALHA, [f"falha {i}" for i in range(e.LIMITE_AVISOS + 3)], "x" * 5000
    )
    assert len(registro.avisos) == e.LIMITE_AVISOS + 1
    assert registro.avisos[-1] == "… e mais 3 aviso(s)"
    assert len(registro.erro) == e.LIMITE_ERRO


def test_concluir_de_novo_com_o_mesmo_status_nao_muda_o_fim():
    registro = e.Execucao("fotografia")
    registro.concluir(e.SUCESSO, [])
    fim, duracao = registro.fim_utc, registro.duracao_s
    registro.concluir(e.SUCESSO, ["ignorado"])
    assert (registro.fim_utc, registro.duracao_s, registro.avisos) == (fim, duracao, [])
    registro.concluir(e.FALHA, [], "falhou depois do manifesto")
    assert registro.status == e.FALHA


# --------------------------------------------------------------------------- registrar


def test_sem_banco_nao_grava_nem_cria_o_arquivo(tmp_path, monkeypatch, caplog):
    caminho = tmp_path / "nao_existe.duckdb"
    monkeypatch.setattr(db, "_ARQUIVO_DB", caminho)
    with e.registrada("ingestao"):
        pass
    assert not caminho.exists()
    assert "banco nao_existe.duckdb inexistente" in caplog.text


def test_falha_ao_gravar_vira_aviso_sem_alterar_o_resultado(
    arquivo, monkeypatch, caplog
):
    def bloqueado():
        raise duckdb.IOException("Could not set lock on file\nsegunda linha")

    monkeypatch.setattr(db, "conectar", bloqueado)
    with e.registrada("qualidade"):
        pass
    assert "Registro de execução não gravado: Could not set lock on file" in caplog.text
    assert "segunda linha" not in caplog.text


def test_erro_no_mart_de_saude_vira_aviso(arquivo, monkeypatch, caplog):
    def quebrar(con, nomes):
        raise m.ErroMaterializacao("validação da chave", "chave duplicada")

    monkeypatch.setattr(m, "atualizar", quebrar)
    assert e.registrar(execucao("ingestao", datetime(2026, 11, 2, 9))) is False
    assert "chave duplicada" in caplog.text


# --------------------------------------------------------------------------- mart de saúde


def test_mart_tem_uma_linha_por_etapa_mesmo_sem_registro(arquivo):
    assert e.registrar(
        execucao(
            "ingestao", datetime(2026, 11, 2, 9), tabelas={"raw.a": 10, "raw.b": 5}
        )
    )
    linhas = saude(arquivo)
    assert list(linhas) == ["ingestao", "transformacao", "materializacao", "qualidade"]
    ingestao = linhas["ingestao"]
    assert (
        ingestao["camada"],
        ingestao["status"],
        ingestao["tabelas"],
        ingestao["linhas"],
    ) == (
        "raw",
        "sucesso",
        2,
        15,
    )
    assert ingestao["duracao_s"] == 30.0
    assert pd.isna(linhas["transformacao"]["status"])
    assert pd.isna(linhas["qualidade"]["camada"])


def test_mart_mostra_a_ultima_execucao_e_o_ultimo_sucesso(arquivo):
    e.registrar(
        execucao("materializacao", datetime(2026, 11, 1, 9), tabelas={"marts.x": 1})
    )
    e.registrar(
        execucao("materializacao", datetime(2026, 11, 2, 9), e.FALHA, erro="quebrou")
    )
    linha = saude(arquivo)["materializacao"]
    assert (linha["status"], linha["erro"], linha["inicio_utc"]) == (
        "falha",
        "quebrou",
        datetime(2026, 11, 2, 9),
    )
    assert linha["ultimo_sucesso_utc"] == datetime(2026, 11, 1, 9)
    assert pd.isna(linha["tabelas"])


def test_mart_conta_e_lista_os_avisos_da_qualidade(arquivo):
    avisos = ["roe plausível: 2 violação(ões)", "margens plausíveis: 1 violação(ões)"]
    e.registrar(execucao("qualidade", datetime(2026, 11, 2, 9), avisos=avisos))
    linha = saude(arquivo)["qualidade"]
    assert linha["avisos"] == 2
    assert list(linha["lista_avisos"]) == avisos
    assert pd.isna(linha["linhas"])  # a qualidade não publica tabelas


def test_materializacao_completa_cria_meta_execucoes_vazia(tmp_path):
    con = duckdb.connect(str(tmp_path / "x.duckdb"))
    try:
        e.garantir_tabela(con)
        m.atualizar(con, [e.MART_SAUDE])
        assert con.execute(
            f"SELECT COUNT(*), COUNT(status) FROM {SAUDE}"
        ).fetchall() == [(4, 0)]
    finally:
        con.close()


def test_atualizar_mart_nao_declarado_interrompe(tmp_path):
    con = duckdb.connect()
    try:
        with pytest.raises(m.ErroMaterializacao, match="não declarado"):
            m.atualizar(con, ["marts_que_nao_existe"])
    finally:
        con.close()


# --------------------------------------------------------------------------- ultimas


def test_ultimas_sem_tabela_e_vazio():
    con = duckdb.connect()
    try:
        assert e.ultimas(con) == []
    finally:
        con.close()


def test_ultimas_traz_a_mais_recente_por_etapa_na_ordem_do_pipeline(arquivo):
    e.registrar(execucao("qualidade", datetime(2026, 11, 2, 10)))
    e.registrar(execucao("ingestao", datetime(2026, 11, 1, 9), e.FALHA, erro="rede"))
    e.registrar(execucao("ingestao", datetime(2026, 11, 2, 9), tabelas={"raw.a": 1}))
    con = duckdb.connect(str(arquivo), read_only=True)
    try:
        ultimas = e.ultimas(con)
    finally:
        con.close()
    assert [(u["etapa"], u["status"], u["inicio_utc"]) for u in ultimas] == [
        ("ingestao", "sucesso", "2026-11-02T09:00:00"),
        ("qualidade", "sucesso", "2026-11-02T10:00:00"),
    ]
    assert ultimas[0]["linhas_por_tabela"] == {"raw.a": 1}


def test_como_dict_e_serializavel():
    registro = execucao(
        "fotografia", datetime(2026, 11, 2, 9), tabelas={"f/a.parquet": 2}
    )
    assert registro.como_dict() == {
        "etapa": "fotografia",
        "inicio_utc": "2026-11-02T09:00:00",
        "fim_utc": "2026-11-02T09:00:30",
        "duracao_s": 30.0,
        "status": "sucesso",
        "linhas_por_tabela": {"f/a.parquet": 2},
        "avisos": [],
        "erro": None,
    }


# --------------------------------------------------------------------------- idade dos dados


@pytest.mark.parametrize(
    ("referencia", "hoje", "corridos", "uteis"),
    [
        (date(2026, 11, 2), date(2026, 11, 2), 0, 0),  # mesmo dia
        (date(2026, 10, 30), date(2026, 11, 2), 3, 1),  # sexta -> segunda
        (date(2026, 10, 31), date(2026, 11, 1), 1, 0),  # sábado -> domingo
        (date(2026, 10, 26), date(2026, 11, 2), 7, 5),  # uma semana
        (
            date(2026, 11, 3),
            date(2026, 11, 2),
            -1,
            0,
        ),  # data no futuro não fica negativa
    ],
)
def test_idade_em_dias_corridos_e_uteis(referencia, hoje, corridos, uteis):
    idade = e.idade(referencia, hoje)
    assert (idade.dias_corridos, idade.dias_uteis) == (corridos, uteis)


def test_alerta_so_acima_do_limite_de_dias_uteis():
    assert not e.idade(date(2026, 10, 26), date(2026, 11, 2), limite=5).alerta
    assert e.idade(date(2026, 10, 23), date(2026, 11, 2), limite=5).alerta


def test_hoje_e_o_dia_em_brasilia():
    assert e.hoje_brasilia() == datetime.now(e.BRASILIA).date()
