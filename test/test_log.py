"""Testes de pipeline/log.py: destino das mensagens por nível e reconfiguração sem duplicar."""

import logging

from pipeline import log


def test_info_vai_para_stdout_e_aviso_ou_erro_para_stderr(capsys):
    logger = log.configurar()
    logging.getLogger("pipeline.qualquer").info("relatório")
    logger.warning("[falha] item")
    logger.error("ERRO DE TESTE")
    saida = capsys.readouterr()
    assert saida.out == "relatório\n"
    assert saida.err == "[falha] item\nERRO DE TESTE\n"


def test_configurar_de_novo_nao_duplica_mensagens(capsys):
    log.configurar()
    log.configurar()
    logging.getLogger("pipeline.qualquer").info("uma vez")
    assert capsys.readouterr().out == "uma vez\n"


def test_logs_de_bibliotecas_nao_sao_promovidos(capsys):
    log.configurar()
    logging.getLogger("yfinance").warning("ruído da biblioteca")
    saida = capsys.readouterr()
    assert "ruído" not in saida.out
    assert "ruído" not in saida.err
