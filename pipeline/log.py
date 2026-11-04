"""Logging dos comandos do pipeline (python -m pipeline.<etapa>).

Os módulos registram em logging.getLogger(__name__); `configurar()` é chamado só no main().
Progresso e relatórios (até INFO) vão para stdout; avisos e erros, para stderr. Só a
mensagem é exibida, sem nível nem horário, para manter os relatórios legíveis.
Nunca registrar headers, tokens ou payloads completos.
"""

import logging
import sys

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
