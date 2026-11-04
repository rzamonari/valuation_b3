"""B3 — empresas listadas: mapeamento raw.b3_empresas -> refined.b3_empresas.

Convertida pelo motor genérico de tabelas SQL (comum.preparar_tabela_sql).
"""

from pipeline.transformacao.comum import CNPJ, DATA_BR, Coluna, TabelaSql

TABELA = TabelaSql(
    "b3_empresas",
    "b3_empresas",
    (
        Coluna("codeCVM", "codigo_cvm"),
        Coluna("issuingCompany", "empresa_emissora"),
        Coluna("companyName", "razao_social"),
        Coluna("tradingName", "nome_pregao"),
        Coluna("cnpj", "cnpj", CNPJ),
        Coluna("marketIndicator", "indicador_mercado"),
        Coluna("typeBDR", "tipo_bdr"),
        Coluna("dateListing", "data_listagem", DATA_BR),
        Coluna("status", "situacao"),
        Coluna("segment", "segmento"),
        Coluna("segmentEng", "segmento_ingles"),
        Coluna("type", "tipo_empresa"),
        Coluna("market", "mercado"),
        Coluna("_timestamp_ingestao", "_timestamp_ingestao"),
        Coluna("_source_origin", "_source_origin"),
    ),
    ("codigo_cvm",),
)
