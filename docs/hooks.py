"""Hook do MkDocs: publica documentos da raiz do repositório sem copiá-los para docs/.

As páginas de INCLUSOES existem em docs/ só como marcador; o conteúdo vem do arquivo
de origem (fonte única). Os links desses arquivos são relativos à raiz do repositório,
então são reescritos:
- documento publicado → link para a página correspondente;
- qualquer outro arquivo do repositório (código, plan.md...) → só o texto, pois o
  site não publica o código.
Links absolutos (http, mailto) e âncoras ficam como estão.
"""

import posixpath
import re
from pathlib import Path

# página em docs/ → arquivo de origem na raiz do repositório
INCLUSOES = {
    "referencia/api.md": "doc_api.md",
    "referencia/marts.md": "sql/marts/README.md",
    "referencia/rankings.md": "sql/marts/RANKINGS.md",
}
PUBLICADOS = {origem: pagina for pagina, origem in INCLUSOES.items()}

LINK = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)\s]+)\)")


def reescrever_links(markdown, pagina, origem):
    """Reescreve os links de `origem` (relativos a ela) para valerem em `pagina`."""
    pasta_origem = posixpath.dirname(origem)
    pasta_pagina = posixpath.dirname(pagina) or "."

    def trocar(m):
        texto, destino = m[1], m[2]
        if re.match(r"[a-z][a-z0-9+.-]*:", destino) or destino.startswith("#"):
            return m[0]
        caminho, _, ancora = destino.partition("#")
        caminho = posixpath.normpath(posixpath.join(pasta_origem, caminho))
        publicado = PUBLICADOS.get(caminho)
        if publicado is None and caminho.startswith("docs/"):
            publicado = caminho.removeprefix("docs/")
        if publicado is None:
            return texto
        relativo = posixpath.relpath(publicado, pasta_pagina)
        return f"[{texto}]({relativo}{'#' + ancora if ancora else ''})"

    return LINK.sub(trocar, markdown)


def on_page_markdown(markdown, page, config, **kwargs):
    origem = INCLUSOES.get(page.file.src_uri)
    if origem is None:
        return markdown
    raiz = Path(config["config_file_path"]).parent
    conteudo = (raiz / origem).read_text(encoding="utf-8-sig")
    return reescrever_links(conteudo, page.file.src_uri, origem)
