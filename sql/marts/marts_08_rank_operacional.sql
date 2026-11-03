-- Rank 08 — Operacional
-- Objetivo: empresas com maior margem operacional.
--
-- Fontes Silver (consulta-base):
--   refined.fundamentus_acoes a  INNER JOIN refined.b3_empresas b  LEFT JOIN refined.minhareceita_empresas c
--
-- Indicador (pronto do Fundamentus, não recalculado):
--   margem_ebit : percentual na escala 0–100.
--
-- Elegibilidade: margem_ebit > 0 (NULL é excluído pela comparação).
--
-- Classificação (DENSE_RANK): margem_ebit decrescente.
--
-- Limitação: a Silver não disponibiliza Fluxo de Caixa Operacional; a dimensão de geração de
-- caixa operacional não é implementada e o EBITDA não é usado como substituto.
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
        a.margem_ebit
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
)
SELECT
    DENSE_RANK() OVER (ORDER BY margem_ebit DESC) AS rank,
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
    margem_ebit
FROM elegiveis
ORDER BY rank, ticker;
