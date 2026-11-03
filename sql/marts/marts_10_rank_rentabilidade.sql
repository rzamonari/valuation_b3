-- Rank 10 — Rentabilidade
-- Objetivo: empresas com maior retorno do lucro em relação ao preço da ação.
--
-- Fontes Silver (consulta-base):
--   refined.fundamentus_acoes a  INNER JOIN refined.b3_empresas b  LEFT JOIN refined.minhareceita_empresas c
--
-- Indicadores:
--   preco_lucro    : pronto do Fundamentus, múltiplo (vezes).
--   earnings_yield : DERIVADO na Gold, percentual na escala 0–100.
--                    Fórmula: 100.0 / NULLIF(preco_lucro, 0)
--                    Ex.: P/L = 10 -> earnings_yield = 10 (10%).
--
-- Elegibilidade: preco_lucro > 0 (NULL é excluído pela comparação).
--
-- Classificação (DENSE_RANK): earnings_yield decrescente.
--
-- Grão: uma linha por ticker elegível.
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
        a.preco_lucro,
        100.0 / NULLIF(a.preco_lucro, 0) AS earnings_yield
    FROM refined.fundamentus_acoes a
    INNER JOIN refined.b3_empresas b
        ON b.empresa_emissora = SUBSTRING(a.ticker, 1, 4)
    LEFT JOIN refined.minhareceita_empresas c
        ON c.cnpj = b.cnpj
),
elegiveis AS (
    SELECT *
    FROM base
    WHERE preco_lucro > 0
)
SELECT
    DENSE_RANK() OVER (ORDER BY earnings_yield DESC) AS rank,
    ticker,
    empresa,
    razao_social,
    segmento,
    atividade,
    mercado,
    municipio,
    uf,
    natureza_juridica,
    data_inicio_atividade,
    situacao,
    preco_lucro,
    earnings_yield
FROM elegiveis
ORDER BY rank, ticker;
