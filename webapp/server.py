"""Servidor local da interface web.

Uma busca é um `Job`: roda numa thread própria (o Playwright síncrono não pode
ser chamado de dentro do event loop do asyncio) e publica os eventos do pipeline
para os assinantes conectados por SSE. Só um job por vez — a coleta abre um
Chromium e disputa CPU com o Ollama.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from prospector.ai import AgenteIA
from prospector.config import HISTORICO_PADRAO, Config
from prospector.eventos import Evento
from prospector.exporter import exportar_csv, exportar_xlsx
from prospector.historico import Historico
from prospector.pipeline import Cancelado, executar

RAIZ = Path(__file__).resolve().parent
ESTATICOS = RAIZ / "static"

ESPERA_PING = 15.0  # segundos sem evento antes de mandar um comentário SSE


# ---------------------------------------------------------------- jobs


@dataclass
class Job:
    id: str
    cfg: Config
    estado: str = "rodando"  # rodando | concluido | cancelado | erro
    eventos: list[dict[str, Any]] = field(default_factory=list)
    assinantes: list[queue.Queue] = field(default_factory=list)
    parar: threading.Event = field(default_factory=threading.Event)
    chaves: list[str] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def publicar(self, evento: dict[str, Any]) -> None:
        with self.lock:
            self.eventos.append(evento)
            destinos = list(self.assinantes)
        for fila in destinos:
            fila.put(evento)

    def assinar(self) -> tuple[list[dict[str, Any]], queue.Queue]:
        """Snapshot + fila, sob o mesmo lock, para não perder nem duplicar."""
        fila: queue.Queue = queue.Queue()
        with self.lock:
            passados = list(self.eventos)
            self.assinantes.append(fila)
        return passados, fila

    def cancelar_assinatura(self, fila: queue.Queue) -> None:
        with self.lock:
            if fila in self.assinantes:
                self.assinantes.remove(fila)

    def resumo(self) -> dict[str, Any]:
        return {
            "job_id": self.id,
            "estado": self.estado,
            "rodando": self.estado == "rodando",
            "encontrados": len(self.chaves),
            "nicho": self.cfg.nicho,
            "local": self.cfg.local,
            "base": self.cfg.base,
        }


class Gerenciador:
    def __init__(self, historico: Historico):
        self.historico = historico
        self._jobs: dict[str, Job] = {}
        self._atual: Job | None = None
        self._lock = threading.Lock()

    @property
    def atual(self) -> Job | None:
        return self._atual

    def obter(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def iniciar(self, cfg: Config) -> Job:
        with self._lock:
            if self._atual is not None and self._atual.estado == "rodando":
                raise HTTPException(409, "Já existe uma busca em andamento.")
            job = Job(id=uuid.uuid4().hex[:12], cfg=cfg)
            self._jobs[job.id] = job
            self._atual = job
        threading.Thread(target=self._rodar, args=(job,), daemon=True).start()
        return job

    def _rodar(self, job: Job) -> None:
        def sink(evento: Evento) -> None:
            job.publicar(evento.to_json())

        try:
            leads = executar(
                job.cfg,
                sink=sink,
                deve_parar=job.parar.is_set,
                historico=self.historico,
            )
            job.chaves = [l.chave for l in leads]
            if job.parar.is_set():
                job.estado = "cancelado"
                texto = f"Busca cancelada - {len(leads)} leads guardados"
            else:
                job.estado = "concluido"
                texto = "Busca concluída" if leads else "Nenhum lead encontrado"
        except Cancelado:
            job.estado = "cancelado"
            texto = "Busca cancelada"
        except Exception as e:  # noqa: BLE001
            job.estado = "erro"
            texto = f"A busca falhou: {e}"
            job.publicar(Evento("erro", texto=texto).to_json())

        job.publicar(
            Evento(
                "fim",
                texto=texto,
                dados={"estado": job.estado, "encontrados": len(job.chaves)},
            ).to_json()
        )


# ---------------------------------------------------------------- app

historico = Historico(os.getenv("PROSPECTADOR_HISTORICO", HISTORICO_PADRAO))
gerenciador = Gerenciador(historico)

app = FastAPI(title="Prospectador", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=ESTATICOS), name="static")


class PedidoBusca(BaseModel):
    nicho: str = Field(min_length=2)
    local: str = Field(min_length=2)
    oferta: str = "servicos de marketing digital para pequenas e medias empresas"
    max_leads: int = Field(default=100, ge=1, le=2000)
    max_por_query: int = Field(default=60, ge=1, le=500)
    n_queries: int = Field(default=6, ge=1, le=20)
    usar_ia: bool = True
    enriquecer: bool = True
    pular_conhecidos: bool = True
    ver_navegador: bool = False
    filtro_site: str = "todos"
    filtro_brasileiro: str = "todos"
    base: str = ""  # id da base que recebe os leads; vazio = só no Geral

    def to_config(self) -> Config:
        filtro = self.filtro_site if self.filtro_site in ("todos", "com", "sem") else "todos"
        publico = (
            self.filtro_brasileiro
            if self.filtro_brasileiro in ("marcar", "so_br")
            else "todos"
        )
        return Config(
            nicho=self.nicho.strip(),
            local=self.local.strip(),
            oferta=self.oferta.strip(),
            max_leads=self.max_leads,
            max_por_query=self.max_por_query,
            n_queries=self.n_queries,
            headless=not self.ver_navegador,
            usar_ia=self.usar_ia,
            enriquecer=self.enriquecer,
            filtro_site=filtro,
            filtro_brasileiro=publico,
            base=self.base,
            usar_historico=True,
            pular_conhecidos=self.pular_conhecidos,
        )


class PedidoNome(BaseModel):
    nome: str = Field(min_length=1, max_length=80)


@app.get("/", response_class=HTMLResponse)
def raiz() -> HTMLResponse:
    return HTMLResponse((ESTATICOS / "index.html").read_text(encoding="utf-8"))


@app.get("/api/estado")
def estado() -> dict[str, Any]:
    job = gerenciador.atual
    return {
        "historico_total": historico.total(),
        "job": job.resumo() if job else None,
    }


@app.get("/api/ollama")
def status_ollama() -> dict[str, Any]:
    """Consulta se o modelo local está disponível, para avisar antes da busca."""
    sonda = Config(nicho="sonda", local="sonda", oferta="sonda")
    agente = AgenteIA(sonda)
    return {"ativo": agente.ativo, "modelo": sonda.modelo, "erro": agente.erro_local}


@app.post("/api/buscar")
def buscar(pedido: PedidoBusca) -> dict[str, Any]:
    job = gerenciador.iniciar(pedido.to_config())
    return job.resumo()


@app.post("/api/cancelar")
def cancelar() -> dict[str, Any]:
    job = gerenciador.atual
    if job is None or job.estado != "rodando":
        raise HTTPException(409, "Nenhuma busca em andamento.")
    job.parar.set()
    return {"ok": True}


@app.get("/api/eventos/{job_id}")
def eventos(job_id: str) -> StreamingResponse:
    job = gerenciador.obter(job_id)
    if job is None:
        raise HTTPException(404, "Busca desconhecida.")

    def fluxo() -> Iterator[str]:
        passados, fila = job.assinar()
        try:
            for evento in passados:
                yield _sse(evento)
            if any(e["tipo"] == "fim" for e in passados):
                return
            while True:
                try:
                    evento = fila.get(timeout=ESPERA_PING)
                except queue.Empty:
                    yield ": ping\n\n"
                    continue
                yield _sse(evento)
                if evento["tipo"] == "fim":
                    return
        finally:
            job.cancelar_assinatura(fila)

    return StreamingResponse(
        fluxo(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(evento: dict[str, Any]) -> str:
    return f"data: {json.dumps(evento, ensure_ascii=False)}\n\n"


def _chaves_do_escopo(escopo: str, job_id: str | None) -> list[str] | None:
    """None = histórico inteiro; lista = apenas os leads daquela busca."""
    if escopo != "busca":
        return None
    job = gerenciador.obter(job_id) if job_id else gerenciador.atual
    return list(job.chaves) if job else []


def _filtro_de_base(base: str) -> str | None:
    """`geral` (ou vazio) junta tudo; um id filtra aquela base."""
    return None if base in ("", "geral") else base


# ------------------------------------------------------------ bases e fases


@app.get("/api/bases")
def listar_bases() -> dict[str, Any]:
    return {"bases": historico.bases()}


@app.post("/api/bases")
def criar_base(pedido: PedidoNome) -> dict[str, Any]:
    return historico.criar_base(pedido.nome)


@app.patch("/api/bases/{base_id}")
def renomear_base(base_id: str, pedido: PedidoNome) -> dict[str, Any]:
    base = historico.renomear_base(base_id, pedido.nome)
    if base is None:
        raise HTTPException(404, "Base não encontrada.")
    return base


@app.delete("/api/bases/{base_id}")
def apagar_base(base_id: str) -> dict[str, Any]:
    if not historico.apagar_base(base_id):
        raise HTTPException(404, "Base não encontrada.")
    return {"ok": True}


@app.post("/api/bases/{base_id}/fases")
def criar_fase(base_id: str, pedido: PedidoNome) -> dict[str, Any]:
    base = historico.criar_fase(base_id, pedido.nome)
    if base is None:
        raise HTTPException(404, "Base não encontrada.")
    return base


@app.patch("/api/bases/{base_id}/fases/{fase_id}")
def renomear_fase(base_id: str, fase_id: str, pedido: PedidoNome) -> dict[str, Any]:
    base = historico.renomear_fase(base_id, fase_id, pedido.nome)
    if base is None:
        raise HTTPException(404, "Base ou fase não encontrada.")
    return base


@app.delete("/api/bases/{base_id}/fases/{fase_id}")
def apagar_fase(base_id: str, fase_id: str) -> dict[str, Any]:
    base = historico.apagar_fase(base_id, fase_id)
    if base is None:
        raise HTTPException(409, "Fase não encontrada ou é a última da base.")
    return base


# ------------------------------------------------------------------- leads


@app.get("/api/leads")
def listar_leads(
    base: str = "geral", escopo: str = "todos", job_id: str | None = None
) -> dict[str, Any]:
    chaves = _chaves_do_escopo(escopo, job_id)
    registros = historico.listar(chaves, base=_filtro_de_base(base))
    return {"base": base, "escopo": escopo, "total": len(registros), "leads": registros}


@app.post("/api/leads/{chave}/fase")
def mover_fase(chave: str, fase: str = Body(embed=True)) -> dict[str, Any]:
    registro = historico.mover_lead(chave, fase)
    if registro is None:
        raise HTTPException(404, "Lead ou fase não encontrada nesta base.")
    return registro


@app.post("/api/leads/{chave}/base")
def mover_base(chave: str, base: str = Body(embed=True)) -> dict[str, Any]:
    registro = historico.mover_para_base(chave, base)
    if registro is None:
        raise HTTPException(404, "Lead ou base não encontrada.")
    return registro


@app.post("/api/leads/{chave}/mensagem")
def mensagem(chave: str, texto: str = Body(embed=True)) -> dict[str, Any]:
    registro = historico.salvar_mensagem(chave, texto)
    if registro is None:
        raise HTTPException(404, "Lead não encontrado no histórico.")
    return registro


@app.delete("/api/leads/{chave}")
def esquecer(chave: str) -> dict[str, Any]:
    if not historico.esquecer(chave):
        raise HTTPException(404, "Lead não encontrado no histórico.")
    return {"ok": True, "historico_total": historico.total()}


@app.get("/api/baixar/{formato}")
def baixar(
    formato: str, base: str = "geral", escopo: str = "todos", job_id: str | None = None
) -> FileResponse:
    if formato not in ("csv", "xlsx"):
        raise HTTPException(400, "Formato deve ser csv ou xlsx.")

    chaves = _chaves_do_escopo(escopo, job_id)
    leads = historico.leads(chaves, base=_filtro_de_base(base))
    if not leads:
        raise HTTPException(404, "Nada para exportar.")

    # Gerado na hora a partir do histórico: assim o arquivo já sai com as
    # mensagens que você editou na tela. Vai para `exports/` para não pisar no
    # leads.csv que a CLI escreve na raiz. Só o formato pedido é gerado: um
    # problema no Excel não pode impedir o CSV de sair, nem o contrário.
    nome = "".join(c for c in base if c.isalnum()) or "geral"
    gerar = exportar_csv if formato == "csv" else exportar_xlsx
    destino = RAIZ.parent / "exports" / f"leads-{nome}"
    try:
        try:
            caminho = gerar(leads, destino)
        except PermissionError:
            # No Windows, o arquivo anterior aberto no Excel bloqueia a
            # gravação. Em vez de falhar, grava ao lado com carimbo de hora.
            caminho = gerar(leads, f"{destino}-{time.strftime('%Y%m%d-%H%M%S')}")
    except Exception as e:  # noqa: BLE001 - o motivo precisa chegar na tela
        logging.exception("Falha ao exportar %s", formato)
        raise HTTPException(500, f"Falha ao gerar o {formato}: {e}") from e

    return FileResponse(
        caminho,
        filename=caminho.name,
        media_type="text/csv" if formato == "csv" else None,
    )
