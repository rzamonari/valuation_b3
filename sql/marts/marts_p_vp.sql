-- Mart: P/VP e relação P/VP ÷ ROE
-- Fontes Silver:
--   refined.fundamentus_acoes.preco_valor_patrimonial (indicador pronto do Fundamentus)
--   refined.fundamentus_acoes.roe                     (indicador pronto do Fundamentus)
--
-- preco_valor_patrimonial : múltiplo (vezes), valor original do Fundamentus.
-- roe                     : percentual na escala 0–100, valor original do Fundamentus.
-- p_vp_por_roe            : DERIVADO na Gold. Múltiplo P/VP por ponto percentual de ROE.
--                           Fórmula: p_vp_por_roe = preco_valor_patrimonial / roe
--                           ROE zero ou NULL -> NULL (sem divisão por zero).
--
-- Negativos preservados. Valor justo pela equação de Gordon desconsiderado nesta versão
-- (Ke e crescimento perpétuo não possuem parâmetros aprovados).
-- Grão: uma linha por ticker.
SELECT
    ticker,
    preco_valor_patrimonial,
    roe,
    CASE
        WHEN roe = 0 THEN NULL
        ELSE preco_valor_patrimonial / roe
    END AS p_vp_por_roe
FROM refined.fundamentus_acoes
ORDER BY ticker;
