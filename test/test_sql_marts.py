"""Testes das consultas reais de sql/marts/ sobre tabelas refined inventadas em tmp_path.

Cada tabela refined tem só as colunas que as consultas referenciam. O vínculo
Fundamentus → B3 é empresa_emissora = 4 primeiras letras do ticker (consulta-base).
"""

from pathlib import Path

import duckdb

from pipeline.materializacao import dependencias

PASTA_MARTS = Path(__file__).resolve().parent.parent / "sql" / "marts"

INDICADORES = [
    "cotacao",
    "liquidez_2_meses",
    "roic",
    "roe",
    "enterprise_value_ebit",
    "preco_lucro",
    "dividend_yield",
    "margem_ebit",
    "margem_liquida",
    "divida_liquida_patrimonio",
    "preco_valor_patrimonial",
    "crescimento_receita_5_anos",
    "patrimonio_liquido",
]


def novo_banco(tmp_path, acoes, emissoras, receita=()):
    """acoes: dicts por ticker (indicador ausente = NULL); emissoras: (codigo, cnpj);
    receita: (cnpj, atividade)."""
    con = duckdb.connect(str(tmp_path / "teste.duckdb"))
    con.execute("CREATE SCHEMA refined")
    colunas = ", ".join(f"{c} DECIMAL(12,2)" for c in INDICADORES)
    con.execute(f"CREATE TABLE refined.fundamentus_acoes (ticker VARCHAR, {colunas})")
    for acao in acoes:
        valores = [acao["ticker"]] + [acao.get(c) for c in INDICADORES]
        con.execute(
            "INSERT INTO refined.fundamentus_acoes VALUES "
            f"({', '.join('?' for _ in valores)})",
            valores,
        )
    con.execute(
        "CREATE TABLE refined.b3_empresas (empresa_emissora VARCHAR, cnpj VARCHAR, "
        "nome_pregao VARCHAR, razao_social VARCHAR, segmento VARCHAR, mercado VARCHAR, "
        "situacao VARCHAR)"
    )
    for codigo, cnpj in emissoras:
        con.execute(
            "INSERT INTO refined.b3_empresas VALUES (?, ?, ?, ?, 'Novo Mercado', 'Bovespa', "
            "'Ativo')",
            [codigo, cnpj, f"{codigo} SA", f"{codigo} S.A."],
        )
    con.execute(
        "CREATE TABLE refined.minhareceita_empresas (cnpj VARCHAR, cnae_fiscal_descricao VARCHAR, "
        "municipio VARCHAR, uf VARCHAR, natureza_juridica VARCHAR, data_inicio_atividade DATE)"
    )
    for cnpj, atividade in receita:
        con.execute(
            "INSERT INTO refined.minhareceita_empresas VALUES (?, ?, 'SAO PAULO', 'SP', "
            "'Sociedade Anônima Aberta', DATE '2000-01-01')",
            [cnpj, atividade],
        )
    return con


def _texto(nome):
    texto = (PASTA_MARTS / f"{nome}.sql").read_text(encoding="utf-8-sig").strip()
    return texto.removesuffix(";")


def _materializar_dependencias(con, nome):
    """Grava em marts.<dep> os marts que a consulta lê (ex.: marts_50 lê os rankings)."""
    con.execute("CREATE SCHEMA IF NOT EXISTS marts")
    for dep in sorted(dependencias(_texto(nome))):
        _materializar_dependencias(con, dep)
        con.execute(f"CREATE OR REPLACE TABLE marts.{dep} AS {_texto(dep)}")


def executar_mart(con, nome):
    _materializar_dependencias(con, nome)
    cursor = con.execute(_texto(nome))
    colunas = [d[0] for d in cursor.description]
    return [dict(zip(colunas, linha, strict=False)) for linha in cursor.fetchall()]


def por_ticker(linhas, coluna):
    return {linha["ticker"]: linha[coluna] for linha in linhas}


def emissoras_de(acoes):
    return [(a["ticker"][:4], f"{i:014d}") for i, a in enumerate(acoes, start=1)]


# --------------------------------------------------------------------------- marts_01_rank_valor


def test_rank_valor_deixa_fora_roic_ou_ev_ebit_nao_positivos(tmp_path):
    acoes = [
        {"ticker": "BOAS3", "roic": 20, "enterprise_value_ebit": 5},  # elegível
        {"ticker": "NEGA3", "roic": -1, "enterprise_value_ebit": 5},  # ROIC negativo
        {"ticker": "ZERO3", "roic": 0, "enterprise_value_ebit": 5},  # ROIC zero
        {"ticker": "NULO3", "roic": None, "enterprise_value_ebit": 5},  # ROIC ausente
        {
            "ticker": "EVNG3",
            "roic": 20,
            "enterprise_value_ebit": -2,
        },  # EV/EBIT negativo
    ]
    con = novo_banco(tmp_path, acoes, emissoras_de(acoes))
    assert [linha["ticker"] for linha in executar_mart(con, "marts_01_rank_valor")] == [
        "BOAS3"
    ]


def test_rank_valor_ordena_pela_soma_dos_ranks_de_roic_e_ev_ebit(tmp_path):
    acoes = [
        # rank_roic 1 + rank_ev_ebit 2 = 3
        {"ticker": "AAAA3", "roic": 30, "enterprise_value_ebit": 6},
        # rank_roic 2 + rank_ev_ebit 1 = 3 (empata com AAAA3)
        {"ticker": "BBBB3", "roic": 20, "enterprise_value_ebit": 4},
        # rank_roic 3 + rank_ev_ebit 3 = 6
        {"ticker": "CCCC3", "roic": 10, "enterprise_value_ebit": 9},
    ]
    con = novo_banco(tmp_path, acoes, emissoras_de(acoes))
    linhas = executar_mart(con, "marts_01_rank_valor")
    assert por_ticker(linhas, "soma_ranks") == {"AAAA3": 3, "BBBB3": 3, "CCCC3": 6}
    # DENSE_RANK: soma empatada recebe o mesmo rank e o próximo não pula número
    assert por_ticker(linhas, "rank") == {"AAAA3": 1, "BBBB3": 1, "CCCC3": 2}


def test_rank_valor_deixa_fora_ticker_sem_emissora_na_b3(tmp_path):
    acoes = [
        {
            "ticker": "COMB3",
            "roic": 20,
            "enterprise_value_ebit": 5,
        },  # emissora COMB cadastrada
        {
            "ticker": "SEMB3",
            "roic": 25,
            "enterprise_value_ebit": 4,
        },  # sem emissora: INNER JOIN
    ]
    con = novo_banco(tmp_path, acoes, [("COMB", "00000000000001")])
    assert [linha["ticker"] for linha in executar_mart(con, "marts_01_rank_valor")] == [
        "COMB3"
    ]


def test_rank_valor_mantem_ticker_sem_minha_receita_com_atividade_nula(tmp_path):
    acoes = [
        {
            "ticker": "COMR3",
            "roic": 20,
            "enterprise_value_ebit": 5,
        },  # tem Minha Receita
        {
            "ticker": "SEMR3",
            "roic": 15,
            "enterprise_value_ebit": 6,
        },  # CNPJ sem Minha Receita
    ]
    emissoras = [("COMR", "00000000000001"), ("SEMR", "00000000000002")]
    receita = [("00000000000001", "Fabricação de aço")]
    con = novo_banco(tmp_path, acoes, emissoras, receita)
    atividade = por_ticker(executar_mart(con, "marts_01_rank_valor"), "atividade")
    assert atividade == {"COMR3": "Fabricação de aço", "SEMR3": None}


# ---------------------------------------------------------------- marts_03_rank_eficiencia


def test_rank_eficiencia_deixa_fora_margem_nao_positiva(tmp_path):
    acoes = [
        {"ticker": "BOAS3", "margem_ebit": 30, "margem_liquida": 10},  # elegível
        {"ticker": "EBIT3", "margem_ebit": 0, "margem_liquida": 10},  # margem EBIT zero
        {
            "ticker": "LIQU3",
            "margem_ebit": 30,
            "margem_liquida": -1,
        },  # margem líquida negativa
        {
            "ticker": "NULO3",
            "margem_ebit": None,
            "margem_liquida": 10,
        },  # margem EBIT ausente
    ]
    con = novo_banco(tmp_path, acoes, emissoras_de(acoes))
    assert [
        linha["ticker"] for linha in executar_mart(con, "marts_03_rank_eficiencia")
    ] == ["BOAS3"]


def test_rank_eficiencia_desempata_margem_ebit_pela_margem_liquida(tmp_path):
    acoes = [
        {
            "ticker": "AAAA3",
            "margem_ebit": 30,
            "margem_liquida": 10,
        },  # mesma EBIT, líquida menor
        {
            "ticker": "BBBB3",
            "margem_ebit": 30,
            "margem_liquida": 20,
        },  # mesma EBIT, líquida maior
        {"ticker": "CCCC3", "margem_ebit": 40, "margem_liquida": 5},  # maior EBIT vence
    ]
    con = novo_banco(tmp_path, acoes, emissoras_de(acoes))
    linhas = executar_mart(con, "marts_03_rank_eficiencia")
    assert por_ticker(linhas, "rank") == {"CCCC3": 1, "BBBB3": 2, "AAAA3": 3}


# ------------------------------------------------------------- marts_50_rank_recomendacoes

# Elegível nos 10 rankings (02: DY > 0, P/L > 0, payout ≥ 0; 04 e 09: DL/PL ≤ 1,5;
# 06: P/VP > 0; 07: crescimento informado e ROIC > 10).
COMPLETA = {
    "liquidez_2_meses": 1000,
    "roic": 30,
    "roe": 25,
    "enterprise_value_ebit": 5,
    "preco_lucro": 10,
    "dividend_yield": 6,
    "margem_ebit": 30,
    "margem_liquida": 20,
    "divida_liquida_patrimonio": 0.5,
    "preco_valor_patrimonial": 2,
    "crescimento_receita_5_anos": 10,
}
# Não elegível em nenhum ranking: todos os indicadores negativos, zero ou acima do limite.
NENHUMA = {
    "liquidez_2_meses": 1000,
    "roic": -5,
    "roe": -2,
    "enterprise_value_ebit": -1,
    "preco_lucro": -3,
    "dividend_yield": 0,
    "margem_ebit": -1,
    "margem_liquida": -1,
    "divida_liquida_patrimonio": 3,
    "preco_valor_patrimonial": 0,
    "crescimento_receita_5_anos": None,
}


def test_saldo_positivo_e_compra_e_saldo_negativo_e_venda(tmp_path):
    acoes = [
        # única elegível em todos os rankings: 10 × Superior → saldo +10
        {"ticker": "BOAS3", **COMPLETA},
        # não elegível nos 10: saldo -10
        {"ticker": "RUIM3", **NENHUMA},
    ]
    con = novo_banco(tmp_path, acoes, emissoras_de(acoes))
    linhas = executar_mart(con, "marts_50_rank_recomendacoes")
    assert por_ticker(linhas, "saldo") == {"BOAS3": 10, "RUIM3": -10}
    assert por_ticker(linhas, "recomendacao") == {"BOAS3": "Compra", "RUIM3": "Venda"}
    assert por_ticker(linhas, "posicao") == {"BOAS3": 1, "RUIM3": 2}


def test_saldo_zero_e_manter(tmp_path):
    acoes = [
        # elegível nos 10; perde para MEIO3 em 5 rankings (Inferior) e é a única nos outros 5
        # (Superior): 5 - 5 = 0
        {"ticker": "BOAS3", **COMPLETA},
        # melhor que BOAS3 em Valor, Eficiência, Pechincha, Operacional e Rentabilidade
        # (Superior); sem DY, ROE, DL/PL e crescimento → não elegível nos outros 5: 5 - 5 = 0
        {
            "ticker": "MEIO3",
            "liquidez_2_meses": 1000,
            "roic": 40,
            "enterprise_value_ebit": 3,
            "preco_lucro": 5,
            "dividend_yield": 0,
            "margem_ebit": 50,
            "margem_liquida": 40,
            "preco_valor_patrimonial": 1,
        },
    ]
    con = novo_banco(tmp_path, acoes, emissoras_de(acoes))
    linhas = executar_mart(con, "marts_50_rank_recomendacoes")
    assert por_ticker(linhas, "qtd_superior") == {"BOAS3": 5, "MEIO3": 5}
    assert por_ticker(linhas, "qtd_inferior") == {"BOAS3": 5, "MEIO3": 0}
    assert por_ticker(linhas, "qtd_nao_elegivel") == {"BOAS3": 0, "MEIO3": 5}
    assert por_ticker(linhas, "recomendacao") == {"BOAS3": "Manter", "MEIO3": "Manter"}


def test_ticker_sem_liquidez_fica_fora_das_recomendacoes(tmp_path):
    acoes = [
        {"ticker": "BOAS3", **COMPLETA},  # negociada
        {
            "ticker": "PARA3",
            **COMPLETA,
            "liquidez_2_meses": 0,
        },  # sem negociação em 2 meses
        {"ticker": "NULA3", **COMPLETA, "liquidez_2_meses": None},  # liquidez ausente
    ]
    con = novo_banco(tmp_path, acoes, emissoras_de(acoes))
    tickers = [
        linha["ticker"] for linha in executar_mart(con, "marts_50_rank_recomendacoes")
    ]
    assert tickers == ["BOAS3"]


def test_recomendacao_usa_o_ranking_materializado(tmp_path):
    # marts_50 lê marts.marts_01_rank_valor em vez de repetir a regra: ticker ausente do
    # mart do ranking é não elegível naquele tema.
    acoes = [{"ticker": "BOAS3", **COMPLETA}, {"ticker": "OTIM3", **COMPLETA}]
    con = novo_banco(tmp_path, acoes, emissoras_de(acoes))
    antes = executar_mart(con, "marts_50_rank_recomendacoes")
    assert por_ticker(antes, "faixa_valor") == {
        "BOAS3": "Superior",
        "OTIM3": "Superior",
    }

    texto = _texto("marts_50_rank_recomendacoes")
    con.execute("DELETE FROM marts.marts_01_rank_valor WHERE ticker = 'OTIM3'")
    cursor = con.execute(texto)
    colunas = [d[0] for d in cursor.description]
    depois = [dict(zip(colunas, linha, strict=False)) for linha in cursor.fetchall()]
    assert por_ticker(depois, "faixa_valor") == {
        "BOAS3": "Superior",
        "OTIM3": "Não elegível",
    }
    assert por_ticker(depois, "qtd_nao_elegivel") == {"BOAS3": 0, "OTIM3": 1}


# --------------------------------------------------------------------------- cards × marts_50
# Cards e marts_painel_indicadores leem marts.marts_50_rank_recomendacoes: os números exibidos
# no painel precisam bater com a recomendação consolidada.

CARDS = {
    "marts_card_02_acoes_compra": "Compra",
    "marts_card_03_acoes_manter": "Manter",
    "marts_card_04_acoes_venda": "Venda",
}


def acoes_com_as_tres_recomendacoes():
    return [
        {"ticker": "BOAS3", **COMPLETA},
        {"ticker": "OTIM3", **COMPLETA, "roic": 35, "margem_ebit": 35},
        {
            "ticker": "MEIO3",
            "liquidez_2_meses": 1000,
            "roic": 40,
            "enterprise_value_ebit": 3,
            "preco_lucro": 5,
            "dividend_yield": 0,
            "margem_ebit": 50,
            "margem_liquida": 40,
            "preco_valor_patrimonial": 1,
        },
        {"ticker": "RUIM3", **NENHUMA},
        {"ticker": "PESS3", **NENHUMA, "roic": -9},
        {"ticker": "PARA3", **COMPLETA, "liquidez_2_meses": 0},  # fora do universo
    ]


def test_cards_contam_as_recomendacoes_de_marts_50(tmp_path):
    acoes = acoes_com_as_tres_recomendacoes()
    con = novo_banco(tmp_path, acoes, emissoras_de(acoes))
    recomendacoes = por_ticker(
        executar_mart(con, "marts_50_rank_recomendacoes"), "recomendacao"
    )
    assert set(recomendacoes.values()) == {"Compra", "Manter", "Venda"}

    analisadas = executar_mart(con, "marts_card_01_acoes_analisadas")
    assert analisadas == [{"quantidade": len(recomendacoes)}]
    for mart, recomendacao in CARDS.items():
        esperado = sum(1 for r in recomendacoes.values() if r == recomendacao)
        assert executar_mart(con, mart) == [{"quantidade": esperado}], mart


def test_termometro_usa_as_contagens_de_marts_50(tmp_path):
    acoes = acoes_com_as_tres_recomendacoes()
    con = novo_banco(tmp_path, acoes, emissoras_de(acoes))
    recomendacoes = por_ticker(
        executar_mart(con, "marts_50_rank_recomendacoes"), "recomendacao"
    )
    contagem = {
        r: sum(1 for v in recomendacoes.values() if v == r)
        for r in ("Compra", "Manter", "Venda")
    }
    [termometro] = executar_mart(con, "marts_card_05_termometro_mercado")
    assert termometro["total"] == len(recomendacoes)
    assert termometro["quantidade"] == max(contagem.values())


def test_termometro_empate_no_maximo_e_manter(tmp_path):
    # Uma Compra e uma Venda: empate no máximo -> Manter (P1). A subconsulta do ELSE devolve
    # as duas recomendações empatadas e não pode derrubar a consulta.
    acoes = [{"ticker": "BOAS3", **COMPLETA}, {"ticker": "RUIM3", **NENHUMA}]
    con = novo_banco(tmp_path, acoes, emissoras_de(acoes))
    [termometro] = executar_mart(con, "marts_card_05_termometro_mercado")
    assert termometro == {
        "recomendacao": "Manter",
        "quantidade": 1,
        "total": 2,
        "percentual": 50.0,
    }


def test_painel_indicadores_repete_a_recomendacao_de_marts_50(tmp_path):
    acoes = acoes_com_as_tres_recomendacoes()
    con = novo_banco(tmp_path, acoes, emissoras_de(acoes))
    marts_50 = executar_mart(con, "marts_50_rank_recomendacoes")
    painel = executar_mart(con, "marts_painel_indicadores")
    assert por_ticker(painel, "recomendacao") == por_ticker(marts_50, "recomendacao")
    assert por_ticker(painel, "saldo") == por_ticker(marts_50, "saldo")


# --------------------------------------------------------------- marts_exclusoes_universo


def acoes_excluidas():
    """Um ticker por motivo, todos sem emissora na B3, mais um ticker no universo."""
    return [
        {"ticker": "COMB3", "liquidez_2_meses": 100},  # emissora COMB cadastrada
        {"ticker": "FRAC3F", "liquidez_2_meses": 50},  # fracionário, mesmo negociado
        {"ticker": "BDRX34", "liquidez_2_meses": 10},  # BDR, mesmo negociado
        {"ticker": "UNIT11"},  # unit, liquidez ausente
        {"ticker": "PREG3", "liquidez_2_meses": 20, "cotacao": 5},  # negociado
        {"ticker": "PREG4", "liquidez_2_meses": 0},  # mesma emissora, sem negociação
        {"ticker": "VELH6", "liquidez_2_meses": 0},
        {"ticker": "RECB12", "liquidez_2_meses": 0},
    ]


def test_exclusoes_sao_o_complemento_do_universo_com_motivo_por_sufixo(tmp_path):
    con = novo_banco(tmp_path, acoes_excluidas(), [("COMB", "1")])
    linhas = executar_mart(con, "marts_exclusoes_universo")
    assert por_ticker(linhas, "motivo") == {
        "FRAC3F": "Fracionário",
        "BDRX34": "BDR",
        "UNIT11": "Unit",
        "PREG3": "Não identificado",
        "PREG4": "Deslistada ou cancelada",
        "VELH6": "Deslistada ou cancelada",
        "RECB12": "Outro código",
    }
    assert por_ticker(linhas, "emissora")["RECB12"] == "RECB"


def test_exclusoes_preservam_indicadores_e_explicam_a_negociacao(tmp_path):
    con = novo_banco(tmp_path, acoes_excluidas(), [("COMB", "1")])
    linhas = executar_mart(con, "marts_exclusoes_universo")
    assert por_ticker(linhas, "cotacao")["PREG3"] == 5
    assert por_ticker(linhas, "cotacao")["PREG4"] is None  # NULL não vira zero
    detalhe = por_ticker(linhas, "detalhe")
    assert detalhe["PREG3"].endswith("negociado nos últimos 2 meses")
    assert detalhe["PREG4"].endswith("sem negociação nos últimos 2 meses")
    assert "Emissora PREG ausente" in detalhe["PREG4"]


def test_sem_exclusao_quando_toda_emissora_esta_na_b3(tmp_path):
    acoes = [{"ticker": "COMB3"}, {"ticker": "COMB4"}]
    con = novo_banco(tmp_path, acoes, [("COMB", "1")])
    assert executar_mart(con, "marts_exclusoes_universo") == []


def test_contagem_por_motivo_lista_todas_as_categorias(tmp_path):
    con = novo_banco(tmp_path, acoes_excluidas(), [("COMB", "1")])
    linhas = executar_mart(con, "marts_painel_exclusoes_motivo")
    assert [linha["motivo"] for linha in linhas] == [
        "Fracionário",
        "BDR",
        "Unit",
        "Não identificado",
        "Deslistada ou cancelada",
        "Outro código",
    ]
    assert [linha["quantidade"] for linha in linhas] == [1, 1, 1, 1, 2, 1]
    assert [linha["quantidade_negociada"] for linha in linhas] == [1, 1, 0, 1, 0, 0]


def test_contagem_por_motivo_mostra_zero_sem_exclusoes(tmp_path):
    con = novo_banco(tmp_path, [{"ticker": "COMB3"}], [("COMB", "1")])
    linhas = executar_mart(con, "marts_painel_exclusoes_motivo")
    assert len(linhas) == 6
    assert {linha["quantidade"] for linha in linhas} == {0}


# ------------------------------------------------------------- marts_retorno_total_risco


def banco_cotacoes(tmp_path, cotacoes):
    """cotacoes: (ticker, data, fechamento, fechamento_ajustado, dividendos)."""
    con = duckdb.connect(str(tmp_path / "teste.duckdb"))
    con.execute("CREATE SCHEMA refined")
    con.execute(
        "CREATE TABLE refined.yfinance_cotacoes (ticker VARCHAR, data TIMESTAMPTZ, "
        "fechamento DOUBLE, fechamento_ajustado DOUBLE, dividendos DOUBLE)"
    )
    con.executemany(
        "INSERT INTO refined.yfinance_cotacoes VALUES (?, ?::TIMESTAMPTZ, ?, ?, ?)",
        cotacoes,
    )
    return con


def serie(ticker, *pontos):
    """pontos: (data, fechamento, fechamento_ajustado[, dividendos])."""
    return [(ticker, d, f, a, p[0] if p else 0.0) for d, f, a, *p in pontos]


def risco_por_ticker(con):
    return {
        linha["ticker"]: linha
        for linha in executar_mart(con, "marts_retorno_total_risco")
    }


def test_risco_calcula_serie_valida_sem_motivo(tmp_path):
    con = banco_cotacoes(
        tmp_path,
        serie(
            "BOAS3",
            ("2025-01-02", 100, 100),
            ("2025-06-02", 50, 50),
            ("2026-01-02", 80, 80, 5.0),
        ),
    )
    linha = risco_por_ticker(con)["BOAS3"]
    assert linha["motivo_sem_calculo"] is None
    assert linha["max_drawdown"] == -50
    assert linha["cagr"] < 0
    assert linha["volatilidade_anualizada"] > 0
    assert (linha["preco_inicial"], linha["preco_final"]) == (100, 80)


def test_risco_fica_sem_calculo_com_ajustado_negativo_na_janela(tmp_path):
    # provento de 12 com fechamento anterior 10: fator 1 - 12/10 < 0 inverte o passado
    con = banco_cotacoes(
        tmp_path,
        serie(
            "RUIM3",
            ("2025-01-02", 10, -2),
            ("2025-06-02", 10, -2),
            ("2025-06-03", 10, 10, 12.0),
            ("2026-01-02", 12, 12),
        ),
    )
    linha = risco_por_ticker(con)["RUIM3"]
    assert linha["motivo_sem_calculo"].startswith("Ajuste retroativo inválido")
    for coluna in (
        "cagr",
        "volatilidade_anualizada",
        "max_drawdown",
        "preco_inicial",
        "preco_final",
    ):
        assert linha[coluna] is None
    # rastreio da janela preservado: só os preços > 0 contam como válidos
    assert linha["qtd_precos_validos"] == 2
    assert str(linha["data_inicial"])[:10] == "2025-06-03"


def test_risco_fica_sem_calculo_com_provento_acima_do_preco_no_inicio_da_janela(
    tmp_path,
):
    # o pregão anterior (negativo) está fora da janela; o provento do 1º dia ainda conta
    con = banco_cotacoes(
        tmp_path,
        serie(
            "BORD3",
            ("2021-01-01", 10, -1),
            ("2021-01-04", 10, 5, 15.0),
            ("2026-01-04", 12, 6),
        ),
    )
    assert risco_por_ticker(con)["BORD3"]["motivo_sem_calculo"] is not None


def test_risco_ignora_defeito_anterior_a_janela(tmp_path):
    con = banco_cotacoes(
        tmp_path,
        serie(
            "ANTI3",
            ("2015-01-02", 10, -5),
            ("2015-01-05", 10, 4, 20.0),
            ("2025-01-02", 10, 10),
            ("2026-01-02", 11, 11),
        ),
    )
    linha = risco_por_ticker(con)["ANTI3"]
    assert linha["motivo_sem_calculo"] is None
    assert linha["cagr"] is not None


def test_risco_calcula_com_provento_grande_abaixo_do_fechamento_anterior(tmp_path):
    con = banco_cotacoes(
        tmp_path,
        serie(
            "GRAN3",
            ("2025-01-02", 10, 1),
            ("2025-01-03", 1, 1, 9.0),
            ("2026-01-02", 2, 2),
        ),
    )
    linha = risco_por_ticker(con)["GRAN3"]
    assert linha["motivo_sem_calculo"] is None
    assert linha["max_drawdown"] == 0


def test_risco_sem_calculo_nao_contamina_outro_ticker(tmp_path):
    con = banco_cotacoes(
        tmp_path,
        serie("RUIM3", ("2025-01-02", 10, -2), ("2025-01-03", 10, 10, 12.0))
        + serie("BOAS3", ("2025-01-02", 10, 10), ("2025-01-03", 11, 11)),
    )
    linhas = risco_por_ticker(con)
    assert linhas["RUIM3"]["cagr"] is None
    assert linhas["BOAS3"]["cagr"] is not None
    assert linhas["BOAS3"]["motivo_sem_calculo"] is None
