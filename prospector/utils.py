"""Helpers compartilhados entre a coleta e o enriquecimento."""

from __future__ import annotations

import re


def formatar_telefone(bruto: str) -> str:
    """Normaliza para '+55 31 3292-0208' sem estragar número de fora do Brasil.

    O Maps devolve algo como '0313292-0208' (com prefixo de operadora) e os
    links de WhatsApp devolvem '5531992214813'. Quando o número já vem em
    formato internacional (`phone:tel:+19806003232`), o país dele é respeitado:
    forçar o padrão brasileiro virava '+55 18 28891-8797' num telefone da
    Carolina do Norte.
    """
    d = re.sub(r"\D", "", bruto)
    if not d:
        return ""

    internacional = bruto.strip().startswith("+")

    if d.startswith("55") and len(d) >= 12:
        return _formatar_br(d[2:], bruto)
    if internacional and not d.startswith("55"):
        return _formatar_estrangeiro(d)

    # Sem o '+' não dá para saber o país: mantém a leitura brasileira, que é o
    # caso do prefixo de operadora e dos links wa.me daqui.
    if d.startswith("0") and len(d) in (11, 12):
        d = d[1:]
    return _formatar_br(d, bruto)


def _formatar_br(d: str, bruto: str) -> str:
    if len(d) == 11:  # celular: DDD + 9 dígitos
        return f"+55 {d[:2]} {d[2:7]}-{d[7:]}"
    if len(d) == 10:  # fixo: DDD + 8 dígitos
        return f"+55 {d[:2]} {d[2:6]}-{d[6:]}"
    return bruto.strip()


def _formatar_estrangeiro(d: str) -> str:
    """EUA/Canadá ganham o formato local; o resto fica em E.164, sempre legível."""
    if d.startswith("1") and len(d) == 11:
        return f"+1 {d[1:4]} {d[4:7]}-{d[7:]}"
    return f"+{d}"
