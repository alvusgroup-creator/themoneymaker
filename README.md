# Prospectador

Ferramenta local de prospeccao B2B. Voce informa um nicho, uma regiao e a sua
oferta; o programa pesquisa empresas no Google Maps, visita os sites encontrados,
extrai contatos publicos, pontua os leads e exporta uma planilha.

Este projeto nao usa Claude nem Anthropic. A parte de inteligencia roda de duas
formas:

- Com Ollama local, usando um modelo baixado no seu PC.
- Sem Ollama, por regras locais simples.

> Observacao: o programa acessa Google Maps e sites publicos pela internet. O
> "local" aqui significa sem API paga/externa de IA e sem chave da Claude.

## Como funciona

| # | Etapa | Quem faz |
|---|-------|----------|
| 1 | Expande nicho + regiao em buscas complementares | Ollama local ou regras |
| 2 | Coleta nome, telefone, endereco, site e nota no Google Maps | Playwright |
| 3 | Visita o site da empresa atras de e-mail, WhatsApp e redes sociais | httpx + BeautifulSoup |
| 4 | Da nota de 0 a 100 e escreve uma primeira abordagem | Ollama local ou regras |

## Instalacao

Se o ambiente virtual ja existe nesta pasta, pule para "Uso rapido".

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

## Uso rapido (interface visual)

De um duplo clique em **`iniciar.bat`**. Ele sobe o servidor local e abre a
interface no navegador em `http://127.0.0.1:8765`.

Na tela voce preenche nicho, regiao e oferta, clica em **Buscar leads** e
acompanha a coleta ao vivo: a etapa atual, a barra de progresso e o log. Os
leads aparecem como cartoes com score, contatos e a mensagem de abordagem.

O que da para fazer por ali:

- **Marcar como contatado** — fica salvo entre sessoes, nao so nesta janela.
- **Editar a mensagem** de abordagem — a versao editada e a que sai na planilha.
  O botao "Restaurar original" volta para o texto da IA.
- **Nao repetir leads ja prospectados** — ligado por padrao. As empresas que ja
  estao no historico sao descartadas durante a coleta, entao a busca continua
  ate juntar o total pedido de leads *ineditos*.
- **Cancelar** no meio da busca sem perder nada: o que ja foi coletado e
  gravado no historico.
- **Baixar CSV/Excel** da busca atual ou do historico inteiro. Os arquivos vao
  para `exports/`.

O historico fica em `historico.json`, na raiz do projeto. Apagar esse arquivo
zera o "ja prospectado" e as marcacoes de contatado.

A porta pode ser trocada com `PROSPECTADOR_PORTA=9000` no `.env`.

## IA 100% local com Ollama

1. Instale o Ollama no Windows.
2. Baixe um modelo local:

```powershell
ollama pull llama3.1:8b
```

3. Deixe o Ollama aberto/rodando.

O `.env` padrao ja esta assim:

```env
PROSPECTADOR_MODELO=llama3.1:8b
OLLAMA_BASE_URL=http://127.0.0.1:11434
PROSPECTADOR_OLLAMA_TIMEOUT=120
PROSPECTADOR_CONCORRENCIA=8
```

Se seu PC for mais fraco, use um modelo menor. Se quiser mais qualidade e tiver
RAM/VRAM, use um modelo maior, mas lembre de baixar com `ollama pull` e trocar
`PROSPECTADOR_MODELO`.

## Uso pela linha de comando

A CLI continua funcionando igual, para quem prefere o terminal ou quer automatizar.
Exemplo com IA local ou regras locais:

```powershell
.\.venv\Scripts\python.exe run.py `
  --nicho "clinicas de estetica" `
  --local "Belo Horizonte, MG" `
  --oferta "gestao de trafego pago e agendamento automatico por WhatsApp" `
  --max 80
```

Ele gera:

- `leads.csv`
- `leads.xlsx`

Os melhores leads ficam no topo da planilha.

## Modo scraper puro

Se voce quiser somente coletar dados, sem pontuar nem gerar mensagem:

```powershell
.\.venv\Scripts\python.exe run.py `
  --nicho "clinicas de estetica" `
  --local "Belo Horizonte, MG" `
  --max 50 `
  --sem-ia
```

## Teste pequeno recomendado

Antes de rodar uma lista grande, teste com poucos leads:

```powershell
.\.venv\Scripts\python.exe run.py `
  --nicho "restaurantes japoneses" `
  --local "Campinas, SP" `
  --oferta "criacao de campanhas locais para aumentar reservas pelo WhatsApp" `
  --max 10 `
  --max-por-busca 10 `
  --saida teste_leads `
  --ver-navegador
```

## Opcoes

| Flag | Padrao | O que faz |
|------|--------|-----------|
| `--nicho` | obrigatorio | O nicho que voce quer prospectar |
| `--local` | obrigatorio | Cidade/regiao alvo |
| `--oferta` | generico | O que voce vende; melhora score e mensagem |
| `--max` | 100 | Teto de leads na lista final |
| `--max-por-busca` | 60 | Teto de fichas abertas por busca individual |
| `--buscas` | 6 | Quantas buscas serao geradas |
| `--saida` | `leads` | Nome base dos arquivos |
| `--ver-navegador` | desligado | Mostra o Chromium durante a coleta |
| `--sem-ia` | desligado | So coleta/exporta, sem score/mensagem |
| `--sem-enriquecimento` | desligado | Nao visita sites; mais rapido, menos contatos |
| `--com-site` | desligado | Coleta somente empresas com site proprio |
| `--sem-site` | desligado | Coleta somente empresas sem site proprio |
| `--base` | vazio | Quadro que recebe os leads, pelo nome; cria se nao existir |
| `--marcar-brasileiros` | desligado | Anota quem parece publico brasileiro e poe em cima |
| `--so-brasileiros` | desligado | Coleta so quem parece publico brasileiro |
| `--so-ineditos` | desligado | Ignora empresas que ja estao no `historico.json` |
| `--sem-historico` | desligado | Nao grava o resultado no `historico.json` |

O arquivo Excel sempre sai com tres abas: `Leads`, `Com site` e `Sem site`.

### Filtro de site

`--sem-site` e `--com-site` valem **durante** a coleta, nao na exportacao: as
empresas descartadas nao ocupam vaga no `--max`, e a busca continua abrindo
fichas ate juntar o total pedido. Num nicho onde quase todo mundo tem site,
espere abrir muitas fichas para cada lead aproveitado — `--max-por-busca` e
`--buscas` sao as alavancas para achar mais.

"Sem site" quer dizer **sem site proprio**: quem cadastrou so um Instagram,
Facebook ou linktree no Google Maps entra na lista, porque continua sendo uma
empresa sem site. O handle da rede social e' aproveitado como contato.

## Prospectar brasileiros fora do Brasil

O Google Maps nao diz a nacionalidade de ninguem. O que da para ler e' se o
negocio **fala com** brasileiro: a categoria que o proprio Maps atribui
("Restaurante brasileiro"), o nome em portugues, o telefone +55 e o idioma do
site. Um brasileiro dono de empresa com nome e site em ingles nao aparece.

Tres modos no campo *Publico* (ou na CLI):

| Modo | O que faz |
|------|-----------|
| Qualquer empresa | Nem calcula o sinal. Use dentro do Brasil |
| Marcar quem parece brasileiro | Anota o palpite, poe esses leads em cima, nao descarta ninguem |
| So quem parece brasileiro | Descarta o resto **e** busca com os termos que trazem essas empresas |

O terceiro modo tambem troca as buscas, e isso e' o que faz a diferenca: medido
no Maps, `brazilian cleaning services Orlando` e `cleaning services Orlando`
devolvem listas quase sem intersecao — a busca generica nao trouxe **nenhuma**
empresa brasileira em 50 fichas abertas.

Cada lead marcado mostra o selo com a nota e, no `title`, o porque
("categoria do Maps: Restaurante brasileiro", "nome em portugues (faxina)").
Confira: e' um palpite sobre sinais publicos, nao um dado sobre alguem.

Dois limites conhecidos:

- **"Brazilian" as vezes e' o servico, nao o dono.** "Brazilian Blowout" e
  "Brazilian Wax" sao tecnicas vendidas em salao de qualquer dono — o programa
  reconhece essas armadilhas e derruba a pontuacao delas.
- **Portugues nao e' exclusividade do Brasil.** Uma padaria portuguesa em Boston
  pontua pelos mesmos sinais. Em Portugal o programa avisa e passa a ignorar
  nome e site em portugues, porque la isso nao separa ninguem.

## Bases e pipeline

Cada nicho vive numa **base** propria, para os leads de Flooring nao se
misturarem com os de Cleaning. Uma base e' um quadro estilo kanban: colunas sao
as fases da negociacao e os cards se arrastam de uma para outra.

- **Criar**: aba `+ Nova base` na interface, ou `--base "Flooring em North
  Carolina"` na CLI. Bases nunca sao criadas sozinhas.
- **Escolher o destino**: o campo *Base que recebe os leads* no formulario.
  Abrir uma base tambem aponta a proxima busca para ela.
- **Fases**: cada base tem as suas. `+ Fase` cria, `✎` renomeia e `✕` remove
  (os leads da fase removida voltam para a primeira coluna).
- **Geral**: lista todos os leads de todas as bases. Como cada base tem fases
  proprias, ali nao ha colunas — cada card mostra a etiqueta `base · fase` e um
  seletor para mover o lead de base.

Apagar uma base **nao apaga os leads**: eles continuam no Geral, sem base.

Na primeira abertura depois da atualizacao, um `historico.json` antigo e'
migrado sozinho: vira `historico.v1.bak.json` como copia de seguranca, cada par
nicho/regiao antigo vira uma base e quem estava marcado como contatado nasce na
fase `Contatado`.

## Colunas da planilha

`Nome`, `Score`, `Motivo do score`, `Categoria`, `Telefone`, `WhatsApp`,
`E-mails`, `Site`, `Instagram`, `Facebook`, `LinkedIn`, `Endereco`, `Nota`,
`Avaliacoes`, `Mensagem de abordagem`, `Descricao do site`, `Google Maps`,
`Busca de origem`.

## Cuidados

O scraper automatiza o Google Maps com navegador real. Isso pode quebrar se o
layout do Google mudar e pode gerar CAPTCHA em rodadas grandes ou repetidas.
Para uso profissional pesado, o caminho estavel costuma ser uma API oficial de
places, mas este projeto foi mantido sem API externa por escolha.

Use os dados com bom senso e respeito a LGPD: contato B2B legitimo, identificacao
clara e respeito a pedidos de descadastro.

## Estrutura

```text
iniciar.bat                 abre a interface visual (duplo clique)
run.py                      CLI
prospector/
  config.py                 configuracao (.env + flags)
  models.py                 dataclass Lead + colunas da planilha
  eventos.py                eventos do pipeline + saida no terminal
  ai.py                     Ollama local + fallback por regras
  maps_scraper.py           coleta no Google Maps via Playwright
  enrich.py                 varredura dos sites atras de contato
  historico.py              historico.json (ja prospectado, contatado, mensagem)
  exporter.py               CSV + Excel
  pipeline.py               orquestracao das etapas
  utils.py                  helpers compartilhados
webapp/
  __main__.py               sobe o servidor e abre o navegador
  server.py                 API local + streaming do progresso
  static/                   a interface (HTML, CSS, JS)
```

A CLI e a interface usam exatamente o mesmo pipeline: as duas so mudam para
onde o progresso e mostrado.
