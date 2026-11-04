-- Card 04 — Ações com recomendação de Venda
-- Objetivo: quantidade de tickers com recomendação Venda, para o cartão do painel.
-- Fonte Gold: marts.marts_50_rank_recomendacoes (universo e regra de recomendação vivem
-- só nesse mart; a materialização o prepara antes deste).
--
-- Grão: uma linha.
SELECT COUNT(*) AS quantidade
FROM marts.marts_50_rank_recomendacoes
WHERE recomendacao = 'Venda';
