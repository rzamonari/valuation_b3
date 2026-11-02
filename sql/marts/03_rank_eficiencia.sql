-- Rank 03 — Eficiência
-- Objetivo: empresas com maior eficiência operacional e capacidade de transformar receita em lucro.
--
-- Fontes Silver (consulta-base):
--   refined.fundamentus_acoes a  INNER JOIN refined.b3_empresas b  LEFT JOIN refined.minhareceita_empresas c
--
-- Indicadores (prontos do Fundamentus, não recalculados):
--   margem_ebit    : percentual na escala 0–100.
--   margem_liquida : percentual na escala 0–100.
--
-- Elegibilidade: margem_ebit > 0 e margem_liquida > 0 (NULL é excluído pelas comparações).
--
-- Classificação (DENSE_RANK lexicográfico, sem média nem peso): margem_ebit decrescente,
-- margem_liquida decrescente.
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
        a.margem_ebit,
        a.margem_liquida
    FROM refined.fundamentus_acoes a
    INNER JOIN refined.b3_empresas b
        ON b.empresa_emissora = SUBSTRING(a.ticker, 1, 4)
    LEFT JOIN refined.minhareceita_empresas c
        ON c.cnpj = b.cnpj
),
elegiveis AS (
    SELECT *
    FROM base
    WHERE margem_ebit > 0
      AND margem_liquida > 0
)
SELECT
    DENSE_RANK() OVER (ORDER BY margem_ebit DESC, margem_liquida DESC) AS rank,
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
    margem_ebit,
    margem_liquida
FROM elegiveis
ORDER BY rank, ticker;
