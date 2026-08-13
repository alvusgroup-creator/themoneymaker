"""Coleta de estabelecimentos no Google Maps via navegador (Playwright)."""

from __future__ import annotations

import random
import re
import time
from urllib.parse import quote_plus

from playwright.sync_api import Page, TimeoutError as PWTimeout, sync_playwright

from . import brasileiros
from .eventos import Evento, Sink, sink_nulo
from .models import Lead
from .sites import passa_no_filtro
from .utils import formatar_telefone

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

FEED = 'div[role="feed"]'
CARD_LINK = "a.hfpxzc"

# O bloco de informações (endereço, telefone, site) monta depois do h1. Ler o
# site antes disso devolve vazio e transforma uma empresa com site em "sem
# site" — justamente o erro que o filtro não pode cometer.
INFO_PRONTA = "[data-item-id]"

# `authority` é o link de site do Maps; os outros são a mesma âncora vista por
# atributos que o Google costuma manter quando renomeia a classe.
SELETORES_SITE = (
    'a[data-item-id="authority"]',
    'a[data-tooltip="Abrir website"]',
    'a[data-tooltip="Open website"]',
    'a[aria-label^="Website:"]',
    'a[aria-label^="Site:"]',
)

RE_NOTA = re.compile(r"(\d+[.,]\d+)")
RE_REVIEWS = re.compile(r"\(([\d.\s]+)\)")

# Identificador do lugar dentro da URL do Maps (`!1s0x89ac...:0xe2a3...`). É o
# que permite reconhecer o mesmo estabelecimento vindo de buscas diferentes sem
# precisar abrir a ficha de novo.
RE_ID_LOCAL = re.compile(r"!1s(0x[0-9a-f]+:0x[0-9a-f]+)", re.I)


def _identidade(href: str) -> str:
    m = RE_ID_LOCAL.search(href)
    return m.group(1) if m else href


def _pausa(a: float = 0.6, b: float = 1.4) -> None:
    time.sleep(random.uniform(a, b))


def _aceitar_consentimento(page: Page) -> None:
    """A UE/BR às vezes mostra a tela de consentimento antes do Maps."""
    for texto in ("Aceitar tudo", "Accept all", "Concordo", "Aceito"):
        try:
            botao = page.get_by_role("button", name=texto)
            if botao.count() and botao.first.is_visible():
                botao.first.click()
                page.wait_for_load_state("domcontentloaded")
                _pausa()
                return
        except Exception:  # noqa: BLE001
            continue


def _coletar_links(
    page: Page, limite: int, log=print, ja_abertos: set[str] | None = None
) -> list[str]:
    """Rola o painel de resultados até juntar `limite` lugares ainda não abertos.

    Buscas do mesmo nicho se sobrepõem bastante, então `ja_abertos` evita gastar
    uma ficha para reabrir quem já passou por aqui. O critério de parada continua
    olhando o feed inteiro: uma rodada que só traz repetidos ainda é crescimento
    da lista, e desistir ali cortaria resultados novos que vêm logo abaixo.
    """
    try:
        page.wait_for_selector(FEED, timeout=20_000)
    except PWTimeout:
        log("    painel de resultados não carregou (busca sem resultados?)")
        return []

    ja_abertos = ja_abertos or set()
    todos: set[str] = set()
    novos: dict[str, str] = {}
    sem_crescimento = 0

    while len(novos) < limite and sem_crescimento < 4:
        hrefs = page.eval_on_selector_all(
            CARD_LINK, "els => els.map(e => e.href).filter(Boolean)"
        )
        antes = len(todos)
        for h in hrefs:
            todos.add(h)
            ident = _identidade(h)
            if ident not in ja_abertos and ident not in novos:
                novos[ident] = h

        sem_crescimento = sem_crescimento + 1 if len(todos) == antes else 0

        repetidos = sum(1 for h in todos if _identidade(h) in ja_abertos)
        extra = f" ({repetidos} já vistos em outra busca)" if repetidos else ""
        log(f"    {len(todos)} resultados carregados{extra}...")
        page.eval_on_selector(FEED, "el => el.scrollTo(0, el.scrollHeight)")
        _pausa(1.0, 1.8)

    return list(novos.values())[:limite]


def _texto(page: Page, seletor: str) -> str:
    try:
        el = page.query_selector(seletor)
        return (el.inner_text().strip() if el else "") or ""
    except Exception:  # noqa: BLE001
        return ""


def _atributo(page: Page, seletor: str, attr: str) -> str:
    try:
        el = page.query_selector(seletor)
        return (el.get_attribute(attr) or "").strip() if el else ""
    except Exception:  # noqa: BLE001
        return ""


def _sem_prefixo(valor: str) -> str:
    """aria-label vem como 'Endereço: Rua X, 123' — corta o rótulo."""
    return valor.split(": ", 1)[1].strip() if ": " in valor else valor.strip()


def _extrair_site(page: Page) -> str:
    """Site da ficha, tentando os seletores em ordem de confiabilidade.

    Devolver "" aqui significa "esta empresa não tem site" para o resto do
    programa, então vale gastar alguns seletores extras antes de desistir.
    """
    for seletor in SELETORES_SITE:
        href = _atributo(page, seletor, "href")
        if href.startswith(("http://", "https://")):
            return href
    return ""


def _extrair_ficha(page: Page, url: str, query: str) -> Lead | None:
    nome = _texto(page, "h1.DUwDvf") or _texto(page, "h1")
    if not nome:
        return None

    bloco_nota = _texto(page, "div.F7nice")
    nota = None
    avaliacoes = None
    if bloco_nota:
        m = RE_NOTA.search(bloco_nota)
        if m:
            nota = float(m.group(1).replace(",", "."))
        m = RE_REVIEWS.search(bloco_nota)
        if m:
            digitos = re.sub(r"\D", "", m.group(1))
            avaliacoes = int(digitos) if digitos else None

    telefone = ""
    item_tel = _atributo(page, 'button[data-item-id^="phone:tel:"]', "data-item-id")
    if item_tel.startswith("phone:tel:"):
        telefone = formatar_telefone(item_tel.replace("phone:tel:", ""))

    endereco = _sem_prefixo(
        _atributo(page, 'button[data-item-id="address"]', "aria-label")
    )
    site = _extrair_site(page)
    categoria = _texto(page, 'button[jsaction*="category"]')

    return Lead(
        nome=nome,
        categoria=categoria,
        endereco=endereco,
        telefone=telefone,
        site=site,
        nota=nota,
        avaliacoes=avaliacoes,
        maps_url=url,
        query_origem=query,
    )


def buscar(
    queries: list[str],
    max_por_query: int,
    max_total: int,
    headless: bool = True,
    sink: Sink = sink_nulo,
    ignorar_chaves: set[str] | None = None,
    deve_parar=None,
    filtro_site: str = "todos",
    filtro_brasileiro: str = "todos",
    lusofona: bool = False,
) -> list[Lead]:
    """Executa as buscas no Google Maps e devolve os leads deduplicados.

    `ignorar_chaves`, `filtro_site` e `filtro_brasileiro` descartam empresas logo
    após abrir a ficha, antes de contarem para `max_total` — a busca continua
    abrindo fichas e trocando de query até juntar o total pedido de leads que
    servem. Filtrar depois da coleta é o que fazia uma busca de 60 leads terminar
    com 2 em nicho onde quase todo mundo tem site. `deve_parar` é consultado
    entre fichas para permitir cancelamento pela interface.
    """
    leads: dict[str, Lead] = {}
    conhecidas = ignorar_chaves or set()
    ja_abertos: set[str] = set()  # lugares já visitados, entre queries
    repetidos = 0
    fora_do_site = 0
    fora_do_publico = 0
    abertas = 0
    filtrando = filtro_site != "todos" or filtro_brasileiro != "todos"

    def log(texto: str) -> None:
        sink(Evento("log", texto=texto.strip(), etapa=2))

    def parar() -> bool:
        return bool(deve_parar and deve_parar())

    with sync_playwright() as p:
        navegador = p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled", "--lang=pt-BR"],
        )
        contexto = navegador.new_context(
            user_agent=UA,
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            viewport={"width": 1440, "height": 900},
        )
        page = contexto.new_page()

        try:
            for i, query in enumerate(queries, 1):
                if len(leads) >= max_total or parar():
                    break

                log(f"[{i}/{len(queries)}] Buscando: {query}")
                url = f"https://www.google.com/maps/search/{quote_plus(query)}?hl=pt-BR"
                page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                _aceitar_consentimento(page)
                _pausa(1.5, 2.5)

                # Sem filtro, abrir mais fichas do que leads faltando é
                # desperdício. Com filtro, é o oposto: a maioria das fichas será
                # descartada sem ocupar vaga, então quem manda é o teto por busca
                # — limitar pelo que falta faria a primeira busca desistir cedo.
                if filtrando or conhecidas:
                    restante = max_por_query
                else:
                    restante = min(max_por_query, max_total - len(leads))
                links = _coletar_links(page, restante, log=log, ja_abertos=ja_abertos)
                log(f"abrindo {len(links)} fichas...")

                for j, link in enumerate(links, 1):
                    if len(leads) >= max_total or parar():
                        break
                    ja_abertos.add(_identidade(link))
                    try:
                        page.goto(link, wait_until="domcontentloaded", timeout=40_000)
                        page.wait_for_selector("h1.DUwDvf", timeout=12_000)
                        # O painel de contatos monta depois do título; sem esta
                        # espera o site pode ser lido como vazio.
                        try:
                            page.wait_for_selector(INFO_PRONTA, timeout=8_000)
                        except PWTimeout:
                            pass
                        _pausa(0.4, 0.9)
                        lead = _extrair_ficha(page, link, query)
                    except PWTimeout:
                        continue
                    except Exception as e:  # noqa: BLE001
                        log(f"ficha {j} falhou: {e}")
                        continue

                    if not lead:
                        continue
                    abertas += 1
                    if lead.chave in conhecidas:
                        repetidos += 1
                        continue
                    if brasileiros.ativo(filtro_brasileiro):
                        brasileiros.avaliar(lead, lusofona=lusofona)

                    barrado = ""
                    if not passa_no_filtro(lead.site, filtro_site):
                        fora_do_site += 1
                        barrado = "site"
                    elif not brasileiros.passa_no_filtro(lead, filtro_brasileiro):
                        fora_do_publico += 1
                        barrado = "publico"
                    if barrado:
                        # Sem esta linha a etapa fica minutos sem sinal de vida
                        # quando o filtro barra quase tudo.
                        if (fora_do_site + fora_do_publico) % 10 == 0:
                            log(
                                f"{abertas} fichas abertas · {fora_do_site} com site · "
                                f"{fora_do_publico} fora do publico · "
                                f"{len(leads)} aproveitadas"
                            )
                        continue
                    if lead.chave not in leads:
                        leads[lead.chave] = lead
                        sink(
                            Evento(
                                "progresso",
                                etapa=2,
                                atual=len(leads),
                                total=max_total,
                                dados={
                                    "nome": lead.nome,
                                    "repetidos": repetidos,
                                    "descartados": fora_do_site + fora_do_publico,
                                },
                            )
                        )
        finally:
            contexto.close()
            navegador.close()

    if repetidos:
        log(f"{repetidos} empresas ignoradas por já estarem no histórico")
    if fora_do_site:
        log(f"{fora_do_site} empresas descartadas pelo filtro de site")
    if fora_do_publico:
        log(f"{fora_do_publico} empresas descartadas por não parecerem público brasileiro")
    if len(leads) < max_total and not parar():
        log(
            f"{abertas} fichas abertas nas {len(queries)} buscas para {len(leads)} "
            "leads. Para achar mais, aumente as buscas ou as fichas por busca."
        )

    return list(leads.values())
