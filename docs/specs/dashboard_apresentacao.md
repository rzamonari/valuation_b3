# ESPECIFICAÇÃO — PAINEL DE RECOMENDAÇÕES (DASHBOARD)
## Pipeline de Indicadores Fundamentalistas B3 — Camada de Apresentação

**Versão:** 1.5
**Data de referência dos números desta spec:** 2026-11-02 (conferidos nas tabelas `marts` em 2026-11-03)
**Specs relacionadas:** `marts_sql_indicadores.md`, `marts_sql_rank.md`,
`marts_materializacao.md` (materialização da camada Gold)

**Histórico**
- 1.0 (2026-11-02): versão inicial.
- 1.1 (2026-11-02): removidas a faixa "Onde estão as empresas" (mapa, ranking de estados, clique
  no mapa como filtro, filtro de UF da barra lateral, mart `marts_painel_empresas_uf.sql` e
  `assets/br_uf.geojson`) e o
  "Mapa de calor dos rankings"; seções renumeradas; aparência passa a ser o Modo Escuro
  Profissional (item 8) com paleta ajustada para contraste em fundo escuro; pendências P1 a P4
  respondidas.
- 1.2 (2026-11-02): título passa a "🔭 B3 Valuation · Visões de Investimentos"; data de
  referência lida de `refined.fundamentus_acoes` como data no fuso de Brasília e exibida como
  "Dados do Fundamentus de dd/mm/aaaa"; novo texto do aviso, com a ressalva em negrito; coluna UF
  removida do ranking consolidado.
- 1.3 (2026-11-02): ícone do título passa a 📈 (gráfico de alta); rótulo da data volta a
  "Dados de dd/mm/aaaa" (a data continua vindo de `refined.fundamentus_acoes`).
- 1.4 (2026-11-03): removida a faixa "Panorama dos sinais" (gráficos "Força dos sinais" e
  "Recomendações por segmento de listagem" e os marts `marts_painel_distribuicao_saldo.sql` e
  `marts_painel_recomendacao_segmento.sql`, que só ela usava); faixas renumeradas de 1 a 5.
- 1.5 (2026-11-03): o painel passa a ler as tabelas físicas do schema `marts` de
  `fundamentalistas.duckdb`, materializadas por `pipeline/materializacao.py`, em vez de executar
  o texto dos `.sql` de `sql/marts/`. Revisados: "O que já existe", itens 1, 2, 3 e 7, critérios
  de aceite e entrega. Novas regras: a única SQL do painel é `SELECT * FROM marts.<tabela>`;
  tabela ausente orienta a rodar a materialização; ordem de exibição sempre explícita no pandas.

---

## CONTEXTO

Estou construindo um pipeline de dados em Python sobre indicadores fundamentalistas de ações da
B3 (Fundamentus, B3, Minha Receita e YFinance), em arquitetura Medallion (`raw` → `refined` →
`marts`). As consultas da camada Gold ficam em `sql/marts/` e são materializadas como tabelas no
schema `marts` do mesmo banco. Trabalho com spec-driven development: esta spec é a fonte da verdade e o
código é consequência dela. Não acrescente requisito que não esteja escrito aqui. Se algo estiver
ambíguo, pergunte antes de escrever código.

O público do painel é o **investidor pessoa física**, inclusive iniciante. O painel deve responder,
nesta ordem, às perguntas que ele faz ao abrir a ferramenta:

1. Como está o mercado hoje? (cartões e termômetro)
2. Quais ações aparecem melhor e por quê? (ranking de oportunidades)
3. Quais ações combinam qualidade e preço justo? (valor × qualidade)
4. Quem lidera cada estratégia? (rankings temáticos)
5. Como está uma ação específica? (ficha da ação)

## STACK

- Python 3.13, uv, DuckDB (`fundamentalistas.duckdb` na raiz do projeto).
- `streamlit` e `plotly` (`plotly.express` e, onde indicado, `plotly.graph_objects`), já
  declarados no `pyproject.toml`. Não adicionar outras bibliotecas de gráfico ou de UI.

## O QUE JÁ EXISTE (use, não reimplemente)

Cada arquivo `sql/marts/<nome>.sql` é materializado, por `uv run python -m pipeline.materializacao`,
na tabela física `marts.<nome>` de `fundamentalistas.duckdb`. O nome da tabela é o nome do arquivo
sem extensão. A materialização substitui todas as tabelas por inteiro, numa única transação, e
valida cada uma contra a consulta de origem antes de confirmar (`sql/marts/README.md` §12).
O `.sql` continua sendo a fonte da verdade da regra de negócio e a tabela é o que o painel lê.
As tabelas a usar:

| Uso no painel | Tabela (`marts.`) | Grão |
|---|---|---|
| Cartão 1 | `marts_card_01_acoes_analisadas` | 1 linha, coluna `quantidade` |
| Cartão 2 | `marts_card_02_acoes_compra` | 1 linha, coluna `quantidade` |
| Cartão 3 | `marts_card_03_acoes_manter` | 1 linha, coluna `quantidade` |
| Cartão 4 | `marts_card_04_acoes_venda` | 1 linha, coluna `quantidade` |
| Cartão 5 | `marts_card_02_acoes_semindicacao` | 1 linha, coluna `quantidade` |
| Termômetro | `marts_card_05_termometro_mercado` | 1 linha |
| Data de referência | `marts_painel_data_referencia` | 1 linha |
| Valor × qualidade, ficha | `marts_painel_indicadores` | 1 linha por ticker analisado |
| Ranking de oportunidades, filtros | `marts_50_rank_recomendacoes` | 1 linha por ticker negociado |
| Rankings temáticos | `marts_01_rank_valor` … `marts_10_rank_rentabilidade` | 1 linha por ticker elegível |
| Ficha: risco e retorno | `marts_retorno_total_risco` | 1 linha por ticker |
| Ficha: cotações | `marts_cotacao` | 1 linha por (ticker, data) |

Ordem de execução do pipeline antes de abrir o painel:
`pipeline.ingestao` → `pipeline.transformacao` → `pipeline.materializacao`.
O painel mostra o que foi materializado por último. Se a Silver mudar e a materialização não for
executada, ele continua mostrando a fotografia anterior, que é coerente consigo mesma (inclusive a
data de referência, que também vem de uma tabela `marts`).

A conexão já existe em `pipeline/db.py` (`conectar()`), mas abre o banco para escrita. O painel
**não** a usa (ver item 1). O painel também não importa `pipeline/materializacao.py` e nunca
dispara a materialização. Motivo: o painel é somente leitura.

## ARTEFATOS A PRODUZIR

- `painel.py`, na raiz: leitura, formatação e funções de gráfico. **Não importa streamlit.**
- `app.py`, na raiz: a página. Executável com:
  `uv run streamlit run app.py`
- `.streamlit/config.toml`: tema do painel (item 8).
- Os novos marts listados no item 3, em `sql/marts/` (já entregues na v1.0 e materializados pela
  v1.5), seguindo as regras da spec `marts_sql_indicadores.md` (somente leitura, comentário
  de cabeçalho, grão documentado). Todo mart novo precisa ter a chave lógica declarada em
  `pipeline/materializacao.py` (`MARTS`); sem isso a materialização recusa o arquivo.

---

# SPEC

## 1. LEITURA (`painel.py`)

`ler(nomes) -> dict[str, DataFrame]`. Para cada nome, executa `SELECT * FROM marts."<nome>"`
(identificador entre aspas, vindo só das constantes de `painel.py`) e devolve a tabela inteira, sem
seleção de colunas, filtro, junção ou `ORDER BY`. Nenhuma outra SQL, com uma única exceção
(`ler_cotacao`, abaixo).
Motivo: o número já foi calculado e validado na materialização; ler a tabela pronta evita
reexecutar os rankings a cada abertura e garante que todas as faixas mostram a mesma fotografia.

- `painel.py` não lê os arquivos de `sql/marts/`.
  Motivo: há uma única fonte em tempo de exibição, a tabela.
- Conexão com `duckdb.connect("fundamentalistas.duckdb", read_only=True)`, aberta e fechada
  dentro de cada leitura.
  Motivo: conexão aberta segura o arquivo, e o pipeline (ingestão, transformação e
  materialização) não consegue gravar com o painel de pé.
- Se o banco estiver bloqueado por outro processo (por exemplo, a DuckDB UI do `ui.py` ou a
  materialização em andamento), mostrar erro claro (item 7), sem traceback.
- `ler_cotacao(ticker) -> DataFrame`: executa
  `SELECT * FROM marts."marts_cotacao" WHERE ticker = ?`, com parâmetro vinculado.
  Motivo: a tabela tem cerca de 1,9 milhão de linhas; filtrar linhas é permitido (item 2) e
  fazê-lo no banco evita carregar tudo em memória.
- `tabelas_faltando() -> list[str]`: devolve, como `marts.<nome>`, as tabelas obrigatórias (todas
  as da lista "O QUE JÁ EXISTE") que não existem no banco. Se o arquivo `fundamentalistas.duckdb`
  não existir, devolve só o nome dele. A consulta usa o catálogo `duckdb_tables()` na mesma
  conexão somente leitura.
- **Ordem das linhas.** Tabela não garante ordem de leitura. Toda exibição que depende de ordem
  ordena explicitamente no pandas (permitido pelo item 2):
  - ranking consolidado e lista da ficha por `posicao`, `ticker`;
  - rankings temáticos por `rank`, `ticker`;
  - cotação por `data`.
  Os cartões, o termômetro e a data de referência têm uma linha só.

## 2. NENHUM CÁLCULO

Proibido em `painel.py` e `app.py`: `groupby`, `sum`, `mean`, `count`, `value_counts`, `merge`,
`join`, `pivot`, `crosstab`, `px.histogram` (agrega no gráfico), `nbins`, e qualquer conta entre
colunas.

Permitido: ordenar, filtrar linhas, `head(n)`, renomear coluna, formatar texto e mapear valores
categóricos para cor, ícone ou rótulo por dicionário constante (item 4.1).

Motivo: número novo na tela exige um `.sql` novo em `sql/marts/`, declarado em
`pipeline/materializacao.py` e materializado em `marts`. Se faltar algum número, pare e diga qual
mart está faltando.

## 3. NOVOS MARTS NECESSÁRIOS

Já criados na v1.0. A partir da v1.5, chegam ao painel como as tabelas `marts.<nome>`
correspondentes. Mantidos aqui como definição:

| Arquivo | Conteúdo | Grão |
|---|---|---|
| `marts_card_05_termometro_mercado.sql` | `recomendacao` predominante entre as ações analisadas, `quantidade` dela, `total` analisado e `percentual` (0–100) | 1 linha |
| `marts_painel_data_referencia.sql` | data da fotografia do Fundamentus: `MAX(_timestamp_ingestao)` de `refined.fundamentus_acoes` (única coluna de data da tabela), convertido para o fuso `America/Sao_Paulo` e truncado para `DATE`, como `data_referencia`. Motivo: a data exibida não pode depender do fuso da máquina | 1 linha |
| `marts_painel_indicadores.sql` | por ticker analisado: `ticker`, `empresa`, `segmento`, `uf`, `recomendacao`, `saldo`, `liquidez_2_meses`, `cotacao`, `roic`, `roe`, `enterprise_value_ebit`, `preco_lucro`, `earnings_yield`, `preco_valor_patrimonial`, `dividend_yield`, `payout`, `margem_ebit`, `margem_liquida`, `divida_liquida_patrimonio`, `crescimento_receita_5_anos` | 1 linha por ticker |

Regras:

- Todos partem da mesma regra de recomendação de `marts_50_rank_recomendacoes.sql` (universo:
  ações analisadas, `liquidez_2_meses > 0`). Revisão de 04/11/2026: em vez de copiar a consulta,
  leem `marts.marts_50_rank_recomendacoes` (dependência resolvida pela materialização).
- Valores do Fundamentus preservados, na escala original (percentuais 0–100).
- Termômetro: empate na quantidade máxima → `Manter` (P1, respondida).

## 4. LAYOUT (`app.py`) — de cima para baixo, `layout="wide"`

Cada seção começa com um título curto e uma linha de subtítulo em linguagem de investidor
(exemplo: "Quanto maior o saldo, mais rankings a ação lidera"). Cada gráfico tem título numerado
pela seção ("3 · Qualidade versus preço"), eixos com unidade e tooltip (`hover`) em português,
formatado pelas funções do item 5. Usar `width="stretch"` (`use_container_width` está
descontinuado).

### 4.1 Linguagem visual de recomendação

Dicionário constante, usado em **todos** os cartões, gráficos, tabelas e badges:

| Recomendação | Ícone | Rótulo | Cor (sobre fundo escuro, item 8) |
|---|---|---|---|
| Compra | 🟢 | Compra / Oportunidade | verde `#22C55E` |
| Manter | 🟡 | Manter / Neutro | amarelo `#FACC15` |
| Venda | 🔴 | Venda / Risco | vermelho `#F87171` |
| Sem indicação | ⚪ | Sem indicação | cinza `#94A3B8` |

Motivo das cores: os tons claros e saturados mantêm contraste de pelo menos 4,5:1 contra o fundo
escuro do item 8, para que números e marcas se destaquem.

Faixas dos rankings: Superior = verde, Intermediário = amarelo, Inferior = vermelho,
Não elegível = cinza.

A cor nunca é a única pista: sempre acompanhar ícone e rótulo. Motivo: acessibilidade para quem
não distingue verde de vermelho.

### 4.2 Cabeçalho

- Esquerda: título "📈 B3 Valuation · Visões de Investimentos" (ícone de gráfico de alta) e,
  abaixo, "Dados de <data_referencia>"
  (`marts_painel_data_referencia`, formato `dd/mm/aaaa`; nunca data fixa no código).
- Direita: botão "Recarregar dados" (item 7).
- Faixa de aviso discreta (`st.caption`), sempre visível, com a ressalva final em negrito:
  "Sinais relativos derivados de 10 rankings fundamentalistas sobre fotografia de dados.
  **Não constitui recomendação de investimento**."
  Motivo: é a limitação documentada em `marts_50_rank_recomendacoes.sql`.

### 4.3 Faixa 1 — Pulso do mercado: seis cartões

Seis colunas iguais, nesta ordem. Cada cartão é um bloco HTML estilizado
(`st.markdown(..., unsafe_allow_html=True)`), com borda superior na cor do item 4.1, número grande,
rótulo e uma linha de definição curta:

1. **Ações analisadas** — `marts_card_01_acoes_analisadas.quantidade`.
   Definição: "tickers negociados nos últimos 2 meses". Cor neutra (azul da marca, item 8).
2. **🟢 Compra** — `marts_card_02_acoes_compra.quantidade`. Definição: "saldo positivo nos 10 rankings".
3. **🟡 Manter** — `marts_card_03_acoes_manter.quantidade`. Definição: "saldo zero".
4. **🔴 Venda** — `marts_card_04_acoes_venda.quantidade`. Definição: "saldo negativo".
5. **⚪ Sem indicação** — `marts_card_02_acoes_semindicacao.quantidade`.
   Definição: "sem negociação nos últimos 2 meses".
6. **Termômetro de mercado** — `marts_card_05_termometro_mercado`. O cartão inteiro assume o
   fundo suave e a borda da cor da recomendação predominante, com:
   - ícone e rótulo do item 4.1 em destaque (ex.: "🔴 Venda / Risco");
   - linha "`<percentual>` das ações analisadas" (ex.: "70,6% das ações analisadas");
   - barra horizontal empilhada fina (Compra | Manter | Venda) com as quantidades dos cartões 2 a
     4, nas cores do item 4.1, sem eixos. É só desenho das quantidades, não cálculo.

Nos cartões 2 a 4, mostrar abaixo do número o percentual sobre as analisadas **somente se** vier
de mart. Nesta versão não vem: não mostrar.

### 4.4 Faixa 2 — Ranking de oportunidades: largura inteira

- **2 · Ranking consolidado** (`marts_50_rank_recomendacoes`, filtrado pelo item 6): `st.dataframe`
  com `column_config`:
  - `posicao`; recomendação como badge com ícone (item 4.1); `ticker`; `empresa`; `segmento`;
  - `cotacao` em reais; `liquidez_2_meses` em reais compactos (item 5);
  - `saldo` como `ProgressColumn` de −10 a +10;
  - as dez colunas `faixa_*` como ícones de faixa (🟢 Superior, 🟡 Intermediário, 🔴 Inferior,
    ⚪ Não elegível), com cabeçalho igual ao nome curto do ranking (Valor, Proventos, …).
  Ordenação padrão: `posicao`. Altura para cerca de 15 linhas, com rolagem.

### 4.5 Faixa 3 — Valor × qualidade: largura inteira

- **3 · Qualidade versus preço** (`marts_painel_indicadores`, filtrado pelo item 6): dispersão com
  eixo X = EV/EBIT (múltiplo, "x"), eixo Y = ROIC (%), cor = recomendação, tamanho do ponto =
  `liquidez_2_meses`, tooltip com ticker, empresa, P/L, DY e ROE.
  Mostrar apenas linhas com EV/EBIT e ROIC maiores que zero (filtro de linhas) e recortar o eixo X
  em 0–30 e o Y em 0–60, avisando na legenda quantas ações ficaram fora do recorte só se o número
  vier de mart; nesta versão, escrever "Valores extremos fora da área visível".
  Linhas de referência tracejadas: ROIC = 15% ("custo de capital de referência", spec de marts
  §6.1) e EV/EBIT = 10. Rótulo dos quadrantes, em cinza: superior esquerdo "Qualidade a bom preço",
  inferior direito "Cara e pouco rentável".
  Motivo: é a leitura da Magic Formula, base do Rank Valor, que o investidor entende sem fórmula.
  EV/EBIT = 10 aprovado pelo usuário (P3).

### 4.6 Faixa 4 — Rankings temáticos: largura inteira, `st.tabs`

Uma aba por ranking, nesta ordem e com estes nomes e frases (o investidor escolhe a estratégia,
não a sigla):

| Aba | Arquivo | Frase de apoio | Gráfico (top 15 por `rank`) |
|---|---|---|---|
| 💎 Valor | `marts_01` | Rentáveis e baratas (Magic Formula simplificada) | barras de ROIC com EV/EBIT no tooltip |
| 💰 Proventos | `marts_02` | Maiores pagadoras com payout saudável | barras de DY |
| ⚙️ Eficiência | `marts_03` | Melhores margens | barras agrupadas margem EBIT e líquida |
| 📈 Retorno | `marts_04` | ROE alto com dívida controlada | barras de ROE |
| 🏷️ Pechincha | `marts_05` | Menores múltiplos de preço | barras de P/L |
| 🏛️ Patrimônio | `marts_06` | Menor preço por ponto de rentabilidade | barras de P/VP ÷ ROE |
| 🚀 Crescimento | `marts_07` | Receita crescendo com ROIC > 10% | barras de crescimento 5 anos |
| 🏭 Operacional | `marts_08` | Maior margem operacional | barras de margem EBIT |
| 🛡️ Seguro | `marts_09` | Menor alavancagem com rentabilidade | barras de DL/PL |
| 🎯 Rentabilidade | `marts_10` | Maior lucro por real investido | barras de earnings yield |

Cada aba: barras horizontais, melhor em cima, uma cor só (azul da marca), valor rotulado na barra,
e ao lado uma tabela com `rank`, `ticker`, `empresa` e os indicadores do arquivo. Empates de rank
mostram o mesmo número (é `DENSE_RANK`); ordenar por `rank` e depois `ticker`.

### 4.7 Faixa 5 — Ficha da ação: largura inteira

`st.selectbox` com os tickers de `marts_50_rank_recomendacoes` (rótulo "TICKER · empresa"), padrão
= `posicao` 1. Mostra:

- Cabeçalho: ticker, empresa, segmento, município/UF, badge da recomendação, saldo.
- Linha de mini cartões (`marts_painel_indicadores`, `marts_retorno_total_risco`): cotação, P/L,
  P/VP, DY, ROE, ROIC, DL/PL, CAGR 5 anos, volatilidade anualizada, máximo drawdown.
  Valor nulo aparece como "—", nunca como zero.
- **5 · Perfil nos 10 rankings**: gráfico polar (radar) com os 10 rankings no eixo angular e a
  faixa no radial por um código ordinal fixo vindo de dicionário constante, usado apenas para
  posicionar (Não elegível 0 no centro, Inferior 1, Intermediário 2, Superior 3 na borda),
  preenchido na cor da recomendação. Rótulos radiais com os nomes das faixas, nunca os códigos.
- **5 · Cotação histórica** (`ler_cotacao`): linha de `fechamento_ajustado` com seletor de período
  (botões 1A, 3A, 5A, Tudo, via `rangeselector` do plotly) e barras de `volume` em um segundo painel
  abaixo, eixo X compartilhado. As datas com `dividendos > 0` recebem um marcador "💰" sobre a
  linha (filtro de linhas, sem conta), com o valor do provento no tooltip.
  Preços nulos ou menores ou iguais a zero ficam fora do desenho (filtro de linhas) e a ficha avisa
  "N cotações inválidas ocultas" só se o número vier de mart; nesta versão, não avisar.
  Motivo: a Silver tem preços ajustados negativos em alguns tickers (`sql/marts/README.md`).

## 5. FORMATO (`painel.py`), funções puras, sem streamlit e sem banco

- `reais(valor, casas=2)` → `"R$ 1.003.862,14"`
- `reais_compacto(valor)` → `"R$ 12,3 mi"`, `"R$ 1,2 bi"`, `"R$ 850 mil"`
- `pct(valor, casas=1)` → `"6,9%"`. **Não multiplica por 100**: os percentuais do projeto já estão
  na escala 0–100.
- `multiplo(valor, casas=1)` → `"8,4x"`
- `numero(valor, casas=0)` → `"1.920.774"`
- `data_br(valor)` → `"02/11/2026"`
- Qualquer função recebendo `None`/`NaN` devolve `"—"`.

Milhar com ponto, decimal com vírgula, sempre. Não usar locale do sistema.
Motivo: o resultado não pode depender da máquina de quem roda.

Uma função por gráfico, recebendo DataFrame(s) e devolvendo a figura plotly, com o mesmo template
visual (item 8).
Motivo: um relatório HTML futuro reaproveita as mesmas funções, e os gráficos ficam testáveis sem
streamlit.

## 6. FILTROS

Barra lateral (`st.sidebar`), com o título "Filtros":

- Recomendação (`st.pills`, seleção múltipla, com ícones; padrão: todas).
- Segmento de listagem (`st.multiselect`).
- Liquidez mínima em 2 meses (`st.select_slider` com faixas fixas: Todas, R$ 100 mil, R$ 1 mi,
  R$ 10 mi). Motivo: o investidor pessoa física deve poder esconder papéis sem liquidez.
- Botão "Limpar filtros".

Os filtros só recortam linhas das faixas 2, 3 e 5 (lista do seletor). Os cartões e as abas de
rankings **não mudam**, e a barra lateral diz isso embaixo dos filtros:
"Os cartões e os rankings temáticos valem para o mercado inteiro."
Motivo: recortar linha é filtro; recalcular cartão ou contagem por filtro seria regra de negócio
fora do SQL.

Se o filtro deixar zero linhas, mostrar `st.info("Nenhuma ação atende aos filtros.")` no lugar do
gráfico ou da tabela.

## 7. CACHE E ERRO

- Leitura com `st.cache_data`. O botão "Recarregar dados" limpa o cache e recarrega a página.
  `ler_cotacao` também em cache, por ticker.
- Sem `fundamentalistas.duckdb`, ou faltando qualquer tabela obrigatória (`tabelas_faltando()`):
  `st.error` com o título "Tabelas obrigatórias não encontradas:", a lista do que falta e a
  orientação "Gere a camada Gold com `uv run python -m pipeline.materializacao` e clique em
  Recarregar dados.", seguido de `st.stop()`. A verificação roda a cada carregamento da página, fora
  do cache, para que o botão "Recarregar dados" reconheça as tabelas recém-criadas.
- Banco bloqueado por outro processo (inclusive durante a verificação de tabelas): `st.error` com
  o texto "O banco está em uso por outro processo. Feche a DuckDB UI (`ui.py`), a ingestão ou a
  materialização e clique em Recarregar dados." e `st.stop()`.
- Erro do DuckDB ao ler uma tabela: `st.error` com o nome da tabela (`marts.<nome>`) e a mensagem
  do DuckDB, seguido de `st.stop()`.

## 8. APARÊNCIA — Modo Escuro Profissional

Motivo: o painel é usado para análise intensiva; fundo escuro reduz a fadiga visual e faz os
números e as séries coloridas se destacarem, com contraste alto em gráficos múltiplos.

Paleta (constantes únicas em `painel.py`, espelhadas no `config.toml`):

| Papel | Cor |
|---|---|
| Fundo da página | `#0B1120` |
| Fundo secundário (barra lateral, cartões, tooltip) | `#111827` |
| Borda e grade | `#1F2A3C` |
| Texto principal | `#E5E7EB` |
| Texto secundário (definições, anotações, legendas de eixo) | `#94A3B8` |
| Azul da marca (botões, séries de uma cor, cartão 1) | `#3B82F6` |
| Azul claro (segunda série e volume) | `#93C5FD` |
| Recomendações e faixas | item 4.1 |

- `.streamlit/config.toml`: `base = "dark"`, `primaryColor` azul da marca, fundo, fundo
  secundário e texto da tabela acima, fonte sans-serif padrão.
- Template plotly único em `painel.py`: fundo transparente (herda o da página), grade horizontal na
  cor de borda, sem grade vertical, texto principal claro, tooltip com fundo secundário, margens
  enxutas, legenda horizontal acima do gráfico, `hovermode` unificado nas séries temporais.
  `st.plotly_chart(..., theme=None)` para o template mandar nas cores.
- Cartões em fundo secundário com borda; o termômetro usa fundo suave da cor predominante
  (transparência) e borda inteira nessa cor.
- Espaçamento consistente entre faixas (`st.divider` entre seções) e títulos de seção com ícone
  discreto. Nada de cores fora desta tabela e do item 4.1.
- Página com `page_title="B3 Valuation"`, `page_icon="📊"`.

---

# DIVERGÊNCIAS CONHECIDAS (não corrigir nesta entrega)

- **D1 — Universos dos cartões.** "Ações analisadas" (391) vem da consulta-base com join na B3
  (541 tickers) e `liquidez_2_meses > 0`. "Ações sem indicação" (598) conta direto em
  `refined.fundamentus_acoes` (995 tickers). Por isso 391 + 598 = 989 ≠ 995: 6 tickers negociados
  sem emissora na B3 não aparecem em nenhum dos dois cartões. O painel mostra os números dos marts
  como estão e, no tooltip do cartão 5, explica "contado sobre todos os tickers do Fundamentus".
  Mantido como está por decisão do usuário (P4).
- **D2 — Nome do arquivo do cartão 5.** `marts_card_02_acoes_semindicacao.sql` repete o prefixo
  `02` por decisão registrada na spec de marts §14.2. Não renomear.

# PENDÊNCIAS (respondidas pelo usuário em 2026-11-02)

- **P1 — Empate no termômetro.** Empate na quantidade máxima → 🟡 Manter / Neutro.
- **P2 — Malha do mapa.** Obsoleta na v1.1: a faixa do mapa foi removida.
- **P3 — Referência EV/EBIT = 10** na faixa 3: aprovada; desenhar as linhas de ROIC 15% e
  EV/EBIT 10.
- **P4 — Universo do cartão "Sem indicação"** (D1): manter como está.

---

# CRITÉRIOS DE ACEITE

Valores da base em 2026-11-02, conferidos nas tabelas `marts` em 2026-11-03. Se a base for
recarregada e materializada de novo, os números da tela devem ser iguais aos das tabelas `marts`
naquele momento:

- Os cinco primeiros cartões mostram: **391 · 95 · 20 · 276 · 598**.
- O termômetro mostra **🔴 Venda / Risco** com **70,6% das ações analisadas**, em vermelho.
- O painel não mostra mapa, ranking de estados, mapa de calor dos rankings nem o panorama dos
  sinais (força dos sinais e recomendações por segmento).
- O painel abre no Modo Escuro Profissional (item 8), com as cores do item 4.1.
- A tabela do ranking consolidado abre com 391 linhas, ordenada por `posicao`, com Compra no topo.
- Cada aba de ranking abre com o rank 1 do arquivo correspondente no topo.
- A ficha de uma ação sem cotação no YFinance mostra "—" nos indicadores de risco e a mensagem
  "Sem histórico de cotação para este ticker" no lugar do gráfico.
- Uma busca por `groupby`, `.sum(`, `.mean(`, `.count(`, `value_counts`, `merge`, `pivot` e
  `px.histogram` em `painel.py` e `app.py` não encontra nada.
- Com o painel de pé, a ingestão roda sem erro de lock; com a DuckDB UI (`ui.py`) aberta, o painel
  mostra a mensagem de banco bloqueado em vez de traceback.
- Toda SQL de `painel.py` e `app.py` é `SELECT * FROM marts."<nome>"`, com `WHERE ticker = ?` só
  na cotação, mais a consulta de catálogo de `tabelas_faltando()`. Nenhuma referência a `raw.`,
  `refined.` ou ao texto de `sql/marts/*.sql`.
- Sem as tabelas `marts` (por exemplo, num banco ainda não materializado), o painel lista as
  tabelas faltantes e orienta a rodar `pipeline.materializacao`, sem traceback. Depois de
  materializar, "Recarregar dados" abre o painel normalmente.
- Com a materialização rodando, o painel mostra a mensagem de banco bloqueado. Com o painel de pé,
  a materialização roda sem erro de lock.
- Nenhum arquivo de `raw`/`refined`, do `pipeline/` ou SQL já existente é alterado.

# ENTREGA

1. A spec como docstring no topo de `painel.py`, com o motivo de cada regra.
2. O código, comentado só onde a decisão não é óbvia.
3. Os novos marts do item 3, cada um validado no DuckDB (linhas, unicidade do grão, soma
   consistente com os cartões).
4. Uma lista final do que foi assumido e que não estava na spec.
5. (v1.5) Testes automatizados de `painel.py` sem streamlit, sobre um banco temporário, cobrindo:
   - leitura das tabelas `marts`;
   - `tabelas_faltando()`;
   - filtro da cotação por ticker;
   - erro de leitura com o nome da tabela;
   - banco bloqueado.
