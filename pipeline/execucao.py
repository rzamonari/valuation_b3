"""Registro de execução das etapas do pipeline: meta.execucoes e o mart de saúde.

Cada comando (uv run python -m pipeline.<etapa>) mede a própria execução com `registrada()` e,
ao terminar com sucesso ou falha, grava uma linha em meta.execucoes: etapa, início, fim,
duração, linhas por tabela publicada, status, avisos e erro. Em seguida republica
marts.marts_painel_saude_pipeline com a materialização da Gold (validação na temporária e
transação única), para o painel ler a saúde como lê qualquer outro mart.

# DECISÕES

1. O registro nunca muda o resultado da etapa: falha ao gravar (banco bloqueado pela DuckDB UI,
   por exemplo) vira aviso no log e o código de saída continua o da etapa. Sem o arquivo do
   banco, nada é gravado: o registro não cria um banco vazio.
2. Etapa que falha também registra, com status "falha" e o erro. O erro e os avisos vêm do
   próprio log da etapa (pipeline.log.capturar): as mensagens de ERRO viram o erro e as de
   AVISO (retries, falhas por item), os avisos. A qualidade e a fotografia informam os avisos
   explicitamente: as verificações com AVISO e o número de violações.
3. Horários em TIMESTAMP sem fuso, sempre UTC (colunas *_utc): o banco, o Parquet da fotografia
   e o painel leem o mesmo valor em qualquer máquina. A duração vem do relógio monotônico.
4. Linhas por tabela: a contagem que a etapa já relata (raw.*, refined.*, marts.* ou os
   arquivos da fotografia), numa lista de STRUCT(tabela, linhas) na mesma linha da execução.
5. Idade dos dados (idade()): dias úteis (segunda a sexta, sem feriados da B3) entre a data de
   referência e hoje no horário de Brasília (UTC−3, sem horário de verão desde 2019). Fica fora
   do mart porque depende do dia em que o painel é aberto, e não dos dados: o mart
   materializado e a fotografia congelariam o valor.
"""

import logging
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta, timezone

import duckdb

from pipeline import db
from pipeline import log as pipeline_log
from pipeline.db import _ident

log = logging.getLogger("pipeline.execucao")

SCHEMA = "meta"
TABELA = "execucoes"
MART_SAUDE = "marts_painel_saude_pipeline"
SUCESSO = "sucesso"
FALHA = "falha"
ETAPAS = ("ingestao", "transformacao", "materializacao", "qualidade", "fotografia")
LIMITE_AVISOS = (
    20  # avisos guardados por execução; o excedente vira uma linha de resumo
)
LIMITE_ERRO = 2000  # caracteres do erro guardado
LIMITE_DIAS_UTEIS = 5  # idade dos dados acima disto gera alerta no painel
BRASILIA = timezone(timedelta(hours=-3))

DDL = f"""
CREATE TABLE IF NOT EXISTS {_ident(SCHEMA)}.{_ident(TABELA)} (
    id VARCHAR NOT NULL PRIMARY KEY,
    etapa VARCHAR NOT NULL,
    inicio_utc TIMESTAMP NOT NULL,
    fim_utc TIMESTAMP NOT NULL,
    duracao_s DOUBLE NOT NULL,
    status VARCHAR NOT NULL,
    linhas_por_tabela STRUCT(tabela VARCHAR, linhas BIGINT)[] NOT NULL,
    avisos VARCHAR[] NOT NULL,
    erro VARCHAR
)
"""


def _agora() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass
class Execucao:
    """Uma execução de etapa, do início (iniciar) ao fim (concluir)."""

    etapa: str
    inicio_utc: datetime = field(default_factory=_agora)
    fim_utc: datetime | None = None
    duracao_s: float | None = None
    status: str | None = None
    tabelas: dict[str, int] = field(default_factory=dict)
    avisos: list[str] | None = None  # None = usar os avisos capturados do log
    erro: str | None = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    _relogio: float = field(default_factory=time.monotonic, repr=False)

    def concluir(self, status: str, avisos: list[str], erro: str | None = None) -> None:
        """Fecha a execução. Concluir de novo com o mesmo status não altera nada (a fotografia
        conclui antes de escrever o manifesto, e o fim da etapa não pode divergir dele)."""
        if self.fim_utc is not None and self.status == status:
            return
        self.fim_utc = _agora()
        self.duracao_s = round(time.monotonic() - self._relogio, 3)
        self.status = status
        if self.avisos is None:
            self.avisos = avisos
        if len(self.avisos) > LIMITE_AVISOS:
            excedente = len(self.avisos) - LIMITE_AVISOS
            self.avisos = self.avisos[:LIMITE_AVISOS] + [
                f"… e mais {excedente} aviso(s)"
            ]
        if erro is not None:
            self.erro = erro[:LIMITE_ERRO]

    def como_dict(self) -> dict:
        """Forma serializável (manifesto da fotografia)."""
        return {
            "etapa": self.etapa,
            "inicio_utc": self.inicio_utc.isoformat(timespec="seconds"),
            "fim_utc": self.fim_utc.isoformat(timespec="seconds")
            if self.fim_utc
            else None,
            "duracao_s": self.duracao_s,
            "status": self.status,
            "linhas_por_tabela": dict(self.tabelas),
            "avisos": list(self.avisos or []),
            "erro": self.erro,
        }


# --------------------------------------------------------------------------- gravação


def garantir_tabela(con: duckdb.DuckDBPyConnection) -> None:
    """Cria meta.execucoes (vazia) se ainda não existir; o mart de saúde lê essa tabela."""
    db.criar_schema(con, SCHEMA)
    con.execute(DDL)


def gravar(con: duckdb.DuckDBPyConnection, execucao: Execucao) -> None:
    """Acrescenta a execução em meta.execucoes e republica o mart de saúde."""
    # tardio: a materialização também registra a própria execução por este módulo
    from pipeline import materializacao

    garantir_tabela(con)
    con.execute(
        f"INSERT INTO {_ident(SCHEMA)}.{_ident(TABELA)} VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            execucao.id,
            execucao.etapa,
            execucao.inicio_utc,
            execucao.fim_utc,
            execucao.duracao_s,
            execucao.status,
            [{"tabela": t, "linhas": n} for t, n in execucao.tabelas.items()],
            list(execucao.avisos or []),
            execucao.erro,
        ],
    )
    materializacao.atualizar(con, [MART_SAUDE])


def registrar(execucao: Execucao) -> bool:
    """Abre o banco, grava a execução e fecha. Nunca levanta (decisão 1)."""
    arquivo = db.caminho_banco()
    if not arquivo.exists():
        log.warning(
            f"Registro de execução não gravado: banco {arquivo.name} inexistente."
        )
        return False
    try:
        con = db.conectar()
    except duckdb.Error as exc:
        log.warning(f"Registro de execução não gravado: {str(exc).splitlines()[0]}")
        return False
    try:
        gravar(con, execucao)
    except Exception as exc:  # noqa: BLE001 — o registro não altera o resultado da etapa
        log.warning(f"Registro de execução não gravado: {str(exc).strip()}")
        return False
    finally:
        con.close()
    return True


@contextmanager
def registrada(etapa: str) -> Iterator[Execucao]:
    """Mede o bloco e registra a execução ao sair, com sucesso ou falha.

    Falha = exceção ou sys.exit com código diferente de zero (a exceção segue adiante).
    O bloco informa as linhas por tabela em execucao.tabelas e, se quiser, os avisos.
    """
    execucao = Execucao(etapa)
    try:
        with pipeline_log.capturar() as captura:
            try:
                yield execucao
            except SystemExit as exc:
                status = SUCESSO if exc.code in (None, 0) else FALHA
                _concluir(execucao, status, captura, exc)
                raise
            except BaseException as exc:
                _concluir(execucao, FALHA, captura, exc)
                raise
            else:
                _concluir(execucao, SUCESSO, captura)
    finally:
        registrar(execucao)


def _concluir(execucao, status, captura, exc=None):
    erro = None
    if status == FALHA:
        mensagens = list(captura.erros)
        if not mensagens and not isinstance(exc, SystemExit):
            mensagens = [f"{type(exc).__name__}: {exc}"]
        erro = "\n".join(mensagens) or "falha sem mensagem de erro"
    execucao.concluir(status, list(captura.avisos), erro)


# --------------------------------------------------------------------------- leitura


def ultimas(con: duckdb.DuckDBPyConnection) -> list[dict]:
    """Execução mais recente de cada etapa em meta.execucoes (vazio se a tabela não existe)."""
    existe = con.execute(
        "SELECT COUNT(*) FROM duckdb_tables() WHERE database_name = current_database() "
        "AND schema_name = ? AND table_name = ?",
        [SCHEMA, TABELA],
    ).fetchall()[0][0]
    if not existe:
        return []
    linhas = con.execute(
        f"SELECT etapa, inicio_utc, fim_utc, duracao_s, status, linhas_por_tabela, avisos, "
        f"erro FROM {_ident(SCHEMA)}.{_ident(TABELA)} "
        "QUALIFY ROW_NUMBER() OVER (PARTITION BY etapa ORDER BY inicio_utc DESC, id DESC) = 1"
    ).fetchall()
    ordem = {e: i for i, e in enumerate(ETAPAS)}
    resultado = []
    for etapa, inicio, fim, duracao, status, tabelas, avisos, erro in sorted(
        linhas, key=lambda r: (ordem.get(r[0], len(ETAPAS)), r[0])
    ):
        resultado.append(
            {
                "etapa": etapa,
                "inicio_utc": inicio.isoformat(timespec="seconds"),
                "fim_utc": fim.isoformat(timespec="seconds"),
                "duracao_s": duracao,
                "status": status,
                "linhas_por_tabela": {t["tabela"]: t["linhas"] for t in tabelas},
                "avisos": list(avisos),
                "erro": erro,
            }
        )
    return resultado


# --------------------------------------------------------------------------- idade dos dados


@dataclass(frozen=True)
class Idade:
    dias_corridos: int
    dias_uteis: int
    limite_dias_uteis: int

    @property
    def alerta(self) -> bool:
        return self.dias_uteis > self.limite_dias_uteis


def hoje_brasilia() -> date:
    return datetime.now(BRASILIA).date()


def idade(
    data_referencia: date, hoje: date | None = None, limite: int = LIMITE_DIAS_UTEIS
) -> Idade:
    """Dias corridos e úteis (seg. a sex.) de data_referencia (exclusive) até hoje (inclusive)."""
    hoje = hoje_brasilia() if hoje is None else hoje
    corridos = (hoje - data_referencia).days
    uteis = sum(
        (data_referencia + timedelta(days=d)).weekday() < 5
        for d in range(1, max(corridos, 0) + 1)
    )
    return Idade(corridos, uteis, limite)
