ESPECIFICAÇÃO — TESTES UNITÁRIOS DO CÓDIGO
Projeto: b3_valuation (Pipeline de Indicadores Fundamentalistas B3)
Versão: 2.0 (2026-11-03)

HISTÓRICO
- 1.0: versão inicial, escrita para outro projeto (pedidos, entregas, relatorio.py,
  pipeline/marts.py, ingestão por CSV).
- 2.0 (2026-11-03): reescrita para este projeto.
  - Módulos, regras e marts trocados pelos reais.
  - relatorio.py removido (não existe).
  - A materialização (pipeline/materializacao.py) ocupa o lugar de "marts".
  - Ingestão fora dos testes nesta versão.
  - Os testes atuais de tests/ migram para test/.
  - Critérios de aceite ajustados.

CONTEXTO
Estou construindo um pipeline de dados em Python sobre indicadores fundamentalistas de ações da
B3. As fontes são B3, Fundamentus, Minha Receita e YFinance, em arquitetura Medallion:
raw → refined → marts, no banco fundamentalistas.duckdb. Trabalho com spec-driven development: a
spec abaixo é a fonte da verdade e o código é consequência dela. Não acrescente requisito que
não esteja escrito aqui. Se algo estiver ambíguo, pergunte antes de escrever código.

STACK
- Python 3.13, uv, DuckDB
- pytest e pytest-cov, já declarados no grupo dev do pyproject.toml

O QUE JÁ EXISTE (leia tudo antes de escrever qualquer teste)
- pipeline/db.py: conexão e gravação genérica.
- pipeline/ingestao.py: camada raw. Extrai da rede (B3, Fundamentus, Minha Receita, yfinance).
- pipeline/transformacao.py: camada refined. Tem a spec completa na docstring, com critérios de
  aceite (§15) e testes obrigatórios (§16).
- pipeline/materializacao.py: camada marts. Materializa cada sql/marts/<nome>.sql em
  marts.<nome>; as decisões ficam na docstring.
- sql/marts/*.sql: 30 consultas, cada uma com cabeçalho de regra e grão.
- painel.py: leitura, formatação e gráficos. Spec v1.5 na docstring.
- app.py e ui.py: telas, fora da medição (item 1).
- Testes atuais em tests/: test_transformacao.py, test_materializacao.py e test_painel.py.
  Eles passam e são o ponto de partida: migram para test/ (ver ARTEFATOS) e são completados.
  Não são reescritos do zero.

ARTEFATOS A PRODUZIR
Pasta test/ na raiz, com um arquivo por módulo:
  test_db.py, test_transformacao.py, test_marts.py, test_sql_marts.py, test_painel.py
(sem test_ingestao.py: ver item 4.2)
Migração:
- tests/test_transformacao.py → test/test_transformacao.py
- tests/test_materializacao.py → test/test_marts.py
- tests/test_painel.py → test/test_painel.py
A migração é feita com git mv, preservando o histórico. A pasta tests/ deixa de existir.

Executável com:
  uv run pytest --cov

Configuração no pyproject.toml (substitui o bloco [tool.pytest.ini_options] atual):
  [tool.pytest.ini_options]
  testpaths = ["test"]
  pythonpath = ["."]
  [tool.coverage.run]
  source = ["."]
  omit = ["test/*", "app.py", "ui.py", ".venv/*"]
  [tool.coverage.report]
  fail_under = 60
  show_missing = true

SPEC
1. META
   60% de coverage de linhas no TOTAL do código Python medido: pipeline/ e painel.py. A meta é do
   total, não de cada arquivo. Arquivo que nenhum teste importa conta como 0%, e é isso que o
   source = ["."] garante.
   Linha de base (2026-11-03, tests/ atual): 59% no total, sendo ingestao.py 0%, db.py 57%,
   painel.py 50%, materializacao.py 87% e transformacao.py 90%.
   Ficam fora da medição: app.py, a tela do Streamlit, conferida no navegador; e ui.py, que só
   abre a interface do DuckDB.
   Motivo: testar layout por coverage não prova nada.

2. NUNCA O BANCO, OS DADOS NEM A REDE DO PROJETO
   Nenhum teste abre fundamentalistas.duckdb nem acessa a internet.
   - Cada teste usa tmp_path, com um DuckDB novo dentro dele.
   - Para o código encontrar esse banco, use monkeypatch.setattr na constante de caminho do
     módulo: db._ARQUIVO_DB, painel.ARQUIVO_DB, e materializacao.PASTA_MARTS quando o teste
     usar uma pasta de SQL própria.
   Ler os arquivos sql/marts/*.sql do projeto é permitido: eles são o código sob teste (item 4.5).
   Motivo: o teste tem que rodar em qualquer máquina, sem o pipeline ter rodado e sem rede, e não
   pode alterar o banco de ninguém.
   São testes unitários do código. Testes de qualidade sobre o dado real (chave única, domínio,
   totais que batem) ficam fora deste pedido.

3. DADO INVENTADO, RESULTADO DA REGRA
   Toda entrada é inventada pelo teste: poucas linhas, cada uma com um comentário dizendo por que
   está ali. Exemplos: ticker com ROIC negativo, ticker sem emissora na B3, valor "-" do
   Fundamentus, linha duplicada idêntica, preço ajustado negativo, CNPJ sem zeros à esquerda.
   O valor esperado sai da conta feita sobre essa entrada, nunca de um número medido no dado real
   de fundamentalistas.duckdb (1.920.774 cotações, 995 tickers, 391 analisadas, 70,6%...).
   Motivo: o dado real muda todo dia; a regra não.

4. O QUE TESTAR
   Os critérios de aceite das docstrings e dos cabeçalhos SQL são a lista de partida: cada
   critério que descreve uma regra vira pelo menos um teste. O que já está coberto em tests/ não
   precisa ser duplicado. Em especial:

   4.1 db (test_db.py)
   - conectar() abre o banco do caminho em db._ARQUIVO_DB.
   - criar_schema é idempotente: chamar duas vezes não falha.
   - gravar grava todas as colunas como VARCHAR, preserva NULL, devolve o COUNT(*) gravado e
     substitui a tabela numa segunda gravação (não acumula).

   4.2 ingestão
   Fora dos testes nesta versão. pipeline/ingestao.py só extrai da rede (B3, Fundamentus,
   Minha Receita, yfinance), e o item 2 proíbe acesso à internet. O arquivo conta 0% no TOTAL e
   entra na lista de Missing da entrega.

   4.3 transformação (test_transformacao.py)
   Já coberta em tests/. Completar o que faltar dos §15/§16 da docstring, por exemplo:
   - duplicata exata sai e é contada;
   - data da B3 vira DATE e cotação do yfinance vira TIMESTAMP WITH TIME ZONE;
   - valor do Fundamentus vira DECIMAL na escala original;
   - "-" vira NULL;
   - valor que não converte encerra main() com SystemExit(1), sem virar nulo.

   4.4 materialização (test_marts.py)
   Já coberta em tests/test_materializacao.py. Regras que devem estar provadas:
   - .sql sem chave lógica declarada em MARTS para antes de executar, sem criar tabela.
   - Chave duplicada ou nula, ou mart de linha única com quantidade de linhas diferente de 1,
     encerra e deixa o schema marts como estava.
   - Erro em qualquer .sql faz rollback de todos.
   - Segunda execução substitui sem duplicar.
   - Linha removida da refined some do mart na execução seguinte.
   - Tabela em marts sem .sql correspondente é mantida e reportada como órfã, nunca apagada.
   - raw e refined não mudam.
   - main() com falha encerra com SystemExit(1).

   4.5 consultas SQL (test_sql_marts.py)
   Rodar o texto real de sql/marts/<arquivo>.sql (UTF-8 sem BOM, sem ";" final) sobre tabelas
   refined inventadas. Criar refined.fundamentus_acoes, refined.b3_empresas e
   refined.minhareceita_empresas só com as colunas que a consulta referencia (o DESCRIBE da
   consulta aponta as que faltam).
   - marts_01_rank_valor:
     - ticker com roic ≤ 0, roic NULL ou EV/EBIT ≤ 0 fica fora;
     - rank = DENSE_RANK da soma de rank_roic (decrescente) e rank_ev_ebit (crescente);
     - empate de soma recebe o mesmo rank;
     - ticker sem emissora em b3_empresas fica fora (INNER JOIN);
     - ticker sem Minha Receita aparece, com atividade nula (LEFT JOIN).
   - marts_03_rank_eficiencia:
     - margem_ebit ≤ 0 ou margem_liquida ≤ 0 fica fora;
     - empate em margem_ebit é desempatado por margem_liquida decrescente.
   - marts_50_rank_recomendacoes:
     - saldo > 0 → Compra, saldo = 0 → Manter, saldo < 0 → Venda;
     - ticker com liquidez_2_meses = 0 fica fora.

   4.6 painel (test_painel.py)
   - reais, reais_compacto, pct, multiplo, numero e data_br com entradas inventadas:
     - milhar com ponto e decimal com vírgula;
     - pct não multiplica por 100;
     - None/NaN → "—".
   - Cada função de gráfico devolve uma figura com tantos pontos quantas linhas o DataFrame
     inventado deixa depois da regra da própria função:
     - fig_valor_qualidade: só as linhas com EV/EBIT > 0 e ROIC > 0;
     - fig_ranking_tematico: as n primeiras por rank e ticker (n padrão 15);
     - fig_cotacao: omite preço ajustado nulo ou ≤ 0;
     - fig_radar: recebe uma linha só e desenha um ponto por ranking (10).
   - filtrar recorta só por recomendação, segmento e liquidez mínima.
   - ler, tabelas_faltando, ler_cotacao, ErroMart e BancoBloqueado: já cobertos em tests/.

   Caminho de erro que encerra com sys.exit: pytest.raises(SystemExit) e assert no código de saída.

5. ESTILO
   pytest puro: funções test_* com assert. DuckDB de verdade, nunca mock do banco.
   Fixtures: só tmp_path e monkeypatch. As fixtures próprias de tests/ (con, pasta, banco) viram
   funções auxiliares comuns, chamadas dentro do teste com tmp_path. Os testes atuais que usam
   capsys passam a conferir o código de saída e os campos da exceção, em vez do texto impresso.
   O nome do teste é a frase que ele prova:
     test_roic_negativo_fica_fora_do_rank_valor
   Proibido:
   - teste sem assert;
   - skip e xfail;
   - try/except em volta do assert;
   - pytest.approx em valor monetário ou DECIMAL.
   Motivo: cada um sobe o coverage sem provar nada.

6. NÃO ALTERE O CÓDIGO DO PROJETO
   Nenhum arquivo muda fora de test/, da remoção de tests/ (migração) e do pyproject.toml. Se uma
   parte só for testável mudando o código, não mude: liste na entrega, com o motivo.

CRITÉRIOS DE ACEITE
- uv run pytest --cov termina sem falha, com TOTAL de 60% ou mais.
  Revisão (04/11/2026): meta elevada para 85% (fail_under = 85), com a cobertura já em 92%;
  o mesmo comando roda no GitHub Actions (.github/workflows/ci.yml).
- Com fundamentalistas.duckdb renomeado, o resultado é o mesmo.
- Rodar duas vezes seguidas dá o mesmo resultado: mesmos testes aprovados e mesma tabela de
  coverage. Só o tempo de execução pode mudar.
- Uma busca por 1920774 e 70.588 dentro de test/ não encontra nada.
- A entrega altera somente test/, tests/ (removida) e pyproject.toml. Alterações que já estavam
  pendentes antes da entrega não contam.

ENTREGA
1. Os arquivos de teste.
2. A saída de uv run pytest --cov, com a tabela por arquivo.
3. As linhas que ficaram sem teste (coluna Missing) e por que não valeram o esforço agora.
4. Uma lista final do que você assumiu e que não estava na spec.
