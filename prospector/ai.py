"""Camada local de inteligencia: Ollama ou regras deterministicas."""

from __future__ import annotations

import json
import re
from typing import TypeVar

import httpx
from pydantic import BaseModel, Field

from .config import Config
from .eventos import Evento, Sink, sink_nulo
from .models import Lead

TAMANHO_LOTE = 8
T = TypeVar("T", bound=BaseModel)


class PlanoDeBusca(BaseModel):
    queries: list[str] = Field(
        description="Buscas prontas para colar no Google Maps, uma por linha."
    )


class AnaliseLead(BaseModel):
    indice: int = Field(description="Indice do lead exatamente como veio na entrada.")
    score: int = Field(description="Nota de 0 a 100 de aderencia do lead a oferta.")
    motivo: str = Field(description="Uma frase curta justificando o score.")
    mensagem: str = Field(
        description="Primeira abordagem por WhatsApp, em portugues, no maximo 4 linhas."
    )


class LoteDeAnalises(BaseModel):
    analises: list[AnaliseLead]


class AgenteIA:
    """Usa um modelo local via Ollama. Sem Ollama, cai para regras locais."""

    def __init__(self, cfg: Config, sink: Sink = sink_nulo):
        self.cfg = cfg
        self.sink = sink
        self.ativo = False
        self.erro_local = ""
        self._client: httpx.Client | None = None

        if not cfg.usar_ia:
            return

        self._client = httpx.Client(
            base_url=cfg.ollama_url.rstrip("/"), timeout=cfg.ollama_timeout
        )
        self.ativo = self._ollama_pronto()

    @property
    def modo(self) -> str:
        if not self.cfg.usar_ia:
            return "desativada"
        return "Ollama local" if self.ativo else "regras locais"

    def _ollama_pronto(self) -> bool:
        if not self._client:
            return False
        try:
            resp = self._client.get("/api/tags")
            resp.raise_for_status()
            modelos = {
                item.get("name", "")
                for item in resp.json().get("models", [])
                if isinstance(item, dict)
            }
            if self.cfg.modelo not in modelos:
                self.erro_local = (
                    f"modelo '{self.cfg.modelo}' nao encontrado no Ollama. "
                    f"Rode: ollama pull {self.cfg.modelo}"
                )
                return False
            return True
        except Exception as e:  # noqa: BLE001
            self.erro_local = (
                f"Ollama nao respondeu em {self.cfg.ollama_url}. "
                "Abra o Ollama ou use --sem-ia."
            )
            if str(e):
                self.erro_local += f" Detalhe: {e}"
            return False

    def _chat_json(self, prompt: str, schema: type[T], num_predict: int) -> T:
        if not self._client:
            raise RuntimeError("cliente Ollama indisponivel")

        payload = {
            "model": self.cfg.modelo,
            "stream": False,
            "format": schema.model_json_schema(),
            "options": {"temperature": 0.2, "num_predict": num_predict},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Responda somente com JSON valido no formato solicitado. "
                        "Nao use markdown, comentarios ou texto fora do JSON."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        }
        resp = self._client.post("/api/chat", json=payload)
        if resp.status_code >= 400:
            payload_simples = {**payload, "format": "json"}
            resp = self._client.post("/api/chat", json=payload_simples)
        resp.raise_for_status()
        conteudo = resp.json()["message"]["content"].strip()
        try:
            dados = json.loads(conteudo)
        except json.JSONDecodeError:
            inicio = conteudo.find("{")
            fim = conteudo.rfind("}")
            if inicio < 0 or fim < inicio:
                raise
            dados = json.loads(conteudo[inicio : fim + 1])
        return schema.model_validate(dados)

    def gerar_queries(self) -> list[str]:
        """Expande nicho + local em buscas para o Google Maps."""
        if not self.cfg.usar_ia or not self.ativo:
            return self._usar_fallback()

        prompt = (
            f"Preciso prospectar empresas do nicho: {self.cfg.nicho}\n"
            f"Regiao alvo: {self.cfg.local}\n"
            f"O que eu vendo para elas: {self.cfg.oferta}\n\n"
            f"Gere {self.cfg.n_queries} buscas para o Google Maps que juntas cubram o "
            "maximo possivel desse nicho nessa regiao.\n"
            "Regras:\n"
            "- O Google Maps busca em volta de um ponto: se a regiao for um estado, "
            "uma provincia ou um pais, quebre em cidades reais e diferentes dessa "
            "regiao, uma por busca. Duas buscas na mesma cidade devolvem a mesma "
            "lista e desperdicam a coleta.\n"
            "- Escreva cada busca no idioma que se usa para procurar naquela regiao "
            "(regiao no Brasil: portugues; nos EUA: ingles; e assim por diante).\n"
            "- Varie tambem sinonimos do nicho e subespecialidades.\n"
            "- Cada busca deve ser curta, como uma pessoa digitaria no Google Maps."
        )

        # O termo da busca é a alavanca principal para achar negócio de
        # brasileiro fora do Brasil: "brazilian cleaning Orlando" e "cleaning
        # Orlando" devolvem listas quase sem interseção.
        if self.cfg.filtro_brasileiro == "so_br":
            prompt += (
                "\n\nIMPORTANTE: quero empresas que atendem a comunidade brasileira "
                "nessa regiao. Inclua nas buscas as palavras que essas empresas usam "
                "para serem achadas por brasileiros: 'brasileiro'/'brazilian' junto do "
                "nicho, e termos do dia a dia brasileiro quando couber (acai, "
                "churrascaria, mercadinho brasileiro, salgados, mega hair, faxina). "
                "Misture buscas em portugues e no idioma local."
            )

        try:
            resp = self._chat_json(prompt, PlanoDeBusca, num_predict=1200)
            queries = [q.strip() for q in resp.queries if q.strip()]
            return queries[: self.cfg.n_queries] or self._usar_fallback()
        except Exception as e:  # noqa: BLE001
            self.sink(
                Evento(
                    "aviso",
                    etapa=1,
                    texto=f"[IA local] falha ao gerar buscas ({e}); usando regras locais.",
                )
            )
            return self._usar_fallback()

    def _usar_fallback(self) -> list[str]:
        """Buscas por regras + o aviso do que elas não conseguem fazer.

        As variantes deterministicas mudam só o texto, nunca o ponto do mapa: o
        Google Maps busca em volta de um centro, então uma regiao grande fica
        coberta pela vizinhanca de uma cidade só. Quem sabe quebrar um estado em
        cidades e' o modelo local; sem ele, quem precisa saber disso e' o usuario.
        """
        queries = self._queries_deterministicas()
        if len(queries) > 1:
            self.sink(
                Evento(
                    "aviso",
                    etapa=1,
                    texto=(
                        "Sem IA local as buscas mudam so o texto, nao a regiao - todas "
                        "caem no mesmo ponto do mapa. Se a regiao for um estado ou pais, "
                        "rode uma busca por cidade para achar mais empresas."
                    ),
                )
            )
        return queries

    def _queries_deterministicas(self) -> list[str]:
        nicho = self.cfg.nicho.strip()
        local = self.cfg.local.strip()
        if self.cfg.filtro_brasileiro == "so_br":
            candidatos = self._queries_brasileiras(nicho, local)
        else:
            candidatos = [
                f"{nicho} em {local}",
                f"{nicho} {local}",
                f"{nicho} perto de {local}",
                f"empresas de {nicho} em {local}",
                f"servicos de {nicho} em {local}",
                f"especialistas em {nicho} {local}",
            ]
        unicos: list[str] = []
        for q in candidatos:
            q = re.sub(r"\s+", " ", q).strip()
            if q and q.casefold() not in {u.casefold() for u in unicos}:
                unicos.append(q)
        return unicos[: max(1, self.cfg.n_queries)]

    def _queries_brasileiras(self, nicho: str, local: str) -> list[str]:
        """Buscas com o termo que faz o negocio brasileiro aparecer.

        Medido no Maps: `brazilian cleaning services Orlando` e `cleaning
        services Orlando` devolvem listas quase sem intersecao, e a segunda nao
        traz nenhuma empresa brasileira em 50 fichas. Sem essas palavras o filtro
        de publico brasileiro colhe zero, por melhor que ele seja.

        A busca generica vai por ultimo de proposito: ela e' o resgate de quem so
        se entrega pelo nome (Cabeloliso, Faxina Express) e so roda se as
        anteriores nao tiverem completado a cota.
        """
        return [
            f"brazilian {nicho} {local}",
            f"{nicho} brasileiro em {local}",
            f"{nicho} brasileiros {local}",
            f"empresa brasileira de {nicho} em {local}",
            f"brasileiros em {local} {nicho}",
            f"{nicho} em {local}",
        ]

    def qualificar(self, leads: list[Lead], on_progress=None, deve_parar=None) -> None:
        """Preenche score, motivo e mensagem de abordagem de cada lead, in-place."""
        if not self.cfg.usar_ia or not leads:
            return

        if not self.ativo:
            self._qualificar_por_regras(leads, on_progress=on_progress)
            return

        for inicio in range(0, len(leads), TAMANHO_LOTE):
            if deve_parar and deve_parar():
                return
            lote = leads[inicio : inicio + TAMANHO_LOTE]
            try:
                self._qualificar_lote_ollama(lote)
            except Exception as e:  # noqa: BLE001
                self.sink(
                    Evento(
                        "aviso",
                        etapa=4,
                        texto=(
                            f"[IA local] lote {inicio // TAMANHO_LOTE + 1} falhou "
                            f"({e}); usando regras locais nesse lote."
                        ),
                    )
                )
                self._qualificar_por_regras(lote)
            if on_progress:
                on_progress(len(lote))

    def _qualificar_lote_ollama(self, lote: list[Lead]) -> None:
        entrada = [
            {
                "indice": i,
                "nome": l.nome,
                "categoria": l.categoria,
                "endereco": l.endereco,
                "nota": l.nota,
                "avaliacoes": l.avaliacoes,
                "tem_site": bool(l.site),
                "site": l.site,
                "tem_email": bool(l.emails),
                "tem_telefone": bool(l.telefone or l.whatsapp),
                "instagram": l.instagram,
                "descricao_site": l.descricao_site[:400],
                "publico_brasileiro": l.sinal_brasileiro >= 30,
                "idioma_do_site": l.idioma_site,
            }
            for i, l in enumerate(lote)
        ]

        prompt = (
            f"Sou um prestador de servico prospectando clientes.\n"
            f"O que eu vendo: {self.cfg.oferta}\n"
            f"Nicho alvo: {self.cfg.nicho} - regiao: {self.cfg.local}\n\n"
            "Abaixo estao empresas encontradas no Google Maps. Para CADA uma, gere:\n"
            "1) score de 0 a 100 para aderencia a oferta;\n"
            "2) motivo curto e concreto;\n"
            "3) mensagem inicial por WhatsApp, no maximo 4 linhas, sem prometer "
            "resultado e terminando com uma pergunta simples.\n\n"
            "Idioma da mensagem: portugues do Brasil quando 'publico_brasileiro' for "
            "true; caso contrario, o idioma que se fala na regiao do lead. Nao "
            "escreva em portugues para quem nao vai entender.\n\n"
            "Mantenha exatamente o mesmo indice de entrada.\n\n"
            f"Empresas:\n{json.dumps(entrada, ensure_ascii=False, indent=1)}"
        )

        resp = self._chat_json(prompt, LoteDeAnalises, num_predict=5000)
        for analise in resp.analises:
            if 0 <= analise.indice < len(lote):
                lead = lote[analise.indice]
                lead.score = max(0, min(100, analise.score))
                lead.motivo_score = analise.motivo.strip()
                lead.mensagem_abordagem = analise.mensagem.strip()

    def _qualificar_por_regras(self, leads: list[Lead], on_progress=None) -> None:
        for lead in leads:
            lead.score = self._score_regras(lead)
            lead.motivo_score = self._motivo_regras(lead)
            lead.mensagem_abordagem = self._mensagem_regras(lead)
            if on_progress:
                on_progress(1)

    def _score_regras(self, lead: Lead) -> int:
        score = 45

        if self._parece_aderente(lead):
            score += 15
        if lead.site:
            score += 8
        else:
            score += 6
        if lead.emails:
            score += 8
        if lead.whatsapp or lead.telefone:
            score += 10
        if lead.instagram:
            score += 5

        avaliacoes = lead.avaliacoes or 0
        if avaliacoes >= 100:
            score += 12
        elif avaliacoes >= 30:
            score += 8
        elif avaliacoes >= 5:
            score += 4

        if lead.nota is not None:
            if lead.nota >= 4.5:
                score += 5
            elif lead.nota < 3.8:
                score -= 8

        if not (lead.telefone or lead.whatsapp or lead.emails):
            score -= 15

        return max(0, min(100, score))

    def _parece_aderente(self, lead: Lead) -> bool:
        texto = f"{lead.nome} {lead.categoria}".casefold()
        termos = [
            t
            for t in re.split(r"\W+", self.cfg.nicho.casefold())
            if len(t) >= 4 and t not in {"para", "com", "servicos"}
        ]
        return any(t in texto for t in termos)

    def _motivo_regras(self, lead: Lead) -> str:
        sinais: list[str] = []
        if self._parece_aderente(lead):
            sinais.append("categoria parece aderente ao nicho")
        if lead.avaliacoes:
            sinais.append(f"{lead.avaliacoes} avaliacoes no Maps")
        if lead.site:
            sinais.append("tem site")
        else:
            sinais.append("nao mostra site no cadastro")
        if lead.emails or lead.whatsapp or lead.telefone:
            sinais.append("tem canal de contato")
        else:
            sinais.append("sem contato claro")
        return "; ".join(sinais[:3]) + "."

    def _mensagem_regras(self, lead: Lead) -> str:
        nome = lead.nome.strip() or "sua empresa"
        if self._escrever_em_ingles(lead):
            return self._mensagem_em_ingles(lead, nome)

        sinal = "o cadastro de voces no Google Maps"
        if lead.site and not lead.emails:
            sinal = "o site de voces e nao encontrei um e-mail claro para contato"
        elif not lead.site:
            sinal = "que o cadastro de voces nao mostra um site"
        elif lead.avaliacoes:
            sinal = f"que voces ja tem {lead.avaliacoes} avaliacoes no Google"

        return (
            f"Oi, tudo bem? Vi a {nome} no Google Maps e notei {sinal}.\n"
            f"Trabalho com {self.cfg.oferta} para negocios desse perfil.\n"
            "Faz sentido conversar rapidamente para ver se isso ajudaria voces?"
        )

    def _escrever_em_ingles(self, lead: Lead) -> bool:
        """Só quando o caso é claro: telefone dos EUA/Canada e nenhum sinal de BR.

        Na duvida fica em portugues — mandar portugues para quem fala ingles
        constrange menos do que o contrario, e Portugal cai fora daqui porque o
        telefone de la nao comeca com +1.
        """
        telefone = (lead.telefone or lead.whatsapp).replace(" ", "")
        return telefone.startswith("+1") and lead.sinal_brasileiro < 30

    def _mensagem_em_ingles(self, lead: Lead, nome: str) -> str:
        sinal = "your Google Maps listing"
        if lead.site and not lead.emails:
            sinal = "your website, but I could not find a clear contact email"
        elif not lead.site:
            sinal = "your listing does not show a website"
        elif lead.avaliacoes:
            sinal = f"you already have {lead.avaliacoes} reviews on Google"

        return (
            f"Hi! I came across {nome} on Google Maps and noticed {sinal}.\n"
            f"I work with {self.cfg.oferta} for businesses like yours.\n"
            "Would it make sense to have a quick chat to see if that could help?"
        )
