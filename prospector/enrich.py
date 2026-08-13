"""Enriquecimento: visita o site da empresa e extrai e-mail, WhatsApp e redes sociais."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from .models import Lead
from .sites import tem_site_proprio
from .utils import formatar_telefone

PAGINAS_CONTATO = ("", "/contato", "/contact", "/fale-conosco", "/sobre", "/quem-somos")

RE_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# Lixo comum que casa com o regex de e-mail mas não é contato de ninguém.
EMAIL_RUIM = re.compile(
    r"(\.(png|jpe?g|gif|svg|webp|css|js)$|@(2x|3x)\.|sentry\.io|wixpress|"
    r"example\.(com|org)|domain\.com|seuemail|your(email|domain)|email\.com$)",
    re.I,
)

RE_WHATS = re.compile(r"(?:wa\.me|api\.whatsapp\.com/send\?phone=)/?(\+?\d{8,15})", re.I)
RE_INSTA = re.compile(r"instagram\.com/([A-Za-z0-9_.]{2,30})", re.I)
RE_FACE = re.compile(r"facebook\.com/([A-Za-z0-9_.\-]{2,60})", re.I)
RE_LINKEDIN = re.compile(r"linkedin\.com/(?:company|in)/([A-Za-z0-9_.\-]{2,60})", re.I)

IGNORAR_SOCIAL = {
    "sharer", "share", "sharer.php", "plugins", "tr", "profile.php",
    "explore", "p", "reel", "reels", "accounts", "login", "home", "pages",
    "dialog", "static", "embed", "developers", "help", "legal", "policies",
}

# Handles que na verdade são arquivos estáticos (rsrc.php, sdk.js, ...).
RE_ARQUIVO = re.compile(r"\.(php|js|css|html?|json|ico|png|jpe?g|svg|gif)$", re.I)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}


def _normalizar(url: str) -> str:
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}" if p.netloc else ""


def _primeiro_valido(regex: re.Pattern, texto: str) -> str:
    for m in regex.finditer(texto):
        handle = m.group(1).strip("/").lower()
        if handle and handle not in IGNORAR_SOCIAL and not RE_ARQUIVO.search(handle):
            return handle
    return ""


def _aproveitar_perfil_social(lead: Lead) -> None:
    """Muitas empresas cadastram o próprio Instagram como 'site' no Maps.

    Nesse caso o handle está na própria URL — extrai dali, já que a página em si
    só devolveria os assets estáticos da rede social.
    """
    host = urlparse(_normalizar(lead.site)).netloc.lower()
    for campo, regex, dominios in (
        ("instagram", RE_INSTA, ("instagram.com",)),
        ("facebook", RE_FACE, ("facebook.com", "fb.com")),
        ("linkedin", RE_LINKEDIN, ("linkedin.com",)),
    ):
        if any(host.endswith(d) for d in dominios):
            handle = _primeiro_valido(regex, lead.site)
            if handle and not getattr(lead, campo):
                setattr(lead, campo, handle)
            return


def _extrair(html: str, lead: Lead) -> None:
    sopa = BeautifulSoup(html, "html.parser")

    # E-mails: mailto: é o sinal mais confiável; depois varre o texto.
    achados: list[str] = []
    for a in sopa.select('a[href^="mailto:"]'):
        endereco = (a.get("href") or "")[7:].split("?")[0].strip()
        if endereco:
            achados.append(endereco)
    achados.extend(RE_EMAIL.findall(sopa.get_text(" ", strip=True)))

    for email in achados:
        email = email.strip().strip(".,;:").lower()
        if EMAIL_RUIM.search(email) or email in lead.emails:
            continue
        lead.emails.append(email)
        if len(lead.emails) >= 3:
            break

    if not lead.whatsapp:
        m = RE_WHATS.search(html)
        if m:
            lead.whatsapp = formatar_telefone(m.group(1))

    for campo, regex in (
        ("instagram", RE_INSTA),
        ("facebook", RE_FACE),
        ("linkedin", RE_LINKEDIN),
    ):
        if not getattr(lead, campo):
            handle = _primeiro_valido(regex, html)
            if handle:
                setattr(lead, campo, handle)

    # O `lang` do <html> é o jeito mais direto de saber com quem o site fala —
    # é o que separa um salão brasileiro de um salão que só vende "Brazilian
    # Blowout".
    if not lead.idioma_site and sopa.html is not None:
        lead.idioma_site = (sopa.html.get("lang") or "").strip()

    if not lead.descricao_site:
        meta = sopa.find("meta", attrs={"name": "description"}) or sopa.find(
            "meta", attrs={"property": "og:description"}
        )
        conteudo = (meta.get("content") if meta else "") or ""
        titulo = sopa.title.get_text(strip=True) if sopa.title else ""
        lead.descricao_site = (f"{titulo} — {conteudo}" if conteudo else titulo)[:500].strip()


def _enriquecer_um(lead: Lead, timeout: float, deve_parar=None) -> Lead:
    base = _normalizar(lead.site)
    if not base:
        return lead
    _aproveitar_perfil_social(lead)
    if not tem_site_proprio(lead.site):
        return lead  # perfil de rede social ou linktree: nada para varrer
    if deve_parar and deve_parar():
        return lead  # tarefa já na fila quando a interface pediu para parar

    try:
        cliente = httpx.Client(
            headers=HEADERS, timeout=timeout, follow_redirects=True, verify=False
        )
    except Exception:  # noqa: BLE001
        return lead

    with cliente:
        for caminho in PAGINAS_CONTATO:
            if lead.emails and lead.whatsapp and lead.instagram:
                break  # já temos o suficiente
            if deve_parar and deve_parar():
                break
            try:
                r = cliente.get(urljoin(base, caminho))
                if r.status_code >= 400 or "html" not in r.headers.get("content-type", ""):
                    continue
                _extrair(r.text, lead)
            except Exception:  # noqa: BLE001
                continue

    return lead


def enriquecer(
    leads: list[Lead],
    concorrencia: int = 8,
    timeout: float = 12.0,
    on_progress=None,
    deve_parar=None,
) -> None:
    """Visita os sites em paralelo e preenche os campos de contato, in-place."""
    alvos = [l for l in leads if l.site]
    if not alvos:
        return

    with ThreadPoolExecutor(max_workers=max(1, concorrencia)) as pool:
        futuros = {pool.submit(_enriquecer_um, l, timeout, deve_parar): l for l in alvos}
        for _ in as_completed(futuros):
            if on_progress:
                on_progress(1)
