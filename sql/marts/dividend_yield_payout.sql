-- Mart: Dividend Yield e Payout
-- Fontes Silver:
--   refined.fundamentus_acoes.dividend_yield (indicador pronto do Fundamentus)
--   refined.fundamentus_acoes.preco_lucro    (indicador pronto do Fundamentus)
--
-- dividend_yield : percentual na escala 0–100, valor original do Fundamentus.
-- payout         : DERIVADO na Gold, percentual na escala 0–100.
--                  Fórmula: payout = dividend_yield * preco_lucro
--                  Ex.: DY = 6 (6%) e P/L = 10 -> payout = 60 (60%).
--                  Qualquer componente NULL -> payout NULL (propagação natural do SQL).
--                  P/L zero -> payout zero (multiplicação, sem divisão).
--
-- Negativos preservados, sem filtros. O DY não é reconciliado com os proventos do YFinance
-- nesta versão (exigiria janela temporal, preço de referência e metodologia não definidos).
-- Grão: uma linha por ticker.
SELECT
    ticker,
    dividend_yield,
    dividend_yield * preco_lucro AS payout
FROM refined.fundamentus_acoes
ORDER BY ticker;
