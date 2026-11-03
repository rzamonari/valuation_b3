-- Painel — Data de referência dos dados
-- Objetivo: data da fotografia do Fundamentus usada por todos os indicadores e rankings.
-- Fonte Silver: refined.fundamentus_acoes (somente leitura).
--
-- data_referencia : MAX(_timestamp_ingestao) (texto ISO-8601 com fuso, única data da tabela),
--                   convertido para o horário de America/Sao_Paulo e truncado para DATE, para
--                   que a data exibida não dependa do fuso da máquina.
--
-- Grão: uma linha.
SELECT
    CAST(
        timezone('America/Sao_Paulo', CAST(MAX(_timestamp_ingestao) AS TIMESTAMPTZ))
        AS DATE
    ) AS data_referencia
FROM refined.fundamentus_acoes;
