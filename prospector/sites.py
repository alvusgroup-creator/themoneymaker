"""Classificação da URL que o Google Maps mostra como "site" da empresa.

O filtro "sem site" só é útil se "site" quiser dizer *site próprio*: uma empresa
cujo único endereço na web é o Instagram não tem site — é exatamente o tipo de
lead que a busca por "sem site" quer encontrar. Sem essa distinção, quem cadastra
o Instagram no campo de site do Maps some da lista.
"""

from __future__ import annotations

from urllib.parse import urlparse

# Perfis de rede social: presença na web, mas não site próprio.
REDES_SOCIAIS = {
    "instagram.com",
    "facebook.com",
    "fb.com",
    "fb.me",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "tiktok.com",
    "youtube.com",
    "youtu.be",
    "threads.net",
    "threads.com",
    "pinterest.com",
    "wa.me",
    "whatsapp.com",
    "api.whatsapp.com",
    "t.me",
    "telegram.me",
}

# Páginas do tipo "todos os meus links" — também não são site próprio.
AGREGADORES_DE_LINK = {
    "linktr.ee",
    "linktree.com",
    "beacons.ai",
    "bio.link",
    "lnk.bio",
    "linkin.bio",
    "campsite.bio",
    "solo.to",
    "taplink.cc",
    "msha.ke",
}

PROPRIO = "proprio"
SOCIAL = "social"
NENHUM = "nenhum"


def dominio(url: str) -> str:
    """Host da URL, sem `www.` e sem porta. String vazia se não der para ler."""
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return ""
    host = host.split("@")[-1].split(":")[0]
    return host[4:] if host.startswith("www.") else host


def _casa(host: str, dominios: set[str]) -> bool:
    return any(host == d or host.endswith("." + d) for d in dominios)


def tipo_de_site(url: str) -> str:
    """`proprio`, `social` ou `nenhum`."""
    host = dominio(url)
    if not host:
        return NENHUM
    if _casa(host, REDES_SOCIAIS) or _casa(host, AGREGADORES_DE_LINK):
        return SOCIAL
    return PROPRIO


def tem_site_proprio(url: str) -> bool:
    return tipo_de_site(url) == PROPRIO


def passa_no_filtro(url: str, filtro: str) -> bool:
    """Regra única do filtro de site, usada na coleta e na conferência final.

    `com` = tem site próprio; `sem` = não tem (inclui quem só cadastrou uma rede
    social); qualquer outro valor não filtra nada.
    """
    if filtro == "com":
        return tem_site_proprio(url)
    if filtro == "sem":
        return not tem_site_proprio(url)
    return True
