-- Mart: Alavancagem
-- Fonte Silver: refined.fundamentus_acoes.divida_liquida_patrimonio (indicador pronto do Fundamentus)
-- Unidade: múltiplo (vezes) — dívida líquida / patrimônio líquido.
-- Nulos e negativos preservados conforme a origem (dívida líquida negativa = caixa líquido).
-- Grão: uma linha por ticker.
--
-- Indicador desconsiderado: divida_liquida_ebitda.
-- Justificativa: a Silver não possui dívida líquida nem EBITDA em valores monetários; o cálculo
-- exigiria novas fontes ou alteração da Silver, o que é vedado pela especificação.
SELECT
    ticker,
    divida_liquida_patrimonio
FROM refined.fundamentus_acoes
ORDER BY ticker;
