-- Mart: Margens
-- Fontes Silver (indicadores prontos do Fundamentus, não recalculados):
--   refined.fundamentus_acoes.margem_ebit
--   refined.fundamentus_acoes.margem_liquida
--   refined.fundamentus_acoes.margem_bruta
-- Unidade: percentual na escala 0–100.
-- Nulos e negativos preservados conforme a origem.
-- Grão: uma linha por ticker.
--
-- Sem agrupamento setorial nesta versão: refined.b3_empresas.segmento é segmento de listagem
-- da B3, não classificação econômica, e a Silver não possui relação confiável ticker -> setor.
SELECT
    ticker,
    margem_ebit,
    margem_liquida,
    margem_bruta
FROM refined.fundamentus_acoes
ORDER BY ticker;
