"""Eventos do pipeline.

Desacopla a execução da apresentação: o pipeline emite eventos e quem consome
decide como mostrar. A CLI usa o `SinkConsole` (rich); a interface web empurra
os mesmos eventos para o navegador via SSE.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn

TipoEvento = Literal["etapa", "log", "progresso", "resumo", "aviso", "erro", "fim"]

TOTAL_ETAPAS = 4


@dataclass
class Evento:
    tipo: TipoEvento
    texto: str = ""
    etapa: int = 0
    atual: int = 0
    total: int = 0
    dados: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "tipo": self.tipo,
            "texto": self.texto,
            "etapa": self.etapa,
            "atual": self.atual,
            "total": self.total,
            "dados": self.dados,
        }


Sink = Callable[[Evento], None]


def sink_nulo(evento: Evento) -> None:
    """Descarta tudo. Útil em testes e em execuções silenciosas."""


class SinkConsole:
    """Reproduz no terminal a saída que o pipeline tinha antes do refactor.

    Mantém uma barra de progresso viva por etapa: ela nasce quando chega um
    evento `etapa` com `total`, avança nos eventos `progresso` (que carregam
    valores absolutos, nunca incrementos) e morre na etapa seguinte ou no `fim`.
    """

    def __init__(self, console: Console | None = None):
        self.console = console or Console()
        self._progress: Progress | None = None
        self._task = None

    def __call__(self, evento: Evento) -> None:
        metodo = getattr(self, f"_on_{evento.tipo}", None)
        if metodo:
            metodo(evento)

    # -- ciclo de vida da barra -------------------------------------------

    def _abrir_barra(self, descricao: str, total: int) -> None:
        self._fechar_barra()
        self._progress = Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            console=self.console,
        )
        self._progress.start()
        self._task = self._progress.add_task(descricao, total=total)

    def _fechar_barra(self) -> None:
        if self._progress is not None:
            self._progress.stop()
            self._progress = None
            self._task = None

    # -- tratadores por tipo ----------------------------------------------

    def _on_etapa(self, e: Evento) -> None:
        self._fechar_barra()
        titulo = f"{e.etapa}/{TOTAL_ETAPAS} {e.texto}" if e.etapa else e.texto
        estilo = "dim" if e.dados.get("desativada") else "bold"
        self.console.rule(f"[{estilo}]{titulo}")
        if e.total:
            self._abrir_barra(e.dados.get("descricao", "progresso"), e.total)

    def _on_progresso(self, e: Evento) -> None:
        if self._progress is not None and self._task is not None:
            self._progress.update(self._task, completed=e.atual, total=e.total or None)

    def _on_log(self, e: Evento) -> None:
        if self._progress is not None:
            return  # não polui a barra ativa
        self.console.print(f"[dim]{e.texto}[/dim]")

    def _on_resumo(self, e: Evento) -> None:
        self._fechar_barra()
        self.console.print(f"[green]{e.texto}[/green]")

    def _on_aviso(self, e: Evento) -> None:
        self._fechar_barra()
        self.console.print(f"[yellow]{e.texto}[/yellow]")

    def _on_erro(self, e: Evento) -> None:
        self._fechar_barra()
        self.console.print(f"[red]{e.texto}[/red]")

    def _on_fim(self, e: Evento) -> None:
        self._fechar_barra()
        if e.texto:
            self.console.rule(f"[bold green]{e.texto}")
        for rotulo, caminho in e.dados.get("arquivos", {}).items():
            self.console.print(f"  {rotulo:<6}-> {caminho}")
