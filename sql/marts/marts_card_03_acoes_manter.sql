WITH recomendacoes AS (
-- Recomendações consolidadas — Compra / Manter / Venda
-- Objetivo: consolidar os 10 rankings fundamentalistas (01 a 10) em uma única recomendação por
-- ticker, para o investidor iniciante, ordenada da melhor (Compra) para a pior (Venda).
--
-- Fontes Silver (consulta-base):
--   refined.fundamentus_acoes a  INNER JOIN refined.b3_empresas b  LEFT JOIN refined.minhareceita_empresas c
--
-- 1. Rankings: cada CTE rank_XX reproduz exatamente a elegibilidade e o DENSE_RANK do arquivo
--    marts_XX_rank_*.sql correspondente, sobre a consulta-base completa. Qualquer alteração em um
--    ranking individual deve ser replicada aqui.
--
-- 2. Faixa por ranking (posição relativa do rank, aritmética inteira, empates na mesma faixa):
--      Superior      (+1): (rank - 1) * 3 <  max_rank - 1, ou max_rank = 1  (terço melhor)
--      Intermediário  (0): demais elegíveis                                (terço do meio)
--      Inferior      (âˆ’1): (rank - 1) * 3 >  2 * (max_rank - 1)            (terço pior)
--      Não elegível  (âˆ’1): não atende à  elegibilidade do ranking (perspectiva desfavorável)
--
-- 3. saldo = qtd_superior - qtd_inferior - qtd_nao_elegivel (âˆ’10 a +10; rankings com peso igual).
--    Recomendação: saldo > 0 -> Compra | saldo = 0 -> Manter | saldo < 0 -> Venda.
--
-- 4. Saída: apenas tickers com liquidez_2_meses > 0 (negociados nos últimos dois meses).
--    posicao = DENSE_RANK por saldo decrescente e qtd_superior decrescente.
--
-- Limitação: sinal relativo e mecà¢nico, derivado apenas dos 10 rankings sobre uma única
-- fotografia do Fundamentus. Não considera preço-alvo, valor intrínseco, histórico, governança,
-- contexto setorial nem o perfil do investidor. NàƒO constitui recomendação de investimento.
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
        a.liquidez_2_meses,
        a.roic,
        a.roe,
        a.enterprise_value_ebit,
        a.preco_lucro,
        a.dividend_yield,
        a.dividend_yield * a.preco_lucro              AS payout,
        a.margem_ebit,
        a.margem_liquida,
        a.divida_liquida_patrimonio,
        a.preco_valor_patrimonial,
        a.preco_valor_patrimonial / NULLIF(a.roe, 0) AS p_vp_por_roe,
        a.crescimento_receita_5_anos,
        100.0 / NULLIF(a.preco_lucro, 0)             AS earnings_yield
    FROM refined.fundamentus_acoes a
    INNER JOIN refined.b3_empresas b
        ON b.empresa_emissora = SUBSTRING(a.ticker, 1, 4)
    LEFT JOIN refined.minhareceita_empresas c
        ON c.cnpj = b.cnpj
),
rank_01 AS (  -- Valor: soma de rank ROIC ↓ e rank EV/EBIT ↑
    SELECT ticker, DENSE_RANK() OVER (ORDER BY soma_ranks ASC) AS rank
    FROM (
        SELECT
            ticker,
            DENSE_RANK() OVER (ORDER BY roic DESC)
                + DENSE_RANK() OVER (ORDER BY enterprise_value_ebit ASC) AS soma_ranks
        FROM base
        WHERE roic > 0
          AND enterprise_value_ebit > 0
    )
),
rank_02 AS (  -- Proventos: DY ↓, payout ↑
    SELECT ticker, DENSE_RANK() OVER (ORDER BY dividend_yield DESC, payout ASC) AS rank
    FROM base
    WHERE dividend_yield > 0
      AND preco_lucro > 0
      AND payout >= 0
),
rank_03 AS (  -- Eficiência: margem EBIT ↓, margem líquida ↓
    SELECT ticker, DENSE_RANK() OVER (ORDER BY margem_ebit DESC, margem_liquida DESC) AS rank
    FROM base
    WHERE margem_ebit > 0
      AND margem_liquida > 0
),
rank_04 AS (  -- Retorno: ROE ↓, DL/PL ↑
    SELECT ticker, DENSE_RANK() OVER (ORDER BY roe DESC, divida_liquida_patrimonio ASC) AS rank
    FROM base
    WHERE roe > 0
      AND divida_liquida_patrimonio IS NOT NULL
      AND divida_liquida_patrimonio <= 1.5
),
rank_05 AS (  -- Pechincha: soma de rank P/L ↑ e rank EV/EBIT ↑
    SELECT ticker, DENSE_RANK() OVER (ORDER BY soma_ranks ASC) AS rank
    FROM (
        SELECT
            ticker,
            DENSE_RANK() OVER (ORDER BY preco_lucro ASC)
                + DENSE_RANK() OVER (ORDER BY enterprise_value_ebit ASC) AS soma_ranks
        FROM base
        WHERE preco_lucro > 0
          AND enterprise_value_ebit > 0
    )
),
rank_06 AS (  -- Patrimônio: P/VP ÷ ROE ↑
    SELECT ticker, DENSE_RANK() OVER (ORDER BY p_vp_por_roe ASC) AS rank
    FROM base
    WHERE preco_valor_patrimonial > 0
      AND roe > 0
),
rank_07 AS (  -- Crescimento: crescimento da receita 5 anos ↓, com ROIC > 10
    SELECT ticker, DENSE_RANK() OVER (ORDER BY crescimento_receita_5_anos DESC) AS rank
    FROM base
    WHERE crescimento_receita_5_anos IS NOT NULL
      AND roic > 10
),
rank_08 AS (  -- Operacional: margem EBIT ↓
    SELECT ticker, DENSE_RANK() OVER (ORDER BY margem_ebit DESC) AS rank
    FROM base
    WHERE margem_ebit > 0
),
rank_09 AS (  -- Seguro: DL/PL ↑, ROIC ↓, ROE ↓
    SELECT ticker, DENSE_RANK() OVER (ORDER BY divida_liquida_patrimonio ASC, roic DESC, roe DESC) AS rank
    FROM base
    WHERE divida_liquida_patrimonio IS NOT NULL
      AND divida_liquida_patrimonio <= 1.5
      AND roic > 0
      AND roe > 0
),
rank_10 AS (  -- Rentabilidade: earnings yield ↓
    SELECT ticker, DENSE_RANK() OVER (ORDER BY earnings_yield DESC) AS rank
    FROM base
    WHERE preco_lucro > 0
),
ranks AS (
    SELECT 'valor'         AS ranking, ticker, rank FROM rank_01
    UNION ALL SELECT 'proventos',      ticker, rank FROM rank_02
    UNION ALL SELECT 'eficiencia',     ticker, rank FROM rank_03
    UNION ALL SELECT 'retorno',        ticker, rank FROM rank_04
    UNION ALL SELECT 'pechincha',      ticker, rank FROM rank_05
    UNION ALL SELECT 'patrimonio',     ticker, rank FROM rank_06
    UNION ALL SELECT 'crescimento',    ticker, rank FROM rank_07
    UNION ALL SELECT 'operacional',    ticker, rank FROM rank_08
    UNION ALL SELECT 'seguro',         ticker, rank FROM rank_09
    UNION ALL SELECT 'rentabilidade',  ticker, rank FROM rank_10
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
)
SELECT COUNT(*) AS quantidade
FROM recomendacoes
WHERE recomendacao = 'Manter';
