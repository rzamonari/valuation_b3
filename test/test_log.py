"""Testes de pipeline/log.py: destino das mensagens e configuração idempotente."""

import logging

import pytest

from pipeline import log


@pytest.fixture
def logger():
    raiz = log.configurar()
    yield raiz
    for handler in list(raiz.handlers):
        raiz.removeHandler(handler)


def test_info_vai_para_stdout_e_aviso_e_erro_para_stderr(logger, capsys):
    modulo = logging.getLogger("pipeline.qualquer")
    modulo.info("progresso")
    modulo.warning("aviso")
    modulo.error("erro")
    saida = capsys.readouterr()
    assert saida.out == "progresso\n"
    assert saida.err == "aviso\nerro\n"


def test_debug_fica_de_fora_no_nivel_padrao(logger, capsys):
    logging.getLogger("pipeline.qualquer").debug("detalhe")
    assert capsys.readouterr() == ("", "")


def test_configurar_de_novo_nao_duplica_mensagens(logger, capsys):
    log.configurar()
    logging.getLogger("pipeline.qualquer").info("uma vez")
    assert capsys.readouterr().out == "uma vez\n"


def test_logger_de_outra_biblioteca_nao_e_afetado(logger, capsys):
    logging.getLogger("yfinance").warning("ruído externo")
    assert "ruído externo" not in capsys.readouterr().err


def test_capturar_separa_avisos_e_erros_do_bloco(logger, capsys):
    modulo = logging.getLogger("pipeline.qualquer")
    modulo.warning("antes")
    with log.capturar() as captura:
        modulo.info("progresso")
        modulo.warning("  [retry 1/2] lento  ")
        modulo.error("\nERRO DE EXTRAÇÃO")
        logging.getLogger("yfinance").warning("de fora do pipeline")
    modulo.warning("depois")
    assert captura.avisos == ["[retry 1/2] lento"]
    assert captura.erros == ["ERRO DE EXTRAÇÃO"]
    capsys.readouterr()
