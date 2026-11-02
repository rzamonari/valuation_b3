-- Rank 06 — Patrimônio
-- Objetivo: empresas com relação atrativa entre preço sobre valor patrimonial e retorno sobre
-- o patrimônio.
--
-- Fontes Silver (consulta-base):
--   refined.fundamentus_acoes a  INNER JOIN refined.b3_empresas b  LEFT JOIN refined.minhareceita_empresas c
--
-- Indicadores:
--   preco_valor_patrimonial : pronto do Fundamentus, múltiplo (vezes).
--   roe                     : pronto do Fundamentus, percentual na escala 0–100.
--   p_vp_por_roe            : DERIVADO na Gold. Múltiplo P/VP por ponto percentual de ROE.
--                             Fórmula: preco_valor_patrimonial / NULLIF(roe, 0)
--                             (ROE mantido na escala original 0–100).
--
-- Elegibilidade: preco_valor_patrimonial > 0 e roe > 0 (NULL é excluído pelas comparações).
--
-- Classificação (DENSE_RANK): p_vp_por_roe crescente.
--
-- Preço justo por Gordon ou outra metodologia não é calculado nesta versão.
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
        a.preco_valor_patrimonial,
        a.roe,
        a.preco_valor_patrimonial / NULLIF(a.roe, 0) AS p_vp_por_roe
    FROM refined.fundamentus_acoes a
    INNER JOIN refined.b3_empresas b
        ON b.empresa_emissora = SUBSTRING(a.ticker, 1, 4)
    LEFT JOIN refined.minhareceita_empresas c
        ON c.cnpj = b.cnpj
),
elegiveis AS (
    SELECT *
    FROM base
    WHERE preco_valor_patrimonial > 0
      AND roe > 0
)
SELECT
    DENSE_RANK() OVER (ORDER BY p_vp_por_roe ASC) AS rank,
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
    preco_valor_patrimonial,
    roe,
    p_vp_por_roe
FROM elegiveis
ORDER BY rank, ticker;
