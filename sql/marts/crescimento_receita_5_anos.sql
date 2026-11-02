-- Mart: Crescimento da receita em 5 anos
-- Fonte Silver: refined.fundamentus_acoes.crescimento_receita_5_anos (indicador pronto do Fundamentus)
-- Unidade: percentual na escala 0–100. O CAGR não é recalculado e não há projeção futura.
-- Nulos e negativos preservados conforme a origem.
-- Grão: uma linha por ticker.
SELECT
    ticker,
    crescimento_receita_5_anos
FROM refined.fundamentus_acoes
ORDER BY ticker;
