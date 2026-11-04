-- Card 05 — Termômetro de mercado
-- Objetivo: recomendação predominante entre as ações analisadas, para o cartão-resumo do painel.
--
-- Universo e regra de recomendação: lidos de marts.marts_50_rank_recomendacoes (dependência
-- resolvida pela materialização), sem repetir a consulta-base, os rankings nem a regra.
-- Universo: ações analisadas (liquidez_2_meses > 0).
--
-- Colunas:
--   recomendacao : Compra, Manter ou Venda com a maior quantidade de tickers.
--                  Empate na quantidade máxima -> 'Manter' (decisão do usuário, pendência P1).
--   quantidade   : tickers com a recomendação predominante.
--   total        : ações analisadas (igual ao card 01).
--   percentual   : quantidade * 100 / total, escala 0–100 (NULL se total = 0).
--
-- Grão: uma linha.
WITH recomendacoes AS (
    SELECT * FROM marts.marts_50_rank_recomendacoes
),
contagem AS (
    -- As três recomendações sempre presentes, com zero quando não houver tickers.
    SELECT
        r.recomendacao,
        COUNT(t.ticker) AS quantidade
    FROM (VALUES ('Compra'), ('Manter'), ('Venda')) AS r(recomendacao)
    LEFT JOIN recomendacoes t
        ON t.recomendacao = r.recomendacao
    GROUP BY r.recomendacao
),
resumo AS (
    SELECT
        MAX(quantidade)                                            AS maximo,
        COUNT(*) FILTER (WHERE quantidade = (SELECT MAX(quantidade) FROM contagem)) AS qtd_no_maximo,
        SUM(quantidade)                                            AS total
    FROM contagem
)
SELECT
    CASE
        WHEN s.qtd_no_maximo > 1 THEN 'Manter'
        ELSE (SELECT c.recomendacao FROM contagem c WHERE c.quantidade = s.maximo)
    END                                         AS recomendacao,
    s.maximo                                    AS quantidade,
    s.total                                     AS total,
    s.maximo * 100.0 / NULLIF(s.total, 0)       AS percentual
FROM resumo s;
