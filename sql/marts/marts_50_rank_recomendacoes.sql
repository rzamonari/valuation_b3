-- Recomendações consolidadas — Compra / Manter / Venda
-- Objetivo: consolidar os 10 rankings fundamentalistas (01 a 10) em uma única recomendação por
-- ticker, para o investidor iniciante, ordenada da melhor (Compra) para a pior (Venda).
--
-- Fontes:
--   Silver (universo e atributos): refined.fundamentus_acoes a  INNER JOIN refined.b3_empresas b
--                                  LEFT JOIN refined.minhareceita_empresas c  (consulta-base)
--   Gold (rankings): ticker e rank dos dez marts_NN_rank_*. A elegibilidade e o DENSE_RANK de cada
--                    tema vivem só no arquivo do ranking; a materialização prepara os dez antes
--                    deste (dependência marts.<nome>, ver pipeline/materializacao.py).
--
-- 1. Rankings: ticker ausente do mart do ranking = não elegível naquele tema.
--
-- 2. Faixa por ranking (posição relativa do rank, aritmética inteira, empates na mesma faixa):
--      Superior      (+1): (rank - 1) * 3 <  max_rank - 1, ou max_rank = 1  (terço melhor)
--      Intermediário  (0): demais elegíveis                                (terço do meio)
--      Inferior      (−1): (rank - 1) * 3 >  2 * (max_rank - 1)            (terço pior)
--      Não elegível  (−1): não atende à elegibilidade do ranking (perspectiva desfavorável)
--
-- 3. saldo = qtd_superior - qtd_inferior - qtd_nao_elegivel (−10 a +10; rankings com peso igual).
--    Recomendação: saldo > 0 -> Compra | saldo = 0 -> Manter | saldo < 0 -> Venda.
--
-- 4. Saída: apenas tickers com liquidez_2_meses > 0 (negociados nos últimos dois meses).
--    posicao = DENSE_RANK por saldo decrescente e qtd_superior decrescente.
--
-- Limitação: sinal relativo e mecânico, derivado apenas dos 10 rankings sobre uma única
-- fotografia do Fundamentus. Não considera preço-alvo, valor intrínseco, histórico, governança,
-- contexto setorial nem o perfil do investidor. NÃO constitui recomendação de investimento.
--
-- Grão: uma linha por ticker negociado.
WITH base AS (
    SELECT
        a.ticker,
        b.nome_pregao           AS empresa,
        b.razao_social,
        b.segmento,
        c.cnae_fiscal_descricao AS atividade,
        b.mercado,
        c.municipio,
        c.uf,
        c.natureza_juridica,
        c.data_inicio_atividade,
        b.situacao,
        a.cotacao,
        a.liquidez_2_meses
    FROM refined.fundamentus_acoes a
    INNER JOIN refined.b3_empresas b
        ON b.empresa_emissora = SUBSTRING(a.ticker, 1, 4)
    LEFT JOIN refined.minhareceita_empresas c
        ON c.cnpj = b.cnpj
),
ranks AS (
    SELECT 'valor'         AS ranking, ticker, rank FROM marts.marts_01_rank_valor
    UNION ALL SELECT 'proventos',      ticker, rank FROM marts.marts_02_rank_proventos
    UNION ALL SELECT 'eficiencia',     ticker, rank FROM marts.marts_03_rank_eficiencia
    UNION ALL SELECT 'retorno',        ticker, rank FROM marts.marts_04_rank_retorno
    UNION ALL SELECT 'pechincha',      ticker, rank FROM marts.marts_05_rank_pechincha
    UNION ALL SELECT 'patrimonio',     ticker, rank FROM marts.marts_06_rank_patrimonio
    UNION ALL SELECT 'crescimento',    ticker, rank FROM marts.marts_07_rank_crescimento
    UNION ALL SELECT 'operacional',    ticker, rank FROM marts.marts_08_rank_operacional
    UNION ALL SELECT 'seguro',         ticker, rank FROM marts.marts_09_rank_seguro
    UNION ALL SELECT 'rentabilidade',  ticker, rank FROM marts.marts_10_rank_rentabilidade
),
faixas_elegiveis AS (
    SELECT
        ranking,
        ticker,
        CASE
            WHEN max_rank = 1                         THEN 'Superior'
            WHEN (rank - 1) * 3 < max_rank - 1        THEN 'Superior'
            WHEN (rank - 1) * 3 > 2 * (max_rank - 1)  THEN 'Inferior'
            ELSE 'Intermediário'
        END AS faixa
    FROM (
        SELECT *, MAX(rank) OVER (PARTITION BY ranking) AS max_rank
        FROM ranks
    )
),
faixas AS (
    -- Todo ticker da consulta-base em todos os 10 rankings; ausência = Não elegível.
    SELECT
        t.ticker,
        r.ranking,
        COALESCE(f.faixa, 'Não elegível') AS faixa
    FROM base t
    CROSS JOIN (SELECT DISTINCT ranking FROM ranks) r
    LEFT JOIN faixas_elegiveis f
        ON f.ticker = t.ticker
       AND f.ranking = r.ranking
),
consolidado AS (
    SELECT
        ticker,
        COUNT(*) FILTER (WHERE faixa = 'Superior')      AS qtd_superior,
        COUNT(*) FILTER (WHERE faixa = 'Intermediário') AS qtd_intermediario,
        COUNT(*) FILTER (WHERE faixa = 'Inferior')      AS qtd_inferior,
        COUNT(*) FILTER (WHERE faixa = 'Não elegível')  AS qtd_nao_elegivel,
        ANY_VALUE(faixa) FILTER (WHERE ranking = 'valor')         AS faixa_valor,
        ANY_VALUE(faixa) FILTER (WHERE ranking = 'proventos')     AS faixa_proventos,
        ANY_VALUE(faixa) FILTER (WHERE ranking = 'eficiencia')    AS faixa_eficiencia,
        ANY_VALUE(faixa) FILTER (WHERE ranking = 'retorno')       AS faixa_retorno,
        ANY_VALUE(faixa) FILTER (WHERE ranking = 'pechincha')     AS faixa_pechincha,
        ANY_VALUE(faixa) FILTER (WHERE ranking = 'patrimonio')    AS faixa_patrimonio,
        ANY_VALUE(faixa) FILTER (WHERE ranking = 'crescimento')   AS faixa_crescimento,
        ANY_VALUE(faixa) FILTER (WHERE ranking = 'operacional')   AS faixa_operacional,
        ANY_VALUE(faixa) FILTER (WHERE ranking = 'seguro')        AS faixa_seguro,
        ANY_VALUE(faixa) FILTER (WHERE ranking = 'rentabilidade') AS faixa_rentabilidade
    FROM faixas
    GROUP BY ticker
),
saldo AS (
    SELECT
        *,
        qtd_superior - qtd_inferior - qtd_nao_elegivel AS saldo
    FROM consolidado
)
SELECT
    DENSE_RANK() OVER (ORDER BY s.saldo DESC, s.qtd_superior DESC) AS posicao,
    CASE
        WHEN s.saldo > 0 THEN 'Compra'
        WHEN s.saldo = 0 THEN 'Manter'
        ELSE 'Venda'
    END AS recomendacao,
    t.ticker,
    t.empresa,
    t.razao_social,
    t.segmento,
    t.atividade,
    t.mercado,
    t.municipio,
    t.uf,
    t.natureza_juridica,
    t.data_inicio_atividade,
    t.situacao,
    t.cotacao,
    t.liquidez_2_meses,
    s.saldo,
    s.qtd_superior,
    s.qtd_intermediario,
    s.qtd_inferior,
    s.qtd_nao_elegivel,
    s.faixa_valor,
    s.faixa_proventos,
    s.faixa_eficiencia,
    s.faixa_retorno,
    s.faixa_pechincha,
    s.faixa_patrimonio,
    s.faixa_crescimento,
    s.faixa_operacional,
    s.faixa_seguro,
    s.faixa_rentabilidade
FROM saldo s
INNER JOIN base t
    ON t.ticker = s.ticker
WHERE t.liquidez_2_meses > 0
ORDER BY posicao, s.ticker;
