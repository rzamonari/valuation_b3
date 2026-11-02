-- Mart: P/L e Earnings Yield
-- Fonte Silver: refined.fundamentus_acoes.preco_lucro (indicador pronto do Fundamentus)
--
-- preco_lucro     : múltiplo (vezes), valor original do Fundamentus.
-- earnings_yield  : DERIVADO na Gold, percentual na escala 0–100.
--                   Fórmula: earnings_yield = 100.0 / preco_lucro
--                   P/L zero ou NULL -> earnings_yield NULL (sem divisão por zero).
--
-- P/L negativo é preservado (gera earnings yield negativo). Nenhum filtro de P/L negativo ou
-- acima de 50 é aplicado: a interpretação desses casos fica fora do cálculo.
-- Grão: uma linha por ticker.
SELECT
    ticker,
    preco_lucro,
    CASE
        WHEN preco_lucro = 0 THEN NULL
        ELSE 100.0 / preco_lucro
    END AS earnings_yield
FROM refined.fundamentus_acoes
ORDER BY ticker;
