"""Yahoo Finance (yfinance): mapeamento raw.yfinance_cotacoes -> refined.yfinance_cotacoes.

Convertida pelo motor genérico de tabelas SQL (comum.preparar_tabela_sql).
"""

from pipeline.transformacao.comum import BIGINT, DOUBLE, TIMESTAMP_TZ, Coluna, TabelaSql

TABELA = TabelaSql(
    "yfinance_cotacoes",
    "yfinance_cotacoes",
    (
        Coluna("ticker", "ticker"),
        Coluna("Date", "data", TIMESTAMP_TZ),
        Coluna("Open", "abertura", DOUBLE),
        Coluna("High", "maxima", DOUBLE),
        Coluna("Low", "minima", DOUBLE),
        Coluna("Close", "fechamento", DOUBLE),
        Coluna("Adj Close", "fechamento_ajustado", DOUBLE),
        Coluna("Volume", "volume", BIGINT),
        Coluna("Dividends", "dividendos", DOUBLE),
        Coluna("Stock Splits", "desdobramentos", DOUBLE),
        Coluna("_source_origin", "_source_origin"),
        Coluna("_timestamp_ingestao", "_timestamp_ingestao"),
        Coluna("Capital Gains", "ganhos_capital", DOUBLE),
    ),
    ("ticker", "data"),
)
