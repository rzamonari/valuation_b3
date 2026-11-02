"""Testes da camada Refined (Silver). Usam bancos DuckDB temporários: a Bronze real não é tocada."""

import json
from datetime import UTC, date, datetime
from decimal import Decimal

import duckdb
import pytest

from pipeline import db
from pipeline import transformacao as t

TABELAS_SILVER = (
    [p.destino for p in t.TABELAS_SQL]
    + [t.ORIGEM_MINHARECEITA]
    + [a.destino for a in t.ARRAYS_EMPRESA]
)


# --------------------------------------------------------------------------- dados sintéticos


def linha_b3(**valores):
    base = {c.origem: "x" for c in t.TABELAS_SQL[0].colunas}
    base.update(codeCVM="900049", cnpj="0", dateListing="31/12/9999")
    return base | valores


def linha_fundamentus(**valores):
    base = {c.origem: "0,00" for c in t.TABELAS_SQL[1].colunas}
    base.update(
        {
            "Papel": "ABCD3",
            "Patrim. Líq": "1.083.050.000,00",
            "Div.Yield": "6,91%",
            "Mrg Bruta": "-208,15%",
            "PSR": "3,423",
            "Dív.Líq/ Patrim.": "\n\t\t\t\t0,10\t\t\t",
            "_timestamp_ingestao": "2026-11-01T18:43:19+00:00",
            "_source_origin": "fundamentus",
        }
    )
    return base | valores


def linha_yfinance(**valores):
    base = {c.origem: "1.5" for c in t.TABELAS_SQL[2].colunas}
    base.update(
        {
            "ticker": "ABCD3",
            "Date": "2026-10-29 00:00:00-03:00",
            "Volume": "100",
            "Dividends": "0.0",
            "Capital Gains": None,
            "_timestamp_ingestao": "2026-11-01T18:45:35+00:00",
            "_source_origin": "yfinance",
        }
    )
    return base | valores


def socio(nome, **valores):
    base = {p: None for p in t.ARRAYS_EMPRESA[0].propriedades}
    base.update(
        nome_socio=nome,
        faixa_etaria="Entre 41 a 50 anos",
        codigo_faixa_etaria=5,
        data_entrada_sociedade="2021-05-27",
        identificador_de_socio=2,
    )
    return base | valores


def empresa(cnpj, **valores):
    base = {p: None for p in t.ESCALARES_EMPRESA}
    base.update(
        cnpj=cnpj,
        uf="SP",
        cep="04794000",
        cnae_fiscal=6462000,
        capital_social=343504.72,
        opcao_pelo_mei=False,
        data_inicio_atividade="2021-11-10",
        qsa=[socio("ANA"), socio("BRUNO"), socio("CARLA")],
        regime_tributario=[
            {
                "ano": 2023,
                "cnpj_da_scp": None,
                "forma_de_tributacao": "LUCRO REAL",
                "quantidade_de_escrituracoes": 1,
            },
            {
                "ano": 2023,
                "cnpj_da_scp": None,
                "forma_de_tributacao": "LUCRO PRESUMIDO",
                "quantidade_de_escrituracoes": 1,
            },
        ],
        cnaes_secundarios=[{"codigo": 3513100, "descricao": "Transmissão"}],
    )
    return base | valores


def linha_minhareceita(dados, cnpj=None):
    cnpj = dados["cnpj"] if cnpj is None else cnpj
    return {
        "cnpj": cnpj,
        "payload_json": json.dumps(dados, ensure_ascii=False),
        "_timestamp_ingestao": "2026-11-01T18:43:39+00:00",
        "_source_origin": f"https://minhareceita.org/{cnpj}",
    }


COLUNAS_BRONZE = {
    **{tab.origem: [c.origem for c in tab.colunas] for tab in t.TABELAS_SQL},
    t.ORIGEM_MINHARECEITA: list(t.COLUNAS_BRONZE_MINHARECEITA),
}


def gravar_bronze(con, tabela, linhas):
    colunas = COLUNAS_BRONZE[tabela]
    definicao = ", ".join(f"{db._ident(c)} VARCHAR" for c in colunas)
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    con.execute(f"CREATE OR REPLACE TABLE raw.{db._ident(tabela)} ({definicao})")
    if linhas:
        marcadores = ", ".join("?" for _ in colunas)
        con.executemany(
            f"INSERT INTO raw.{db._ident(tabela)} VALUES ({marcadores})",
            [[linha[c] for c in colunas] for linha in linhas],
        )


@pytest.fixture
def con(tmp_path):
    conexao = duckdb.connect(str(tmp_path / "teste.duckdb"))
    gravar_bronze(conexao, "b3_empresas", [linha_b3()])
    gravar_bronze(conexao, "fundamentus_acoes", [linha_fundamentus()])
    gravar_bronze(conexao, "yfinance_cotacoes", [linha_yfinance()])
    gravar_bronze(
        conexao,
        "minhareceita_empresas",
        [linha_minhareceita(empresa("11111111000111"))],
    )
    yield conexao
    conexao.close()


def consultar(con, sql):
    return con.execute(sql).fetchall()


def foto(con, schema, tabelas):
    return {
        tab: consultar(con, f"SELECT * FROM {schema}.{db._ident(tab)} ORDER BY ALL")
        for tab in tabelas
    }


def relatorio_de(relatorio, destino):
    return next(r for r in relatorio if r["tabela"] == f"refined.{destino}")


# --------------------------------------------------------------------------- B3


def test_b3_datas_identificadores_e_vazios(con):
    gravar_bronze(
        con,
        "b3_empresas",
        [
            linha_b3(codeCVM="900049", cnpj="0", dateListing="31/12/9999", typeBDR=""),
            linha_b3(
                codeCVM="0050110",
                cnpj="00012345000100",
                dateListing="08/08/1910",
                typeBDR=None,
            ),
        ],
    )
    t.executar(con)
    linhas = consultar(
        con,
        "SELECT codigo_cvm, cnpj, data_listagem, tipo_bdr FROM refined.b3_empresas ORDER BY codigo_cvm",
    )
    assert linhas == [
        ("0050110", "00012345000100", date(1910, 8, 8), None),
        ("900049", "00000000000000", date(9999, 12, 31), ""),
    ]


def test_b3_cnpj_completado_com_zeros_a_esquerda(con):
    gravar_bronze(
        con,
        "b3_empresas",
        [
            linha_b3(codeCVM="1", cnpj="191"),
            linha_b3(codeCVM="2", cnpj="973749000115"),
            linha_b3(codeCVM="3", cnpj="33000167000101"),
            linha_b3(codeCVM="4", cnpj=""),
            linha_b3(codeCVM="5", cnpj=None),
        ],
    )
    t.executar(con)
    assert consultar(
        con, "SELECT codigo_cvm, cnpj FROM refined.b3_empresas ORDER BY codigo_cvm"
    ) == [
        ("1", "00000000000191"),
        ("2", "00973749000115"),
        ("3", "33000167000101"),
        ("4", ""),
        ("5", None),
    ]


@pytest.mark.parametrize(
    "valor", ["33.000.167/0001-01", "123456789012345", " 191", "19A"]
)
def test_b3_cnpj_invalido_falha(con, valor):
    gravar_bronze(con, "b3_empresas", [linha_b3(cnpj=valor)])
    with pytest.raises(t.ErroTransformacao) as erro:
        t.executar(con)
    assert erro.value.coluna == "cnpj"
    assert erro.value.exemplo == repr(valor)


def test_minhareceita_cnpj_completado_com_zeros_a_esquerda(con):
    dados = empresa("191")
    dados["regime_tributario"][0]["cnpj_da_scp"] = "26439940000"
    gravar_bronze(con, "minhareceita_empresas", [linha_minhareceita(dados)])
    t.executar(con)
    esperado = "00000000000191"
    assert consultar(con, "SELECT cnpj FROM refined.minhareceita_empresas") == [
        (esperado,)
    ]
    for tabela in ("qsa", "regime_tributario", "cnaes_secundarios"):
        assert consultar(
            con, f"SELECT DISTINCT cnpj FROM refined.minhareceita_{tabela}"
        ) == [(esperado,)]
    assert consultar(
        con,
        "SELECT cnpj_da_scp FROM refined.minhareceita_regime_tributario ORDER BY sequencia_regime",
    ) == [("00026439940000",), (None,)]


def test_minhareceita_cnpj_bronze_e_json_comparados_apos_padronizacao(con):
    # Mesmo CNPJ com e sem zeros à esquerda: não é divergência.
    gravar_bronze(
        con,
        "minhareceita_empresas",
        [linha_minhareceita(empresa("00000000000191"), cnpj="191")],
    )
    t.executar(con)
    assert consultar(con, "SELECT cnpj FROM refined.minhareceita_empresas") == [
        ("00000000000191",)
    ]
    tipos = dict(
        consultar(
            con,
            "SELECT column_name, data_type FROM duckdb_columns() WHERE table_name = 'b3_empresas' AND schema_name = 'refined'",
        )
    )
    assert (
        tipos["data_listagem"] == "DATE"
        and tipos["codigo_cvm"] == tipos["cnpj"] == "VARCHAR"
    )


@pytest.mark.parametrize("valor", ["31/02/2020", "2020-01-01", "", "1/1/2020"])
def test_b3_data_invalida_falha(con, valor):
    gravar_bronze(con, "b3_empresas", [linha_b3(dateListing=valor)])
    with pytest.raises(t.ErroTransformacao) as erro:
        t.executar(con)
    assert erro.value.coluna == "dateListing"
    assert erro.value.origem == "raw.b3_empresas"


# --------------------------------------------------------------------------- Fundamentus


def test_fundamentus_conversao_brasileira(con):
    gravar_bronze(
        con,
        "fundamentus_acoes",
        [
            linha_fundamentus(),
            linha_fundamentus(Papel="WXYZ4", Cotação="-0,5", PSR="0,00"),
        ],
    )
    t.executar(con)
    linha = consultar(
        con,
        "SELECT patrimonio_liquido, dividend_yield, margem_bruta, preco_vendas, divida_liquida_patrimonio, cotacao "
        "FROM refined.fundamentus_acoes WHERE ticker = 'ABCD3'",
    )[0]
    assert linha == (
        Decimal("1083050000.00"),
        Decimal("6.91"),  # sem divisão por 100
        Decimal("-208.15"),
        Decimal("3.423"),
        Decimal("0.10"),
        Decimal("0.00"),
    )
    assert consultar(
        con,
        "SELECT cotacao, preco_vendas FROM refined.fundamentus_acoes WHERE ticker = 'WXYZ4'",
    ) == [(Decimal("-0.50"), Decimal("0.000"))]


def test_fundamentus_precisao_dinamica_por_coluna(con):
    gravar_bronze(
        con,
        "fundamentus_acoes",
        [linha_fundamentus(), linha_fundamentus(Papel="WXYZ4", PSR="12,5")],
    )
    t.executar(con)
    tipos = dict(
        consultar(
            con,
            "SELECT column_name, data_type FROM duckdb_columns() WHERE schema_name = 'refined' AND table_name = 'fundamentus_acoes'",
        )
    )
    assert tipos["patrimonio_liquido"] == "DECIMAL(12,2)"
    assert (
        tipos["preco_vendas"] == "DECIMAL(5,3)"
    )  # 2 inteiros (12,5) + 3 decimais (3,423)
    assert tipos["cotacao"] == "DECIMAL(3,2)"


def test_fundamentus_precisao_acima_do_limite_falha(con):
    gigante = "1" + ".000" * 13 + ",00"  # 40 dígitos significativos
    gravar_bronze(con, "fundamentus_acoes", [linha_fundamentus(Cotação=gigante)])
    with pytest.raises(t.ErroTransformacao) as erro:
        t.executar(con)
    assert erro.value.etapa == "cálculo de precisão DECIMAL"
    assert erro.value.coluna == "Cotação"


@pytest.mark.parametrize("valor", ["abc", "1,2,3", "1.23,4", "12,5 %", "--", " 1,00"])
def test_fundamentus_valor_invalido_falha_sem_virar_nulo(con, valor):
    gravar_bronze(con, "fundamentus_acoes", [linha_fundamentus(ROE=valor)])
    with pytest.raises(t.ErroTransformacao) as erro:
        t.executar(con)
    assert erro.value.coluna == "ROE"
    assert erro.value.exemplo == repr(valor)


def test_fundamentus_limpeza_restrita_a_div_liq(con):
    # Tabulações/quebras externas só são removidas em Dív.Líq/ Patrim.
    gravar_bronze(
        con, "fundamentus_acoes", [linha_fundamentus(**{"P/L": "\n\t1,00\t"})]
    )
    with pytest.raises(t.ErroTransformacao) as erro:
        t.executar(con)
    assert erro.value.coluna == "P/L"
    # Espaços (não identificados na fonte) não são limpos nem em Dív.Líq/ Patrim.
    gravar_bronze(
        con,
        "fundamentus_acoes",
        [linha_fundamentus(**{"P/L": "1,00", "Dív.Líq/ Patrim.": "\n\t 0,10\t"})],
    )
    with pytest.raises(t.ErroTransformacao) as erro:
        t.executar(con)
    assert erro.value.coluna == "Dív.Líq/ Patrim."


def test_fundamentus_marcador_ausente_vira_nulo(con):
    gravar_bronze(
        con,
        "fundamentus_acoes",
        [linha_fundamentus(**{"Dív.Líq/ Patrim.": "\n\t\t\t\t-\t\t\t", "ROIC": "-"})],
    )
    t.executar(con)
    assert consultar(
        con,
        "SELECT divida_liquida_patrimonio, roic, roe FROM refined.fundamentus_acoes",
    ) == [(None, None, Decimal("0.00"))]


# --------------------------------------------------------------------------- yfinance


def test_yfinance_fuso_horario_e_nulos(con):
    gravar_bronze(
        con,
        "yfinance_cotacoes",
        [
            linha_yfinance(Date="2000-01-03 00:00:00-02:00", **{"Capital Gains": None}),
            linha_yfinance(
                Date="2026-10-29 00:00:00-03:00", **{"Capital Gains": "0.0"}
            ),
        ],
    )
    t.executar(con)
    linhas = consultar(
        con,
        "SELECT data AT TIME ZONE 'UTC', ganhos_capital, dividendos, volume FROM refined.yfinance_cotacoes ORDER BY data",
    )
    assert linhas == [
        (datetime(2000, 1, 3, 2, 0), None, 0.0, 100),
        (datetime(2026, 10, 29, 3, 0), 0.0, 0.0, 100),
    ]
    data = consultar(
        con, "SELECT data FROM refined.yfinance_cotacoes ORDER BY data LIMIT 1"
    )[0][0]
    assert data.astimezone(UTC) == datetime(2000, 1, 3, 2, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "coluna,valor", [("Date", "2026-10-29"), ("Volume", "1.5"), ("Open", "nan")]
)
def test_yfinance_valor_invalido_falha(con, coluna, valor):
    gravar_bronze(con, "yfinance_cotacoes", [linha_yfinance(**{coluna: valor})])
    with pytest.raises(t.ErroTransformacao) as erro:
        t.executar(con)
    assert erro.value.coluna == coluna


# --------------------------------------------------------------------------- duplicidades e chaves


def test_duplicatas_identicas_removidas_e_contabilizadas(con):
    gravar_bronze(
        con,
        "yfinance_cotacoes",
        [
            linha_yfinance(),
            linha_yfinance(),
            linha_yfinance(Date="2026-10-30 00:00:00-03:00"),
        ],
    )
    relatorio = t.executar(con)
    r = relatorio_de(relatorio, "yfinance_cotacoes")
    assert (r["origem"], r["antes_dedup"], r["duplicatas"], r["gravados"]) == (
        3,
        3,
        1,
        2,
    )


def test_chave_divergente_interrompe(con):
    gravar_bronze(
        con, "yfinance_cotacoes", [linha_yfinance(), linha_yfinance(Close="9.9")]
    )
    with pytest.raises(t.ErroTransformacao) as erro:
        t.executar(con)
    assert erro.value.etapa == "validação de chave"
    assert erro.value.coluna == "ticker, data"
    assert "9.9" in erro.value.exemplo and "1.5" in erro.value.exemplo


def test_chave_nula_interrompe(con):
    gravar_bronze(con, "b3_empresas", [linha_b3(codeCVM=None)])
    with pytest.raises(t.ErroTransformacao) as erro:
        t.executar(con)
    assert erro.value.etapa == "validação de chave"
    assert "nula" in erro.value.motivo


# --------------------------------------------------------------------------- Minha Receita


def test_minhareceita_extracao_dos_arrays(con):
    gravar_bronze(
        con,
        "minhareceita_empresas",
        [
            linha_minhareceita(empresa("11111111000111")),
            linha_minhareceita(
                empresa(
                    "22222222000122",
                    qsa=[],
                    regime_tributario=None,
                    cnaes_secundarios=[],
                )
            ),
        ],
    )
    relatorio = t.executar(con)

    assert consultar(
        con,
        "SELECT cnpj, sequencia_socio, nome_socio FROM refined.minhareceita_qsa ORDER BY ALL",
    ) == [
        ("11111111000111", 1, "ANA"),
        ("11111111000111", 2, "BRUNO"),
        ("11111111000111", 3, "CARLA"),
    ]
    assert consultar(
        con,
        "SELECT cnpj, sequencia_regime, ano, forma_de_tributacao FROM refined.minhareceita_regime_tributario ORDER BY ALL",
    ) == [
        ("11111111000111", 1, 2023, "LUCRO REAL"),
        ("11111111000111", 2, 2023, "LUCRO PRESUMIDO"),
    ]
    assert consultar(
        con,
        "SELECT cnpj, codigo_cnae, descricao, _source_origin FROM refined.minhareceita_cnaes_secundarios",
    ) == [
        (
            "11111111000111",
            3513100,
            "Transmissão",
            "https://minhareceita.org/11111111000111",
        )
    ]
    assert (
        relatorio_de(relatorio, "minhareceita_qsa")["origem"] == 3
    )  # arrays vazios/nulos não geram linhas

    empresas = consultar(
        con,
        "SELECT cnpj, email, pais, capital_social, opcao_pelo_mei, data_inicio_atividade FROM refined.minhareceita_empresas ORDER BY cnpj",
    )
    assert empresas[0] == (
        "11111111000111",
        None,
        None,
        Decimal("343504.72"),
        False,
        date(2021, 11, 10),
    )
    colunas = [
        c
        for (c,) in consultar(
            con,
            "SELECT column_name FROM duckdb_columns() WHERE schema_name = 'refined' AND table_name = 'minhareceita_empresas'",
        )
    ]
    assert colunas == list(t.ESCALARES_EMPRESA) + list(
        t.METADADOS
    )  # inclui propriedades sempre nulas; sem arrays nem payload_json


def test_minhareceita_qsa_preserva_ordem_original(con):
    nomes = ["ZECA", "ANA", "MARIA", "BETO"]
    gravar_bronze(
        con,
        "minhareceita_empresas",
        [linha_minhareceita(empresa("11111111000111", qsa=[socio(n) for n in nomes]))],
    )
    t.executar(con)
    assert [
        n
        for (n,) in consultar(
            con,
            "SELECT nome_socio FROM refined.minhareceita_qsa ORDER BY sequencia_socio",
        )
    ] == nomes


@pytest.mark.parametrize(
    "linha,motivo",
    [
        (
            linha_minhareceita(empresa("11111111000111"), cnpj="99999999000199"),
            "diverge",
        ),
        (
            linha_minhareceita(empresa("11.111.111/0001-11"), cnpj="11111111000111"),
            "somente dígitos",
        ),
        (
            linha_minhareceita(empresa("11111111000111"), cnpj="111111110001110"),
            "somente dígitos",
        ),
        (
            linha_minhareceita(empresa("11111111000111", propriedade_nova=1)),
            "não prevista",
        ),
        (
            linha_minhareceita(
                {k: v for k, v in empresa("11111111000111").items() if k != "email"}
            ),
            "ausente",
        ),
        (
            linha_minhareceita(empresa("11111111000111", capital_social="10,00")),
            "incompatível",
        ),
        (
            linha_minhareceita(
                empresa("11111111000111", data_inicio_atividade="10/11/2021")
            ),
            "data inválida",
        ),
        (
            linha_minhareceita(empresa("11111111000111", qsa={"nome_socio": "X"})),
            "esperado array",
        ),
        (linha_minhareceita(empresa("11111111000111", qsa=["X"])), "esperado objeto"),
        (
            linha_minhareceita(
                empresa("11111111000111", cnaes_secundarios=[{"codigo": 1}])
            ),
            "ausente",
        ),
    ],
)
def test_minhareceita_estrutura_incompativel_falha(con, linha, motivo):
    gravar_bronze(con, "minhareceita_empresas", [linha])
    with pytest.raises(t.ErroTransformacao) as erro:
        t.executar(con)
    assert erro.value.etapa == "validação estrutural JSON"
    assert motivo in erro.value.motivo


def test_minhareceita_json_invalido_falha(con):
    gravar_bronze(
        con,
        "minhareceita_empresas",
        [linha_minhareceita(empresa("11111111000111")) | {"payload_json": "{"}],
    )
    with pytest.raises(t.ErroTransformacao, match="JSON inválido"):
        t.executar(con)


# --------------------------------------------------------------------------- atomicidade, idempotência e Bronze


def test_rollback_quando_qualquer_tabela_falha(con):
    t.executar(con)
    antes = foto(con, "refined", TABELAS_SILVER)
    gravar_bronze(
        con,
        "yfinance_cotacoes",
        [linha_yfinance(Close="2.0"), linha_yfinance(Date="2026-10-30 00:00:00-03:00")],
    )
    gravar_bronze(con, "b3_empresas", [linha_b3(codeCVM="123")])
    preparadas = [
        t.preparar_tabela_sql(con, tab) for tab in t.TABELAS_SQL
    ] + t.preparar_minhareceita(con)
    falha = t.Preparada(
        "minhareceita_cnaes_secundarios", "temp.main.nao_existe", 0, 0, 0
    )
    with pytest.raises(t.ErroTransformacao) as erro:
        t.publicar(
            con, preparadas[:-1] + [falha]
        )  # a 7ª tabela falha depois de 6 substituídas
    assert erro.value.etapa == "publicação"
    assert foto(con, "refined", TABELAS_SILVER) == antes


def test_falha_de_validacao_preserva_versao_anterior(con):
    t.executar(con)
    antes = foto(con, "refined", TABELAS_SILVER)
    gravar_bronze(con, "b3_empresas", [linha_b3(codeCVM="777")])  # mudaria a B3...
    gravar_bronze(
        con,
        "minhareceita_empresas",
        [linha_minhareceita(empresa("11111111000111", uf=1))],
    )  # ...mas a última falha
    with pytest.raises(t.ErroTransformacao):
        t.executar(con)
    assert foto(con, "refined", TABELAS_SILVER) == antes


def test_idempotencia_em_duas_execucoes(con):
    primeiro = t.executar(con)
    foto1 = foto(con, "refined", TABELAS_SILVER)
    segundo = t.executar(con)
    assert foto(con, "refined", TABELAS_SILVER) == foto1
    assert primeiro == segundo
    tabelas = consultar(
        con,
        "SELECT table_name FROM duckdb_tables() WHERE schema_name = 'refined' ORDER BY 1",
    )
    assert [n for (n,) in tabelas] == sorted(TABELAS_SILVER)


def test_bronze_permanece_inalterada(con):
    antes = foto(con, "raw", t.TABELAS_BRONZE)
    t.executar(con)
    assert foto(con, "raw", t.TABELAS_BRONZE) == antes


def test_bronze_ausente_encerra_com_codigo_1(con, monkeypatch, capsys):
    con.execute("DROP TABLE raw.fundamentus_acoes")
    with pytest.raises(t.ErroTransformacao, match="pipeline.ingestao"):
        t.executar(con)

    class SemFechar:
        def __getattr__(self, nome):
            return getattr(con, nome)

        def close(self):
            pass

    monkeypatch.setattr(db, "conectar", lambda: SemFechar())
    with pytest.raises(SystemExit) as saida:
        t.main()
    assert saida.value.code == 1
    assert "raw.fundamentus_acoes" in capsys.readouterr().err
