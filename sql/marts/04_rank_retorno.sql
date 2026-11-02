-- Rank 04 — Retorno
-- Objetivo: empresas com maior retorno sobre o patrimônio líquido, com limite de alavancagem.
--
-- Fontes Silver (consulta-base):
--   refined.fundamentus_acoes a  INNER JOIN refined.b3_empresas b  LEFT JOIN refined.minhareceita_empresas c
--
-- Indicadores (prontos do Fundamentus, não recalculados):
--   roe                       : percentual na escala 0–100.
--   divida_liquida_patrimonio : vezes; negativos preservados (podem indicar caixa líquido).
--
-- Elegibilidade: roe > 0, divida_liquida_patrimonio não nula e <= 1,5
-- (limite conservador adotado nesta versão).
--
-- Classificação (DENSE_RANK): roe decrescente, divida_liquida_patrimonio crescente.
--
-- Dívida Líquida/EBITDA não é calculada: a Silver não disponibiliza a dívida líquida
-- necessária para esse cálculo.
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
        a.roe,
        a.divida_liquida_patrimonio
    FROM refined.fundamentus_acoes a
    INNER JOIN refined.b3_empresas b
        ON b.empresa_emissora = SUBSTRING(a.ticker, 1, 4)
    LEFT JOIN refined.minhareceita_empresas c
        ON c.cnpj = b.cnpj
),
elegiveis AS (
    SELECT *
    FROM base
    WHERE roe > 0
      AND divida_liquida_patrimonio IS NOT NULL
      AND divida_liquida_patrimonio <= 1.5
)
SELECT
    DENSE_RANK() OVER (ORDER BY roe DESC, divida_liquida_patrimonio ASC) AS rank,
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
    roe,
    divida_liquida_patrimonio
FROM elegiveis
ORDER BY rank, ticker;
