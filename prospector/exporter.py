"""Exportação da lista de contatos para CSV e Excel."""

from __future__ import annotations

import csv
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .models import COLUNAS, Lead

LARGURAS = {
    "nome": 34, "score": 8, "motivo_score": 46, "categoria": 22, "telefone": 18,
    "whatsapp": 16, "emails": 32, "site": 34, "instagram": 20, "facebook": 20,
    "linkedin": 20, "endereco": 46, "nota": 7, "avaliacoes": 12,
    "sinal_brasileiro": 9, "motivo_brasileiro": 42,
    "mensagem_abordagem": 60, "descricao_site": 46, "maps_url": 30,
    "query_origem": 28,
}


def _ordenar(leads: list[Lead]) -> list[Lead]:
    """Melhores leads primeiro; sem score, quem tem mais canal de contato.

    Quem foi marcado como público brasileiro sobe. Quando ninguém está marcado
    — o caso de qualquer busca dentro do Brasil — o campo vale 0 em todo mundo e
    a ordenação fica exatamente como era.
    """
    return sorted(
        leads,
        key=lambda l: (
            l.sinal_brasileiro >= 30,
            l.score if l.score is not None else -1,
            bool(l.emails) + bool(l.whatsapp) + bool(l.telefone),
            l.avaliacoes or 0,
        ),
        reverse=True,
    )


def _preencher_aba(ws, linhas: list[dict], campos: list[str], titulos: list[str]) -> None:
    ws.append(titulos)

    cabecalho_fundo = PatternFill("solid", fgColor="1F3864")
    for celula in ws[1]:
        celula.font = Font(bold=True, color="FFFFFF")
        celula.fill = cabecalho_fundo
        celula.alignment = Alignment(vertical="center")

    for linha in linhas:
        ws.append([linha.get(c, "") for c in campos])

    for idx, campo in enumerate(campos, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = LARGURAS.get(campo, 20)

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions


def exportar(leads: list[Lead], destino: str) -> tuple[Path, Path]:
    leads = _ordenar(leads)
    linhas = [l.to_row() for l in leads]
    campos = [c for c, _ in COLUNAS]
    titulos = [t for _, t in COLUNAS]

    base = Path(destino)
    base.parent.mkdir(parents=True, exist_ok=True)
    caminho_csv = base.with_suffix(".csv")
    caminho_xlsx = base.with_suffix(".xlsx")

    # utf-8-sig para o Excel em português abrir com acentuação correta
    with caminho_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(titulos)
        for linha in linhas:
            w.writerow([linha.get(c, "") for c in campos])

    wb = Workbook()
    ws = wb.active
    ws.title = "Leads"
    _preencher_aba(ws, linhas, campos, titulos)

    linhas_com_site = [l.to_row() for l in leads if l.site]
    linhas_sem_site = [l.to_row() for l in leads if not l.site]

    ws_com_site = wb.create_sheet("Com site")
    _preencher_aba(ws_com_site, linhas_com_site, campos, titulos)

    ws_sem_site = wb.create_sheet("Sem site")
    _preencher_aba(ws_sem_site, linhas_sem_site, campos, titulos)

    wb.save(caminho_xlsx)

    return caminho_csv, caminho_xlsx
