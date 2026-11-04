-- Exclusões do universo — tickers do Fundamentus fora da consulta-base dos rankings
-- Objetivo: explicar, ticker a ticker, por que uma ação do Fundamentus não entra nos 10 rankings
-- nem nas recomendações (complemento exato do universo).
--
-- Fontes Silver:
--   refined.fundamentus_acoes a  (todos os tickers e os indicadores básicos)
--   refined.b3_empresas b        (cadastro de emissoras; só empresas ativas, situacao = 'A')
--
-- Exclusão: não existe emissora na B3 com empresa_emissora = SUBSTRING(a.ticker, 1, 4), a mesma
-- condição do INNER JOIN da consulta-base (ver sql/marts/RANKINGS.md §1). Universo + exclusões =
-- todos os tickers do Fundamentus, sem sobreposição (reconciliação em pipeline/qualidade.py).
--
-- Motivo (categoria fechada, primeira regra que se aplica, pelo sufixo do ticker):
--   1. Fracionário             : termina em F.
--   2. BDR                     : sufixo 32 a 35.
--   3. Unit                    : sufixo 11.
--   4. Não identificado        : negociado nos últimos 2 meses (liquidez_2_meses > 0) e fora das
--                                categorias acima: está no pregão, mas não no cadastro da B3.
--   5. Deslistada ou cancelada : ação ON/PN (sufixo 3 a 8) sem negociação nos últimos 2 meses e
--                                emissora ausente do cadastro de empresas ativas.
--   6. Outro código            : demais sufixos (ex.: 12, 13, 31, 41, 42) sem negociação.
-- A ausência no cadastro de ativas é o fato observado; "deslistada ou cancelada" é a causa
-- provável (o cadastro não informa a data nem o motivo da saída).
--
-- Indicadores: valores do Fundamentus preservados (NULL continua NULL).
--
-- Grão: uma linha por ticker excluído.
WITH excluidos AS (
    SELECT
        a.ticker,
        SUBSTRING(a.ticker, 1, 4)                      AS emissora,
        regexp_extract(a.ticker, '^[A-Z0-9]{4}(.*)$', 1) AS sufixo,
        a.cotacao,
        a.liquidez_2_meses,
        a.patrimonio_liquido,
        a.preco_lucro,
        a.roe
    FROM refined.fundamentus_acoes a
    WHERE NOT EXISTS (
        SELECT 1
        FROM refined.b3_empresas b
        WHERE b.empresa_emissora = SUBSTRING(a.ticker, 1, 4)
    )
),
classificados AS (
    SELECT
        *,
        CASE
            WHEN sufixo LIKE '%F'                       THEN 'Fracionário'
            WHEN sufixo IN ('32', '33', '34', '35')     THEN 'BDR'
            WHEN sufixo = '11'                          THEN 'Unit'
            WHEN liquidez_2_meses > 0                   THEN 'Não identificado'
            WHEN sufixo IN ('3', '4', '5', '6', '7', '8') THEN 'Deslistada ou cancelada'
            ELSE 'Outro código'
        END AS motivo
    FROM excluidos
)
SELECT
    ticker,
    emissora,
    motivo,
    'Emissora ' || emissora || ' ausente do cadastro de empresas ativas da B3; '
        || CASE
               WHEN liquidez_2_meses > 0 THEN 'negociado nos últimos 2 meses'
               ELSE 'sem negociação nos últimos 2 meses'
           END                                      AS detalhe,
    cotacao,
    liquidez_2_meses,
    patrimonio_liquido,
    preco_lucro,
    roe
FROM classificados
ORDER BY motivo, ticker;
