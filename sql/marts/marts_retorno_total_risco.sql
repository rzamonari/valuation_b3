-- Mart: Retorno total e risco histórico
-- Fonte Silver: refined.yfinance_cotacoes (ticker, data, fechamento_ajustado)
--
-- Metodologia aprovada:
--   Janela      : 5 anos, terminando na última cotação disponível de cada ticker
--                 (data >= última data do ticker - INTERVAL 5 YEAR).
--   Preço       : fechamento_ajustado (retorno total). Preços NULL ou <= 0 são inválidos:
--                 não geram retorno, não entram no pico do drawdown nem no CAGR.
--                 Datas ausentes não são preenchidas; séries não se misturam entre tickers.
--
-- Indicadores (todos DERIVADOS na Gold, percentual na escala 0–100):
--   cagr                   = ((preco_final / preco_inicial) ^ (1 / anos) - 1) * 100
--                            preco_inicial/final = primeiro/último preço válido da janela;
--                            anos = (data_final - data_inicial) em dias / 365.25.
--                            NULL quando não há intervalo (anos = 0).
--   volatilidade_anualizada = stddev_samp(ln(P_t / P_t-1)) * sqrt(252) * 100
--                            Retorno logarítmico entre cotações consecutivas do ticker;
--                            NULL quando qualquer um dos dois preços é inválido.
--                            NULL com menos de 2 retornos.
--   max_drawdown           = min(P_t / max(P_0..P_t) - 1) * 100  (valor <= 0)
--
-- Sharpe desconsiderado nesta versão: não há taxa livre de risco nem metodologia aprovada.
-- Grão: uma linha por ticker presente em refined.yfinance_cotacoes.
WITH limites AS (
    SELECT
        ticker,
        MAX(data) AS data_fim_janela
    FROM refined.yfinance_cotacoes
    GROUP BY ticker
),
janela AS (
    SELECT
        c.ticker,
        c.data,
        CASE
            WHEN c.fechamento_ajustado > 0 THEN c.fechamento_ajustado
        END AS preco
    FROM refined.yfinance_cotacoes AS c
    JOIN limites AS l
        ON l.ticker = c.ticker
    WHERE c.data >= l.data_fim_janela - INTERVAL 5 YEAR
),
serie AS (
    SELECT
        ticker,
        data,
        preco,
        LN(preco / LAG(preco) OVER (PARTITION BY ticker ORDER BY data)) AS retorno_log,
        MAX(preco) OVER (
            PARTITION BY ticker ORDER BY data
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS pico
    FROM janela
),
resumo AS (
    SELECT
        ticker,
        MIN(data) FILTER (WHERE preco IS NOT NULL) AS data_inicial,
        MAX(data) FILTER (WHERE preco IS NOT NULL) AS data_final,
        ARG_MIN(preco, data) FILTER (WHERE preco IS NOT NULL) AS preco_inicial,
        ARG_MAX(preco, data) FILTER (WHERE preco IS NOT NULL) AS preco_final,
        COUNT(preco) AS qtd_precos_validos,
        COUNT(retorno_log) AS qtd_retornos,
        STDDEV_SAMP(retorno_log) AS desvio_retorno_diario,
        MIN(preco / pico - 1) AS drawdown_minimo
    FROM serie
    GROUP BY ticker
),
calculo AS (
    SELECT
        *,
        (EPOCH(data_final) - EPOCH(data_inicial)) / 86400.0 / 365.25 AS anos
    FROM resumo
)
SELECT
    ticker,
    data_inicial,
    data_final,
    anos,
    qtd_precos_validos,
    qtd_retornos,
    preco_inicial,
    preco_final,
    CASE
        WHEN anos > 0 THEN (POWER(preco_final / preco_inicial, 1.0 / anos) - 1) * 100
    END AS cagr,
    desvio_retorno_diario * SQRT(252) * 100 AS volatilidade_anualizada,
    drawdown_minimo * 100 AS max_drawdown
FROM calculo
ORDER BY ticker;
