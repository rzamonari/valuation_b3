"""Testes do hook do MkDocs (docs/hooks.py): inclusão dos documentos da raiz e links."""

from types import SimpleNamespace

from docs import hooks


def pagina(src_uri):
    return SimpleNamespace(file=SimpleNamespace(src_uri=src_uri))


def test_link_para_documento_publicado_aponta_para_a_pagina():
    md = "Ver [Rankings](sql/marts/RANKINGS.md#2-rankings)."
    assert hooks.reescrever_links(md, "referencia/api.md", "doc_api.md") == (
        "Ver [Rankings](rankings.md#2-rankings)."
    )


def test_link_relativo_a_pasta_de_origem_e_resolvido():
    # em sql/marts/README.md, RANKINGS.md é irmão do arquivo
    md = "[r](RANKINGS.md) e [spec](../../docs/specs/marts_sql_rank.md)"
    assert hooks.reescrever_links(md, "referencia/marts.md", "sql/marts/README.md") == (
        "[r](rankings.md) e [spec](../specs/marts_sql_rank.md)"
    )


def test_link_para_arquivo_do_repositorio_vira_texto():
    md = "Código em [`pipeline/db.py`](pipeline/db.py) e [plano](plan.md)."
    assert hooks.reescrever_links(md, "referencia/api.md", "doc_api.md") == (
        "Código em `pipeline/db.py` e plano."
    )


def test_links_absolutos_ancoras_e_imagens_ficam_como_estao():
    md = "[uv](https://docs.astral.sh/uv/) [topo](#1-visao) ![img](a.png)"
    assert hooks.reescrever_links(md, "referencia/api.md", "doc_api.md") == md


def test_pagina_de_inclusao_recebe_o_conteudo_da_origem(tmp_path):
    (tmp_path / "doc_api.md").write_text(
        "# API\n\nVer [marts](sql/marts/README.md).\n", encoding="utf-8"
    )
    config = {"config_file_path": str(tmp_path / "mkdocs.yml")}
    resultado = hooks.on_page_markdown(
        "<!-- marcador -->", page=pagina("referencia/api.md"), config=config
    )
    assert resultado == "# API\n\nVer [marts](marts.md).\n"


def test_demais_paginas_nao_sao_alteradas():
    assert (
        hooks.on_page_markdown("[x](plan.md)", page=pagina("uso.md"), config={})
        == "[x](plan.md)"
    )
