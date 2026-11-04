"""Fundamentus — indicadores: raw.fundamentus_acoes -> refined.fundamentus_acoes (7.2)."""

from pipeline.transformacao.comum import NUMERO_BR, Coluna, TabelaSql

# Só as quebras de linha e tabulações externas observadas em Dív.Líq/ Patrim.
LIMPEZA_EXTREMIDADES = r"regexp_replace({v}, '^[\n\t]+|[\n\t]+$', '', 'g')"

TABELA = TabelaSql(
    "fundamentus_acoes",
    "fundamentus_acoes",
    (
        Coluna("Papel", "ticker"),
        Coluna("Cotação", "cotacao", NUMERO_BR),
        Coluna("P/L", "preco_lucro", NUMERO_BR),
        Coluna("P/VP", "preco_valor_patrimonial", NUMERO_BR),
        Coluna("PSR", "preco_vendas", NUMERO_BR),
        Coluna("Div.Yield", "dividend_yield", NUMERO_BR),
        Coluna("P/Ativo", "preco_ativo", NUMERO_BR),
        Coluna("P/Cap.Giro", "preco_capital_giro", NUMERO_BR),
        Coluna("P/EBIT", "preco_ebit", NUMERO_BR),
        Coluna("P/Ativ Circ.Liq", "preco_ativo_circulante_liquido", NUMERO_BR),
        Coluna("EV/EBIT", "enterprise_value_ebit", NUMERO_BR),
        Coluna("EV/EBITDA", "enterprise_value_ebitda", NUMERO_BR),
        Coluna("Mrg Bruta", "margem_bruta", NUMERO_BR),
        Coluna("Mrg Ebit", "margem_ebit", NUMERO_BR),
        Coluna("Mrg. Líq.", "margem_liquida", NUMERO_BR),
        Coluna("Liq. Corr.", "liquidez_corrente", NUMERO_BR),
        Coluna("ROIC", "roic", NUMERO_BR),
        Coluna("ROE", "roe", NUMERO_BR),
        Coluna("Liq.2meses", "liquidez_2_meses", NUMERO_BR),
        Coluna("Patrim. Líq", "patrimonio_liquido", NUMERO_BR),
        Coluna(
            "Dív.Líq/ Patrim.",
            "divida_liquida_patrimonio",
            NUMERO_BR,
            LIMPEZA_EXTREMIDADES,
        ),
        Coluna("Cresc. Rec.5a", "crescimento_receita_5_anos", NUMERO_BR),
        Coluna("_timestamp_ingestao", "_timestamp_ingestao"),
        Coluna("_source_origin", "_source_origin"),
    ),
    ("ticker",),
)
