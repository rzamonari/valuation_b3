"""Fotografia versionada da Gold: marts.* em Parquet + manifesto com data de referência e hash.

Execução:
  uv run python -m pipeline.fotografia              # exporta do banco (exige qualidade sem erros)
  uv run python -m pipeline.fotografia --verificar  # confere os hashes da fotografia versionada

# DECISÕES

1. Conteúdo: todas as tabelas declaradas em pipeline.materializacao.MARTS, uma por arquivo
   fotografia/<mart>.parquet (zstd), ordenadas pela chave lógica (ou por todas as colunas no
   agregado de linha única). Motivo: o painel só lê marts.*, e a ordem fixa torna o arquivo
   determinístico para a mesma versão do DuckDB — o hash muda só quando os dados mudam.
2. Manifesto (fotografia/manifesto.json): data de referência (marts_painel_data_referencia),
   momento da geração, versão do DuckDB, resumo da qualidade e, por tabela, arquivo, registros,
   bytes e SHA-256. hash = SHA-256 das linhas "<mart> <sha256>" em ordem alfabética: identifica
   a fotografia inteira e não depende do momento da geração.
3. Portão de qualidade: pipeline.qualidade.exigir() antes de exportar; erro = nada é escrito.
4. Publicação atômica: tudo é escrito numa pasta temporária ao lado do destino e trocado por
   renomeação no fim; falha no meio preserva a fotografia anterior.
5. Leitura (conectar): banco DuckDB em memória com views marts."<mart>" sobre os Parquet, para
   o painel usar as mesmas consultas do banco local. verificar() confere manifesto, arquivos
   e hashes antes do uso.
6. Recorte de colunas (COLUNAS): marts_cotacao entra só com as colunas que o painel usa
   (ticker, data, fechamento_ajustado, dividendos, volume), registradas em "colunas" no manifesto.
   Motivo: é quase todo o volume da fotografia (26 MB → 10 MB), e cada fotografia nova fica
   no histórico do git. O banco local continua com a série completa.
"""

import argparse
import hashlib
import json
import logging
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from pipeline import db, qualidade
from pipeline.db import _ident
from pipeline.log import configurar as configurar_logging
from pipeline.materializacao import MARTS, Mart

log = logging.getLogger("pipeline.fotografia")

PASTA_FOTOGRAFIA = db._RAIZ / "fotografia"
MANIFESTO = "manifesto.json"
FORMATO = 1
MART_DATA_REFERENCIA = "marts_painel_data_referencia"
# Marts exportados só com parte das colunas (decisão 6); os demais vão inteiros.
COLUNAS = {
    "marts_cotacao": ("ticker", "data", "fechamento_ajustado", "dividendos", "volume")
}


class ErroFotografia(Exception):
    """Fotografia ausente, incompleta ou com hash divergente do manifesto."""


# --------------------------------------------------------------------------- utilitários


def _sha256(arquivo: Path) -> str:
    h = hashlib.sha256()
    with open(arquivo, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _hash_total(tabelas: dict) -> str:
    linhas = "".join(f"{nome} {t['sha256']}\n" for nome, t in sorted(tabelas.items()))
    return hashlib.sha256(linhas.encode("utf-8")).hexdigest()


def _literal(texto: str) -> str:
    return "'" + str(texto).replace("'", "''") + "'"


def _ordem(mart: Mart) -> str:
    return ", ".join(_ident(c) for c in mart.chave) if mart.chave else "ALL"


def selecao(nome: str) -> str:
    """Lista do SELECT de um mart na fotografia: as colunas de COLUNAS ou todas."""
    return ", ".join(_ident(c) for c in COLUNAS[nome]) if nome in COLUNAS else "*"


def _conferir_tipos(con, nome, arquivo):
    """O Parquet relido precisa ter as colunas e tipos da tabela (ex.: HUGEINT vira DOUBLE)."""

    def colunas(relacao):
        return [(c[0], c[1]) for c in con.execute(f"DESCRIBE {relacao}").fetchall()]

    origem = colunas(f"SELECT {selecao(nome)} FROM marts.{_ident(nome)}")
    relido = colunas(f"SELECT * FROM read_parquet({_literal(arquivo.as_posix())})")
    if origem != relido:
        diferentes = [
            f"{a} -> {b}" for a, b in zip(origem, relido, strict=False) if a != b
        ]
        raise ErroFotografia(
            f"marts.{nome}: tipo sem equivalente em Parquet ({'; '.join(diferentes)})"
        )


# --------------------------------------------------------------------------- exportação


def exportar(
    con: duckdb.DuckDBPyConnection,
    pasta: Path = PASTA_FOTOGRAFIA,
    marts: list[Mart] = MARTS,
) -> dict:
    """Grava a fotografia de marts.* em pasta e devolve o manifesto."""
    resultados = qualidade.exigir(con)
    pasta = Path(pasta)
    temporaria = pasta.with_name(f".{pasta.name}.nova")
    shutil.rmtree(temporaria, ignore_errors=True)
    temporaria.mkdir(parents=True)
    try:
        tabelas = {}
        for mart in sorted(marts, key=lambda m: m.nome):
            arquivo = temporaria / f"{mart.nome}.parquet"
            con.execute(
                f"COPY (SELECT {selecao(mart.nome)} FROM marts.{_ident(mart.nome)} "
                f"ORDER BY {_ordem(mart)}) "
                f"TO {_literal(arquivo.as_posix())} (FORMAT parquet, COMPRESSION zstd)"
            )
            _conferir_tipos(con, mart.nome, arquivo)
            tabelas[mart.nome] = {
                **(
                    {"colunas": list(COLUNAS[mart.nome])}
                    if mart.nome in COLUNAS
                    else {}
                ),
                "arquivo": arquivo.name,
                "registros": con.execute(
                    f"SELECT COUNT(*) FROM marts.{_ident(mart.nome)}"
                ).fetchall()[0][0],
                "bytes": arquivo.stat().st_size,
                "sha256": _sha256(arquivo),
            }
        [(data_referencia,)] = con.execute(
            f"SELECT data_referencia FROM marts.{_ident(MART_DATA_REFERENCIA)}"
        ).fetchall()
        manifesto = {
            "formato": FORMATO,
            "data_referencia": data_referencia.isoformat(),
            "gerada_em": datetime.now(UTC).isoformat(timespec="seconds"),
            "duckdb": duckdb.__version__,
            "hash": _hash_total(tabelas),
            "qualidade": {
                "verificacoes": len(resultados),
                "avisos": sum(r.status == "AVISO" for r in resultados),
            },
            "tabelas": tabelas,
        }
        (temporaria / MANIFESTO).write_text(
            json.dumps(manifesto, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except BaseException:
        shutil.rmtree(temporaria, ignore_errors=True)
        raise
    antiga = pasta.with_name(f".{pasta.name}.antiga")
    shutil.rmtree(antiga, ignore_errors=True)
    if pasta.exists():
        pasta.rename(antiga)
    temporaria.rename(pasta)
    shutil.rmtree(antiga, ignore_errors=True)
    return manifesto


# --------------------------------------------------------------------------- leitura


def ler_manifesto(pasta: Path = PASTA_FOTOGRAFIA) -> dict:
    arquivo = Path(pasta) / MANIFESTO
    if not arquivo.exists():
        raise ErroFotografia(f"manifesto não encontrado: {arquivo}")
    try:
        manifesto = json.loads(arquivo.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ErroFotografia(f"manifesto inválido: {exc}") from exc
    if manifesto.get("formato") != FORMATO:
        raise ErroFotografia(
            f"formato de manifesto não suportado: {manifesto.get('formato')}"
        )
    return manifesto


def verificar(pasta: Path = PASTA_FOTOGRAFIA) -> dict:
    """Confere arquivos e hashes contra o manifesto; devolve o manifesto se íntegro."""
    pasta = Path(pasta)
    manifesto = ler_manifesto(pasta)
    tabelas = manifesto["tabelas"]
    divergentes = []
    for _, t in sorted(tabelas.items()):
        arquivo = pasta / t["arquivo"]
        if not arquivo.exists():
            divergentes.append(f"{t['arquivo']} ausente")
        elif _sha256(arquivo) != t["sha256"]:
            divergentes.append(f"{t['arquivo']} com hash divergente")
    if _hash_total(tabelas) != manifesto["hash"]:
        divergentes.append("hash total divergente das tabelas do manifesto")
    if divergentes:
        raise ErroFotografia("fotografia inválida: " + "; ".join(divergentes))
    return manifesto


def conectar(
    pasta: Path = PASTA_FOTOGRAFIA, nomes: list[str] | None = None
) -> duckdb.DuckDBPyConnection:
    """Banco em memória com views marts."<mart>" sobre os Parquet. Quem chama fecha.

    nomes restringe as views aos marts que serão lidos (None = todos do manifesto): criar a
    view abre o Parquet, e a carga da página não precisa abrir o da cotação.
    """
    pasta = Path(pasta).resolve()
    manifesto = ler_manifesto(pasta)
    tabelas = {
        n: t for n, t in manifesto["tabelas"].items() if nomes is None or n in nomes
    }
    con = duckdb.connect()
    try:
        con.execute("CREATE SCHEMA marts")
        for nome, t in tabelas.items():
            try:
                con.execute(
                    f"CREATE VIEW marts.{_ident(nome)} AS SELECT * FROM "
                    f"read_parquet({_literal((pasta / t['arquivo']).as_posix())})"
                )
            except duckdb.Error as exc:
                raise ErroFotografia(f"{t['arquivo']} ilegível: {exc}") from exc
    except BaseException:
        con.close()
        raise
    return con


# --------------------------------------------------------------------------- comando


def main(argv: list[str] | None = None) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    configurar_logging()
    parser = argparse.ArgumentParser(prog="python -m pipeline.fotografia")
    parser.add_argument(
        "--verificar",
        action="store_true",
        help="só confere os hashes da fotografia versionada",
    )
    args = parser.parse_args(argv)

    if args.verificar:
        try:
            manifesto = verificar(PASTA_FOTOGRAFIA)
        except ErroFotografia as exc:
            log.error(f"\nERRO DE FOTOGRAFIA\n  {exc}")
            sys.exit(1)
        log.info(
            f"Fotografia íntegra: data de referência {manifesto['data_referencia']}, "
            f"{len(manifesto['tabelas'])} tabelas, hash {manifesto['hash']}"
        )
        return

    try:
        con = duckdb.connect(str(db.caminho_banco()), read_only=True)
    except duckdb.Error as exc:
        log.error(f"\nERRO DE FOTOGRAFIA\n  Etapa:   conexão\n  Motivo:  {exc}")
        sys.exit(1)
    try:
        manifesto = exportar(con, PASTA_FOTOGRAFIA)
    except qualidade.ErroQualidade as exc:
        qualidade.imprimir_relatorio(exc.resultados)
        log.error(f"\nERRO DE FOTOGRAFIA\n  Qualidade reprovada: {exc}")
        log.error("Nenhum arquivo da fotografia foi alterado.")
        sys.exit(1)
    except (duckdb.Error, ErroFotografia) as exc:
        log.error(f"\nERRO DE FOTOGRAFIA\n  Etapa:   exportação\n  Motivo:  {exc}")
        log.error("Nenhum arquivo da fotografia foi alterado.")
        sys.exit(1)
    finally:
        con.close()
    total = sum(t["bytes"] for t in manifesto["tabelas"].values())
    log.info(
        f"Fotografia gerada em {PASTA_FOTOGRAFIA.name}/: data de referência "
        f"{manifesto['data_referencia']}, {len(manifesto['tabelas'])} tabelas, "
        f"{total / 1e6:.1f} MB, hash {manifesto['hash']}"
    )
    log.info(
        f"Qualidade: {manifesto['qualidade']['verificacoes']} verificações, "
        f"{manifesto['qualidade']['avisos']} aviso(s). Versione fotografia/ no git."
    )


if __name__ == "__main__":
    main()
