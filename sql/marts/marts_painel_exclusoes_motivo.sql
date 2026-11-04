-- Painel — Exclusões do universo por motivo
-- Objetivo: quantos tickers do Fundamentus ficam fora dos rankings, por motivo, para o painel.
--
-- Fonte Gold: marts.marts_exclusoes_universo (a classificação vive só nesse mart; a
-- materialização o prepara antes deste).
--
-- Regras:
--   - Todas as categorias fechadas aparecem, inclusive as sem ticker (quantidade = 0), na ordem
--     das regras de marts_exclusoes_universo.
--   - quantidade_negociada = tickers com liquidez_2_meses > 0 dentro do motivo.
--
-- Grão: uma linha por motivo.
WITH motivos (ordem, motivo, descricao) AS (
    VALUES
        (1, 'Fracionário',             'Código do mercado fracionário (final F)'),
        (2, 'BDR',                     'Recibo de ação estrangeira (final 32 a 35)'),
        (3, 'Unit',                    'Pacote de ações (final 11)'),
        (4, 'Não identificado',        'Negociado nos últimos 2 meses, mas sem emissora no cadastro da B3'),
        (5, 'Deslistada ou cancelada', 'Ação ON/PN sem negociação e sem emissora ativa na B3'),
        (6, 'Outro código',            'Demais sufixos, sem negociação e sem emissora ativa na B3')
),
exclusoes AS (
    SELECT * FROM marts.marts_exclusoes_universo
)
SELECT
    m.ordem,
    m.motivo,
    m.descricao,
    COUNT(e.ticker)                                          AS quantidade,
    COUNT(e.ticker) FILTER (WHERE e.liquidez_2_meses > 0)    AS quantidade_negociada
FROM motivos m
LEFT JOIN exclusoes e
    ON e.motivo = m.motivo
GROUP BY m.ordem, m.motivo, m.descricao
ORDER BY m.ordem;
