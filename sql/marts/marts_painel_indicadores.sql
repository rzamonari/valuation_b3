-- Painel — Indicadores por ação analisada
-- Objetivo: indicadores do Fundamentus ao lado da recomendação, para a dispersão valor × qualidade
-- e a ficha da ação.
--
-- Universo e regra de recomendação: lidos de marts.marts_50_rank_recomendacoes (dependência
-- resolvida pela materialização), sem repetir a consulta-base, os rankings nem a regra.
-- Universo: ações analisadas (liquidez_2_meses > 0).
--
-- Indicadores: valores do Fundamentus preservados (percentuais na escala 0–100, múltiplos em
-- vezes), lidos de refined.fundamentus_acoes (ticker é único na tabela). Derivados, com a mesma
-- fórmula dos rankings 02 (Proventos) e 10 (Rentabilidade):
--   payout         = dividend_yield * preco_lucro
--   earnings_yield = 100 / preco_lucro (NULL quando P/L = 0)
--
-- Grão: uma linha por ticker analisado.
WITH recomendacoes AS (
    SELECT * FROM marts.marts_50_rank_recomendacoes
)
SELECT
    r.ticker,
    r.empresa,
    r.segmento,
    r.uf,
    r.recomendacao,
    r.saldo,
    r.liquidez_2_meses,
    r.cotacao,
    a.roic,
    a.roe,
    a.enterprise_value_ebit,
    a.preco_lucro,
    100.0 / NULLIF(a.preco_lucro, 0)    AS earnings_yield,
    a.preco_valor_patrimonial,
    a.dividend_yield,
    a.dividend_yield * a.preco_lucro    AS payout,
    a.margem_ebit,
    a.margem_liquida,
    a.divida_liquida_patrimonio,
    a.crescimento_receita_5_anos
FROM recomendacoes r
INNER JOIN refined.fundamentus_acoes a
    ON a.ticker = r.ticker
ORDER BY r.posicao, r.ticker;
