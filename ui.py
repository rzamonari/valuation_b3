"""Abre o banco fundamentalistas.duckdb na interface oficial do DuckDB (DuckDB UI).

Execução: uv run python ui.py   (Ctrl+C para encerrar)
"""

import time

from pipeline import db


def main():
    con = db.conectar()
    try:
        con.execute("INSTALL ui")
        con.execute("LOAD ui")
        # start_ui() sobe o servidor local e abre o navegador em http://localhost:4213
        print(con.execute("CALL start_ui()").fetchall()[0][0])
        print("Banco aberto na DuckDB UI. Pressione Ctrl+C para encerrar.")
        print(
            "Encerre a UI antes de rodar a ingestão: o arquivo fica em uso enquanto ela está aberta."
        )
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        con.close()
        print("DuckDB UI encerrada.")


if __name__ == "__main__":
    main()
