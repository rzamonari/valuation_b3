"""Qualidade dos dados: reconciliação raw → refined → marts e regras de domínio.

Execução: uv run python -m pipeline.qualidade   (depois da materialização; só lê o banco)

# DECISÕES

1. Cada verificação é um SELECT que devolve as linhas que violam a regra: zero linhas = ok.
   Motivo: a mesma forma serve para reconciliação e para regra de domínio, e as primeiras
   linhas devolvidas viram o exemplo do relatório.
2. Reconciliação (sempre ERRO):
   - raw → refined: chaves distintas da Bronze = registros da Silver (a Silver só remove
     duplicatas idênticas e recusa chave nula ou conflitante) e mesma ingestão
     (MAX(_timestamp_ingestao) igual nas duas camadas). As chaves vêm das próprias
     definições da transformação, sem repeti-las aqui.
   - refined → marts: marts por ticker do Fundamentus com o mesmo conjunto de tickers;
     marts_cotacao com as mesmas chaves (ticker, data) da Silver; rankings dentro do universo
     da consulta-base (Fundamentus ⨝ B3 pela emissora); marts_50 = universo negociado
     (liquidez_2_meses > 0); painel e cards coerentes com marts_50; universo + exclusões
     (marts_exclusoes_universo) = todos os tickers do Fundamentus, sem sobreposição (EXCEPT
     ALL: ticker repetido entre as partes também viola); contagem por motivo do painel
     coerente com as exclusões.
3. Regras de domínio:
   - ERRO: o que a fonte nunca deveria violar e hoje não viola (cotação das ações analisadas
     > 0, DY ≥ 0, fechamento > 0, saldo entre −10 e +10...). Falha = código de saída 1 e a
     fotografia (pipeline.fotografia) não é gerada.
   - AVISO: faixas plausíveis de percentuais (FAIXAS_PLAUSIVEIS). O Fundamentus publica
     valores extremos reais (ex.: ROE acima de 1.000.000%, margem líquida de 144.637%), e a
     Silver preserva o dado como veio; o aviso dá visibilidade sem bloquear o pipeline.
     Também AVISO: mais de LIMITE_NAO_IDENTIFICADO exclusões com motivo "Não identificado"
     (negociadas, mas sem emissora no cadastro da B3): o normal é a exclusão ter causa
     conhecida; o aumento pede revisar a classificação ou o cadastro da B3.
   - Fechamento ajustado ≤ 0 (defeito do ajuste retroativo do Yahoo, provento ≥ fechamento
     anterior): AVISO na Silver, que preserva o dado como veio; ERRO no mart de retorno e
     risco se algum indicador for calculado com preço ≤ 0 na janela de 5 anos (o mart deixa
     o ticker sem cálculo, com motivo_sem_calculo).
   - Salto sem evento (razão diária do fechamento > LIMITE_SALTO ou < 1/LIMITE_SALTO num dia
     sem desdobramento nem provento: grupamento não registrado ou cotação errada, D2 da spec
     de indicadores): AVISO na Silver com uma linha por salto; ERRO se um ticker com algum
     indicador de retorno e risco tiver um salto assim na janela de 5 anos.
   NULL não viola regra de domínio: NOT (NULL) não seleciona a linha (nulos preservados).
4. Tabela ausente ou consulta inválida é ERRO, qualquer que seja a severidade declarada.
"""

import logging
import sys
from dataclasses import dataclass

import duckdb

from pipeline import db
from pipeline.db import _ident
from pipeline.log import configurar as configurar_logging
from pipeline.transformacao import ORIGEM_MINHARECEITA, TABELAS_SQL

log = logging.getLogger("pipeline.qualidade")

ERRO = "erro"
AVISO = "aviso"
AMOSTRA = 5  # linhas exibidas como exemplo

RAW_REFINED = "raw → refined"
REFINED_MARTS = "refined → marts"
DOMINIO_REFINED = "domínio refined"
DOMINIO_MARTS = "domínio marts"

# Universo da consulta-base dos rankings: Fundamentus ⨝ B3 pela emissora (4 primeiras letras).
UNIVERSO = (
    "SELECT a.ticker FROM refined.fundamentus_acoes a "
    "INNER JOIN refined.b3_empresas b ON b.empresa_emissora = SUBSTRING(a.ticker, 1, 4)"
)
UNIVERSO_NEGOCIADO = f"{UNIVERSO} WHERE a.liquidez_2_meses > 0"

MARTS_POR_TICKER_FUNDAMENTUS = (
    "marts_alavancagem",
    "marts_crescimento_receita_5_anos",
    "marts_dividend_yield_payout",
    "marts_ev_ebit",
    "marts_margens",
    "marts_p_vp",
    "marts_preco_lucro",
    "marts_roe",
    "marts_roic",
)
RANKINGS = (
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
)
RECOMENDACOES = "marts.marts_50_rank_recomendacoes"
EXCLUSOES = "marts.marts_exclusoes_universo"
EXCLUSOES_MOTIVO = "marts.marts_painel_exclusoes_motivo"
RISCO = "marts.marts_retorno_total_risco"
INDICADORES_RISCO = ("cagr", "volatilidade_anualizada", "max_drawdown")
LIMITE_SALTO = 5  # D2: 278 saltos em 1,9 mi de razões; p99,99 sem evento = 2,82
# Saltos sem evento em toda a Silver, com a razão calculada sobre o pregão anterior.
SALTOS_SEM_EVENTO = (
    "SELECT ticker, data, razao FROM (SELECT ticker, data, "
    "fechamento / LAG(fechamento) OVER (PARTITION BY ticker ORDER BY data) AS razao, "
    "desdobramentos > 0 OR dividendos > 0 AS evento "
    "FROM refined.yfinance_cotacoes WHERE fechamento > 0) "
    f"WHERE NOT evento AND (razao > {LIMITE_SALTO} OR razao < 1.0 / {LIMITE_SALTO})"
)
MOTIVOS_EXCLUSAO = (
    "Fracionário",
    "BDR",
    "Unit",
    "Não identificado",
    "Deslistada ou cancelada",
    "Outro código",
)
NAO_IDENTIFICADO = "Não identificado"
LIMITE_NAO_IDENTIFICADO = 10  # exclusões sem causa conhecida (6 em 2026-11-02)
CARDS = {
    "marts_card_02_acoes_compra": "Compra",
    "marts_card_03_acoes_manter": "Manter",
    "marts_card_04_acoes_venda": "Venda",
}
FAIXAS = ("Superior", "Intermediário", "Inferior", "Não elegível")
TEMAS = (
    "valor",
    "proventos",
    "eficiencia",
    "retorno",
    "pechincha",
    "patrimonio",
    "crescimento",
    "operacional",
    "seguro",
    "rentabilidade",
)

# Percentuais do Fundamentus (escala 0–100): faixa plausível -> AVISO fora dela.
FAIXAS_PLAUSIVEIS = {
    "dividend_yield": (0, 100),
    "margem_bruta": (-100, 100),
    "margem_ebit": (-100, 100),
    "margem_liquida": (-100, 100),
    "roic": (-100, 100),
    "roe": (-100, 100),
    "crescimento_receita_5_anos": (-100, 1000),
}


@dataclass(frozen=True)
class Verificacao:
    nome: str
    camada: str
    severidade: str
    sql: str  # SELECT das linhas que violam a regra


@dataclass(frozen=True)
class Resultado:
    verificacao: Verificacao
    violacoes: int
    exemplos: tuple = ()
    falha: str | None = None  # consulta não executou (tabela ausente, coluna inválida)

    @property
    def ok(self) -> bool:
        return self.falha is None and self.violacoes == 0

    @property
    def status(self) -> str:
        if self.ok:
            return "OK"
        if self.falha is not None or self.verificacao.severidade == ERRO:
            return "ERRO"
        return "AVISO"


class ErroQualidade(Exception):
    """Alguma verificação de severidade ERRO falhou."""

    def __init__(self, resultados: list[Resultado]):
        self.resultados = resultados
        nomes = ", ".join(r.verificacao.nome for r in resultados)
        super().__init__(f"{len(resultados)} verificação(ões) com erro: {nomes}")


# --------------------------------------------------------------------------- construtores


def _comparar(nome, camada, esperado, obtido):
    """Dois escalares que precisam ser iguais (NULL = NULL)."""
    return Verificacao(
        nome,
        camada,
        ERRO,
        f"SELECT esperado, obtido FROM (SELECT ({esperado}) AS esperado, "
        f"({obtido}) AS obtido) WHERE esperado IS DISTINCT FROM obtido",
    )


def _mesmo_conjunto(nome, camada, esperado, obtido):
    """Mesmo conjunto de linhas nos dois lados; a violação diz de que lado sobrou."""
    return Verificacao(
        nome,
        camada,
        ERRO,
        f"SELECT 'só no esperado' AS lado, * FROM (({esperado}) EXCEPT ({obtido})) "
        f"UNION ALL SELECT 'só no obtido', * FROM (({obtido}) EXCEPT ({esperado}))",
    )


def _particao(nome, camada, partes, todo):
    """As partes, somadas com repetição, formam exatamente o todo (sem sobra nem sobreposição)."""
    soma = " UNION ALL ".join(f"({parte})" for parte in partes)
    return Verificacao(
        nome,
        camada,
        ERRO,
        f"SELECT 'sobra ou repetido nas partes' AS lado, * FROM (({soma}) EXCEPT ALL "
        f"({todo})) UNION ALL SELECT 'faltando nas partes', * FROM (({todo}) EXCEPT ALL "
        f"({soma}))",
    )


def _contido(nome, camada, subconjunto, conjunto):
    return Verificacao(nome, camada, ERRO, f"({subconjunto}) EXCEPT ({conjunto})")


def _regra(nome, camada, severidade, tabela, condicao, colunas):
    """Linhas de tabela que não atendem à condição (NULL não viola)."""
    return Verificacao(
        nome,
        camada,
        severidade,
        f"SELECT {', '.join(colunas)} FROM {tabela} WHERE NOT ({condicao})",
    )


# --------------------------------------------------------------------------- catálogo


def _raw_refined():
    tabelas = [
        (t.origem, t.destino, [c.origem for c in t.colunas if c.destino in t.chave])
        for t in TABELAS_SQL
    ]
    tabelas.append((ORIGEM_MINHARECEITA, ORIGEM_MINHARECEITA, ["cnpj"]))
    verificacoes = []
    for origem, destino, chave in tabelas:
        raw = f"raw.{_ident(origem)}"
        refined = f"refined.{_ident(destino)}"
        colunas = ", ".join(_ident(c) for c in chave)
        nao_nulas = " AND ".join(f"{_ident(c)} IS NOT NULL" for c in chave)
        verificacoes += [
            _comparar(
                f"{destino}: chaves distintas da Bronze = registros da Silver",
                RAW_REFINED,
                f"SELECT COUNT(*) FROM (SELECT DISTINCT {colunas} FROM {raw} "
                f"WHERE {nao_nulas})",
                f"SELECT COUNT(*) FROM {refined}",
            ),
            _comparar(
                f"{destino}: mesma ingestão nas duas camadas",
                RAW_REFINED,
                f"SELECT MAX(_timestamp_ingestao) FROM {raw}",
                f"SELECT MAX(_timestamp_ingestao) FROM {refined}",
            ),
        ]
    return verificacoes


def _refined_marts():
    fundamentus = "SELECT ticker FROM refined.fundamentus_acoes"
    verificacoes = [
        _mesmo_conjunto(
            f"{mart}: mesmos tickers do Fundamentus",
            REFINED_MARTS,
            fundamentus,
            f"SELECT ticker FROM marts.{mart}",
        )
        for mart in MARTS_POR_TICKER_FUNDAMENTUS
    ]
    verificacoes += [
        _mesmo_conjunto(
            "marts_cotacao: mesmas chaves (ticker, data) da Silver",
            REFINED_MARTS,
            "SELECT ticker, data FROM refined.yfinance_cotacoes",
            "SELECT ticker, data FROM marts.marts_cotacao",
        ),
        _contido(
            "marts_retorno_total_risco: tickers com cotação na Silver",
            REFINED_MARTS,
            "SELECT ticker FROM marts.marts_retorno_total_risco",
            "SELECT ticker FROM refined.yfinance_cotacoes",
        ),
    ]
    verificacoes += [
        _contido(
            f"{mart}: tickers dentro do universo da consulta-base",
            REFINED_MARTS,
            f"SELECT ticker FROM marts.{mart}",
            UNIVERSO,
        )
        for mart in RANKINGS
    ]
    verificacoes += [
        _mesmo_conjunto(
            "marts_50: universo negociado (liquidez_2_meses > 0)",
            REFINED_MARTS,
            UNIVERSO_NEGOCIADO,
            f"SELECT ticker FROM {RECOMENDACOES}",
        ),
        _mesmo_conjunto(
            "marts_painel_indicadores: mesma recomendação de marts_50",
            REFINED_MARTS,
            f"SELECT ticker, recomendacao, saldo FROM {RECOMENDACOES}",
            "SELECT ticker, recomendacao, saldo FROM marts.marts_painel_indicadores",
        ),
        _comparar(
            "marts_card_01: ações analisadas = linhas de marts_50",
            REFINED_MARTS,
            f"SELECT COUNT(*) FROM {RECOMENDACOES}",
            "SELECT quantidade FROM marts.marts_card_01_acoes_analisadas",
        ),
        _comparar(
            "marts_card_05: total do termômetro = ações analisadas",
            REFINED_MARTS,
            f"SELECT COUNT(*) FROM {RECOMENDACOES}",
            "SELECT total FROM marts.marts_card_05_termometro_mercado",
        ),
        _comparar(
            "marts_card_02_acoes_semindicacao: Fundamentus sem liquidez",
            REFINED_MARTS,
            "SELECT COUNT(*) FROM refined.fundamentus_acoes "
            "WHERE liquidez_2_meses IS NULL OR liquidez_2_meses <= 0",
            "SELECT quantidade FROM marts.marts_card_02_acoes_semindicacao",
        ),
        _particao(
            "marts_exclusoes_universo: universo + exclusões = tickers do Fundamentus",
            REFINED_MARTS,
            [UNIVERSO, f"SELECT ticker FROM {EXCLUSOES}"],
            fundamentus,
        ),
        _mesmo_conjunto(
            "marts_painel_exclusoes_motivo: contagem por motivo das exclusões",
            REFINED_MARTS,
            f"SELECT motivo, COUNT(*) FROM {EXCLUSOES} GROUP BY motivo",
            f"SELECT motivo, quantidade FROM {EXCLUSOES_MOTIVO} WHERE quantidade > 0",
        ),
    ]
    verificacoes += [
        _comparar(
            f"{mart}: contagem de {recomendacao} em marts_50",
            REFINED_MARTS,
            f"SELECT COUNT(*) FROM {RECOMENDACOES} WHERE recomendacao = '{recomendacao}'",
            f"SELECT quantidade FROM marts.{mart}",
        )
        for mart, recomendacao in CARDS.items()
    ]
    return verificacoes


def _dominio_refined():
    fundamentus = "refined.fundamentus_acoes"
    cotacoes = "refined.yfinance_cotacoes"
    regras = [
        _regra(
            "Fundamentus: dividend yield não negativo",
            DOMINIO_REFINED,
            ERRO,
            fundamentus,
            "dividend_yield >= 0",
            ["ticker", "dividend_yield"],
        ),
        _regra(
            "Fundamentus: liquidez de 2 meses não negativa",
            DOMINIO_REFINED,
            ERRO,
            fundamentus,
            "liquidez_2_meses >= 0",
            ["ticker", "liquidez_2_meses"],
        ),
        _regra(
            "Fundamentus: receita não cai mais de 100% em 5 anos",
            DOMINIO_REFINED,
            ERRO,
            fundamentus,
            "crescimento_receita_5_anos >= -100",
            ["ticker", "crescimento_receita_5_anos"],
        ),
        _regra(
            "Fundamentus: cotação > 0 (zero = ausência na fonte)",
            DOMINIO_REFINED,
            AVISO,
            fundamentus,
            "cotacao > 0",
            ["ticker", "cotacao"],
        ),
    ]
    regras += [
        _regra(
            f"Fundamentus: {coluna} entre {minimo} e {maximo}",
            DOMINIO_REFINED,
            AVISO,
            fundamentus,
            f"{coluna} BETWEEN {minimo} AND {maximo}",
            ["ticker", coluna],
        )
        for coluna, (minimo, maximo) in FAIXAS_PLAUSIVEIS.items()
    ]
    regras += [
        _regra(
            f"YFinance: {coluna} {condicao}",
            DOMINIO_REFINED,
            ERRO,
            cotacoes,
            f"{coluna} {condicao}",
            ["ticker", "data", coluna],
        )
        for coluna, condicao in (
            ("fechamento", "> 0"),
            ("volume", ">= 0"),
            ("dividendos", ">= 0"),
            ("desdobramentos", ">= 0"),
        )
    ]
    regras += [
        _regra(
            "YFinance: máxima ≥ mínima",
            DOMINIO_REFINED,
            AVISO,
            cotacoes,
            "maxima >= minima",
            ["ticker", "data", "maxima", "minima"],
        ),
        _regra(
            "YFinance: fechamento ajustado > 0",
            DOMINIO_REFINED,
            AVISO,
            cotacoes,
            "fechamento_ajustado > 0",
            ["ticker", "data", "fechamento_ajustado"],
        ),
        Verificacao(
            f"YFinance: fechamento sem salto > {LIMITE_SALTO}x sem evento",
            DOMINIO_REFINED,
            AVISO,
            f"SELECT * FROM ({SALTOS_SEM_EVENTO}) ORDER BY data DESC, ticker",
        ),
    ]
    return regras


def _dominio_marts():
    faixas = ", ".join(f"'{f}'" for f in FAIXAS)
    motivos = ", ".join(f"'{m}'" for m in MOTIVOS_EXCLUSAO)
    regras = [
        _regra(
            "marts_50: cotação > 0",
            DOMINIO_MARTS,
            ERRO,
            RECOMENDACOES,
            "cotacao > 0",
            ["ticker", "cotacao"],
        ),
        _regra(
            "marts_50: saldo entre -10 e +10",
            DOMINIO_MARTS,
            ERRO,
            RECOMENDACOES,
            "saldo BETWEEN -10 AND 10",
            ["ticker", "saldo"],
        ),
        _regra(
            "marts_50: as quatro faixas somam os 10 rankings",
            DOMINIO_MARTS,
            ERRO,
            RECOMENDACOES,
            "qtd_superior + qtd_intermediario + qtd_inferior + qtd_nao_elegivel = 10",
            ["ticker", "qtd_superior", "qtd_intermediario", "qtd_inferior"],
        ),
        _regra(
            "marts_50: recomendação coerente com o sinal do saldo",
            DOMINIO_MARTS,
            ERRO,
            RECOMENDACOES,
            "recomendacao = CASE WHEN saldo > 0 THEN 'Compra' WHEN saldo = 0 "
            "THEN 'Manter' ELSE 'Venda' END",
            ["ticker", "saldo", "recomendacao"],
        ),
        _regra(
            "marts_50: faixas dentro do domínio",
            DOMINIO_MARTS,
            ERRO,
            RECOMENDACOES,
            " AND ".join(f"faixa_{tema} IN ({faixas})" for tema in TEMAS),
            ["ticker"],
        ),
        _regra(
            "marts_card_05: percentual entre 0 e 100",
            DOMINIO_MARTS,
            ERRO,
            "marts.marts_card_05_termometro_mercado",
            "percentual BETWEEN 0 AND 100",
            ["recomendacao", "percentual"],
        ),
        _regra(
            "marts_exclusoes_universo: motivo dentro do domínio",
            DOMINIO_MARTS,
            ERRO,
            EXCLUSOES,
            f"motivo IN ({motivos})",
            ["ticker", "motivo"],
        ),
        Verificacao(
            f"marts_exclusoes_universo: até {LIMITE_NAO_IDENTIFICADO} sem motivo "
            "identificado",
            DOMINIO_MARTS,
            AVISO,
            f"SELECT COUNT(*) AS quantidade, {LIMITE_NAO_IDENTIFICADO} AS limite "
            f"FROM {EXCLUSOES} WHERE motivo = '{NAO_IDENTIFICADO}' "
            f"HAVING COUNT(*) > {LIMITE_NAO_IDENTIFICADO}",
        ),
        # Independe da regra do mart: a janela e os preços vêm direto da Silver.
        Verificacao(
            "marts_retorno_total_risco: nenhum indicador calculado com "
            "fechamento ajustado ≤ 0 na janela",
            DOMINIO_MARTS,
            ERRO,
            "SELECT r.ticker, COUNT(*) AS precos_nao_positivos "
            f"FROM {RISCO} r "
            "JOIN (SELECT ticker, MAX(data) AS fim FROM refined.yfinance_cotacoes "
            "GROUP BY ticker) l ON l.ticker = r.ticker "
            "JOIN refined.yfinance_cotacoes c ON c.ticker = r.ticker "
            "AND c.data >= l.fim - INTERVAL 5 YEAR "
            "WHERE c.fechamento_ajustado <= 0 AND ("
            + " OR ".join(f"r.{c} IS NOT NULL" for c in INDICADORES_RISCO)
            + ") GROUP BY r.ticker",
        ),
        Verificacao(
            "marts_retorno_total_risco: nenhum indicador calculado com salto sem evento "
            "na janela",
            DOMINIO_MARTS,
            ERRO,
            "SELECT r.ticker, COUNT(*) AS saltos "
            f"FROM {RISCO} r "
            "JOIN (SELECT ticker, MAX(data) AS fim FROM refined.yfinance_cotacoes "
            "GROUP BY ticker) l ON l.ticker = r.ticker "
            f"JOIN ({SALTOS_SEM_EVENTO}) s ON s.ticker = r.ticker "
            "AND s.data >= l.fim - INTERVAL 5 YEAR WHERE "
            + " OR ".join(f"r.{c} IS NOT NULL" for c in INDICADORES_RISCO)
            + " GROUP BY r.ticker",
        ),
        _regra(
            "marts_retorno_total_risco: ticker sem cálculo não tem indicador",
            DOMINIO_MARTS,
            ERRO,
            RISCO,
            "motivo_sem_calculo IS NULL OR "
            + " AND ".join(f"{c} IS NULL" for c in INDICADORES_RISCO),
            ["ticker", "motivo_sem_calculo", *INDICADORES_RISCO],
        ),
        _regra(
            "marts_painel_data_referencia: data informada",
            DOMINIO_MARTS,
            ERRO,
            "marts.marts_painel_data_referencia",
            "data_referencia IS NOT NULL",
            ["data_referencia"],
        ),
    ]
    regras += [
        _regra(
            f"{mart}: rank ≥ 1",
            DOMINIO_MARTS,
            ERRO,
            f"marts.{mart}",
            "rank >= 1",
            ["ticker", "rank"],
        )
        for mart in RANKINGS
    ]
    return regras


def verificacoes() -> list[Verificacao]:
    """Catálogo completo, na ordem do relatório."""
    return _raw_refined() + _refined_marts() + _dominio_refined() + _dominio_marts()


# --------------------------------------------------------------------------- execução


def verificar(con: duckdb.DuckDBPyConnection, v: Verificacao) -> Resultado:
    """Executa uma verificação; falha de consulta vira Resultado com falha."""
    try:
        violacoes = con.execute(f"SELECT COUNT(*) FROM ({v.sql})").fetchall()[0][0]
        exemplos = (
            tuple(con.execute(f"SELECT * FROM ({v.sql}) LIMIT {AMOSTRA}").fetchall())
            if violacoes
            else ()
        )
    except duckdb.Error as exc:
        return Resultado(v, 0, falha=str(exc).splitlines()[0])
    return Resultado(v, violacoes, exemplos)


def executar(
    con: duckdb.DuckDBPyConnection, catalogo: list[Verificacao] | None = None
) -> list[Resultado]:
    """Executa todas as verificações (só leitura) e devolve os resultados."""
    return [
        verificar(con, v) for v in (verificacoes() if catalogo is None else catalogo)
    ]


def erros(resultados: list[Resultado]) -> list[Resultado]:
    return [r for r in resultados if r.status == "ERRO"]


def exigir(con: duckdb.DuckDBPyConnection) -> list[Resultado]:
    """Executa e levanta ErroQualidade se alguma verificação de ERRO falhar."""
    resultados = executar(con)
    falhas = erros(resultados)
    if falhas:
        raise ErroQualidade(falhas)
    return resultados


# --------------------------------------------------------------------------- relatório


def _fmt(n):
    return f"{n:,}".replace(",", ".")


def imprimir_relatorio(resultados: list[Resultado]) -> None:
    largura = max(len(r.verificacao.nome) for r in resultados) + 2
    camada = max(len(r.verificacao.camada) for r in resultados) + 2
    log.info("")
    log.info(f"{'STATUS':<7}{'CAMADA':<{camada}}{'VERIFICAÇÃO':<{largura}}VIOLAÇÕES")
    log.info("-" * (7 + camada + largura + 10))
    for r in resultados:
        linha = (
            f"{r.status:<7}{r.verificacao.camada:<{camada}}"
            f"{r.verificacao.nome:<{largura}}{_fmt(r.violacoes) if r.falha is None else '—'}"
        )
        if r.status == "OK":
            log.info(linha)
            continue
        detalhe = r.falha or "; ".join(
            "(" + ", ".join(str(c) for c in e) + ")" for e in r.exemplos
        )
        (log.error if r.status == "ERRO" else log.warning)(
            f"{linha}\n         {detalhe}"
        )
    log.info("-" * (7 + camada + largura + 10))
    contagem = {
        s: sum(r.status == s for r in resultados) for s in ("OK", "AVISO", "ERRO")
    }
    log.info(
        f"{len(resultados)} verificações: {contagem['OK']} ok, "
        f"{contagem['AVISO']} aviso(s), {contagem['ERRO']} erro(s)"
    )


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    configurar_logging()
    try:
        con = duckdb.connect(str(db.caminho_banco()), read_only=True)
    except duckdb.Error as exc:
        log.error(f"\nERRO DE QUALIDADE\n  Etapa:   conexão\n  Motivo:  {exc}")
        sys.exit(1)
    try:
        resultados = executar(con)
    finally:
        con.close()
    imprimir_relatorio(resultados)
    if erros(resultados):
        log.error(
            "\nQualidade reprovada: corrija os erros antes de gerar a fotografia."
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
