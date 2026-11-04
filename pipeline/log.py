"""Configuração do logging das etapas do pipeline (Bronze, Silver e Gold).

Decisões de implementação:
1. Só o logger "pipeline" é configurado; logs de bibliotecas (yfinance, urllib3) não são
   promovidos. Cada módulo registra em logging.getLogger("pipeline.<módulo>"), com nome fixo:
   executado com -m, __name__ seria "__main__" e as mensagens ficariam fora deste logger.
2. INFO vai para stdout e WARNING ou acima para stderr, como os print(..., file=sys.stderr)
   que substitui: quem redireciona a saída continua separando relatório de erro.
3. Formato só com a mensagem: os relatórios das etapas são tabelas alinhadas, e prefixos de
   data/nível quebrariam o alinhamento. O nível já é expresso pelo destino (stdout/stderr) e
   pelo texto ("ERRO DE ...", "[falha]", "[retry]").
4. Nunca registre headers, tokens ou payloads completos.
"""

import logging
import sys

LOGGER = "pipeline"


class _AbaixoDeAviso(logging.Filter):
    def filter(self, registro: logging.LogRecord) -> bool:
        return registro.levelno < logging.WARNING


def configurar(nivel: int = logging.INFO) -> logging.Logger:
    """(Re)configura o logger "pipeline"; chamar novamente não duplica as mensagens."""
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(encoding="utf-8")

    formato = logging.Formatter("%(message)s")
    saida = logging.StreamHandler(sys.stdout)
    saida.addFilter(_AbaixoDeAviso())
    erros = logging.StreamHandler(sys.stderr)
    erros.setLevel(logging.WARNING)
    for handler in (saida, erros):
        handler.setFormatter(formato)

    logger = logging.getLogger(LOGGER)
    logger.handlers = [saida, erros]
    logger.setLevel(nivel)
    logger.propagate = False
    return logger
