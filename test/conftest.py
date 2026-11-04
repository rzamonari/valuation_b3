"""Configuração comum dos testes."""

import pytest

import painel
from pipeline import db


@pytest.fixture(autouse=True)
def sem_banco_do_ambiente(monkeypatch, tmp_path):
    """VALUATIONB3_DB do shell nunca vale nos testes: o banco real não pode ser tocado.

    Pelo mesmo motivo, a fonte do painel não vem do shell e a fotografia versionada do
    repositório fica fora de alcance (o teste que precisar dela cria a sua em tmp_path).
    O arquivo padrão do banco também aponta para tmp_path: o registro de execução
    (pipeline.execucao) de um main() testado nunca grava em fundamentalistas.duckdb.
    """
    monkeypatch.delenv(db.VARIAVEL_DB, raising=False)
    monkeypatch.setattr(db, "_ARQUIVO_DB", tmp_path / "sem_banco.duckdb")
    monkeypatch.delenv(painel.VARIAVEL_FONTE, raising=False)
    monkeypatch.setattr(painel, "PASTA_FOTOGRAFIA", tmp_path / "sem_fotografia")
