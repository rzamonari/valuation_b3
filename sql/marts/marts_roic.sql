-- Mart: ROIC (retorno sobre o capital investido)
-- Fonte Silver: refined.fundamentus_acoes.roic (indicador pronto do Fundamentus, não recalculado)
-- Unidade: percentual na escala 0–100 (ex.: 12.50 = 12,50%)
-- Nulos e negativos preservados conforme a origem. Sem classificação frente ao custo de capital
-- (a faixa de 14%–16% é apenas diretriz de interpretação, não regra de cálculo).
-- Grão: uma linha por ticker (chave lógica da tabela de origem).
SELECT
    ticker,
    roic
FROM refined.fundamentus_acoes
ORDER BY ticker;
