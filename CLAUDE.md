# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Idioma

Todo o código deste projeto é em português do Brasil: nomes de classes, funções,
variáveis, docstrings, comentários, flags da CLI e saída no terminal. Mantenha
esse padrão em qualquer código novo. Traduzir para inglês quebra a consistência
com o resto da base.

## Commands

Windows/PowerShell, Python 3.11, venv já existente em `.venv`. Sempre chame o
interpretador do venv explicitamente:

```powershell
# Instalação (só se .venv não existir)
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium

# Interface visual (o iniciar.bat faz isto e abre o navegador)
.\.venv\Scripts\python.exe -m webapp

# Servidor sem abrir navegador, porta fixa — o que usar ao depurar a web
.\.venv\Scripts\python.exe -m uvicorn webapp.server:app --host 127.0.0.1 --port 8765

# Execução completa pela CLI
.\.venv\Scripts\python.exe run.py --nicho "clinicas de estetica" --local "Belo Horizonte, MG" --oferta "gestao de trafego pago" --max 80

# Smoke test rápido (poucos leads, navegador visível para depurar o scraper)
.\.venv\Scripts\python.exe run.py --nicho "restaurantes japoneses" --local "Campinas, SP" --max 10 --max-por-busca 10 --saida teste_leads --ver-navegador

# Só o scraper, sem Ollama e sem visitar sites (iteração mais rápida)
.\.venv\Scripts\python.exe run.py --nicho X --local Y --max 10 --sem-ia --sem-enriquecimento
```

Não há suíte de testes, linter nem formatador configurados no repositório. A
verificação prática é rodar o smoke test acima. Não é um repositório git.

Para testar qualquer coisa **sem** depender do Google Maps, troque
`prospector.maps_scraper.buscar` por uma função que devolva `Lead`s falsos antes
de importar `webapp.server`. Termine a assinatura do dublê com `**kwargs`: a de
`buscar()` já cresceu várias vezes (`filtro_site`, `filtro_brasileiro`,
`lusofona`) e um dublê fixo passa a estourar `TypeError` dentro da thread do
job, que aparece como "0 leads" em vez de erro. Rode sempre com a cwd num diretório temporário e com
`PROSPECTADOR_HISTORICO` apontando para fora do projeto — senão o teste
sobrescreve o `historico.json` e os `leads.*` reais.

## Arquitetura

Pipeline linear de 4 etapas, orquestrado por [prospector/pipeline.py](prospector/pipeline.py).
Duas interfaces consomem o mesmo pipeline: `run.py` (CLI) e `webapp/` (web).

1. **Planejar** — `AgenteIA.gerar_queries()` expande nicho + local em N buscas.
2. **Coletar** — `maps_scraper.buscar()` roda o Google Maps no Chromium.
3. **Enriquecer** — `enrich.enriquecer()` visita os sites atrás de contatos.
4. **Qualificar** — `AgenteIA.qualificar()` preenche score, motivo e mensagem.

### O pipeline não escreve na tela

Nada abaixo de `pipeline.py` conhece terminal ou navegador: o progresso sai como
`Evento` para um `sink` ([prospector/eventos.py](prospector/eventos.py)). A CLI
liga um `SinkConsole` (que reconstrói as barras do rich); o servidor liga um sink
que publica para o navegador. **Adicionar saída nova é emitir evento, nunca
`print`/`console.print` dentro do pacote** — um `print` solto some na interface
web. Eventos de `progresso` carregam sempre valores absolutos (`atual`/`total`),
nunca incrementos.

### Cancelar não descarta trabalho

`executar()` recebe `deve_parar` e o repassa ao scraper, ao enriquecimento e à
qualificação. Quando ele vira verdadeiro, as etapas seguintes são puladas mas os
leads já coletados **são gravados no histórico e devolvidos** — o registro
acontece em `executar()`, fora do `_etapas()`, exatamente para sobreviver ao
cancelamento. `Cancelado` só é levantado antes de existir qualquer lead.

### Histórico

[prospector/historico.py](prospector/historico.py) mantém `historico.json`
(escrita atômica via `os.replace`, `threading.Lock` porque o servidor mexe nele
de várias threads). Guarda duas coisas que o pipeline não produz: `fase` (a
coluna do quadro) e `mensagem_editada`. Reencontrar uma empresa numa busca nova
**atualiza os dados e preserva esses dois campos, mais a base** — qualquer
mudança em `registrar()` precisa manter isso; mover card é decisão de quem
trabalha o funil, não da coleta. `salvar_mensagem()` grava `""` quando o texto é
igual ao da IA, para o campo voltar a acompanhar a IA numa requalificação futura.

### Bases: um quadro por nicho

Um lead pertence a uma **base** (`registro["base"]`) e, dentro dela, a uma
**fase** (`registro["fase"]`). Bases existem para não misturar nichos: Flooring
em North Carolina e Cleaning em Philadelphia são quadros separados. São criadas
**só à mão** — nem a busca nem o pipeline inventam base; a web manda o id
escolhido no formulário e a CLI manda o nome em `--base`, resolvido para id em
`executar_e_exportar()`.

Cada base tem as **próprias fases**, então o lead guarda o `id` da fase, nunca o
nome: renomear é trocar uma string na base, sem varrer lead nenhum. Como as fases
não são compartilhadas, a aba **Geral** não pode ser um kanban — ela lista todos
os leads com etiqueta de base e fase. `mover_lead()` recusa fase que não seja da
base do lead; é a única barreira contra um card acabar numa coluna de outro
quadro.

Apagar base ou fase **nunca apaga lead**: a base some e os leads ficam sem base
(visíveis só no Geral); a fase some e os leads dela vão para a primeira coluna.
A última fase de uma base não pode ser removida — a próxima busca não teria onde
colocar os leads.

`historico.json` está na versão 2. `_migrar_para_v2()` roda sozinho ao carregar
um arquivo v1: grava `historico.v1.bak.json` ao lado, cria uma base por par
nicho/região encontrado nos leads antigos e converte o antigo booleano
`contatado` na fase de mesmo nome. Mexer no formato de novo exige repetir esse
par backup + migração.

Com `cfg.pular_conhecidos`, as chaves conhecidas vão para `maps_scraper.buscar()`
e são descartadas logo após abrir a ficha, antes de contarem para `max_total` —
a busca continua até juntar o total pedido de leads inéditos.

### Filtrar é trabalho da coleta, não da exportação

`cfg.filtro_site` também vai para `maps_scraper.buscar()` e é aplicado ficha a
ficha, pelo mesmo motivo de `pular_conhecidos`: descartado não ocupa vaga em
`max_total`, e a busca segue trocando de query até juntar o total pedido. Filtrar
depois da coleta fazia um pedido de 60 leads terminar com 1 em nicho onde quase
todo mundo tem site, e o caminho de cancelamento devolvia a lista **sem** filtrar.
Qualquer filtro novo que decida se um lead entra na lista pertence a esse mesmo
ponto — nunca a um passo posterior em `_etapas()`.

[prospector/sites.py](prospector/sites.py) é a regra única do que conta como
site: `passa_no_filtro()` na coleta e `tipo_de_site()` nos resumos e no
enriquecimento. "Sem site" significa **sem site próprio** — Instagram, Facebook,
TikTok, wa.me e linktree contam como `social`, não como site, e por isso entram
na lista de "sem site". Ao mexer nos conjuntos de domínios, lembre que eles
decidem quem entra na coleta, não só como o lead é exibido.

### Público brasileiro

[prospector/brasileiros.py](prospector/brasileiros.py) pontua o quanto o negócio
parece **falar com** brasileiro (categoria do Maps, nome em português, telefone
+55, `lang` do site) e escreve `sinal_brasileiro` + `motivo_brasileiro` no lead.
Não é nacionalidade do dono, e o motivo existe para o usuário conferir o palpite.

`cfg.filtro_brasileiro` tem três estados: `todos` (nem calcula), `marcar` (anota
e ordena por cima) e `so_br` (descarta durante a coleta). Três detalhes que
custaram medição no Maps e não devem ser desfeitos sem repetir a medição:

- **Só ligar o filtro não basta.** `brazilian cleaning Orlando` e `cleaning
  Orlando` devolvem listas quase sem interseção, e a genérica não trouxe uma
  empresa brasileira em 50 fichas. Por isso `so_br` também troca as queries
  (`_queries_brasileiras()` nas regras, instrução extra no prompt da IA).
- **`marcar` existe porque prospecção dentro do Brasil zera o valor do sinal**:
  lá todo lead tem +55 e nome em português. Em vez de adivinhar o país pela
  região digitada — `Campinas, SP` contra `Orlando, FL` —, quem liga é o usuário.
- **Em região lusófona (`regiao_lusofona()`) os sinais de idioma valem zero**:
  em Lisboa todo negócio da rua tem nome e site em português; só "brasileiro" na
  categoria/nome e telefone +55 separam alguém.

A ordenação (`historico.listar` e `exporter._ordenar`) põe marcado na frente.
Como o campo é 0 em todo mundo quando o modo está desligado, isso é um no-op nas
buscas normais — mantenha essa propriedade ao mexer na chave de ordenação.

### Servidor web

[webapp/server.py](webapp/server.py): uma busca é um `Job` numa thread própria —
obrigatório, porque o Playwright síncrono não roda dentro do event loop do
asyncio. Só um job por vez (409 se já houver um). Os eventos vão para os
assinantes por SSE; cada assinante recebe um snapshot do que já passou **e** uma
fila nova sob o mesmo lock, então recarregar a página no meio da busca reconecta
sem perder nem duplicar eventos.

O download é gerado na hora a partir do histórico (para sair com as mensagens
editadas) e vai para `exports/`, não para o `leads.csv` da raiz que a CLI usa.

### Contrato central: a IA nunca pode derrubar a execução

[prospector/ai.py](prospector/ai.py) tem dois caminhos para cada capacidade: Ollama
local e regras determinísticas. `AgenteIA.__init__` decide `self.ativo` fazendo
`GET /api/tags` e conferindo se o modelo exato de `cfg.modelo` está na lista —
Ollama no ar com outro modelo baixado conta como indisponível. A degradação
acontece em três níveis, todos capturando `Exception` e caindo para regras:
no startup, na geração de queries, e por lote na qualificação (`TAMANHO_LOTE = 8`
leads por chamada). Qualquer recurso novo de IA precisa manter esse contrato —
um par método-Ollama + método-regras, sem exceção que escape.

Saída estruturada: o schema Pydantic vai em `format` no `/api/chat`; se a
requisição responder >= 400, há um retry com `format: "json"` (Ollama antigo), e
o parse do conteúdo tem fallback de recorte entre a primeira `{` e a última `}`.

### Lead é mutado in-place

`Lead` ([prospector/models.py](prospector/models.py)) é uma dataclass mutável que
atravessa o pipeline inteiro. `enrich.enriquecer()` e `AgenteIA.qualificar()`
**não retornam nada** — escrevem direto nos objetos da lista. A deduplicação
entre buscas usa `Lead.chave` (sha1 de nome+endereço, com telefone no lugar do
endereço quando ele vem vazio).

Para adicionar uma coluna na planilha são três lugares: o campo em `Lead`, a
tupla `(campo, "Título")` em `COLUNAS`, e a largura em `LARGURAS` dentro de
[prospector/exporter.py](prospector/exporter.py).

### Scraper: acoplado ao DOM do Google Maps

[prospector/maps_scraper.py](prospector/maps_scraper.py) usa a API síncrona do
Playwright, uma única página, navegando ficha a ficha. Depende de seletores
ofuscados do Google (`div[role="feed"]`, `a.hfpxzc`, `h1.DUwDvf`, `div.F7nice`,
`button[data-item-id^="phone:tel:"]`, `a[data-item-id="authority"]`). Esses
seletores são o ponto de falha mais provável do projeto: quando a coleta voltar
vazia, suspeite deles primeiro e depure com `--ver-navegador`. O scroll do painel
para quando a lista não cresce em 4 rodadas seguidas. Há pausas aleatórias e um
user-agent fixo para reduzir bloqueio; rodadas grandes ainda podem gerar CAPTCHA.

O bloco de contatos monta **depois** do `h1`, por isso a ficha só é lida após
`INFO_PRONTA` (`[data-item-id]`) aparecer: ler antes devolve site vazio e
transforma empresa com site em "sem site", que é o erro que o filtro não pode
cometer. `_extrair_site()` tenta `SELETORES_SITE` em ordem justamente porque um
"" aqui é interpretado como ausência de site pelo resto do programa.

Buscas do mesmo nicho se sobrepõem muito, então `_coletar_links()` recebe os
lugares já abertos e devolve só os inéditos, identificados por `RE_ID_LOCAL`
(o `!1s0x...:0x...` da URL, estável entre queries). A parada por
`sem_crescimento` continua olhando o feed inteiro: uma rodada que só traz
repetidos ainda é crescimento da lista.

### Enriquecimento: concorrente e tolerante a falha

[prospector/enrich.py](prospector/enrich.py) usa `ThreadPoolExecutor` (httpx
síncrono, `verify=False`) tentando uma lista fixa de caminhos por domínio
(`/`, `/contato`, `/contact`, `/fale-conosco`, ...), parando cedo quando já tem
e-mail + WhatsApp + Instagram. Quando o "site" cadastrado no Maps é na verdade
uma rede social, o handle é extraído da própria URL e a página não é visitada.
Há filtros anti-lixo (`EMAIL_RUIM`, `IGNORAR_SOCIAL`, `RE_ARQUIVO`) — ao mexer
nas regex, verifique nesses conjuntos antes de assumir que um handle sumiu.

### Config

[prospector/config.py](prospector/config.py) chama `load_dotenv()` e usa
`os.getenv` como valor default dos campos da dataclass — os defaults são
avaliados **uma vez, no import do módulo**. Mudança em `.env` exige reiniciar o
processo. Flags da CLI e o formulário da web cobrem o comportamento por
execução; `.env` cobre modelo, URL/timeout do Ollama, concorrência,
`PROSPECTADOR_HISTORICO` e `PROSPECTADOR_PORTA`.

## Saída

`leads.csv` (delimitador `;`, `utf-8-sig` para o Excel em pt-BR abrir com
acentuação) e `leads.xlsx` com três abas: `Leads`, `Com site`, `Sem site`.
Ordenação: score desc, depois quantidade de canais de contato, depois avaliações.
A CLI escreve na raiz; a web escreve em `exports/`. Tudo isso, mais
`historico.json`, está no `.gitignore`.

## Interface

Sem framework, sem build, sem dependência externa: três arquivos em
[webapp/static/](webapp/static/) servidos direto. O CSS usa tokens em `:root`
com sobrescrita em `@media (prefers-color-scheme: dark)` — ao acrescentar cor,
defina nos dois blocos, nunca só no escuro. Dados vindos do usuário vão para a
tela via `textContent`/`createElement`, nunca `innerHTML`.

## Restrições do projeto

Sem API paga e sem serviço externo de IA — é uma decisão de design, não uma
pendência. Não introduza SDK da Anthropic, OpenAI ou API oficial de places sem
o usuário pedir explicitamente. O único serviço consumido é o Ollama em
`127.0.0.1`, e ele é opcional.
