-- Rank 07 — Crescimento
-- Objetivo: empresas com maior crescimento de receita nos últimos cinco anos, exigindo
-- rentabilidade mínima sobre o capital investido.
--
-- Fontes Silver (consulta-base):
--   refined.fundamentus_acoes a  INNER JOIN refined.b3_empresas b  LEFT JOIN refined.minhareceita_empresas c
--
-- Indicadores (prontos do Fundamentus, não recalculados):
--   crescimento_receita_5_anos : percentual na escala 0–100 (CAGR não é reconstruído).
--   roic                       : percentual na escala 0–100.
--
-- Elegibilidade: crescimento_receita_5_anos não nulo e roic > 10 (10%).
--
-- Classificação (DENSE_RANK): crescimento_receita_5_anos decrescente.
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
        a.crescimento_receita_5_anos,
        a.roic
    FROM refined.fundamentus_acoes a
    INNER JOIN refined.b3_empresas b
        ON b.empresa_emissora = SUBSTRING(a.ticker, 1, 4)
    LEFT JOIN refined.minhareceita_empresas c
        ON c.cnpj = b.cnpj
),
elegiveis AS (
    SELECT *
    FROM base
    WHERE crescimento_receita_5_anos IS NOT NULL
      AND roic > 10
)
SELECT
    DENSE_RANK() OVER (ORDER BY crescimento_receita_5_anos DESC) AS rank,
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
    crescimento_receita_5_anos,
    roic
FROM elegiveis
ORDER BY rank, ticker;
