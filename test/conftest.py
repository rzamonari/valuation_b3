"""Configuração comum dos testes."""

import pytest

from pipeline import db


@pytest.fixture(autouse=True)
def sem_banco_do_ambiente(monkeypatch):
    """VALUATIONB3_DB do shell nunca vale nos testes: o banco real não pode ser tocado."""
    monkeypatch.delenv(db.VARIAVEL_DB, raising=False)
