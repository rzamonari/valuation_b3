WITH base AS (
    SELECT DISTINCT ticker, liquidez_2_meses
    FROM refined.fundamentus_acoes
)
SELECT COUNT(*) AS quantidade
FROM base
WHERE liquidez_2_meses IS NULL OR liquidez_2_meses <= 0;
