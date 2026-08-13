"""Histórico local de leads já prospectados.

Guarda tudo em um único JSON ao lado do projeto. Serve para três propósitos:
não repetir empresas em buscas futuras, separar os leads em **bases** (uma por
nicho/região, para os leads de Flooring não se misturarem com os de Cleaning) e
preservar o estado de trabalho (fase do pipeline e mensagem editada) entre
execuções.

Cada base tem o seu próprio conjunto de fases — renomear uma fase da base de
Flooring não mexe na base de Cleaning. Por isso o lead guarda o **id** da fase,
não o nome: renomear é trocar uma string na base, sem varrer lead nenhum.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import Lead

CAMINHO_PADRAO = Path("historico.json")
VERSAO = 2

# Fases que toda base nova nasce tendo. A partir daí cada base segue sua vida:
# dá para renomear, acrescentar e remover.
FASES_PADRAO = (
    "Novo lead",
    "Contatado",
    "Interessado",
    "Reunião marcada",
    "Proposta enviada",
    "Fechado",
)

# Para onde vai quem estava marcado como contatado no formato antigo.
FASE_DE_CONTATADO = "Contatado"


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _novo_id() -> str:
    return uuid.uuid4().hex[:12]


def _fases_novas() -> list[dict[str, str]]:
    return [{"id": _novo_id(), "nome": nome} for nome in FASES_PADRAO]


class Historico:
    """Acesso serializado ao arquivo. O servidor web toca nele de várias threads."""

    def __init__(self, caminho: Path | str = CAMINHO_PADRAO):
        self.caminho = Path(caminho)
        self._lock = threading.Lock()
        self._dados: dict[str, Any] = {"versao": VERSAO, "bases": {}, "leads": {}}
        self._carregar()

    # -- disco -------------------------------------------------------------

    def _carregar(self) -> None:
        if not self.caminho.exists():
            return
        try:
            bruto = json.loads(self.caminho.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # Arquivo corrompido não pode derrubar a aplicação: começa limpo e
            # preserva o original ao lado para inspeção manual.
            try:
                self.caminho.replace(self.caminho.with_suffix(".json.corrompido"))
            except OSError:
                pass
            return
        if not (isinstance(bruto, dict) and isinstance(bruto.get("leads"), dict)):
            return

        self._dados = {
            "versao": bruto.get("versao", VERSAO),
            "bases": bruto.get("bases") if isinstance(bruto.get("bases"), dict) else {},
            "leads": bruto["leads"],
        }
        if self._dados["versao"] < VERSAO:
            self._migrar_para_v2()

    def _migrar_para_v2(self) -> None:
        """Distribui os leads antigos em bases derivadas do nicho + região.

        Antes da v2 tudo vivia numa lista só e o trabalho feito era um booleano
        `contatado`. Deixar esses leads sem base esconderia todos eles do
        quadro; então cada par nicho/região vira uma base (que dá para renomear
        ou apagar depois) e quem estava contatado nasce na fase equivalente.
        """
        try:
            reserva = self.caminho.with_name(self.caminho.stem + ".v1.bak.json")
            reserva.write_text(
                json.dumps(self._dados, ensure_ascii=False, indent=1), encoding="utf-8"
            )
        except OSError:
            pass  # backup é cortesia, não pode impedir a migração

        por_contexto: dict[tuple[str, str], str] = {}
        for registro in self._dados["leads"].values():
            nicho = (registro.get("nicho") or "").strip()
            local = (registro.get("local") or "").strip()
            if not nicho and not local:
                registro.setdefault("base", "")
                registro.setdefault("fase", "")
                continue

            chave = (nicho.casefold(), local.casefold())
            if chave not in por_contexto:
                nome = f"{nicho} em {local}" if nicho and local else (nicho or local)
                por_contexto[chave] = self._criar_base_sem_lock(nome)["id"]

            base = self._dados["bases"][por_contexto[chave]]
            registro["base"] = base["id"]
            registro["fase"] = _id_por_nome(
                base["fases"],
                FASE_DE_CONTATADO if registro.get("contatado") else base["fases"][0]["nome"],
            )

        for registro in self._dados["leads"].values():
            registro.pop("contatado", None)
            registro.pop("contatado_em", None)

        self._dados["versao"] = VERSAO
        self._salvar_sem_lock()

    def _salvar_sem_lock(self) -> None:
        temporario = self.caminho.with_suffix(".json.tmp")
        temporario.parent.mkdir(parents=True, exist_ok=True)
        temporario.write_text(
            json.dumps(self._dados, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        os.replace(temporario, self.caminho)  # troca atômica

    # -- bases -------------------------------------------------------------

    def _criar_base_sem_lock(self, nome: str) -> dict[str, Any]:
        base = {
            "id": _novo_id(),
            "nome": nome.strip() or "Base sem nome",
            "fases": _fases_novas(),
            "criada_em": _agora(),
        }
        self._dados["bases"][base["id"]] = base
        return base

    def _primeira_fase(self, base_id: str) -> str:
        base = self._dados["bases"].get(base_id)
        return base["fases"][0]["id"] if base and base["fases"] else ""

    def _fase_valida(self, base_id: str, fase_id: str) -> bool:
        base = self._dados["bases"].get(base_id)
        return bool(base) and any(f["id"] == fase_id for f in base["fases"])

    def bases(self) -> list[dict[str, Any]]:
        """Bases com a contagem de leads por fase, prontas para montar o quadro."""
        with self._lock:
            saida = []
            for base in self._dados["bases"].values():
                do_base = [
                    r for r in self._dados["leads"].values() if r.get("base") == base["id"]
                ]
                por_fase: dict[str, int] = {f["id"]: 0 for f in base["fases"]}
                for registro in do_base:
                    if registro.get("fase") in por_fase:
                        por_fase[registro["fase"]] += 1
                saida.append(
                    {
                        "id": base["id"],
                        "nome": base["nome"],
                        "fases": [dict(f) for f in base["fases"]],
                        "criada_em": base.get("criada_em", ""),
                        "total": len(do_base),
                        "por_fase": por_fase,
                    }
                )
            saida.sort(key=lambda b: b["criada_em"])
            return saida

    def base_por_nome(self, nome: str) -> dict[str, Any] | None:
        """Busca sem diferenciar maiúsculas: a CLI recebe o nome, não o id."""
        alvo = nome.strip().casefold()
        with self._lock:
            for base in self._dados["bases"].values():
                if base["nome"].casefold() == alvo:
                    return dict(base)
            return None

    def criar_base(self, nome: str) -> dict[str, Any]:
        with self._lock:
            base = self._criar_base_sem_lock(nome)
            self._salvar_sem_lock()
            return dict(base)

    def renomear_base(self, base_id: str, nome: str) -> dict[str, Any] | None:
        with self._lock:
            base = self._dados["bases"].get(base_id)
            if base is None:
                return None
            base["nome"] = nome.strip() or base["nome"]
            self._salvar_sem_lock()
            return dict(base)

    def apagar_base(self, base_id: str) -> bool:
        """Some com a base, não com os leads: eles voltam a existir só no Geral."""
        with self._lock:
            if base_id not in self._dados["bases"]:
                return False
            del self._dados["bases"][base_id]
            for registro in self._dados["leads"].values():
                if registro.get("base") == base_id:
                    registro["base"] = ""
                    registro["fase"] = ""
            self._salvar_sem_lock()
            return True

    # -- fases -------------------------------------------------------------

    def criar_fase(self, base_id: str, nome: str) -> dict[str, Any] | None:
        with self._lock:
            base = self._dados["bases"].get(base_id)
            if base is None:
                return None
            base["fases"].append({"id": _novo_id(), "nome": nome.strip() or "Nova fase"})
            self._salvar_sem_lock()
            return dict(base)

    def renomear_fase(self, base_id: str, fase_id: str, nome: str) -> dict[str, Any] | None:
        with self._lock:
            base = self._dados["bases"].get(base_id)
            if base is None:
                return None
            for fase in base["fases"]:
                if fase["id"] == fase_id:
                    fase["nome"] = nome.strip() or fase["nome"]
                    self._salvar_sem_lock()
                    return dict(base)
            return None

    def apagar_fase(self, base_id: str, fase_id: str) -> dict[str, Any] | None:
        """Remove a fase e recolhe os leads dela para a primeira que sobrar.

        A última fase não pode sair: uma base sem fase nenhuma não teria para
        onde mandar os leads da próxima busca.
        """
        with self._lock:
            base = self._dados["bases"].get(base_id)
            if base is None or len(base["fases"]) <= 1:
                return None
            if not any(f["id"] == fase_id for f in base["fases"]):
                return None

            base["fases"] = [f for f in base["fases"] if f["id"] != fase_id]
            destino = base["fases"][0]["id"]
            for registro in self._dados["leads"].values():
                if registro.get("base") == base_id and registro.get("fase") == fase_id:
                    registro["fase"] = destino
            self._salvar_sem_lock()
            return dict(base)

    # -- leitura -----------------------------------------------------------

    def chaves(self) -> set[str]:
        with self._lock:
            return set(self._dados["leads"])

    def total(self) -> int:
        with self._lock:
            return len(self._dados["leads"])

    def listar(
        self, apenas_chaves: list[str] | None = None, base: str | None = None
    ) -> list[dict[str, Any]]:
        """Registros prontos para a interface, do melhor score para o pior.

        `base` filtra por uma base específica; `None` devolve o Geral, com os
        leads de todas as bases mais os que não estão em nenhuma.
        """
        with self._lock:
            leads = self._dados["leads"]
            if apenas_chaves is None:
                registros = list(leads.values())
            else:
                registros = [leads[c] for c in apenas_chaves if c in leads]
            if base is not None:
                registros = [r for r in registros if r.get("base", "") == base]
            nomes_de_base = {b["id"]: b["nome"] for b in self._dados["bases"].values()}
            nomes_de_fase = {
                f["id"]: f["nome"]
                for b in self._dados["bases"].values()
                for f in b["fases"]
            }

        saida = []
        for registro in registros:
            copia = dict(registro)
            copia["base_nome"] = nomes_de_base.get(copia.get("base", ""), "")
            copia["fase_nome"] = nomes_de_fase.get(copia.get("fase", ""), "")
            saida.append(copia)

        # Marcado como público brasileiro sobe. Sem ninguém marcado — toda busca
        # feita dentro do Brasil — o campo é 0 em todos e a ordem não muda.
        return sorted(
            saida,
            key=lambda r: (
                (r.get("sinal_brasileiro") or 0) >= 30,
                r.get("score") if r.get("score") is not None else -1,
                r.get("avaliacoes") or 0,
            ),
            reverse=True,
        )

    def leads(self, chaves: list[str] | None = None, base: str | None = None) -> list[Lead]:
        """Reconstrói objetos `Lead`, já com a mensagem editada aplicada."""
        resultado: list[Lead] = []
        for registro in self.listar(chaves, base):
            lead = Lead.from_dict(registro)
            if registro.get("mensagem_editada"):
                lead.mensagem_abordagem = registro["mensagem_editada"]
            resultado.append(lead)
        return resultado

    # -- escrita -----------------------------------------------------------

    def registrar(self, leads: list[Lead], contexto: dict[str, Any] | None = None) -> int:
        """Grava os leads da busca. Devolve quantos eram inéditos.

        Reencontrar uma empresa não apaga o trabalho já feito nela: `fase` e
        `mensagem_editada` são preservados, o resto é atualizado. Um lead que já
        está numa base **não muda de base** por aparecer em outra busca — mover
        card é decisão de quem trabalha o funil, não da coleta.
        """
        contexto = contexto or {}
        base_da_busca = contexto.get("base", "") or ""
        novos = 0
        with self._lock:
            if base_da_busca and base_da_busca not in self._dados["bases"]:
                base_da_busca = ""

            for lead in leads:
                chave = lead.chave
                anterior = self._dados["leads"].get(chave, {})
                if not anterior:
                    novos += 1

                base = anterior.get("base") or base_da_busca
                fase = anterior.get("fase") or ""
                if not self._fase_valida(base, fase):
                    fase = self._primeira_fase(base)

                registro = lead.to_dict()
                registro.update(
                    {
                        "chave": chave,
                        "base": base,
                        "fase": fase,
                        "mensagem_editada": anterior.get("mensagem_editada", ""),
                        "primeira_vez_em": anterior.get("primeira_vez_em") or _agora(),
                        "visto_em": _agora(),
                        "nicho": contexto.get("nicho", anterior.get("nicho", "")),
                        "local": contexto.get("local", anterior.get("local", "")),
                    }
                )
                self._dados["leads"][chave] = registro
            self._salvar_sem_lock()
        return novos

    def mover_lead(self, chave: str, fase_id: str) -> dict[str, Any] | None:
        """Arrastar um card de coluna. Só aceita fase que exista na base do lead."""
        with self._lock:
            registro = self._dados["leads"].get(chave)
            if registro is None:
                return None
            if not self._fase_valida(registro.get("base", ""), fase_id):
                return None
            registro["fase"] = fase_id
            registro["fase_mudou_em"] = _agora()
            self._salvar_sem_lock()
            return dict(registro)

    def mover_para_base(self, chave: str, base_id: str) -> dict[str, Any] | None:
        """Manda o lead para outra base, sempre na primeira fase dela."""
        with self._lock:
            registro = self._dados["leads"].get(chave)
            if registro is None:
                return None
            if base_id and base_id not in self._dados["bases"]:
                return None
            registro["base"] = base_id
            registro["fase"] = self._primeira_fase(base_id) if base_id else ""
            self._salvar_sem_lock()
            return dict(registro)

    def salvar_mensagem(self, chave: str, texto: str) -> dict[str, Any] | None:
        with self._lock:
            registro = self._dados["leads"].get(chave)
            if registro is None:
                return None
            # Texto igual ao original da IA não conta como edição: assim o campo
            # volta a acompanhar a IA se a empresa for requalificada depois.
            limpo = texto.strip()
            original = (registro.get("mensagem_abordagem") or "").strip()
            registro["mensagem_editada"] = "" if limpo == original else limpo
            self._salvar_sem_lock()
            return dict(registro)

    def esquecer(self, chave: str) -> bool:
        with self._lock:
            if chave not in self._dados["leads"]:
                return False
            del self._dados["leads"][chave]
            self._salvar_sem_lock()
            return True

    def limpar(self) -> int:
        with self._lock:
            quantos = len(self._dados["leads"])
            self._dados["leads"] = {}
            self._salvar_sem_lock()
            return quantos


def _id_por_nome(fases: list[dict[str, str]], nome: str) -> str:
    for fase in fases:
        if fase["nome"] == nome:
            return fase["id"]
    return fases[0]["id"] if fases else ""
