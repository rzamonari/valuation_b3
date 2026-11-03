-- Mart: Cotação por ação (histórico)
-- Fonte Silver: refined.yfinance_cotacoes (somente leitura)
--
-- Retorna as colunas de negócio da tabela sem transformação: valores originais,
-- nulos preservados, sem filtros de qualidade e sem preenchimento de datas ausentes.
-- Colunas técnicas de linhagem (_source_origin, _timestamp_ingestao) não são retornadas.
--
-- data                : TIMESTAMP WITH TIME ZONE, data da cotação.
-- abertura .. fechamento, fechamento_ajustado : preço por ação (R$), valores do YFinance.
-- volume              : quantidade negociada no pregão.
-- dividendos, desdobramentos, ganhos_capital : eventos do YFinance na data.
--
-- Grão: uma linha por (ticker, data). Ordem: ticker e data crescente.
SELECT
    ticker,
    data,
    abertura,
    maxima,
    minima,
    fechamento,
    fechamento_ajustado,
    volume,
    dividendos,
    desdobramentos,
    ganhos_capital
FROM refined.yfinance_cotacoes
ORDER BY ticker, data;
