"""Agente local de prospeccao - CLI.

Exemplo:
    python run.py --nicho "clinicas de estetica" --local "Belo Horizonte, MG" \
                  --oferta "gestao de trafego pago e agendamento por WhatsApp" --max 80
"""

from __future__ import annotations

import argparse
import sys

from prospector.config import Config
from prospector.pipeline import executar_e_exportar


def parse_args() -> Config:
    p = argparse.ArgumentParser(
        prog="prospectador",
        description="Pesquisa um nicho no Google Maps e monta uma lista de contatos.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--nicho", required=True, help='Ex.: "clinicas de estetica"')
    p.add_argument("--local", required=True, help='Ex.: "Belo Horizonte, MG"')
    p.add_argument(
        "--oferta",
        default="servicos de marketing digital para pequenas e medias empresas",
        help="O que voce vende. A IA local usa isso para pontuar e escrever a abordagem.",
    )
    p.add_argument(
        "--max",
        type=int,
        default=100,
        dest="max_leads",
        help="Total maximo de leads na lista final.",
    )
    p.add_argument(
        "--max-por-busca",
        type=int,
        default=60,
        dest="max_por_query",
        help="Maximo de resultados por busca individual.",
    )
    p.add_argument(
        "--buscas",
        type=int,
        default=6,
        dest="n_queries",
        help="Quantas buscas a IA local ou as regras devem gerar.",
    )
    p.add_argument(
        "--saida",
        default="leads",
        help="Nome base dos arquivos (gera .csv e .xlsx).",
    )
    p.add_argument(
        "--base",
        default="",
        help=(
            'Quadro que recebe os leads, pelo nome (ex.: "Flooring em North Carolina"). '
            "Cria se ainda nao existir. Sem isso os leads ficam so no Geral."
        ),
    )
    p.add_argument(
        "--ver-navegador",
        action="store_true",
        help="Mostra o Chromium durante a coleta (util para depurar).",
    )
    p.add_argument(
        "--sem-ia",
        action="store_true",
        help="Desliga a qualificacao: so o scraper.",
    )
    p.add_argument(
        "--sem-enriquecimento",
        action="store_true",
        help="Nao visita os sites das empresas (bem mais rapido).",
    )
    p.add_argument(
        "--so-ineditos",
        action="store_true",
        help="Ignora empresas que ja estao no historico de buscas anteriores.",
    )
    p.add_argument(
        "--sem-historico",
        action="store_true",
        help="Nao grava o resultado no historico.json.",
    )
    grupo_br = p.add_mutually_exclusive_group()
    grupo_br.add_argument(
        "--marcar-brasileiros",
        action="store_true",
        help=(
            "Anota quais leads parecem falar com o publico brasileiro e coloca "
            "esses primeiro, sem descartar ninguem. Use fora do Brasil."
        ),
    )
    grupo_br.add_argument(
        "--so-brasileiros",
        action="store_true",
        help=(
            "Coleta so quem parece falar com o publico brasileiro (categoria do "
            "Maps, nome em portugues, telefone +55, site em portugues) e busca "
            "com os termos que trazem essas empresas. Nao identifica o dono: acha "
            "negocio voltado a comunidade brasileira."
        ),
    )
    grupo_site = p.add_mutually_exclusive_group()
    grupo_site.add_argument(
        "--com-site",
        action="store_true",
        help="Coleta somente empresas com site proprio no Google Maps.",
    )
    grupo_site.add_argument(
        "--sem-site",
        action="store_true",
        help=(
            "Coleta somente empresas sem site proprio. Quem cadastrou so uma rede "
            "social conta como sem site. A busca continua ate juntar --max leads "
            "que passem no filtro."
        ),
    )

    a = p.parse_args()
    filtro_site = "todos"
    if a.com_site:
        filtro_site = "com"
    elif a.sem_site:
        filtro_site = "sem"

    filtro_brasileiro = "todos"
    if a.so_brasileiros:
        filtro_brasileiro = "so_br"
    elif a.marcar_brasileiros:
        filtro_brasileiro = "marcar"

    return Config(
        nicho=a.nicho,
        local=a.local,
        oferta=a.oferta,
        max_leads=a.max_leads,
        max_por_query=a.max_por_query,
        n_queries=a.n_queries,
        headless=not a.ver_navegador,
        usar_ia=not a.sem_ia,
        enriquecer=not a.sem_enriquecimento,
        saida=a.saida,
        filtro_site=filtro_site,
        filtro_brasileiro=filtro_brasileiro,
        base=a.base,
        usar_historico=not a.sem_historico,
        pular_conhecidos=a.so_ineditos,
    )


def main() -> int:
    cfg = parse_args()
    try:
        executar_e_exportar(cfg)
    except KeyboardInterrupt:
        print("\nInterrompido pelo usuario.")
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
