"""Painel de recomendações — leitura, formatação e gráficos (camada de apresentação).

Spec: docs/specs/dashboard_apresentacao.md (v1.5). Resumo das regras, com o motivo de cada uma:

1. LEITURA
   - ler(nomes) executa SELECT * FROM marts."<nome>": as tabelas físicas que
     pipeline/materializacao.py gera a partir de sql/marts/<nome>.sql. Motivo: o número já foi
     calculado e validado na materialização; todas as faixas mostram a mesma fotografia e os
     rankings não são reexecutados a cada abertura. Os .sql não são lidos aqui.
   - Conexão duckdb.connect("fundamentalistas.duckdb", read_only=True), aberta e fechada dentro
     de cada leitura. Motivo: conexão aberta segura o arquivo e o pipeline não consegue gravar.
   - Banco bloqueado por outro processo (DuckDB UI do ui.py, ingestão, materialização) vira
     BancoBloqueado, com mensagem clara no app e sem traceback.
   - ler_cotacao(ticker): marts.marts_cotacao com WHERE ticker = ? (parâmetro vinculado).
     Motivo: a tabela tem ~1,9 milhão de linhas; filtrar no banco evita carregar tudo em memória.
   - tabelas_faltando() lista as tabelas obrigatórias ausentes (catálogo duckdb_tables()).
   - Tabela não garante ordem: quem exibe ordena no pandas (posicao/rank, ticker; data).

2. NENHUM CÁLCULO
   - Aqui e em app.py não há agregação do pandas (agrupar, somar, contar, média, contagem de
     valores, mesclar, juntar, transpor para tabela dinâmica, tabular cruzado), nem histograma do
     plotly, nem conta entre colunas. Permitido: ordenar, filtrar linhas, head(n), renomear,
     formatar texto e mapear categorias para cor, ícone ou rótulo por dicionário constante.
     Motivo: número novo na tela exige um .sql novo em sql/marts/, declarado em
     pipeline/materializacao.py e materializado em marts.

3. MARTS DO PAINEL (marts.marts_card_05_* e marts.marts_painel_*), todos com a regra de
   recomendação de marts_50 copiada literalmente. Termômetro: empate -> Manter (P1).

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

5. FORMATO: milhar com ponto e decimal com vírgula, sem locale do sistema (o resultado não pode
   depender da máquina). pct() não multiplica por 100: os percentuais já estão em 0–100.
   Nulo vira "—", nunca zero. Uma função por gráfico, sem streamlit, para um relatório HTML
   futuro reaproveitar e para testar sem streamlit.

6. FILTROS recortam só as linhas do ranking consolidado, da dispersão valor × qualidade e da
   lista da ficha. Cartões e rankings temáticos valem para o mercado inteiro.
   Motivo: recalcular contagem por filtro seria regra de negócio fora do SQL.

7. CACHE E ERRO (app.py): st.cache_data; tabela faltando (orienta rodar a materialização),
   banco bloqueado ou erro de leitura -> st.error + st.stop(). A checagem de tabelas fica fora
   do cache para "Recarregar dados" enxergar uma materialização recém-feita.

8. APARÊNCIA: Modo Escuro Profissional (paleta abaixo, espelhada em .streamlit/config.toml).
   Motivo: análise intensiva; fundo escuro reduz a fadiga visual e destaca números e séries.
"""

import math
from datetime import date, datetime

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots

from pipeline import db

ARQUIVO_DB = (
    db.caminho_banco()
)  # o mesmo banco do pipeline (VALUATIONB3_DB ou o padrão)
SCHEMA_MARTS = "marts"

MARTS_CARDS = [
    "marts_card_01_acoes_analisadas",
    "marts_card_02_acoes_compra",
    "marts_card_03_acoes_manter",
    "marts_card_04_acoes_venda",
    "marts_card_02_acoes_semindicacao",
    "marts_card_05_termometro_mercado",
]
MARTS_PAINEL = [
    "marts_painel_data_referencia",
    "marts_painel_indicadores",
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


# --------------------------------------------------------------------------------------------
# 1. Leitura
# --------------------------------------------------------------------------------------------
class BancoBloqueado(Exception):
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


def tabelas_faltando():
    """Banco ou tabelas marts obrigatórias que não existem (rótulos marts.<nome>)."""
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


def _conectar():
    try:
        return duckdb.connect(str(ARQUIVO_DB), read_only=True)
    except duckdb.IOException as erro:
        # No Windows o lock de outro processo chega como IOException ao abrir o arquivo.
        raise BancoBloqueado(MSG_BLOQUEADO) from erro


def ler(nomes):
    """Lê cada tabela marts.<nome> inteira e devolve {nome: DataFrame}."""
    con = _conectar()
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
    con = _conectar()
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
        "frase": "Maiores pagadoras com payout saudável",
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
        xaxis={
            "showgrid": False,
            "zeroline": False,
            "linecolor": BORDA,
            "tickfont": {"color": TEXTO_2},
            "title": {"font": {"color": TEXTO_2}},
        },
        yaxis={
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
CSS = f"""
<style>
.b3-card {{background:{FUNDO_2}; border:1px solid {BORDA}; border-top:4px solid var(--cor);
  border-radius:8px; padding:14px 16px; min-height:150px; display:flex; flex-direction:column;
  gap:2px;}}
.b3-card.destaque {{background:var(--fundo); border:2px solid var(--cor);}}
.b3-rotulo {{font-size:0.9rem; font-weight:600; color:{TEXTO_2};}}
.b3-numero {{font-size:2.2rem; font-weight:700; line-height:1.15; color:{TEXTO};}}
.b3-destaque {{font-size:1.15rem; font-weight:700; color:var(--cor); margin-top:4px;}}
.b3-def {{font-size:0.8rem; color:{TEXTO_2};}}
.b3-barra {{display:flex; height:8px; border-radius:4px; overflow:hidden; margin-top:auto;}}
</style>
"""


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
        annotation_position="top",
        annotation_font_color=TEXTO_2,
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
                customdata=list(zip(*dados, strict=True)),
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
    fig.update_layout(barmode="group", showlegend=len(ranking["barras"]) > 1)
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
        margin={"l": 60, "r": 60, "t": 72, "b": 30},
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
