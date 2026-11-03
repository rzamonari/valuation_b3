-- Mart: EV/EBIT (valor da firma sobre o resultado operacional)
-- Fonte Silver: refined.fundamentus_acoes.enterprise_value_ebit (indicador pronto do Fundamentus)
-- Unidade: múltiplo (vezes). Enterprise Value e EBIT não são recalculados.
-- Nulos e negativos preservados conforme a origem.
-- Grão: uma linha por ticker.
SELECT
    ticker,
    enterprise_value_ebit
FROM refined.fundamentus_acoes
ORDER BY ticker;
