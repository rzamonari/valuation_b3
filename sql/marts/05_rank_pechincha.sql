-- Rank 05 — Pechincha
-- Objetivo: empresas com múltiplos de avaliação positivos e relativamente baixos.
--
-- Fontes Silver (consulta-base):
--   refined.fundamentus_acoes a  INNER JOIN refined.b3_empresas b  LEFT JOIN refined.minhareceita_empresas c
--
-- Indicadores (prontos do Fundamentus, não recalculados):
--   preco_lucro           : múltiplo (vezes).
--   enterprise_value_ebit : múltiplo (vezes).
--
-- Elegibilidade: preco_lucro > 0 e enterprise_value_ebit > 0 (NULL é excluído pelas comparações).
-- Sem limites máximos para os múltiplos.
--
-- Classificação (DENSE_RANK):
--   1. rank_preco_lucro = P/L crescente.
--   2. rank_ev_ebit     = EV/EBIT crescente.
--   3. soma_ranks       = rank_preco_lucro + rank_ev_ebit (os múltiplos não são somados
--                         diretamente, pois têm escalas diferentes).
--   4. rank             = soma_ranks crescente (menor soma = melhor).
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
        a.enterprise_value_ebit
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
      AND enterprise_value_ebit > 0
),
ranks_individuais AS (
    SELECT
        *,
        DENSE_RANK() OVER (ORDER BY preco_lucro ASC)           AS rank_preco_lucro,
        DENSE_RANK() OVER (ORDER BY enterprise_value_ebit ASC) AS rank_ev_ebit
    FROM elegiveis
),
soma AS (
    SELECT
        *,
        rank_preco_lucro + rank_ev_ebit AS soma_ranks
    FROM ranks_individuais
)
SELECT
    DENSE_RANK() OVER (ORDER BY soma_ranks ASC) AS rank,
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
    enterprise_value_ebit,
    rank_preco_lucro,
    rank_ev_ebit,
    soma_ranks
FROM soma
ORDER BY rank, ticker;
