"""Painel de recomendações — leitura, formatação e gráficos (camada de apresentação).

Spec: docs/specs/dashboard_apresentacao.md (v1.5). Resumo das regras, com o motivo de cada uma:

1. LEITURA
   - ler(nomes) executa SELECT * FROM marts."<nome>": as tabelas físicas que
     pipeline/materializacao.py gera a partir de sql/marts/<nome>.sql. Motivo: o número já foi
     calculado e validado na materialização; todas as faixas mostram a mesma fotografia e os
     rankings não são reexecutados a cada abertura. Os .sql não são lidos aqui.
   - Conexão duckdb.connect(ARQUIVO_DB, read_only=True), aberta e fechada dentro
     de cada leitura. Motivo: conexão aberta segura o arquivo e o pipeline não consegue gravar.
   - Banco bloqueado por outro processo (DuckDB UI do ui.py, ingestão, materialização) vira
     BancoBloqueado, com mensagem clara no app e sem traceback.
   - ler_cotacao(ticker): marts.marts_cotacao com WHERE ticker = ? (parâmetro vinculado).
     Motivo: a tabela tem ~1,9 milhão de linhas; filtrar no banco evita carregar tudo em memória.
   - tabelas_faltando() lista as tabelas obrigatórias ausentes (catálogo duckdb_tables()).
   - FONTE: banco local (ARQUIVO_DB) ou fotografia versionada (fotografia/, gerada por
     pipeline.fotografia). VALUATIONB3_FONTE = "banco" ou "fotografia" fixa a fonte; sem a
     variável, usa o banco se o arquivo existir e, senão, a fotografia (caso do Streamlit
     Cloud, onde o banco não é versionado). Na fotografia, tabelas_faltando() confere os
     hashes do manifesto antes de qualquer leitura (FotografiaInvalida se divergir) e a
     leitura usa views marts."<nome>" sobre os Parquet: as consultas são as mesmas.
   - Tabela não garante ordem: quem exibe ordena no pandas (posicao/rank, ticker; data).

2. NENHUM CÁLCULO
   - Aqui e em app.py não há agregação do pandas (agrupar, somar, contar, média, contagem de
     valores, mesclar, juntar, transpor para tabela dinâmica, tabular cruzado), nem histograma do
     plotly, nem conta entre colunas. Permitido: ordenar, filtrar linhas, head(n), renomear,
     formatar texto e mapear categorias para cor, ícone ou rótulo por dicionário constante.
     Motivo: número novo na tela exige um .sql novo em sql/marts/, declarado em
     pipeline/materializacao.py e materializado em marts.

3. MARTS DO PAINEL (marts.marts_card_* e marts.marts_painel_*): leem a recomendação de
   marts.marts_50_rank_recomendacoes, sem repetir a regra. Termômetro: empate -> Manter (P1).
   Exclusões do universo por motivo: marts.marts_painel_exclusoes_motivo (contagem pronta,
   inclusive motivos com zero); o painel só ordena e renomeia.

4. LAYOUT (app.py) e LINGUAGEM VISUAL
   - Cinco faixas: pulso do mercado, ranking de oportunidades, valor × qualidade, rankings
     temáticos e ficha da ação (v1.1 removeu o mapa e o mapa de calor; v1.4, o panorama).
   - Recomendação sempre com ícone + rótulo + cor (REC). Motivo: acessibilidade para quem não
     distingue verde de vermelho.
   - Faixas: Superior verde, Intermediário amarelo, Inferior vermelho, Não elegível cinza.
   - Valor × qualidade: linhas ROIC 15% (custo de capital de referência, spec de marts §6.1) e
     EV/EBIT 10 (convenção de mercado aprovada pelo usuário, P3).
   - Cotação: preços nulos ou <= 0 ficam fora do desenho. Motivo: a Silver tem preços ajustados
     negativos em alguns tickers.
   - Responsivo (v1.7): cartões do pulso e mini cartões da ficha em grade CSS que muda o número
     de colunas pela largura da área de conteúdo (GRADE_PULSO, GRADE_FICHA); pares de colunas
     quebram em linhas abaixo de 22rem por coluna; quebra de linha só entre palavras e número
     sem quebra. Motivo: st.columns não empilha com a barra lateral aberta e espremia os
     cartões até partir palavras ("Ações analisa das") e números.

5. FORMATO: milhar com ponto e decimal com vírgula, sem locale do sistema (o resultado não pode
   depender da máquina). pct() não multiplica por 100: os percentuais já estão em 0–100.
   Nulo vira "—", nunca zero. Uma função por gráfico, sem streamlit, para um relatório HTML
   futuro reaproveitar e para testar sem streamlit.

6. FILTROS recortam só as linhas do ranking consolidado, da dispersão valor × qualidade e da
   lista da ficha. Cartões e rankings temáticos valem para o mercado inteiro.
   Motivo: recalcular contagem por filtro seria regra de negócio fora do SQL.

7. CACHE E ERRO (app.py): st.cache_data; tabela faltando (orienta rodar a materialização),
   banco bloqueado ou erro de leitura -> st.error + st.stop(). A checagem de tabelas fica fora
   do cache para "Recarregar dados" enxergar uma materialização recém-feita; na fotografia, os
   hashes só são recalculados quando tamanho ou data de algum arquivo muda.
   marts_cotacao (~1,9 milhão de linhas) nunca entra na carga da página: só ler_cotacao(ticker)
   a abre, com view apenas desse mart, em st.cache_data por ticker.

8. APARÊNCIA: Modo Escuro Profissional (paleta abaixo, espelhada em .streamlit/config.toml).
   Motivo: análise intensiva; fundo escuro reduz a fadiga visual e destaca números e séries.

9. SAÚDE DO PIPELINE (aba própria): marts.marts_painel_saude_pipeline (última execução de cada
   etapa, de meta.execucoes) e, na fotografia, a linha da própria fotografia no manifesto.
   O mart é opcional: sem ele (fotografia ou banco anteriores ao registro) a aba explica o
   motivo e as demais seguem. A idade dos dados vem de pipeline.execucao.idade(): depende do
   dia em que o painel é aberto, por isso não está em mart; o alerta passa de
   execucao.LIMITE_DIAS_UTEIS dias úteis.
"""

import math
import os
from datetime import date, datetime

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots

from pipeline import db, execucao, fotografia

# Mesmo arquivo do pipeline (fundamentalistas.duckdb ou VALUATIONB3_DB), lido na importação.
ARQUIVO_DB = db.caminho_banco()
PASTA_FOTOGRAFIA = fotografia.PASTA_FOTOGRAFIA
VARIAVEL_FONTE = "VALUATIONB3_FONTE"
BANCO = "banco"
FOTOGRAFIA = "fotografia"
SCHEMA_MARTS = "marts"

MARTS_CARDS = [
    "marts_card_01_acoes_analisadas",
    "marts_card_02_acoes_compra",
    "marts_card_03_acoes_manter",
    "marts_card_04_acoes_venda",
    "marts_card_02_acoes_semindicacao",
    "marts_card_05_termometro_mercado",
]
MART_EXCLUSOES = "marts_painel_exclusoes_motivo"
MARTS_PAINEL = [
    "marts_painel_data_referencia",
    "marts_painel_indicadores",
    MART_EXCLUSOES,
]
MARTS_RANKINGS = [
    "marts_01_rank_valor",
    "marts_02_rank_proventos",
    "marts_03_rank_eficiencia",
    "marts_04_rank_retorno",
    "marts_05_rank_pechincha",
    "marts_06_rank_patrimonio",
    "marts_07_rank_crescimento",
    "marts_08_rank_operacional",
    "marts_09_rank_seguro",
    "marts_10_rank_rentabilidade",
]
MART_RECOMENDACOES = "marts_50_rank_recomendacoes"
MART_RISCO = "marts_retorno_total_risco"
MART_COTACAO = "marts_cotacao"
# Opcional: lido só pela aba "Saúde do pipeline" (ler_saude).
MART_SAUDE = execucao.MART_SAUDE

# Lidos de uma vez no carregamento da página (a cotação é lida por ticker).
MARTS_CARREGAR = (
    MARTS_CARDS + MARTS_PAINEL + MARTS_RANKINGS + [MART_RECOMENDACOES, MART_RISCO]
)
MARTS_OBRIGATORIOS = MARTS_CARREGAR + [MART_COTACAO]

MSG_BLOQUEADO = (
    "O banco está em uso por outro processo. Feche a DuckDB UI (`ui.py`), a ingestão ou a "
    "materialização e clique em Recarregar dados."
)
MSG_MATERIALIZAR = (
    "Gere a camada Gold com `uv run python -m pipeline.materializacao` e clique em "
    "Recarregar dados."
)
MSG_FOTOGRAFIA = (
    "Gere a fotografia com `uv run python -m pipeline.fotografia` e versione a pasta "
    "`fotografia/`."
)


# --------------------------------------------------------------------------------------------
# 1. Leitura
# --------------------------------------------------------------------------------------------
class BancoBloqueado(Exception):
    pass


class FotografiaInvalida(Exception):
    pass


class ErroMart(Exception):
    def __init__(self, tabela, mensagem):
        super().__init__(f"{tabela}: {mensagem}")
        self.tabela = tabela
        self.mensagem = mensagem


def _tabela(nome):
    return f'{SCHEMA_MARTS}."{nome}"'


def _rotulo(nome):
    return f"{SCHEMA_MARTS}.{nome}"


def fonte():
    """De onde o painel lê: BANCO ou FOTOGRAFIA (ver regra 1, FONTE)."""
    escolhida = os.environ.get(VARIAVEL_FONTE, "").strip().lower()
    if escolhida in (BANCO, FOTOGRAFIA):
        return escolhida
    if escolhida:
        raise ValueError(
            f"{VARIAVEL_FONTE}={escolhida!r} inválida: use {BANCO!r} ou {FOTOGRAFIA!r}"
        )
    if ARQUIVO_DB.exists() or not (PASTA_FOTOGRAFIA / fotografia.MANIFESTO).exists():
        return BANCO
    return FOTOGRAFIA


def origem():
    """Rótulo da fonte para o cabeçalho do app (sem ler as tabelas)."""
    if fonte() == BANCO:
        return f"banco local `{ARQUIVO_DB.name}`"
    manifesto = fotografia.ler_manifesto(PASTA_FOTOGRAFIA)
    return (
        f"fotografia versionada de {data_br(date.fromisoformat(manifesto['data_referencia']))}"
        f" · hash `{manifesto['hash'][:12]}`"
    )


def mensagem_faltando():
    return MSG_FOTOGRAFIA if fonte() == FOTOGRAFIA else MSG_MATERIALIZAR


# Assinatura dos arquivos (caminho, tamanho, mtime) -> manifesto já conferido.
_FOTOGRAFIA_VERIFICADA = {}


def _assinatura(pasta):
    if not pasta.is_dir():
        return (str(pasta),)
    return (str(pasta.resolve()),) + tuple(
        (a.name, a.stat().st_size, a.stat().st_mtime_ns)
        for a in sorted(pasta.iterdir())
        if a.is_file()
    )


def _verificar_fotografia():
    """fotografia.verificar() só quando algum arquivo mudou desde a última conferência.

    Motivo: o SHA-256 lê os ~27 MB da pasta (10 MB só da cotação) e tabelas_faltando() roda a
    cada interação; com os arquivos intactos, o resultado é o mesmo.
    """
    assinatura = _assinatura(PASTA_FOTOGRAFIA)
    if assinatura not in _FOTOGRAFIA_VERIFICADA:
        try:
            manifesto = fotografia.verificar(PASTA_FOTOGRAFIA)
        except fotografia.ErroFotografia as erro:
            raise FotografiaInvalida(str(erro)) from erro
        _FOTOGRAFIA_VERIFICADA.clear()
        _FOTOGRAFIA_VERIFICADA[assinatura] = manifesto
    return _FOTOGRAFIA_VERIFICADA[assinatura]


def tabelas_faltando():
    """Banco ou tabelas marts obrigatórias que não existem (rótulos marts.<nome>)."""
    if fonte() == FOTOGRAFIA:
        manifesto = _verificar_fotografia()
        return [_rotulo(n) for n in MARTS_OBRIGATORIOS if n not in manifesto["tabelas"]]
    if not ARQUIVO_DB.exists():
        return [ARQUIVO_DB.name]
    con = _conectar()
    try:
        existentes = {
            nome
            for (nome,) in con.execute(
                "SELECT table_name FROM duckdb_tables() WHERE schema_name = ?",
                [SCHEMA_MARTS],
            ).fetchall()
        }
    finally:
        con.close()
    return [_rotulo(n) for n in MARTS_OBRIGATORIOS if n not in existentes]


def _conectar(nomes=None):
    if fonte() == FOTOGRAFIA:
        try:
            return fotografia.conectar(PASTA_FOTOGRAFIA, nomes)
        except fotografia.ErroFotografia as erro:
            raise FotografiaInvalida(str(erro)) from erro
    try:
        return duckdb.connect(str(ARQUIVO_DB), read_only=True)
    except duckdb.IOException as erro:
        # No Windows o lock de outro processo chega como IOException ao abrir o arquivo.
        raise BancoBloqueado(MSG_BLOQUEADO) from erro


def ler(nomes):
    """Lê cada tabela marts.<nome> inteira e devolve {nome: DataFrame}."""
    con = _conectar(nomes)
    try:
        resultado = {}
        for nome in nomes:
            try:
                resultado[nome] = con.execute(f"SELECT * FROM {_tabela(nome)}").df()
            except duckdb.Error as erro:
                raise ErroMart(_rotulo(nome), str(erro)) from erro
        return resultado
    finally:
        con.close()


def ler_cotacao(ticker):
    """Histórico de um ticker: marts.marts_cotacao filtrada no banco por parâmetro vinculado."""
    sql = f"SELECT * FROM {_tabela(MART_COTACAO)} WHERE ticker = ?"
    con = _conectar([MART_COTACAO])
    try:
        try:
            return con.execute(sql, [ticker]).df()
        except duckdb.Error as erro:
            raise ErroMart(_rotulo(MART_COTACAO), str(erro)) from erro
    finally:
        con.close()


# --------------------------------------------------------------------------------------------
# 5. Formato (funções puras)
# --------------------------------------------------------------------------------------------
TRACO = "—"


def _nulo(valor):
    if valor is None or valor is pd.NA or valor is pd.NaT:
        return True
    try:
        return math.isnan(float(valor))
    except (TypeError, ValueError):
        return False


def _br(valor, casas):
    # Formata em padrão americano e troca os separadores: independe do locale da máquina.
    texto = f"{float(valor):,.{casas}f}"
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


def numero(valor, casas=0):
    return TRACO if _nulo(valor) else _br(valor, casas)


def reais(valor, casas=2):
    return TRACO if _nulo(valor) else f"R$ {_br(valor, casas)}"


def reais_compacto(valor):
    if _nulo(valor):
        return TRACO
    v = float(valor)
    for limite, sufixo, casas in ((1e9, "bi", 1), (1e6, "mi", 1), (1e3, "mil", 0)):
        if abs(v) >= limite:
            return f"R$ {_br(v / limite, casas)} {sufixo}"
    return reais(v)


def pct(valor, casas=1):
    return TRACO if _nulo(valor) else f"{_br(valor, casas)}%"


def multiplo(valor, casas=1):
    return TRACO if _nulo(valor) else f"{_br(valor, casas)}x"


def data_br(valor):
    if _nulo(valor):
        return TRACO
    if isinstance(valor, str):
        valor = datetime.fromisoformat(valor)
    if isinstance(valor, (datetime, date)):
        return valor.strftime("%d/%m/%Y")
    return pd.Timestamp(valor).strftime("%d/%m/%Y")


# --------------------------------------------------------------------------------------------
# 4.1 e 8. Paleta do Modo Escuro Profissional e linguagem visual (dicionários constantes)
# --------------------------------------------------------------------------------------------
FUNDO = "#0B1120"
FUNDO_2 = "#111827"
BORDA = "#1F2A3C"
TEXTO = "#E5E7EB"
TEXTO_2 = "#94A3B8"
AZUL = "#3B82F6"
AZUL_CLARO = "#93C5FD"
CINZA = "#94A3B8"

REC = {
    "Compra": {"icone": "🟢", "rotulo": "Compra / Oportunidade", "cor": "#22C55E"},
    "Manter": {"icone": "🟡", "rotulo": "Manter / Neutro", "cor": "#FACC15"},
    "Venda": {"icone": "🔴", "rotulo": "Venda / Risco", "cor": "#F87171"},
    "Sem indicação": {"icone": "⚪", "rotulo": "Sem indicação", "cor": CINZA},
}
RECS_ANALISADAS = ["Compra", "Manter", "Venda"]
BADGE = {k: f"{v['icone']} {v['rotulo']}" for k, v in REC.items()}
COR_BADGE = {BADGE[k]: v["cor"] for k, v in REC.items()}
ORDEM_BADGE = [BADGE[k] for k in RECS_ANALISADAS]

# Código ordinal fixo usado apenas para posicionar a faixa no radar; nunca exibido.
FAIXAS = {
    "Não elegível": {"icone": "⚪", "curto": "N/E", "cor": CINZA, "codigo": 0},
    "Inferior": {
        "icone": "🔴",
        "curto": "Inf.",
        "cor": REC["Venda"]["cor"],
        "codigo": 1,
    },
    "Intermediário": {
        "icone": "🟡",
        "curto": "Int.",
        "cor": REC["Manter"]["cor"],
        "codigo": 2,
    },
    "Superior": {
        "icone": "🟢",
        "curto": "Sup.",
        "cor": REC["Compra"]["cor"],
        "codigo": 3,
    },
}
FAIXA_CODIGO = {k: v["codigo"] for k, v in FAIXAS.items()}
FAIXA_CELULA = {k: f"{v['icone']} {v['curto']}" for k, v in FAIXAS.items()}
FAIXA_NOMES_POR_CODIGO = ["Não elegível", "Inferior", "Intermediário", "Superior"]

# Indicadores: rótulo curto e função de formato.
INDICADORES = {
    "roic": ("ROIC", pct),
    "roe": ("ROE", pct),
    "enterprise_value_ebit": ("EV/EBIT", multiplo),
    "preco_lucro": ("P/L", multiplo),
    "earnings_yield": ("Earnings yield", pct),
    "preco_valor_patrimonial": ("P/VP", multiplo),
    "p_vp_por_roe": ("P/VP ÷ ROE", lambda v: numero(v, 3)),
    "dividend_yield": ("DY", pct),
    "payout": ("Payout", pct),
    "margem_ebit": ("Margem EBIT", pct),
    "margem_liquida": ("Margem líquida", pct),
    "divida_liquida_patrimonio": ("DL/PL", lambda v: numero(v, 2)),
    "crescimento_receita_5_anos": ("Cresc. receita 5 anos", pct),
}

# 4.7 Rankings temáticos, na ordem das abas. "chave" liga à coluna faixa_* de marts_50.
RANKINGS = [
    {
        "chave": "valor",
        "mart": "marts_01_rank_valor",
        "aba": "💎 Valor",
        "nome": "Valor",
        "frase": "Rentáveis e baratas (Magic Formula simplificada)",
        "barras": ["roic"],
        "tooltip": ["enterprise_value_ebit"],
        "tabela": ["roic", "enterprise_value_ebit"],
    },
    {
        "chave": "proventos",
        "mart": "marts_02_rank_proventos",
        "aba": "💰 Proventos",
        "nome": "Proventos",
        "frase": "Maiores pagadoras de dividendos, com menor payout no desempate",
        "barras": ["dividend_yield"],
        "tooltip": ["payout"],
        "tabela": ["dividend_yield", "preco_lucro", "payout"],
    },
    {
        "chave": "eficiencia",
        "mart": "marts_03_rank_eficiencia",
        "aba": "⚙️ Eficiência",
        "nome": "Eficiência",
        "frase": "Melhores margens",
        "barras": ["margem_ebit", "margem_liquida"],
        "tooltip": [],
        "tabela": ["margem_ebit", "margem_liquida"],
    },
    {
        "chave": "retorno",
        "mart": "marts_04_rank_retorno",
        "aba": "📈 Retorno",
        "nome": "Retorno",
        "frase": "ROE alto com dívida controlada",
        "barras": ["roe"],
        "tooltip": ["divida_liquida_patrimonio"],
        "tabela": ["roe", "divida_liquida_patrimonio"],
    },
    {
        "chave": "pechincha",
        "mart": "marts_05_rank_pechincha",
        "aba": "🏷️ Pechincha",
        "nome": "Pechincha",
        "frase": "Menores múltiplos de preço",
        "barras": ["preco_lucro"],
        "tooltip": ["enterprise_value_ebit"],
        "tabela": ["preco_lucro", "enterprise_value_ebit"],
    },
    {
        "chave": "patrimonio",
        "mart": "marts_06_rank_patrimonio",
        "aba": "🏛️ Patrimônio",
        "nome": "Patrimônio",
        "frase": "Menor preço por ponto de rentabilidade",
        "barras": ["p_vp_por_roe"],
        "tooltip": ["preco_valor_patrimonial", "roe"],
        "tabela": ["preco_valor_patrimonial", "roe", "p_vp_por_roe"],
    },
    {
        "chave": "crescimento",
        "mart": "marts_07_rank_crescimento",
        "aba": "🚀 Crescimento",
        "nome": "Crescimento",
        "frase": "Receita crescendo com ROIC > 10%",
        "barras": ["crescimento_receita_5_anos"],
        "tooltip": ["roic"],
        "tabela": ["crescimento_receita_5_anos", "roic"],
    },
    {
        "chave": "operacional",
        "mart": "marts_08_rank_operacional",
        "aba": "🏭 Operacional",
        "nome": "Operacional",
        "frase": "Maior margem operacional",
        "barras": ["margem_ebit"],
        "tooltip": [],
        "tabela": ["margem_ebit"],
    },
    {
        "chave": "seguro",
        "mart": "marts_09_rank_seguro",
        "aba": "🛡️ Seguro",
        "nome": "Seguro",
        "frase": "Menor alavancagem com rentabilidade",
        "barras": ["divida_liquida_patrimonio"],
        "tooltip": ["roic", "roe"],
        "tabela": ["divida_liquida_patrimonio", "roic", "roe"],
    },
    {
        "chave": "rentabilidade",
        "mart": "marts_10_rank_rentabilidade",
        "aba": "🎯 Rentabilidade",
        "nome": "Rentabilidade",
        "frase": "Maior lucro por real investido",
        "barras": ["earnings_yield"],
        "tooltip": ["preco_lucro"],
        "tabela": ["preco_lucro", "earnings_yield"],
    },
]
FAIXA_COLUNAS = {f"faixa_{r['chave']}": r["nome"] for r in RANKINGS}

# 6. Faixas fixas de liquidez mínima em 2 meses.
LIQUIDEZ_MINIMA = {
    "Todas": None,
    "R$ 100 mil": 100_000,
    "R$ 1 mi": 1_000_000,
    "R$ 10 mi": 10_000_000,
}


def filtrar(df, recomendacoes, segmentos, liquidez_minima):
    """Recorta linhas por recomendação, segmento e liquidez (segmentos vazio = sem filtro;
    recomendações vazia não deixa nenhuma linha)."""
    mascara = df["recomendacao"].isin(recomendacoes)
    if segmentos:
        mascara &= df["segmento"].isin(segmentos)
    if liquidez_minima is not None:
        mascara &= df["liquidez_2_meses"] >= liquidez_minima
    return df[mascara]


# --------------------------------------------------------------------------------------------
# 8. Template plotly único (Modo Escuro Profissional)
# --------------------------------------------------------------------------------------------
FONTE = "Source Sans Pro, sans-serif"
pio.templates["b3"] = go.layout.Template(
    layout=go.Layout(
        font={"family": FONTE, "color": TEXTO, "size": 13},
        title={
            "font": {"size": 16, "color": TEXTO},
            "x": 0,
            "xanchor": "left",
            "y": 0.97,
            "yref": "container",
        },
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        separators=",.",
        margin={"l": 8, "r": 8, "t": 72, "b": 8},
        legend={
            "orientation": "h",
            "x": 0,
            "xanchor": "left",
            "y": 1.0,
            "yanchor": "bottom",
            "title": {"text": ""},
            "font": {"color": TEXTO},
        },
        # automargin: a margem cresce até caber o rótulo (ticker, R$) em vez de cortá-lo.
        xaxis={
            "automargin": True,
            "showgrid": False,
            "zeroline": False,
            "linecolor": BORDA,
            "tickfont": {"color": TEXTO_2},
            "title": {"font": {"color": TEXTO_2}},
        },
        yaxis={
            "automargin": True,
            "showgrid": True,
            "gridcolor": BORDA,
            "zeroline": False,
            "linecolor": BORDA,
            "tickfont": {"color": TEXTO_2},
            "title": {"font": {"color": TEXTO_2}},
        },
        hoverlabel={
            "font": {"family": FONTE, "color": TEXTO},
            "bgcolor": FUNDO_2,
            "bordercolor": BORDA,
        },
        colorway=[AZUL],
    )
)
TEMPLATE = "b3"


def _layout(fig, titulo, altura):
    fig.update_layout(template=TEMPLATE, title={"text": titulo}, height=altura)
    return fig


# --------------------------------------------------------------------------------------------
# Cartões (HTML)
# --------------------------------------------------------------------------------------------
# Grades responsivas: (largura mínima da área de conteúdo em rem, colunas). A largura é a do
# contêiner (container query), não a da janela: a barra lateral aberta também estreita a área.
# Pulso: 6 lado a lado (1440 px), 3 × 2 (tablet ou janela média), 2 × 3 (celular).
# Ficha: 10 métricas em 5 × 2 ou 2 × 5, sem linha incompleta.
GRADE_PULSO = ((0, 2), (30, 3), (54, 6))
GRADE_FICHA = ((0, 2), (40, 5))
# Saúde: 4 métricas em 4 × 1 ou 2 × 2.
GRADE_SAUDE = ((0, 2), (40, 4))


def css_grade(nome, grade):
    """Regras CSS da grade .b3-grade-<nome>: a menor faixa é a base, as outras, @container."""
    regras = []
    for minimo, colunas in sorted(grade):
        regra = f".b3-grade-{nome} {{grid-template-columns:repeat({colunas}, minmax(0, 1fr));}}"
        regras.append(
            regra if minimo == 0 else f"@container (min-width: {minimo}rem) {{{regra}}}"
        )
    return "\n".join(regras)


def html_grade(nome, itens):
    """Itens HTML (cartões, métricas) numa grade .b3-grade-<nome>, na ordem recebida."""
    return (
        f'<div class="b3-envelope"><div class="b3-grade b3-grade-{nome}">'
        f"{''.join(itens)}</div></div>"
    )


# Pares de st.columns dentro de st.container(key="par-…") ou do cabeçalho quebram em linhas
# quando a coluna ficaria mais estreita que o mínimo (st.columns sozinho só empilha abaixo de
# 640 px de janela, sem contar a barra lateral).
CSS = f"""
<style>
.b3-envelope {{container-type:inline-size; margin-bottom:1rem;}}
.b3-grade {{display:grid; gap:0.75rem;}}
{css_grade("pulso", GRADE_PULSO)}
{css_grade("ficha", GRADE_FICHA)}
{css_grade("saude", GRADE_SAUDE)}
.b3-card, .b3-metrica {{overflow-wrap:normal; word-break:normal; hyphens:manual;}}
.b3-card {{background:{FUNDO_2}; border:1px solid {BORDA}; border-top:4px solid var(--cor);
  border-radius:8px; padding:14px 16px; min-height:150px; display:flex; flex-direction:column;
  gap:2px;}}
.b3-card.destaque {{background:var(--fundo); border:2px solid var(--cor);}}
.b3-rotulo {{font-size:0.9rem; font-weight:600; color:{TEXTO_2}; line-height:1.3;}}
.b3-numero {{font-size:2.2rem; font-weight:700; line-height:1.15; color:{TEXTO};
  white-space:nowrap; font-variant-numeric:tabular-nums;}}
.b3-destaque {{font-size:1.15rem; font-weight:700; color:var(--cor); margin-top:4px;}}
.b3-def {{font-size:0.8rem; color:{TEXTO_2}; line-height:1.35;}}
.b3-barra {{display:flex; height:8px; border-radius:4px; overflow:hidden; margin-top:auto;}}
.b3-metrica {{border:1px solid {BORDA}; border-radius:8px; padding:12px 14px;
  display:flex; flex-direction:column; justify-content:space-between; gap:6px;}}
.b3-metrica .b3-rotulo {{font-size:0.85rem; font-weight:400;}}
.b3-valor {{font-size:1.5rem; font-weight:600; line-height:1.2; color:{TEXTO};
  white-space:nowrap; font-variant-numeric:tabular-nums;}}
.st-key-cabecalho [data-testid="stHorizontalBlock"],
[class*="st-key-par-"] [data-testid="stHorizontalBlock"] {{flex-wrap:wrap; row-gap:1rem;}}
.st-key-cabecalho [data-testid="stColumn"] {{min-width:min(100%, 11rem);}}
[class*="st-key-par-"] [data-testid="stColumn"] {{min-width:min(100%, 22rem);}}
.st-key-cabecalho h1 {{font-size:clamp(1.75rem, 1.1rem + 2.4vw, 2.75rem);}}
</style>
"""


def html_metrica(rotulo, valor):
    """Mini cartão da ficha: rótulo e valor já formatado (o texto exibido não muda)."""
    return (
        f'<div class="b3-metrica"><div class="b3-rotulo">{rotulo}</div>'
        f'<div class="b3-valor">{valor}</div></div>'
    )


def html_cartao(rotulo, valor, definicao, cor, dica=None):
    titulo = f' title="{dica}"' if dica else ""
    return (
        f'<div class="b3-card" style="--cor:{cor}"{titulo}>'
        f'<div class="b3-rotulo">{rotulo}</div>'
        f'<div class="b3-numero">{numero(valor)}</div>'
        f'<div class="b3-def">{definicao}</div></div>'
    )


def html_termometro(termometro, compra, manter, venda):
    """Cartão 6: assume a cor da recomendação predominante; a barra só desenha as quantidades
    dos cartões 2 a 4 (flex-grow proporcional ao próprio número, sem conta)."""
    linha = termometro.iloc[0]
    rec = REC[linha["recomendacao"]]
    barra = ""
    for chave, qtd in (("Compra", compra), ("Manter", manter), ("Venda", venda)):
        barra += (
            f'<span style="flex:{int(qtd)} 1 0; background:{REC[chave]["cor"]}" '
            f'title="{BADGE[chave]}: {numero(qtd)}"></span>'
        )
    return (
        f'<div class="b3-card destaque" style="--cor:{rec["cor"]}; --fundo:{rec["cor"]}1F">'
        f'<div class="b3-rotulo">🌡️ Termômetro de mercado</div>'
        f'<div class="b3-destaque">{rec["icone"]} {rec["rotulo"]}</div>'
        f'<div class="b3-def">{pct(linha["percentual"])} das ações analisadas</div>'
        f'<div class="b3-barra">{barra}</div></div>'
    )


# --------------------------------------------------------------------------------------------
# Gráficos — uma função por gráfico
# --------------------------------------------------------------------------------------------
def tabela_consolidado(rec):
    """DataFrame de exibição do ranking consolidado (formatação, sem conta)."""
    df = rec.sort_values(["posicao", "ticker"])
    vista = pd.DataFrame(
        {
            "posicao": df["posicao"],
            "recomendacao": df["recomendacao"].map(BADGE),
            "ticker": df["ticker"],
            "empresa": df["empresa"],
            "segmento": df["segmento"],
            "cotacao": df["cotacao"].map(reais),
            "liquidez_2_meses": df["liquidez_2_meses"].map(reais_compacto),
            "saldo": df["saldo"],
        }
    )
    for coluna in FAIXA_COLUNAS:
        vista[coluna] = df[coluna].map(FAIXA_CELULA)
    return vista


def tabela_exclusoes(exclusoes):
    """DataFrame de exibição das exclusões do universo por motivo (ordem das regras)."""
    df = exclusoes.sort_values("ordem")
    return pd.DataFrame(
        {
            "motivo": df["motivo"],
            "descricao": df["descricao"],
            "quantidade": df["quantidade"],
            "quantidade_negociada": df["quantidade_negociada"],
        }
    )


def fig_valor_qualidade(ind):
    df = ind[(ind["enterprise_value_ebit"] > 0) & (ind["roic"] > 0)].assign(
        rotulo=lambda d: d["recomendacao"].map(BADGE),
        pl=lambda d: d["preco_lucro"].map(multiplo),
        dy=lambda d: d["dividend_yield"].map(pct),
        roe_txt=lambda d: d["roe"].map(pct),
        ev_txt=lambda d: d["enterprise_value_ebit"].map(multiplo),
        roic_txt=lambda d: d["roic"].map(pct),
        liq=lambda d: d["liquidez_2_meses"].map(reais_compacto),
    )
    fig = px.scatter(
        df,
        x="enterprise_value_ebit",
        y="roic",
        color="rotulo",
        size="liquidez_2_meses",
        size_max=36,
        color_discrete_map=COR_BADGE,
        category_orders={"rotulo": ORDEM_BADGE},
        custom_data=[
            "ticker",
            "empresa",
            "ev_txt",
            "roic_txt",
            "pl",
            "dy",
            "roe_txt",
            "liq",
        ],
    )
    fig.update_traces(
        marker={"opacity": 0.8, "line": {"width": 0.6, "color": FUNDO}},
        hovertemplate=(
            "<b>%{customdata[0]}</b> · %{customdata[1]}<br>EV/EBIT: %{customdata[2]}"
            "<br>ROIC: %{customdata[3]}<br>P/L: %{customdata[4]}<br>DY: %{customdata[5]}"
            "<br>ROE: %{customdata[6]}<br>Liquidez 2 meses: %{customdata[7]}<extra></extra>"
        ),
    )
    fig.add_hline(
        y=15,
        line_dash="dash",
        line_color=TEXTO_2,
        annotation_text="ROIC 15% · custo de capital de referência",
        annotation_position="top right",
        annotation_font_color=TEXTO_2,
    )
    fig.add_vline(
        x=10,
        line_dash="dash",
        line_color=TEXTO_2,
        annotation_text="EV/EBIT 10x",
        # dentro da área do gráfico: acima dela, o rótulo cobria a legenda
        annotation_position="top right",
        annotation_yanchor="top",
        annotation_font_color=TEXTO_2,
    )
    # px.scatter põe o nome da coluna ("rotulo") como título da legenda; o tamanho fixo evita
    # que o marcador da legenda herde o tamanho da bolha. Abaixo do gráfico, a legenda pode
    # quebrar em várias linhas no celular sem cobrir o título.
    fig.update_layout(
        legend={
            "title": {"text": ""},
            "itemsizing": "constant",
            "y": -0.16,
            "yanchor": "top",
        }
    )
    for x, y, texto, xa, ya in (
        (0.5, 58, "Qualidade a bom preço", "left", "top"),
        (29.5, 1, "Cara e pouco rentável", "right", "bottom"),
    ):
        fig.add_annotation(
            x=x,
            y=y,
            text=texto,
            showarrow=False,
            xanchor=xa,
            yanchor=ya,
            font={"color": TEXTO_2, "size": 14},
        )
    fig.update_xaxes(
        title="EV/EBIT (x) — menor = mais barata",
        range=[0, 30],
        ticksuffix="x",
        showgrid=True,
        gridcolor=BORDA,
    )
    fig.update_yaxes(
        title="ROIC (%) — maior = mais rentável", range=[0, 60], ticksuffix="%"
    )
    return _layout(fig, "3 · Qualidade versus preço", 560)


def _top_ranking(df, n=15):
    return df.sort_values(["rank", "ticker"]).head(n)


def fig_ranking_tematico(df, ranking, n=15):
    top = _top_ranking(df, n)
    tickers = top["ticker"].tolist()
    extras = ranking["tooltip"]
    fig = go.Figure()
    cores = [AZUL, AZUL_CLARO]
    for i, coluna in enumerate(ranking["barras"]):
        rotulo, formato = INDICADORES[coluna]
        dados = [top["empresa"].tolist(), top["rank"].tolist()]
        dica = ""
        for j, extra in enumerate(extras):
            dados.append(top[extra].map(INDICADORES[extra][1]).tolist())
            dica += f"<br>{INDICADORES[extra][0]}: %{{customdata[{j + 2}]}}"
        fig.add_trace(
            go.Bar(
                name=rotulo,
                y=tickers,
                x=top[coluna].tolist(),
                orientation="h",
                marker_color=cores[i],
                text=top[coluna].map(formato).tolist(),
                textposition="outside",
                cliponaxis=False,
                textfont={"color": TEXTO},
                customdata=list(zip(*dados, strict=False)),
                hovertemplate=(
                    f"<b>%{{y}}</b> · %{{customdata[0]}}<br>Rank %{{customdata[1]}}"
                    f"<br>{rotulo}: %{{text}}{dica}<extra></extra>"
                ),
            )
        )
    unidade = INDICADORES[ranking["barras"][0]][0]
    if len(ranking["barras"]) > 1:
        unidade = "Margem (%)"
    elif INDICADORES[ranking["barras"][0]][1] is pct:
        unidade += " (%)"
    elif INDICADORES[ranking["barras"][0]][1] is multiplo:
        unidade += " (x)"
    # margem direita: o rótulo "outside" da maior barra não entra no automargin dos eixos.
    fig.update_layout(
        barmode="group",
        showlegend=len(ranking["barras"]) > 1,
        margin={"r": 56},
    )
    fig.update_yaxes(autorange="reversed", type="category", title=None, showgrid=False)
    fig.update_xaxes(title=unidade, showgrid=True, gridcolor=BORDA)
    return _layout(fig, f"4 · {ranking['aba']} — top {n}", 120 + 30 * len(top))


def tabela_ranking_tematico(df, ranking, n=15):
    top = _top_ranking(df, n)
    vista = pd.DataFrame(
        {"rank": top["rank"], "ticker": top["ticker"], "empresa": top["empresa"]}
    )
    for coluna in ranking["tabela"]:
        rotulo, formato = INDICADORES[coluna]
        vista[rotulo] = top[coluna].map(formato)
    return vista


def fig_radar(linha):
    """Perfil do ticker nos 10 rankings: faixa no eixo radial pelo código ordinal fixo."""
    nomes = list(FAIXA_COLUNAS.values())
    faixas = [linha[c] for c in FAIXA_COLUNAS]
    r = [FAIXA_CODIGO[f] for f in faixas]
    cor = REC[linha["recomendacao"]]["cor"]
    fig = go.Figure(
        go.Scatterpolar(
            r=r + r[:1],
            theta=nomes + nomes[:1],
            customdata=faixas + faixas[:1],
            fill="toself",
            fillcolor=f"{cor}40",
            line={"color": cor, "width": 2},
            marker={"size": 7},
            hovertemplate="<b>%{theta}</b><br>%{customdata}<extra></extra>",
        )
    )
    fig.update_layout(
        showlegend=False,
        polar={
            "bgcolor": "rgba(0,0,0,0)",
            "radialaxis": {
                "range": [0, 3],
                "tickvals": [0, 1, 2, 3],
                "ticktext": FAIXA_NOMES_POR_CODIGO,
                "gridcolor": BORDA,
                "linecolor": BORDA,
                "tickfont": {"size": 10, "color": TEXTO_2},
                "angle": 90,
            },
            "angularaxis": {
                "gridcolor": BORDA,
                "linecolor": BORDA,
                "direction": "clockwise",
                "tickfont": {"color": TEXTO},
            },
        },
        # o eixo polar não tem automargin: 84 px cabem "Operacional" e "Rentabilidade"
        margin={"l": 84, "r": 84, "t": 72, "b": 30},
    )
    return _layout(fig, "5 · Perfil nos 10 rankings", 440)


def fig_cotacao(cot):
    """Linha de fechamento ajustado + volume; proventos marcados com 💰."""
    validas = cot[cot["fechamento_ajustado"].notna() & (cot["fechamento_ajustado"] > 0)]
    validas = validas.sort_values("data")
    proventos = validas[validas["dividendos"] > 0]
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.75, 0.25],
        vertical_spacing=0.04,
    )
    fig.add_trace(
        go.Scatter(
            x=validas["data"],
            y=validas["fechamento_ajustado"],
            mode="lines",
            name="Fechamento ajustado",
            line={"color": AZUL, "width": 1.6},
            text=validas["fechamento_ajustado"].map(reais),
            hovertemplate="Fechamento ajustado: %{text}<extra></extra>",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=proventos["data"],
            y=proventos["fechamento_ajustado"],
            mode="text",
            text="💰",
            textposition="top center",
            name="Provento",
            textfont={"size": 14},
            customdata=proventos["dividendos"].map(lambda v: reais(v, 4)),
            hovertemplate="💰 Provento: %{customdata} por ação<extra></extra>",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Bar(
            x=validas["data"],
            y=validas["volume"],
            name="Volume",
            marker_color=AZUL_CLARO,
            marker_opacity=0.6,
            text=validas["volume"].map(numero),
            textposition="none",
            hovertemplate="Volume: %{text}<extra></extra>",
        ),
        row=2,
        col=1,
    )
    fig.update_xaxes(
        rangeselector={
            "buttons": [
                {"count": 1, "label": "1A", "step": "year", "stepmode": "backward"},
                {"count": 3, "label": "3A", "step": "year", "stepmode": "backward"},
                {"count": 5, "label": "5A", "step": "year", "stepmode": "backward"},
                {"label": "Tudo", "step": "all"},
            ],
            "x": 0,
            "y": 1.02,
            "bgcolor": FUNDO_2,
            "activecolor": AZUL,
            "bordercolor": BORDA,
            "borderwidth": 1,
            "font": {"color": TEXTO},
        },
        row=1,
        col=1,
    )
    fig.update_yaxes(title="Preço ajustado (R$)", tickprefix="R$ ", row=1, col=1)
    fig.update_yaxes(title="Volume (ações)", row=2, col=1)
    fig.update_layout(hovermode="x unified", showlegend=False, bargap=0)
    return _layout(fig, "5 · Cotação histórica", 520)


# --------------------------------------------------------------------------------------------
# 9. Saúde do pipeline (aba própria no app)
# --------------------------------------------------------------------------------------------
ETAPA_ROTULO = {
    "ingestao": "1 · Ingestão",
    "transformacao": "2 · Transformação",
    "materializacao": "3 · Materialização",
    "qualidade": "4 · Qualidade",
    "fotografia": "5 · Fotografia",
}
CAMADA_ROTULO = {
    "raw": "Bronze (raw)",
    "refined": "Silver (refined)",
    "marts": "Gold (marts)",
}
STATUS_EXECUCAO = {
    execucao.SUCESSO: {"rotulo": "✅ Sucesso", "cor": REC["Compra"]["cor"]},
    execucao.FALHA: {"rotulo": "❌ Falha", "cor": REC["Venda"]["cor"]},
}
SEM_REGISTRO = "⚪ Sem registro"


def _existe(con, nome):
    # information_schema cobre a tabela do banco e a view da fotografia
    return (
        con.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema = ? AND table_name = ?",
            [SCHEMA_MARTS, nome],
        ).fetchall()[0][0]
        > 0
    )


def ler_saude():
    """marts.marts_painel_saude_pipeline, ou None se o mart não existe.

    O mart é opcional (fora de MARTS_OBRIGATORIOS): fotografias e bancos anteriores ao
    registro de execução não o têm, e isso não pode impedir o painel de abrir.
    """
    con = _conectar([MART_SAUDE])
    try:
        if not _existe(con, MART_SAUDE):
            return None
        try:
            return con.execute(f"SELECT * FROM {_tabela(MART_SAUDE)}").df()
        except duckdb.Error as erro:
            raise ErroMart(_rotulo(MART_SAUDE), str(erro)) from erro
    finally:
        con.close()


def execucao_fotografia():
    """Registro da geração da fotografia lida (manifesto), ou None no banco local."""
    if fonte() != FOTOGRAFIA:
        return None
    manifesto = fotografia.ler_manifesto(PASTA_FOTOGRAFIA)
    for registro in manifesto.get("execucoes", []):
        if registro["etapa"] == "fotografia":
            return registro
    return None


def idade_dados(data_referencia, hoje=None):
    """Idade da data de referência em dias corridos e úteis (pipeline.execucao.idade)."""
    return execucao.idade(pd.Timestamp(data_referencia).date(), hoje)


def data_hora(valor):
    """Horário UTC do registro de execução: '02/11/2026 09:05 UTC'."""
    if _nulo(valor):
        return TRACO
    if isinstance(valor, str):
        valor = datetime.fromisoformat(valor)
    return f"{pd.Timestamp(valor).strftime('%d/%m/%Y %H:%M')} UTC"


def duracao(segundos):
    """'8,4 s', '3 min 05 s' ou '1 h 02 min'."""
    if _nulo(segundos):
        return TRACO
    s = float(segundos)
    if s < 60:
        return f"{_br(s, 1)} s"
    minutos, resto = divmod(round(s), 60)
    if minutos < 60:
        return f"{minutos} min {resto:02d} s"
    horas, minutos = divmod(minutos, 60)
    return f"{horas} h {minutos:02d} min"


def _status(valor):
    return SEM_REGISTRO if _nulo(valor) else STATUS_EXECUCAO[valor]["rotulo"]


def tabela_saude(saude):
    """DataFrame de exibição da última execução de cada etapa (formatação, sem conta)."""
    df = saude.sort_values("ordem")
    return pd.DataFrame(
        {
            "etapa": df["etapa"].map(ETAPA_ROTULO),
            "status": df["status"].map(_status),
            "inicio": df["inicio_utc"].map(data_hora),
            "duracao": df["duracao_s"].map(duracao),
            "camada": df["camada"].map(lambda c: CAMADA_ROTULO.get(c, TRACO)),
            "tabelas": df["tabelas"].map(numero),
            "linhas": df["linhas"].map(numero),
            "avisos": df["avisos"].map(numero),
            "ultimo_sucesso": df["ultimo_sucesso_utc"].map(data_hora),
        }
    )


def tabela_linhas_por_tabela(saude):
    """Uma linha por tabela publicada na última execução de cada etapa."""
    linhas = [
        {
            "etapa": ETAPA_ROTULO[etapa],
            "tabela": item["tabela"],
            "linhas": numero(item["linhas"]),
        }
        for etapa, itens in zip(saude["etapa"], saude["linhas_por_tabela"], strict=True)
        if _lista(itens)
        for item in itens
    ]
    return pd.DataFrame(linhas, columns=["etapa", "tabela", "linhas"])


def fig_duracao_etapas(saude):
    """Barras horizontais com a duração da última execução de cada etapa, cor pelo status."""
    df = saude[saude["duracao_s"].notna()].sort_values("ordem", ascending=False)
    fig = go.Figure(
        go.Bar(
            x=df["duracao_s"],
            y=df["etapa"].map(ETAPA_ROTULO),
            orientation="h",
            marker_color=df["status"].map(lambda s: STATUS_EXECUCAO[s]["cor"]),
            text=df["duracao_s"].map(duracao),
            textposition="outside",
            customdata=df["status"].map(_status),
            hovertemplate="%{y}: %{text} · %{customdata}<extra></extra>",
        )
    )
    fig.update_xaxes(title="Duração (s)", showgrid=True, gridcolor=BORDA)
    fig.update_yaxes(showgrid=False)
    return _layout(fig, "Duração da última execução por etapa", 320)


def _linha_etapa(saude, etapa):
    linhas = saude[saude["etapa"] == etapa]
    return None if linhas.empty else linhas.iloc[0]


def metricas_saude(saude, idade, registro_fotografia):
    """[(rótulo, valor)] dos 4 mini cartões da aba: idade, ingestão, qualidade e fotografia."""
    uteis = "dia útil" if idade.dias_uteis == 1 else "dias úteis"
    metricas = [
        (
            f"Idade dos dados ({idade.dias_corridos} corridos)",
            f"{idade.dias_uteis} {uteis}",
        )
    ]
    ingestao = None if saude is None else _linha_etapa(saude, "ingestao")
    qualidade = None if saude is None else _linha_etapa(saude, "qualidade")
    metricas.append(
        (
            "Última ingestão",
            TRACO if ingestao is None else data_br(ingestao["inicio_utc"]),
        )
    )
    metricas.append(
        (
            "Avisos da qualidade",
            TRACO if qualidade is None else numero(qualidade["avisos"]),
        )
    )
    metricas.append(
        (
            "Fotografia gerada em",
            (TRACO if fonte() == FOTOGRAFIA else "banco local")
            if registro_fotografia is None
            else data_br(registro_fotografia["fim_utc"]),
        )
    )
    return metricas


def falhas_saude(saude):
    """[(etapa, início, último sucesso, erro)] das etapas cuja última execução falhou."""
    df = saude[saude["status"] == execucao.FALHA].sort_values("ordem")
    return [
        (ETAPA_ROTULO[e], data_hora(i), data_hora(u), erro)
        for e, i, u, erro in zip(
            df["etapa"],
            df["inicio_utc"],
            df["ultimo_sucesso_utc"],
            df["erro"],
            strict=True,
        )
    ]


def avisos_saude(saude):
    """[(etapa, [avisos])] das etapas com aviso na última execução, na ordem do pipeline."""
    df = saude.sort_values("ordem")
    return [
        (ETAPA_ROTULO[e], list(lista))
        for e, lista in zip(df["etapa"], df["lista_avisos"], strict=True)
        if _lista(lista)
    ]


def _lista(valor):
    """Lista não vazia vinda do DuckDB (list ou array); NULL e lista vazia são falsos."""
    return not _nulo(valor) and len(valor) > 0
