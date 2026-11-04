-- Painel — Saúde do pipeline
-- Objetivo: a execução mais recente de cada etapa que produz e valida a Gold, para a aba
--           "Saúde do pipeline" do painel.
-- Fonte: meta.execucoes (pipeline/execucao.py; uma linha por execução de etapa, somente leitura).
--
-- ordem            : posição da etapa no pipeline (1 = ingestão ... 4 = qualidade).
-- camada           : schema que a etapa publica (raw, refined, marts); NULL na qualidade, que
--                    só lê.
-- status           : 'sucesso' ou 'falha' da execução mais recente; NULL se a etapa nunca
--                    executou com registro.
-- inicio_utc,
-- fim_utc,
-- duracao_s        : da execução mais recente (UTC, sem fuso).
-- tabelas, linhas  : quantidade de tabelas publicadas e soma das linhas delas = linhas da
--                    camada nessa execução. NULL em etapa sem tabela (qualidade) ou sem registro.
-- linhas_por_tabela: lista (tabela, linhas) como a etapa relatou.
-- avisos           : quantidade de avisos; lista_avisos traz o texto de cada um.
-- erro             : mensagem da falha (NULL em sucesso).
-- ultimo_sucesso_utc: início da execução com sucesso mais recente da etapa (igual a inicio_utc
--                    quando a última deu certo; anterior a ele quando a última falhou).
--
-- A fotografia não entra: o próprio registro dela vai para o manifesto (fotografia/manifesto.json),
-- gravado depois que este mart já foi exportado. A idade dos dados não é calculada aqui: depende
-- do dia em que o painel é aberto (pipeline/execucao.py, idade()).
--
-- Grão: uma linha por etapa (sempre 4 linhas, inclusive etapa sem registro).
WITH etapas (ordem, etapa, camada) AS (
    VALUES
        (1, 'ingestao', 'raw'),
        (2, 'transformacao', 'refined'),
        (3, 'materializacao', 'marts'),
        (4, 'qualidade', NULL)
),

ultima AS (
    SELECT *
    FROM meta.execucoes
    QUALIFY ROW_NUMBER() OVER (PARTITION BY etapa ORDER BY inicio_utc DESC, id DESC) = 1
),

ultimo_sucesso AS (
    SELECT etapa, MAX(inicio_utc) AS ultimo_sucesso_utc
    FROM meta.execucoes
    WHERE status = 'sucesso'
    GROUP BY etapa
)

SELECT
    e.ordem,
    e.etapa,
    CAST(e.camada AS VARCHAR) AS camada,
    u.status,
    u.inicio_utc,
    u.fim_utc,
    u.duracao_s,
    CAST(NULLIF(len(u.linhas_por_tabela), 0) AS BIGINT) AS tabelas,
    CAST(list_sum([t.linhas FOR t IN u.linhas_por_tabela]) AS BIGINT) AS linhas,
    u.linhas_por_tabela,
    CAST(len(u.avisos) AS BIGINT) AS avisos,
    u.avisos AS lista_avisos,
    u.erro,
    s.ultimo_sucesso_utc
FROM etapas AS e
LEFT JOIN ultima AS u ON u.etapa = e.etapa
LEFT JOIN ultimo_sucesso AS s ON s.etapa = e.etapa
ORDER BY e.ordem;
