"""Orquestracao das etapas: planejar, coletar, enriquecer e qualificar.

Nada aqui escreve no terminal: o progresso sai como eventos para o `sink`. A CLI
liga um `SinkConsole`; a interface web liga um sink que empurra para o navegador.
"""

from __future__ import annotations

from typing import Callable

from . import brasileiros, enrich, maps_scraper
from .ai import AgenteIA
from .config import Config
from .eventos import Evento, Sink, SinkConsole, sink_nulo
from .exporter import exportar
from .historico import Historico
from .models import Lead
from .sites import PROPRIO, SOCIAL, tipo_de_site


class Cancelado(Exception):
    """A interface pediu para parar no meio da execução."""


def executar(
    cfg: Config,
    sink: Sink = sink_nulo,
    deve_parar: Callable[[], bool] | None = None,
    historico: Historico | None = None,
) -> list[Lead]:
    """Roda o pipeline inteiro.

    Cancelar não joga fora trabalho: as etapas seguintes são puladas, mas o que
    já foi coletado é gravado no histórico e devolvido normalmente.
    """
    leads: list[Lead] = []
    try:
        leads = _etapas(cfg, sink, deve_parar, historico)
    except Cancelado:
        sink(Evento("aviso", texto="Busca interrompida - guardando o que ja foi coletado."))

    if historico is not None and leads:
        novos = historico.registrar(
            leads, {"nicho": cfg.nicho, "local": cfg.local, "base": cfg.base}
        )
        sink(
            Evento(
                "log",
                texto=f"Historico atualizado: {novos} empresas ineditas de {len(leads)}.",
            )
        )
    return leads


def _etapas(
    cfg: Config,
    sink: Sink,
    deve_parar: Callable[[], bool] | None,
    historico: Historico | None,
) -> list[Lead]:
    def parar() -> bool:
        return bool(deve_parar and deve_parar())

    def checar_cancelamento() -> None:
        if parar():
            raise Cancelado()

    ia = AgenteIA(cfg, sink=sink)

    if cfg.usar_ia:
        if ia.ativo:
            sink(Evento("resumo", texto=f"IA local ligada via Ollama: {cfg.modelo}"))
        else:
            detalhe = f" {ia.erro_local}" if ia.erro_local else ""
            sink(
                Evento(
                    "aviso",
                    texto=(
                        "Ollama local indisponivel - usando buscas, score e "
                        f"mensagens por regras locais.{detalhe}"
                    ),
                )
            )

    ignorar: set[str] = set()
    if historico is not None and cfg.pular_conhecidos:
        ignorar = historico.chaves()
        if ignorar:
            sink(
                Evento(
                    "log",
                    texto=f"{len(ignorar)} empresas do historico serao ignoradas.",
                )
            )

    # 1. Planejar as buscas
    checar_cancelamento()
    sink(Evento("etapa", etapa=1, texto="Planejando as buscas"))
    queries = ia.gerar_queries()
    for q in queries:
        sink(Evento("log", etapa=1, texto=f"- {q}"))

    # 2. Coletar no Google Maps
    checar_cancelamento()
    if cfg.filtro_site == "sem":
        sink(Evento("log", etapa=2, texto="Filtro: só empresas sem site proprio."))
    elif cfg.filtro_site == "com":
        sink(Evento("log", etapa=2, texto="Filtro: só empresas com site proprio."))

    lusofona = brasileiros.regiao_lusofona(cfg.local)
    marcando_br = brasileiros.ativo(cfg.filtro_brasileiro)
    if marcando_br:
        sink(
            Evento(
                "log",
                etapa=2,
                texto=(
                    "Filtro: só quem parece publico brasileiro."
                    if cfg.filtro_brasileiro == "so_br"
                    else "Marcando quem parece publico brasileiro."
                ),
            )
        )
        if lusofona:
            sink(
                Evento(
                    "aviso",
                    etapa=2,
                    texto=(
                        "Regiao de lingua portuguesa: nome e site em portugues nao "
                        "distinguem ninguem aqui, entao so contam 'brasileiro' na "
                        "categoria/nome e telefone +55."
                    ),
                )
            )
    sink(
        Evento(
            "etapa",
            etapa=2,
            texto="Coletando no Google Maps",
            total=cfg.max_leads,
            dados={"descricao": "leads encontrados"},
        )
    )
    # O filtro de site vai junto: descartar depois da coleta desperdiçava a cota
    # de `max_leads` com empresas que nunca entrariam na lista.
    leads = maps_scraper.buscar(
        queries,
        max_por_query=cfg.max_por_query,
        max_total=cfg.max_leads,
        headless=cfg.headless,
        sink=sink,
        ignorar_chaves=ignorar,
        deve_parar=deve_parar,
        filtro_site=cfg.filtro_site,
        filtro_brasileiro=cfg.filtro_brasileiro,
        lusofona=lusofona,
    )
    sink(Evento("resumo", texto=f"{len(leads)} empresas unicas encontradas."))
    if not leads:
        if cfg.filtro_site != "todos" or cfg.filtro_brasileiro != "todos":
            sink(
                Evento(
                    "aviso",
                    texto=(
                        "Nenhuma empresa passou nos filtros. Aumente as buscas "
                        "ou as fichas por busca, ou tente uma regiao mais especifica."
                    ),
                )
            )
        return leads

    proprios = sum(1 for l in leads if tipo_de_site(l.site) == PROPRIO)
    sociais = sum(1 for l in leads if tipo_de_site(l.site) == SOCIAL)
    sink(
        Evento(
            "resumo",
            texto=(
                f"{proprios} com site proprio | {sociais} so com rede social | "
                f"{len(leads) - proprios - sociais} sem nada na web"
            ),
        )
    )
    if parar():
        return leads

    # 3. Enriquecer com os dados do site
    com_site = sum(1 for l in leads if l.site)
    if cfg.enriquecer and com_site and not parar():
        sink(
            Evento(
                "etapa",
                etapa=3,
                texto="Buscando e-mails e redes sociais",
                total=com_site,
                dados={"descricao": "sites visitados"},
            )
        )
        feitos = 0

        def avancar_site(n: int) -> None:
            nonlocal feitos
            feitos += n
            sink(Evento("progresso", etapa=3, atual=feitos, total=com_site))

        enrich.enriquecer(
            leads,
            concorrencia=cfg.concorrencia,
            timeout=cfg.timeout_site,
            on_progress=avancar_site,
            deve_parar=deve_parar,
        )
        sink(
            Evento(
                "resumo",
                texto=(
                    f"{sum(1 for l in leads if l.emails)} com e-mail | "
                    f"{sum(1 for l in leads if l.whatsapp)} com WhatsApp | "
                    f"{sum(1 for l in leads if l.instagram)} com Instagram"
                ),
            )
        )
        # O idioma do site só existe agora: vale reavaliar o palpite de público.
        if marcando_br:
            for lead in leads:
                brasileiros.avaliar(lead, lusofona=lusofona)
    else:
        motivo = "Enriquecimento desativado" if not cfg.enriquecer else "Nenhum site para visitar"
        sink(Evento("etapa", etapa=3, texto=motivo, dados={"desativada": True}))

    if marcando_br:
        parecem = sum(1 for l in leads if brasileiros.parece_brasileiro(l))
        sink(
            Evento(
                "resumo",
                texto=f"{parecem} de {len(leads)} parecem falar com publico brasileiro.",
            )
        )

    # 4. Qualificar e escrever a abordagem
    if cfg.usar_ia and not parar():
        sink(
            Evento(
                "etapa",
                etapa=4,
                texto=f"Qualificando os leads ({ia.modo})",
                total=len(leads),
                dados={"descricao": "leads analisados"},
            )
        )
        analisados = 0

        def avancar_lead(n: int) -> None:
            nonlocal analisados
            analisados += n
            sink(Evento("progresso", etapa=4, atual=analisados, total=len(leads)))

        ia.qualificar(leads, on_progress=avancar_lead, deve_parar=deve_parar)
        pontuados = [l for l in leads if l.score is not None]
        if pontuados:
            media = sum(l.score for l in pontuados) / len(pontuados)
            quentes = sum(1 for l in pontuados if l.score >= 70)
            sink(
                Evento(
                    "resumo",
                    texto=f"Score medio {media:.0f} | {quentes} leads acima de 70.",
                )
            )
    else:
        sink(
            Evento(
                "etapa", etapa=4, texto="Qualificacao desativada", dados={"desativada": True}
            )
        )

    return leads


def executar_e_exportar(cfg: Config, sink: Sink | None = None) -> list[Lead]:
    sink = sink or SinkConsole()
    historico = Historico(cfg.historico) if cfg.usar_historico else None

    # Na CLI `--base` vem como nome; aqui vira o id que o histórico entende.
    if historico is not None and cfg.base:
        base = historico.base_por_nome(cfg.base) or historico.criar_base(cfg.base)
        sink(Evento("log", texto=f"Base: {base['nome']}"))
        cfg.base = base["id"]

    leads = executar(cfg, sink=sink, historico=historico)
    if not leads:
        sink(Evento("erro", texto="Nenhum lead encontrado. Tente outro nicho ou regiao."))
        return []

    csv_path, xlsx_path = exportar(leads, cfg.saida)
    sink(
        Evento(
            "fim",
            texto="Pronto",
            dados={
                "arquivos": {
                    "CSV": str(csv_path.resolve()),
                    "Excel": str(xlsx_path.resolve()),
                }
            },
        )
    )
    return leads
