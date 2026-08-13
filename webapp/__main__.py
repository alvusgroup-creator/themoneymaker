"""Sobe o servidor local e abre o navegador. Alvo do iniciar.bat."""

from __future__ import annotations

import os
import socket
import threading
import webbrowser

import uvicorn
from dotenv import load_dotenv

# O servidor só é importado pelo uvicorn lá embaixo, então o load_dotenv() que
# mora em prospector.config ainda não rodou: sem esta linha, PROSPECTADOR_PORTA
# no .env seria ignorada.
load_dotenv()

HOST = "127.0.0.1"
PORTA_PADRAO = 8765


def _porta_livre(inicial: int) -> int:
    for porta in range(inicial, inicial + 20):
        with socket.socket() as s:
            try:
                s.bind((HOST, porta))
                return porta
            except OSError:
                continue
    return inicial


def main() -> None:
    escolhida = os.getenv("PROSPECTADOR_PORTA")
    porta = int(escolhida) if escolhida else _porta_livre(PORTA_PADRAO)
    url = f"http://{HOST}:{porta}"

    threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    print(f"\n  Prospectador rodando em {url}")
    print("  Feche esta janela (ou Ctrl+C) para encerrar.\n")

    uvicorn.run("webapp.server:app", host=HOST, port=porta, log_level="warning")


if __name__ == "__main__":
    main()
