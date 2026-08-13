"""Detecção de negócio voltado ao público brasileiro.

O Google Maps não diz a nacionalidade de ninguém. O que dá para ler é se o
negócio **fala com** brasileiro: a categoria que o próprio Maps atribui, o nome
em português, o telefone e o idioma do site. Um brasileiro dono de uma empresa
com nome e site em inglês é invisível aqui — o `motivo_brasileiro` existe para
você conferir o palpite em vez de confiar cego nele.

Cuidado embutido: "Brazilian" no nome às vezes é o **serviço**, não o dono —
"Brazilian Blowout" e "Brazilian Wax" são técnicas vendidas em salão de qualquer
dono, e por isso derrubam o peso do nome em vez de aumentá-lo.

Limite conhecido: português não é exclusividade do Brasil. Uma padaria
portuguesa em Boston pontua pelos mesmos sinais de nome e idioma que uma
brasileira. Onde o Maps diz "brasileiro" na categoria ou o telefone é +55 não há
dúvida; no resto, o `motivo_brasileiro` mostra em que o palpite se apoiou.
"""

from __future__ import annotations

import re
import unicodedata

from .models import Lead
from .sites import dominio

# A partir daqui o lead entra na lista quando o filtro está ligado.
CORTE = 30

RE_BRASILEIRO = re.compile(r"brasileir|brazilian|brasil\b|brazil\b", re.I)

# Serviços que se chamam "brazilian" sem ter nada de brasileiro por trás.
RE_ARMADILHA = re.compile(r"blowout|wax|keratin|botox|bikini", re.I)

# Palavras que praticamente só aparecem em português. Ficaram de fora, de
# propósito, as que o espanhol escreve igual ou quase igual (casa, mercado,
# pastel, sabor, estetica, delicia, churrasco, brasa, panificadora): nos EUA
# elas casariam com meio comércio latino e enchariam a lista de ruído.
PALAVRAS_PT = (
    # comida
    "churrascaria", "padaria", "mercearia", "mercadinho", "acai", "pao",
    "paozinho", "coxinha", "salgado", "salgados", "feijoada", "brigadeiro",
    "doceria", "sorveteria", "lanchonete", "boteco", "botequim", "quitanda",
    "guarana", "espetinho", "rodizio", "tempero", "temperos", "tapiocaria",
    # beleza
    "cabelo", "cabelos", "cabeleireiro", "cabeleireira", "beleza", "salao",
    "unhas", "sobrancelha", "sobrancelhas", "escova", "alisamento", "tranca",
    "trancas", "mega hair",
    # serviços
    "limpeza", "faxina", "diarista", "construcao", "mudanca", "jardinagem",
    "encanador", "dedetizacao", "marido de aluguel",
    # gentílicos e afeto
    "mineiro", "mineira", "carioca", "paulista", "baiano", "baiana",
    "nordestino", "cearense", "capixaba", "pernambucano", "sertanejo",
    "tupiniquim", "saudade", "aconchego", "recanto", "cantinho",
)

# Onde o português é a língua local: ali "nome em português" e "site em
# português" não separam nada — todo negócio da rua tem os dois.
LUGARES_LUSOFONOS = (
    "portugal", "lisboa", "porto", "braga", "coimbra", "faro", "algarve",
    "madeira", "acores", "aveiro", "cascais", "sintra", "guimaraes", "setubal",
    "brasil", "brazil", "angola", "mocambique", "cabo verde",
)


def _normalizar(texto: str) -> str:
    """Minúsculas e sem acento: negócio no exterior costuma largar o acento."""
    sem_acento = unicodedata.normalize("NFKD", texto or "")
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return sem_acento.casefold()


def _casa_palavra(texto: str, palavra: str) -> bool:
    """Palavra longa casa dentro de composto (`cabeloliso`); curta só inteira.

    Sem esse corte, `pao` acharia "Paola" e `acai` acharia qualquer coisa.
    """
    if len(palavra) >= 6 or " " in palavra:
        return palavra in texto
    return re.search(rf"\b{re.escape(palavra)}\b", texto) is not None


def regiao_lusofona(local: str) -> bool:
    alvo = _normalizar(local)
    return any(lugar in alvo for lugar in LUGARES_LUSOFONOS)


def avaliar(lead: Lead, lusofona: bool = False) -> None:
    """Preenche `sinal_brasileiro` e `motivo_brasileiro` no lead, in-place.

    Pode rodar duas vezes: na coleta (só nome, categoria e telefone) e de novo
    depois do enriquecimento, quando o idioma do site já é conhecido.
    """
    pontos = 0
    motivos: list[str] = []

    nome = _normalizar(lead.nome)
    categoria = _normalizar(lead.categoria)

    # 1. Categoria do próprio Maps ("Restaurante brasileiro"): o sinal mais forte.
    if RE_BRASILEIRO.search(categoria):
        pontos += 45
        motivos.append(f"categoria do Maps: {lead.categoria}")

    # 2. Nome citando Brasil — a menos que seja nome de serviço.
    if RE_BRASILEIRO.search(nome):
        if RE_ARMADILHA.search(nome):
            pontos += 5
            motivos.append("nome cita Brazilian, mas parece nome de servico")
        else:
            pontos += 30
            motivos.append("nome cita Brasil")

    # 3. Palavras em português no nome. Como a lista só tem palavra que o
    # espanhol e o inglês não usam, uma única já basta para o lead entrar —
    # "Faxina Express" e "Cabeloliso" não têm outro sinal além do nome. Em país
    # lusófono isso não separa nada e vale zero.
    achadas = [p for p in PALAVRAS_PT if _casa_palavra(nome, p)]
    if achadas and not lusofona:
        pontos += min(45, 30 + 10 * (len(achadas) - 1))
        motivos.append(f"nome em portugues ({', '.join(achadas[:3])})")

    # 4. Telefone brasileiro cadastrado num negócio de fora: sinal e tanto.
    if lead.telefone.replace(" ", "").startswith("+55"):
        pontos += 40
        motivos.append("telefone brasileiro")

    # 5. Site .br e idioma do site (preenchidos pelo enriquecimento).
    host = dominio(lead.site)
    if host.endswith(".br"):
        pontos += 30
        motivos.append("dominio .br")
    if lead.idioma_site.lower().startswith("pt") and not lusofona:
        pontos += 35
        motivos.append("site em portugues")

    lead.sinal_brasileiro = max(0, min(100, pontos))
    lead.motivo_brasileiro = "; ".join(motivos)


def parece_brasileiro(lead: Lead) -> bool:
    return lead.sinal_brasileiro >= CORTE


def ativo(filtro: str) -> bool:
    """Prospecção dentro do Brasil não deve nem calcular o sinal.

    Lá todo lead tem telefone +55 e nome em português: o selo apareceria em cada
    card sem separar nada. Em vez de adivinhar o país pela região digitada — e
    errar em "Campinas, SP" contra "Orlando, FL" —, quem liga é o usuário.
    """
    return filtro in ("marcar", "so_br")


def passa_no_filtro(lead: Lead, filtro: str) -> bool:
    """Só `so_br` descarta; `marcar` apenas anota o sinal e deixa passar."""
    if filtro == "so_br":
        return parece_brasileiro(lead)
    return True
