-- Mart: ROE (retorno sobre o patrimônio líquido)
-- Fonte Silver: refined.fundamentus_acoes.roe (indicador pronto do Fundamentus, não recalculado)
-- Unidade: percentual na escala 0–100.
-- Nulos e negativos preservados conforme a origem. Sem classificação automática de alavancagem
-- (ROE muito acima do ROIC é apenas diretriz de interpretação).
-- Grão: uma linha por ticker.
SELECT
    ticker,
    roe
FROM refined.fundamentus_acoes
ORDER BY ticker;
