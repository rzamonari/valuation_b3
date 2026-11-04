"""Painel de recomendações B3 Valuation.

Execução: uv run streamlit run app.py
Regras e motivos: docstring de painel.py (spec docs/specs/dashboard_apresentacao.md).
"""

import streamlit as st

import painel as p

st.set_page_config(page_title="B3 Valuation", page_icon="📊", layout="wide")
st.markdown(p.CSS, unsafe_allow_html=True)

AVISO = (
    "Sinais relativos derivados de 10 rankings fundamentalistas sobre fotografia de dados. "
    "**Não constitui recomendação de investimento**."
)
FILTROS_PADRAO = {"f_rec": p.RECS_ANALISADAS, "f_seg": [], "f_liq": "Todas"}


@st.cache_data(show_spinner="Lendo os marts…")
def carregar():
    return p.ler(p.MARTS_CARREGAR)


@st.cache_data(show_spinner=False)
def carregar_cotacao(ticker):
    return p.ler_cotacao(ticker)


def parar_com_erro(erro):
    if isinstance(erro, p.BancoBloqueado):
        st.error(p.MSG_BLOQUEADO)
    elif isinstance(erro, p.FotografiaInvalida):
        st.error(f"Fotografia dos dados inválida:\n\n{erro}\n\n{p.MSG_FOTOGRAFIA}")
    else:
        st.error(f"Erro ao ler `{erro.tabela}`:\n\n{erro.mensagem}")
    st.stop()


def secao(icone, titulo, subtitulo):
    st.divider()
    st.subheader(f"{icone} {titulo}")
    st.caption(subtitulo)


def grafico(fig, **kwargs):
    # theme=None: o template de painel.py manda nas cores, não o tema do Streamlit.
    return st.plotly_chart(fig, width="stretch", theme=None, **kwargs)


def limpar_filtros():
    for chave, valor in FILTROS_PADRAO.items():
        st.session_state[chave] = list(valor) if isinstance(valor, list) else valor


# --------------------------------------------------------------------------------------------
# Cabeçalho
# --------------------------------------------------------------------------------------------
esq, dir_ = st.columns([4, 1], vertical_alignment="center")
esq.title("📈 B3 Valuation · Visões de Investimentos")
linha_data = esq.empty()
if dir_.button("🔄 Recarregar dados", width="stretch"):
    st.cache_data.clear()
    st.rerun()
st.caption(f"⚠️ {AVISO}")

# Fora do cache: "Recarregar dados" precisa enxergar uma materialização recém-feita.
try:
    faltando = p.tabelas_faltando()
except (p.BancoBloqueado, p.FotografiaInvalida) as erro:
    parar_com_erro(erro)
if faltando:
    mensagem = "Tabelas obrigatórias não encontradas:\n"
    for tabela in faltando:
        mensagem += f"\n- `{tabela}`"
    st.error(f"{mensagem}\n\n{p.mensagem_faltando()}")
    st.stop()

try:
    d = carregar()
except (p.BancoBloqueado, p.ErroMart, p.FotografiaInvalida) as erro:
    parar_com_erro(erro)

linha_data.markdown(
    f"Dados de **{p.data_br(d['marts_painel_data_referencia'].iloc[0, 0])}**"
    f" · fonte: {p.origem()}"
)

rec = d[p.MART_RECOMENDACOES]
ind = d["marts_painel_indicadores"]

# --------------------------------------------------------------------------------------------
# Filtros (recortam só as faixas 2, 3 e a lista da ficha)
# --------------------------------------------------------------------------------------------
for chave, valor in FILTROS_PADRAO.items():
    st.session_state.setdefault(
        chave, list(valor) if isinstance(valor, list) else valor
    )

with st.sidebar:
    st.header("Filtros")
    st.pills(
        "Recomendação",
        p.RECS_ANALISADAS,
        selection_mode="multi",
        key="f_rec",
        format_func=lambda r: p.BADGE[r],
    )
    st.multiselect(
        "Segmento de listagem",
        sorted(rec["segmento"].dropna().unique().tolist()),
        key="f_seg",
        placeholder="Todos",
    )
    st.select_slider("Liquidez mínima em 2 meses", list(p.LIQUIDEZ_MINIMA), key="f_liq")
    st.button("Limpar filtros", on_click=limpar_filtros, width="stretch")
    st.caption("Os cartões e os rankings temáticos valem para o mercado inteiro.")

filtros = (
    st.session_state["f_rec"],
    st.session_state["f_seg"],
    p.LIQUIDEZ_MINIMA[st.session_state["f_liq"]],
)
rec_f = p.filtrar(rec, *filtros)
ind_f = p.filtrar(ind, *filtros)
SEM_LINHAS = "Nenhuma ação atende aos filtros."

# --------------------------------------------------------------------------------------------
# Faixa 1 — Pulso do mercado
# --------------------------------------------------------------------------------------------
secao(
    "🩺", "Pulso do mercado", "Como está o mercado hoje, pela leitura dos 10 rankings"
)


def qtd(nome):
    return d[nome]["quantidade"].iloc[0]


compra, manter, venda = (
    qtd("marts_card_02_acoes_compra"),
    qtd("marts_card_03_acoes_manter"),
    qtd("marts_card_04_acoes_venda"),
)
cartoes = [
    p.html_cartao(
        "Ações analisadas",
        qtd("marts_card_01_acoes_analisadas"),
        "tickers negociados nos últimos 2 meses",
        p.AZUL,
    ),
    p.html_cartao(
        p.BADGE["Compra"],
        compra,
        "saldo positivo nos 10 rankings",
        p.REC["Compra"]["cor"],
    ),
    p.html_cartao(p.BADGE["Manter"], manter, "saldo zero", p.REC["Manter"]["cor"]),
    p.html_cartao(p.BADGE["Venda"], venda, "saldo negativo", p.REC["Venda"]["cor"]),
    p.html_cartao(
        p.BADGE["Sem indicação"],
        qtd("marts_card_02_acoes_semindicacao"),
        "sem negociação nos últimos 2 meses",
        p.REC["Sem indicação"]["cor"],
        dica="Contado sobre todos os tickers do Fundamentus",
    ),
    p.html_termometro(d["marts_card_05_termometro_mercado"], compra, manter, venda),
]
for coluna, html in zip(st.columns(6), cartoes, strict=False):
    coluna.markdown(html, unsafe_allow_html=True)

with st.expander("Por que alguns tickers do Fundamentus ficam fora dos rankings?"):
    st.caption(
        "Entram nos rankings só os tickers cuja emissora (4 primeiras letras) está no "
        "cadastro de empresas ativas da B3. Os demais, por motivo:"
    )
    st.dataframe(
        p.tabela_exclusoes(d[p.MART_EXCLUSOES]),
        hide_index=True,
        width="stretch",
        column_config={
            "motivo": st.column_config.TextColumn("Motivo"),
            "descricao": st.column_config.TextColumn("Descrição"),
            "quantidade": st.column_config.NumberColumn("Tickers"),
            "quantidade_negociada": st.column_config.NumberColumn(
                "Negociados em 2 meses"
            ),
        },
    )

# --------------------------------------------------------------------------------------------
# Faixa 2 — Ranking de oportunidades
# --------------------------------------------------------------------------------------------
secao(
    "🏆",
    "Ranking de oportunidades",
    "Ações ordenadas pelo saldo nos 10 rankings — as primeiras lideram mais estratégias",
)
st.markdown("**2 · Ranking consolidado**")
if rec_f.empty:
    st.info(SEM_LINHAS)
else:
    st.caption(
        "Faixas: 🟢 Sup. = Superior · 🟡 Int. = Intermediário · 🔴 Inf. = Inferior · "
        "⚪ N/E = Não elegível"
    )
    config = {
        "posicao": st.column_config.NumberColumn("Posição", width="small"),
        "recomendacao": st.column_config.TextColumn("Recomendação"),
        "ticker": st.column_config.TextColumn("Ticker", width="small"),
        "empresa": st.column_config.TextColumn("Empresa"),
        "segmento": st.column_config.TextColumn("Segmento"),
        "cotacao": st.column_config.TextColumn("Cotação"),
        "liquidez_2_meses": st.column_config.TextColumn("Liquidez 2 meses"),
        "saldo": st.column_config.ProgressColumn(
            "Saldo", min_value=-10, max_value=10, format="%+d"
        ),
    }
    for coluna, nome in p.FAIXA_COLUNAS.items():
        config[coluna] = st.column_config.TextColumn(nome, width="small")
    st.dataframe(
        p.tabela_consolidado(rec_f),
        column_config=config,
        hide_index=True,
        width="stretch",
        height=35 * 16 + 3,
    )

# --------------------------------------------------------------------------------------------
# Faixa 3 — Valor × qualidade
# --------------------------------------------------------------------------------------------
secao(
    "⚖️",
    "Valor × qualidade",
    "No alto e à esquerda ficam empresas muito rentáveis a preço baixo",
)
if ind_f.empty:
    st.info(SEM_LINHAS)
else:
    grafico(p.fig_valor_qualidade(ind_f))
    st.caption(
        "Mostra só ações com EV/EBIT e ROIC maiores que zero. Valores extremos fora da "
        "área visível. Tamanho do ponto = liquidez em 2 meses."
    )

# --------------------------------------------------------------------------------------------
# Faixa 4 — Rankings temáticos
# --------------------------------------------------------------------------------------------
secao("🧭", "Rankings temáticos", "Escolha uma estratégia e veja quem lidera")
for aba, ranking in zip(
    st.tabs([r["aba"] for r in p.RANKINGS]), p.RANKINGS, strict=False
):
    with aba:
        st.caption(ranking["frase"])
        df_rank = d[ranking["mart"]]
        c1, c2 = st.columns([3, 2])
        with c1:
            grafico(p.fig_ranking_tematico(df_rank, ranking))
        with c2:
            st.dataframe(
                p.tabela_ranking_tematico(df_rank, ranking),
                hide_index=True,
                width="stretch",
                height=35 * 16 + 3,
                column_config={
                    "rank": st.column_config.NumberColumn("Rank", width="small"),
                    "ticker": "Ticker",
                    "empresa": "Empresa",
                },
            )

# --------------------------------------------------------------------------------------------
# Faixa 5 — Ficha da ação
# --------------------------------------------------------------------------------------------
secao("🔎", "Ficha da ação", "Tudo sobre uma ação em uma tela")
lista = rec_f.sort_values(["posicao", "ticker"])
if lista.empty:
    st.info(SEM_LINHAS)
    st.stop()

rotulos = {
    t: f"{t} · {e}" for t, e in zip(lista["ticker"], lista["empresa"], strict=False)
}
ticker = st.selectbox("Ação", list(rotulos), format_func=rotulos.get)
linha = lista[lista["ticker"] == ticker].iloc[0]
indic = ind[ind["ticker"] == ticker].iloc[0]
risco_df = d[p.MART_RISCO][d[p.MART_RISCO]["ticker"] == ticker]
risco = risco_df.iloc[0] if not risco_df.empty else {}

local = (
    f"{linha['municipio']}/{linha['uf']}" if isinstance(linha["uf"], str) else p.TRACO
)
st.markdown(
    f"### {linha['ticker']} · {linha['empresa']}\n"
    f"{linha['segmento']} · {local} · **{p.BADGE[linha['recomendacao']]}** · "
    f"saldo **{int(linha['saldo']):+d}** · posição {int(linha['posicao'])}"
)

mini = [
    ("Cotação", p.reais(indic["cotacao"])),
    ("P/L", p.multiplo(indic["preco_lucro"])),
    ("P/VP", p.multiplo(indic["preco_valor_patrimonial"])),
    ("DY", p.pct(indic["dividend_yield"])),
    ("ROE", p.pct(indic["roe"])),
    ("ROIC", p.pct(indic["roic"])),
    ("DL/PL", p.numero(indic["divida_liquida_patrimonio"], 2)),
    ("Retorno anual (CAGR 5 anos)", p.pct(risco.get("cagr"))),
    ("Volatilidade anualizada", p.pct(risco.get("volatilidade_anualizada"))),
    ("Máximo drawdown", p.pct(risco.get("max_drawdown"))),
]
for inicio in (0, 5):
    for coluna, (rotulo, valor) in zip(
        st.columns(5), mini[inicio : inicio + 5], strict=False
    ):
        coluna.metric(rotulo, valor, border=True)
if isinstance(risco.get("motivo_sem_calculo"), str):
    st.caption(f"Retorno e risco sem cálculo: {risco['motivo_sem_calculo']}.")

c1, c2 = st.columns([2, 3])
with c1:
    grafico(p.fig_radar(linha))
with c2:
    try:
        cotacao = carregar_cotacao(ticker)
    except (p.BancoBloqueado, p.ErroMart, p.FotografiaInvalida) as erro:
        parar_com_erro(erro)
    if cotacao.empty:
        st.info("Sem histórico de cotação para este ticker")
    else:
        grafico(p.fig_cotacao(cotacao))
