"""Estruturas de dados do pipeline."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, fields, asdict
from typing import Any


@dataclass
class Lead:
    """Um estabelecimento encontrado, já enriquecido e (opcionalmente) qualificado."""

    nome: str
    categoria: str = ""
    endereco: str = ""
    telefone: str = ""
    site: str = ""
    nota: float | None = None
    avaliacoes: int | None = None
    maps_url: str = ""
    query_origem: str = ""

    # Preenchidos pelo enriquecimento (visita ao site da empresa)
    emails: list[str] = field(default_factory=list)
    whatsapp: str = ""
    instagram: str = ""
    facebook: str = ""
    linkedin: str = ""
    descricao_site: str = ""
    idioma_site: str = ""  # o `lang` do <html>, usado para detectar público

    # Preenchidos por brasileiros.avaliar()
    sinal_brasileiro: int = 0
    motivo_brasileiro: str = ""

    # Preenchidos pela IA
    score: int | None = None
    motivo_score: str = ""
    mensagem_abordagem: str = ""

    @property
    def chave(self) -> str:
        """Identificador estável para deduplicar entre buscas diferentes."""
        base = f"{self.nome.strip().casefold()}|{self.endereco.strip().casefold()}"
        if not self.endereco:
            base = f"{base}|{self.telefone}"
        return hashlib.sha1(base.encode("utf-8")).hexdigest()

    def to_row(self) -> dict[str, Any]:
        d = asdict(self)
        d["emails"] = ", ".join(self.emails)
        return d

    def to_dict(self) -> dict[str, Any]:
        """Serialização fiel (emails continua lista). Use para persistir."""
        return asdict(self)

    @classmethod
    def from_dict(cls, dados: dict[str, Any]) -> "Lead":
        """Reconstrói ignorando chaves extras que o histórico acrescenta."""
        campos = {f.name for f in fields(cls)}
        limpo = {k: v for k, v in dados.items() if k in campos}
        limpo.setdefault("nome", "")
        if not isinstance(limpo.get("emails"), list):
            bruto = limpo.get("emails") or ""
            limpo["emails"] = [e.strip() for e in str(bruto).split(",") if e.strip()]
        return cls(**limpo)


COLUNAS = [
    ("nome", "Nome"),
    ("score", "Score"),
    ("motivo_score", "Motivo do score"),
    ("categoria", "Categoria"),
    ("telefone", "Telefone"),
    ("whatsapp", "WhatsApp"),
    ("emails", "E-mails"),
    ("site", "Site"),
    ("instagram", "Instagram"),
    ("facebook", "Facebook"),
    ("linkedin", "LinkedIn"),
    ("endereco", "Endereço"),
    ("nota", "Nota"),
    ("avaliacoes", "Avaliações"),
    ("sinal_brasileiro", "Sinal BR"),
    ("motivo_brasileiro", "Por que parece BR"),
    ("mensagem_abordagem", "Mensagem de abordagem"),
    ("descricao_site", "Descrição do site"),
    ("maps_url", "Google Maps"),
    ("query_origem", "Busca de origem"),
]
