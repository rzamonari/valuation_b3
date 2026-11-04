-- Mart: Retorno total e risco histórico
-- Fonte Silver: refined.yfinance_cotacoes (ticker, data, fechamento, fechamento_ajustado,
--               dividendos)
--
-- Metodologia aprovada:
--   Janela      : 5 anos, terminando na última cotação disponível de cada ticker
--                 (data >= última data do ticker - INTERVAL 5 YEAR).
--   Preço       : fechamento_ajustado (retorno total). Preços NULL ou <= 0 são inválidos:
--                 não geram retorno, não entram no pico do drawdown nem no CAGR.
--                 Datas ausentes não são preenchidas; séries não se misturam entre tickers.
--
-- Ajuste retroativo inválido (decisão D1 da spec de indicadores, aprovada em 2026-11-04):
--   O Yahoo ajusta o passado pelo fator (1 - provento / fechamento anterior). Quando o
--   provento é >= fechamento anterior, o fator fica <= 0 e inverte o sinal de toda a série
--   anterior; trechos positivos entre duas inversões também ficam errados. Se a janela tem
--   alguma data com fechamento_ajustado <= 0 ou algum desses proventos, o ticker fica SEM
--   CÁLCULO: cagr, volatilidade_anualizada, max_drawdown, preco_inicial e preco_final NULL e
--   motivo_sem_calculo preenchido. Datas e contagens da janela continuam para rastreio.
--
-- Salto sem evento (decisão D2 da spec de indicadores, aprovada em 2026-11-04):
--   O fechamento do Yahoo já vem ajustado por desdobramento (razão mediana 1,0 nos dias com
--   desdobramento). Uma razão diária fechamento / fechamento anterior > 5 ou < 0,2 num dia sem
--   desdobramento nem provento é grupamento ou desdobramento não registrado, ou cotação
--   errada, e contamina o fechamento_ajustado. Com um salto assim na janela, o ticker também
--   fica SEM CÁLCULO; motivo_sem_calculo distingue D1, D2 ou os dois.
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
saltos AS (
    -- razão calculada antes do corte da janela: o salto do primeiro dia da janela conta
    SELECT ticker, data
    FROM (
        SELECT
            ticker,
            data,
            fechamento / LAG(fechamento) OVER (PARTITION BY ticker ORDER BY data) AS razao,
            desdobramentos > 0 OR dividendos > 0 AS evento
        FROM refined.yfinance_cotacoes
        WHERE fechamento > 0
    )
    WHERE NOT evento AND (razao > 5 OR razao < 0.2)
),
saltos_janela AS (
    SELECT DISTINCT s.ticker
    FROM saltos AS s
    JOIN limites AS l
        ON l.ticker = s.ticker
    WHERE s.data >= l.data_fim_janela - INTERVAL 5 YEAR
),
historico AS (
    -- fechamento anterior calculado antes do corte da janela: o provento do primeiro dia
    -- da janela também é comparado com o pregão anterior
    SELECT
        ticker,
        data,
        fechamento_ajustado,
        dividendos > 0
            AND dividendos >= LAG(fechamento) OVER (PARTITION BY ticker ORDER BY data)
            AS ajuste_invalido
    FROM refined.yfinance_cotacoes
),
janela AS (
    SELECT
        h.ticker,
        h.data,
        CASE
            WHEN h.fechamento_ajustado > 0 THEN h.fechamento_ajustado
        END AS preco,
        h.fechamento_ajustado <= 0 OR h.ajuste_invalido AS ajuste_invalido
    FROM historico AS h
    JOIN limites AS l
        ON l.ticker = h.ticker
    WHERE h.data >= l.data_fim_janela - INTERVAL 5 YEAR
),
serie AS (
    SELECT
        ticker,
        data,
        preco,
        ajuste_invalido,
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
        MIN(preco / pico - 1) AS drawdown_minimo,
        COALESCE(BOOL_OR(ajuste_invalido), FALSE) AS ajuste_invalido
    FROM serie
    GROUP BY ticker
),
calculo AS (
    SELECT
        r.*,
        sj.ticker IS NOT NULL AS salto_sem_evento,
        r.ajuste_invalido OR sj.ticker IS NOT NULL AS sem_calculo,
        (EPOCH(r.data_final) - EPOCH(r.data_inicial)) / 86400.0 / 365.25 AS anos
    FROM resumo AS r
    LEFT JOIN saltos_janela AS sj
        ON sj.ticker = r.ticker
)
SELECT
    ticker,
    data_inicial,
    data_final,
    anos,
    qtd_precos_validos,
    qtd_retornos,
    CASE WHEN NOT sem_calculo THEN preco_inicial END AS preco_inicial,
    CASE WHEN NOT sem_calculo THEN preco_final END AS preco_final,
    CASE
        WHEN NOT sem_calculo AND anos > 0
            THEN (POWER(preco_final / preco_inicial, 1.0 / anos) - 1) * 100
    END AS cagr,
    CASE
        WHEN NOT sem_calculo THEN desvio_retorno_diario * SQRT(252) * 100
    END AS volatilidade_anualizada,
    CASE WHEN NOT sem_calculo THEN drawdown_minimo * 100 END AS max_drawdown,
    CASE
        WHEN ajuste_invalido AND salto_sem_evento
            THEN 'Ajuste retroativo inválido do Yahoo (provento >= fechamento anterior); '
                || 'salto sem evento no fechamento (razão diária > 5 ou < 0,2)'
        WHEN ajuste_invalido
            THEN 'Ajuste retroativo inválido do Yahoo (provento >= fechamento anterior)'
        WHEN salto_sem_evento
            THEN 'Salto sem evento no fechamento (razão diária > 5 ou < 0,2)'
    END AS motivo_sem_calculo
FROM calculo
ORDER BY ticker;
