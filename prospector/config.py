"""Configuração carregada de .env + argumentos da linha de comando."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

MODELO_PADRAO = "llama3.1:8b"
OLLAMA_URL_PADRAO = "http://127.0.0.1:11434"
HISTORICO_PADRAO = "historico.json"


@dataclass
class Config:
    nicho: str
    local: str
    oferta: str
    max_leads: int = 100
    max_por_query: int = 60
    n_queries: int = 6
    headless: bool = True
    usar_ia: bool = True
    enriquecer: bool = True
    saida: str = "leads"
    filtro_site: str = "todos"
    # "todos" ou "so_br": mantém só quem parece falar com público brasileiro.
    filtro_brasileiro: str = "todos"
    # Base (quadro) que recebe os leads desta busca. A web manda o id; a CLI
    # manda o nome e `executar_e_exportar` resolve antes de rodar.
    base: str = ""
    # Histórico: `usar_historico` grava o resultado; `pular_conhecidos` faz a
    # coleta descartar empresas que já estão gravadas.
    usar_historico: bool = True
    pular_conhecidos: bool = False
    historico: str = os.getenv("PROSPECTADOR_HISTORICO", HISTORICO_PADRAO)
    modelo: str = os.getenv("PROSPECTADOR_MODELO", MODELO_PADRAO)
    ollama_url: str = os.getenv("OLLAMA_BASE_URL", OLLAMA_URL_PADRAO)
    ollama_timeout: float = float(os.getenv("PROSPECTADOR_OLLAMA_TIMEOUT", "120"))
    concorrencia: int = int(os.getenv("PROSPECTADOR_CONCORRENCIA", "8"))
    timeout_site: float = 12.0
