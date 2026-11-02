-- Rank 02 — Proventos
-- Objetivo: empresas com Dividend Yield positivo e relação indicativa equilibrada entre a
-- distribuição de dividendos e o lucro.
--
-- Fontes Silver (consulta-base):
--   refined.fundamentus_acoes a  INNER JOIN refined.b3_empresas b  LEFT JOIN refined.minhareceita_empresas c
--
-- Indicadores:
--   dividend_yield : pronto do Fundamentus, percentual na escala 0–100.
--   preco_lucro    : pronto do Fundamentus, múltiplo (vezes).
--   payout         : DERIVADO na Gold, payout ESTIMADO em percentual (escala 0–100).
--                    Fórmula: payout = dividend_yield * preco_lucro
--                    Ex.: DY = 6 (6%) e P/L = 10 -> payout = 60 (60%).
--
-- Elegibilidade: dividend_yield > 0, preco_lucro > 0 e 0 <= payout <= 100.
--
-- Classificação (DENSE_RANK, nesta ordem): dividend_yield decrescente, payout crescente.
--
-- Limitação: o payout estimado não comprova a sustentabilidade futura dos dividendos, a
-- recorrência dos pagamentos nem a capacidade de geração de caixa da empresa.
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
        a.dividend_yield,
        a.preco_lucro,
        a.dividend_yield * a.preco_lucro AS payout
    FROM refined.fundamentus_acoes a
    INNER JOIN refined.b3_empresas b
        ON b.empresa_emissora = SUBSTRING(a.ticker, 1, 4)
    LEFT JOIN refined.minhareceita_empresas c
        ON c.cnpj = b.cnpj
),
elegiveis AS (
    SELECT *
    FROM base
    WHERE dividend_yield > 0
      AND preco_lucro > 0
      AND payout >= 0
      AND payout <= 100
)
SELECT
    DENSE_RANK() OVER (ORDER BY dividend_yield DESC, payout ASC) AS rank,
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
    dividend_yield,
    preco_lucro,
    payout
FROM elegiveis
ORDER BY rank, ticker;
