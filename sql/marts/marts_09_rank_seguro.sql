-- Rank 09 — Seguro
-- Objetivo: empresas com menor alavancagem financeira e rentabilidade positiva.
--
-- Fontes Silver (consulta-base):
--   refined.fundamentus_acoes a  INNER JOIN refined.b3_empresas b  LEFT JOIN refined.minhareceita_empresas c
--
-- Indicadores (prontos do Fundamentus, não recalculados):
--   divida_liquida_patrimonio : vezes; negativos preservados (podem indicar caixa líquido).
--   roic                      : percentual na escala 0–100.
--   roe                       : percentual na escala 0–100.
--
-- Elegibilidade: divida_liquida_patrimonio não nula e <= 1,5, roic > 0 e roe > 0.
--
-- Classificação (DENSE_RANK, nesta ordem): divida_liquida_patrimonio crescente, roic
-- decrescente, roe decrescente.
--
-- Limitação: avalia apenas os indicadores disponíveis; não representa avaliação completa de
-- risco de crédito, liquidez ou solvência.
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
        a.divida_liquida_patrimonio,
        a.roic,
        a.roe
    FROM refined.fundamentus_acoes a
    INNER JOIN refined.b3_empresas b
        ON b.empresa_emissora = SUBSTRING(a.ticker, 1, 4)
    LEFT JOIN refined.minhareceita_empresas c
        ON c.cnpj = b.cnpj
),
elegiveis AS (
    SELECT *
    FROM base
    WHERE divida_liquida_patrimonio IS NOT NULL
      AND divida_liquida_patrimonio <= 1.5
      AND roic > 0
      AND roe > 0
)
SELECT
    DENSE_RANK() OVER (ORDER BY divida_liquida_patrimonio ASC, roic DESC, roe DESC) AS rank,
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
    divida_liquida_patrimonio,
    roic,
    roe
FROM elegiveis
ORDER BY rank, ticker;
