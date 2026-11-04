"""Logging dos comandos do pipeline (python -m pipeline.<etapa>).

Os módulos registram em logging.getLogger(__name__); `configurar()` é chamado só no main().
Progresso e relatórios (até INFO) vão para stdout; avisos e erros, para stderr. Só a
mensagem é exibida, sem nível nem horário, para manter os relatórios legíveis.
Nunca registrar headers, tokens ou payloads completos.

`capturar()` guarda os avisos e erros emitidos durante um bloco: é a fonte dos avisos e do
erro do registro de execução (pipeline.execucao), sem repetir a mensagem em cada etapa.
"""

import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

RAIZ = "pipeline"


class _Saida(logging.StreamHandler):
    """Escreve no sys.stdout/sys.stderr vigente, mesmo se ele for trocado depois."""

    def __init__(self, nome):
        self._nome = nome
        super().__init__()

    @property
    def stream(self):
        return getattr(sys, self._nome)

    @stream.setter
    def stream(self, _valor):
        pass  # o destino é sempre o atributo atual de sys


class _AteInfo(logging.Filter):
    def filter(self, registro: logging.LogRecord) -> bool:
        return registro.levelno < logging.WARNING


def configurar(nivel: int = logging.INFO) -> logging.Logger:
    """Configura o logger raiz do pipeline; chamar de novo não duplica handlers."""
    logger = logging.getLogger(RAIZ)
    logger.setLevel(nivel)
    for handler in [h for h in logger.handlers if isinstance(h, _Saida)]:
        logger.removeHandler(handler)

    saida = _Saida("stdout")
    saida.addFilter(_AteInfo())
    erros = _Saida("stderr")
    erros.setLevel(logging.WARNING)
    for handler in (saida, erros):
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    return logger


@dataclass
class Captura:
    """Mensagens de aviso e de erro registradas sob o logger do pipeline."""

    avisos: list[str] = field(default_factory=list)
    erros: list[str] = field(default_factory=list)


class _Capturar(logging.Handler):
    def __init__(self, captura: Captura):
        super().__init__(logging.WARNING)
        self._captura = captura

    def emit(self, registro: logging.LogRecord) -> None:
        mensagem = registro.getMessage().strip()
        if registro.levelno == logging.WARNING:
            self._captura.avisos.append(mensagem)
        else:
            self._captura.erros.append(mensagem)


@contextmanager
def capturar() -> Iterator[Captura]:
    """Guarda em Captura os avisos e erros do logger do pipeline emitidos dentro do bloco."""
    captura = Captura()
    handler = _Capturar(captura)
    logger = logging.getLogger(RAIZ)
    logger.addHandler(handler)
    try:
        yield captura
    finally:
        logger.removeHandler(handler)
