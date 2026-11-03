"""Materialização da camada Gold (Marts): resultado de cada sql/marts/*.sql em marts.<arquivo>.

Execução: uv run python -m pipeline.materializacao

Spec: .venv/.specs/marts.agregacao.md (ajuste "Materialização dos resultados na camada Gold").

# DECISÕES DE IMPLEMENTAÇÃO

1. Inventário: todo arquivo sql/marts/*.sql é um mart e precisa estar em MARTS (e vice-versa).
   Um .sql novo sem chave lógica declarada interrompe a execução: a granularidade é decidida
   por quem escreve a consulta (comentário "Grão:" do próprio arquivo), nunca presumida aqui.
2. Nome da tabela = nome do arquivo sem extensão (sql/marts/marts_roic.sql -> marts.marts_roic).
   Motivo: rastreabilidade 1:1 com o arquivo e com os nomes usados no painel, e nenhum
   identificador começando por dígito (marts.01_rank_valor exigiria aspas em toda consulta).
3. O texto do .sql é executado como está (UTF-8, sem BOM e sem o ';' final), igual ao painel.
   Nenhum cálculo, filtro ou coluna é acrescentado.
4. Estratégia de atualização: substituição integral em todas as tabelas, por natureza:
   - Fotografia por ticker (indicadores, rankings, recomendações, painel): o resultado vale para
     a data de referência atual da Silver; linhas de execuções anteriores seriam obsoletas.
   - Agregado de linha única (cards, termômetro, data de referência): idem, sempre uma linha.
   - Série histórica (marts_cotacao): a consulta devolve o histórico inteiro de
     refined.yfinance_cotacoes, sem filtro incremental, e a própria Silver é substituída por
     inteiro a cada transformação. O fechamento ajustado é recalculado retroativamente pelo
     YFinance a cada provento/desdobramento, então acrescentar só datas novas deixaria preços
     antigos desatualizados e manteria linhas removidas da Silver.
5. Preparação: cada consulta é executada uma única vez para uma tabela temporária da conexão;
   validam-se colunas e tipos (iguais ao DESCRIBE da consulta) e a chave lógica (sem nulos e
   sem duplicatas; chave vazia = exatamente uma linha). Nada é publicado se qualquer mart falhar.
6. Publicação: CREATE OR REPLACE TABLE marts.<nome> AS SELECT * FROM <temporária> de todos os
   marts em uma única transação. Antes do COMMIT, cada tabela publicada é comparada com a
   temporária: quantidade de registros, colunas e tipos, e igualdade de valores nos dois
   sentidos com EXCEPT ALL (multiconjunto; NULL é igual a NULL), o que também cobre nulos e
   duplicações. Qualquer divergência faz ROLLBACK: a versão anterior das tabelas permanece.
   A comparação é com a temporária, e não com uma nova execução da consulta, porque agregações
   em DOUBLE executadas em paralelo (desvio-padrão, somas) podem variar no último bit.
7. Somente o schema marts é criado ou alterado; raw e refined são apenas lidos. Tabelas em marts
   sem .sql correspondente não são apagadas: aparecem no relatório como órfãs para decisão manual.
"""

import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import duckdb

from pipeline import db

SCHEMA_DESTINO = "marts"
PASTA_MARTS = Path(__file__).resolve().parent.parent / "sql" / "marts"
AMOSTRA = 5  # chaves exibidas em mensagens de erro

FOTOGRAFIA = "fotografia por ticker"
LINHA_UNICA = "agregado de linha única"
SERIE = "série histórica"
ESTRATEGIA = "substituição integral"


@dataclass(frozen=True)
class Mart:
    nome: str
    chave: tuple  # () = resultado de linha única
    natureza: str


# Chave lógica conforme o comentário "Grão:" de cada arquivo.
MARTS = [
    Mart("marts_01_rank_valor", ("ticker",), FOTOGRAFIA),
    Mart("marts_02_rank_proventos", ("ticker",), FOTOGRAFIA),
    Mart("marts_03_rank_eficiencia", ("ticker",), FOTOGRAFIA),
    Mart("marts_04_rank_retorno", ("ticker",), FOTOGRAFIA),
    Mart("marts_05_rank_pechincha", ("ticker",), FOTOGRAFIA),
    Mart("marts_06_rank_patrimonio", ("ticker",), FOTOGRAFIA),
    Mart("marts_07_rank_crescimento", ("ticker",), FOTOGRAFIA),
    Mart("marts_08_rank_operacional", ("ticker",), FOTOGRAFIA),
    Mart("marts_09_rank_seguro", ("ticker",), FOTOGRAFIA),
    Mart("marts_10_rank_rentabilidade", ("ticker",), FOTOGRAFIA),
    Mart("marts_50_rank_recomendacoes", ("ticker",), FOTOGRAFIA),
    Mart("marts_alavancagem", ("ticker",), FOTOGRAFIA),
    Mart("marts_card_01_acoes_analisadas", (), LINHA_UNICA),
    Mart("marts_card_02_acoes_compra", (), LINHA_UNICA),
    Mart("marts_card_02_acoes_semindicacao", (), LINHA_UNICA),
    Mart("marts_card_03_acoes_manter", (), LINHA_UNICA),
    Mart("marts_card_04_acoes_venda", (), LINHA_UNICA),
    Mart("marts_card_05_termometro_mercado", (), LINHA_UNICA),
    Mart("marts_cotacao", ("ticker", "data"), SERIE),
    Mart("marts_crescimento_receita_5_anos", ("ticker",), FOTOGRAFIA),
    Mart("marts_dividend_yield_payout", ("ticker",), FOTOGRAFIA),
    Mart("marts_ev_ebit", ("ticker",), FOTOGRAFIA),
    Mart("marts_margens", ("ticker",), FOTOGRAFIA),
    Mart("marts_p_vp", ("ticker",), FOTOGRAFIA),
    Mart("marts_painel_data_referencia", (), LINHA_UNICA),
    Mart("marts_painel_indicadores", ("ticker",), FOTOGRAFIA),
    Mart("marts_preco_lucro", ("ticker",), FOTOGRAFIA),
    Mart("marts_retorno_total_risco", ("ticker",), FOTOGRAFIA),
    Mart("marts_roe", ("ticker",), FOTOGRAFIA),
    Mart("marts_roic", ("ticker",), FOTOGRAFIA),
]


class ErroMaterializacao(Exception):
    """Falha que interrompe a materialização sem alterar nenhuma tabela Gold."""

    def __init__(self, etapa, motivo, *, arquivo=None, destino=None, exemplo=None):
        super().__init__(motivo)
        self.etapa = etapa
        self.motivo = motivo
        self.arquivo = arquivo
        self.destino = destino
        self.exemplo = exemplo

    def __str__(self):
        campos = [
            ("Etapa", self.etapa),
            ("Arquivo", self.arquivo),
            ("Destino", self.destino),
            ("Exemplo", self.exemplo),
            ("Motivo", self.motivo),
        ]
        return "\n".join(
            f"  {rotulo + ':':<9}{valor}" for rotulo, valor in campos if valor
        )


@dataclass
class Preparada:
    mart: Mart
    arquivo: str
    temporaria: str
    colunas: list  # [(nome, tipo)] na ordem da consulta
    registros: int


# --------------------------------------------------------------------------- utilitários


def _ident(nome):
    return db._ident(nome)


def _gold(nome):
    return f"{_ident(SCHEMA_DESTINO)}.{_ident(nome)}"


def _rotulo_gold(nome):
    return f"{SCHEMA_DESTINO}.{nome}"


def _temporaria(nome):
    return f"temp.main.{_ident(f'_marts_{nome}')}"


def _fmt(n):
    return f"{n:,}".replace(",", ".")


@contextmanager
def _contexto(etapa, arquivo=None, destino=None):
    """Converte falhas do DuckDB em ErroMaterializacao com etapa, arquivo e tabela."""
    try:
        yield
    except ErroMaterializacao:
        raise
    except duckdb.Error as exc:
        raise ErroMaterializacao(
            etapa, str(exc), arquivo=arquivo, destino=destino
        ) from exc


def _contar(con, tabela):
    return con.execute(f"SELECT COUNT(*) FROM {tabela}").fetchall()[0][0]


def _colunas(con, relacao):
    """[(nome, tipo)] de uma tabela ou de uma consulta entre parênteses."""
    return [(c[0], c[1]) for c in con.execute(f"DESCRIBE {relacao}").fetchall()]


def _texto_sql(arquivo):
    texto = Path(arquivo).read_text(encoding="utf-8-sig").strip()
    return texto.removesuffix(";").rstrip()


# --------------------------------------------------------------------------- inventário


def inventariar(pasta=PASTA_MARTS, marts=MARTS):
    """Confere que cada .sql da pasta tem um Mart declarado e vice-versa."""
    arquivos = {f.stem for f in Path(pasta).glob("*.sql")}
    declarados = {m.nome for m in marts}
    sem_chave = sorted(arquivos - declarados)
    sem_arquivo = sorted(declarados - arquivos)
    if sem_chave:
        raise ErroMaterializacao(
            "inventário",
            "arquivo SQL sem chave lógica declarada em pipeline.materializacao.MARTS "
            "(declare o grão antes de materializar)",
            exemplo=", ".join(f"{n}.sql" for n in sem_chave),
        )
    if sem_arquivo:
        raise ErroMaterializacao(
            "inventário",
            "mart declarado sem arquivo SQL correspondente",
            exemplo=", ".join(f"{n}.sql" for n in sem_arquivo),
        )
    return sorted(marts, key=lambda m: m.nome)


# --------------------------------------------------------------------------- validações


def _validar_chave(con, tabela, mart, rotulo):
    if not mart.chave:
        n = _contar(con, tabela)
        if n != 1:
            raise ErroMaterializacao(
                "validação da chave",
                f"resultado de linha única devolveu {_fmt(n)} registros",
                destino=rotulo,
            )
        return
    colunas = ", ".join(_ident(c) for c in mart.chave)
    nulos = con.execute(
        f"SELECT COUNT(*) FROM {tabela} WHERE "
        + " OR ".join(f"{_ident(c)} IS NULL" for c in mart.chave)
    ).fetchall()[0][0]
    if nulos:
        raise ErroMaterializacao(
            "validação da chave",
            f"{_fmt(nulos)} registros com chave ({', '.join(mart.chave)}) nula",
            destino=rotulo,
        )
    duplicadas = con.execute(
        f"SELECT {colunas}, COUNT(*) AS n FROM {tabela} GROUP BY ALL "
        f"HAVING COUNT(*) > 1 ORDER BY ALL LIMIT {AMOSTRA}"
    ).fetchall()
    if duplicadas:
        raise ErroMaterializacao(
            "validação da chave",
            f"chave ({', '.join(mart.chave)}) duplicada: o resultado não respeita o grão declarado",
            destino=rotulo,
            exemplo="; ".join(str(d) for d in duplicadas),
        )


def _validar_publicada(con, p):
    """Compara marts.<nome> com a temporária: registros, colunas, tipos e valores."""
    rotulo = _rotulo_gold(p.mart.nome)
    destino = _gold(p.mart.nome)
    colunas = _colunas(con, destino)
    if colunas != p.colunas:
        raise ErroMaterializacao(
            "validação da publicação",
            f"colunas/tipos divergentes da consulta: {colunas} != {p.colunas}",
            destino=rotulo,
        )
    gravados = _contar(con, destino)
    if gravados != p.registros:
        raise ErroMaterializacao(
            "validação da publicação",
            f"{_fmt(gravados)} registros gravados para {_fmt(p.registros)} da consulta",
            destino=rotulo,
        )
    for a, b in ((destino, p.temporaria), (p.temporaria, destino)):
        divergentes = _contar(con, f"(SELECT * FROM {a} EXCEPT ALL SELECT * FROM {b})")
        if divergentes:
            raise ErroMaterializacao(
                "validação da publicação",
                f"{_fmt(divergentes)} registros divergentes entre a tabela e a consulta",
                destino=rotulo,
            )
    _validar_chave(con, destino, p.mart, rotulo)


# --------------------------------------------------------------------------- preparação


def preparar(con, mart, pasta=PASTA_MARTS):
    """Executa o .sql uma vez para uma tabela temporária e valida colunas e chave."""
    arquivo = Path(pasta) / f"{mart.nome}.sql"
    rotulo_arquivo = f"sql/marts/{arquivo.name}"
    rotulo = _rotulo_gold(mart.nome)
    temporaria = _temporaria(mart.nome)
    with _contexto("execução da consulta", arquivo=rotulo_arquivo, destino=rotulo):
        sql = _texto_sql(arquivo)
        esperadas = _colunas(con, f"({sql})")
        con.execute(f"CREATE OR REPLACE TEMP TABLE {temporaria} AS {sql}")
        colunas = _colunas(con, temporaria)
        if colunas != esperadas:
            raise ErroMaterializacao(
                "execução da consulta",
                f"colunas/tipos divergentes do DESCRIBE da consulta: {colunas} != {esperadas}",
                arquivo=rotulo_arquivo,
                destino=rotulo,
            )
        ausentes = [c for c in mart.chave if c not in {n for n, _ in colunas}]
        if ausentes:
            raise ErroMaterializacao(
                "validação da chave",
                f"coluna(s) da chave lógica ausente(s) no resultado: {', '.join(ausentes)}",
                arquivo=rotulo_arquivo,
                destino=rotulo,
            )
        _validar_chave(con, temporaria, mart, rotulo)
        return Preparada(
            mart, rotulo_arquivo, temporaria, colunas, _contar(con, temporaria)
        )


# --------------------------------------------------------------------------- publicação


def publicar(con, preparadas):
    """Substitui as tabelas Gold e as valida em uma única transação; falha = rollback."""
    con.begin()
    try:
        db.criar_schema(con, SCHEMA_DESTINO)
        for p in preparadas:
            with _contexto(
                "publicação", arquivo=p.arquivo, destino=_rotulo_gold(p.mart.nome)
            ):
                con.execute(
                    f"CREATE OR REPLACE TABLE {_gold(p.mart.nome)} AS SELECT * FROM {p.temporaria}"
                )
        for p in preparadas:
            with _contexto(
                "validação da publicação",
                arquivo=p.arquivo,
                destino=_rotulo_gold(p.mart.nome),
            ):
                _validar_publicada(con, p)
        con.commit()
    except Exception as exc:
        try:
            con.rollback()
        except duckdb.Error:
            pass  # a transação já foi abortada pelo próprio DuckDB
        if isinstance(exc, ErroMaterializacao):
            exc.motivo = (
                f"{exc.motivo} — rollback executado: nenhuma tabela Gold foi alterada"
            )
            raise
        raise ErroMaterializacao(
            "publicação",
            f"{exc} — rollback executado: nenhuma tabela Gold foi alterada",
            destino=SCHEMA_DESTINO,
        ) from exc


def _remover_temporarias(con, preparadas):
    for p in preparadas:
        con.execute(f"DROP TABLE IF EXISTS {p.temporaria}")


# --------------------------------------------------------------------------- relatório


def _orfas(con, marts):
    existentes = con.execute(
        "SELECT table_name FROM duckdb_tables() WHERE database_name = current_database() "
        "AND schema_name = ? ORDER BY 1",
        [SCHEMA_DESTINO],
    ).fetchall()
    declarados = {m.nome for m in marts}
    return [n for (n,) in existentes if n not in declarados]


def _coletar_relatorio(con, preparadas, marts):
    tabelas = [
        {
            "tabela": _rotulo_gold(p.mart.nome),
            "arquivo": p.arquivo,
            "registros": _contar(con, _gold(p.mart.nome)),
            "colunas": len(p.colunas),
            "chave": ", ".join(p.mart.chave) or "(linha única)",
            "natureza": p.mart.natureza,
            "estrategia": ESTRATEGIA,
        }
        for p in preparadas
    ]
    return {"tabelas": tabelas, "orfas": _orfas(con, marts)}


def _imprimir_relatorio(relatorio):
    tabelas = relatorio["tabelas"]
    largura = max(len(r["tabela"]) for r in tabelas) + 2
    numeros = max(len(_fmt(r["registros"])) for r in tabelas) + 2
    print()
    print(f"{'TABELA':<{largura}}{'REGISTROS':>{numeros + 2}}  COLS  CHAVE LÓGICA")
    print("-" * (largura + numeros + 40))
    for r in tabelas:
        print(
            f"{r['tabela']:<{largura}}{_fmt(r['registros']):>{numeros + 2}}"
            f"  {r['colunas']:>4}  {r['chave']}"
        )
    print("-" * (largura + numeros + 40))
    total = sum(r["registros"] for r in tabelas)
    print(
        f"{f'{len(tabelas)} tabelas materializadas':<{largura}}{_fmt(total):>{numeros + 2}}"
    )
    print(
        f"\nEstratégia: {ESTRATEGIA} em transação única; registros, colunas, tipos, "
        "valores (EXCEPT ALL) e chave lógica validados antes do COMMIT."
    )
    if relatorio["orfas"]:
        print(
            "\nATENÇÃO: tabelas em marts sem .sql correspondente (não foram removidas): "
            + ", ".join(relatorio["orfas"])
        )


# --------------------------------------------------------------------------- orquestração


def executar(con, pasta=PASTA_MARTS, marts=MARTS):
    """Inventaria, prepara e valida todos os marts e só então os publica atomicamente."""
    marts = inventariar(pasta, marts)
    preparadas = []
    try:
        for mart in marts:
            preparadas.append(preparar(con, mart, pasta))
        publicar(con, preparadas)
        return _coletar_relatorio(con, preparadas, marts)
    finally:
        _remover_temporarias(con, preparadas)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    try:
        con = db.conectar()
    except duckdb.Error as exc:
        print(
            f"\nERRO DE MATERIALIZAÇÃO\n  Etapa:   conexão\n  Motivo:  {exc}",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        relatorio = executar(con)
    except ErroMaterializacao as exc:
        print(f"\nERRO DE MATERIALIZAÇÃO\n{exc}", file=sys.stderr)
        print("Nenhuma tabela Gold foi alterada.", file=sys.stderr)
        sys.exit(1)
    finally:
        con.close()
    _imprimir_relatorio(relatorio)


if __name__ == "__main__":
    main()
