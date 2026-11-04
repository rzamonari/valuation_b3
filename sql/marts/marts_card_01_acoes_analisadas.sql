-- Card 01 — Ações analisadas
-- Objetivo: quantidade de tickers negociados (liquidez_2_meses > 0) com recomendação, para o cartão do painel.
-- Fonte Gold: marts.marts_50_rank_recomendacoes (universo e regra de recomendação vivem
-- só nesse mart; a materialização o prepara antes deste).
--
-- Grão: uma linha.
SELECT COUNT(*) AS quantidade
FROM marts.marts_50_rank_recomendacoes;
