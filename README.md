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

## Instalacao passo a passo

Para quem acabou de baixar o projeto do GitHub. Sao cinco passos obrigatorios,
uma vez so. O `iniciar.bat` **nao instala nada** — ele so confere se o ambiente
existe e sobe o servidor, entao os passos abaixo precisam vir antes do primeiro
duplo clique.

Testado no Windows 10/11 com PowerShell.

### 1. Instalar o Python 3.11 ou mais novo

Baixe em [python.org/downloads](https://www.python.org/downloads/). No
instalador, **marque a caixa `Add python.exe to PATH`** antes de clicar em
Install — sem isso o comando `python` nao e' encontrado no terminal.

Confira num PowerShell novo:

```powershell
python --version
```

Tem que responder `Python 3.11.x` ou superior. Se aparecer a Microsoft Store ou
"nao e' reconhecido", o Python nao esta no PATH: reinstale marcando a caixa.

### 2. Baixar o projeto

Com o Git instalado:

```powershell
git clone https://github.com/alvusgroup-creator/themoneymaker.git
cd themoneymaker
```

Sem Git: botao verde **Code -> Download ZIP** na pagina do GitHub, extraia a
pasta e entre nela.

### 3. Abrir o PowerShell dentro da pasta do projeto

Se voce usou o `git clone`, ja esta nela. Se baixou o ZIP: abra a pasta no
Explorador de Arquivos, clique com o botao direito num espaco vazio e escolha
**"Abrir no Terminal"** (ou segure Shift + botao direito -> "Abrir janela do
PowerShell aqui").

Os proximos comandos so funcionam com o terminal aberto nessa pasta — a que tem
o `iniciar.bat` e o `requirements.txt` dentro.

### 4. Criar o ambiente virtual e instalar as dependencias

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

O primeiro comando cria a pasta `.venv` (o Python isolado do projeto). O segundo
baixa Playwright, FastAPI, httpx, openpyxl e o resto. Leva alguns minutos.

> Os comandos chamam `.\.venv\Scripts\python.exe` direto de proposito, em vez de
> ativar o venv com `Activate.ps1`. Assim voce nao esbarra na politica de
> execucao de scripts do PowerShell (`execution policy`), que bloqueia a
> ativacao em muitas maquinas com a configuracao padrao.

### 5. Baixar o navegador do Playwright

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
```

**Esse passo e' separado e obrigatorio.** O `pip install` do passo anterior
instala apenas a biblioteca que *controla* o navegador; o Chromium em si e' um
download a parte, de uns 115 MB. Sem ele a coleta falha com
`Executable doesn't exist`.

### Pronto: rodar

De um duplo clique em **`iniciar.bat`**.

### Opcional: IA local com Ollama

O programa funciona sem nada disso — sem Ollama ele usa regras locais para gerar
as buscas, o score e a mensagem. Se quiser textos melhores, veja
[IA 100% local com Ollama](#ia-100-local-com-ollama) mais abaixo.

### Opcional: arquivo `.env`

Tambem nao e' necessario: todos os valores tem padrao no proprio codigo. So crie
se quiser mudar porta, modelo ou concorrencia:

```powershell
copy .env.example .env
```

Depois edite o `.env` no bloco de notas. Toda mudanca nele exige fechar e abrir
o programa de novo — os valores sao lidos uma unica vez, na inicializacao.

### O que nao vem no download

`historico.json`, `leads.csv`, `leads.xlsx`, `exports/` e `.env` nao estao no
repositorio de proposito — sao dados seus, criados na primeira execucao. Uma
copia recem-baixada comeca com o historico vazio.

## Uso rapido (interface visual)

De um duplo clique em **`iniciar.bat`**. Ele sobe o servidor local e abre a
interface no navegador em `http://127.0.0.1:8765`.

Se for a primeira vez nesta copia do projeto, faca antes a
[instalacao passo a passo](#instalacao-passo-a-passo).

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

## Problemas comuns

**`python` nao e' reconhecido como comando**

O Python nao esta no PATH. Reinstale marcando `Add python.exe to PATH`
([passo 1](#1-instalar-o-python-311-ou-mais-novo)) e abra um terminal novo — uma
janela ja aberta continua com o PATH antigo.

**A janela do `iniciar.bat` diz "Ambiente virtual nao encontrado"**

Falta o [passo 4](#4-criar-o-ambiente-virtual-e-instalar-as-dependencias), ou o
terminal/atalho esta apontando para outra pasta. A pasta certa e' a que tem o
`requirements.txt` e o `iniciar.bat` lado a lado.

**`ModuleNotFoundError: No module named 'fastapi'` (ou `playwright`, `httpx`...)**

O `pip install -r requirements.txt` nao rodou, rodou pela metade, ou foi feito no
Python do sistema em vez do venv. Repita o
[passo 4](#4-criar-o-ambiente-virtual-e-instalar-as-dependencias) chamando o
interpretador com o caminho completo `.\.venv\Scripts\python.exe`.

**`BrowserType.launch: Executable doesn't exist at ...chrome-headless-shell.exe`**

Falta o [passo 5](#5-baixar-o-navegador-do-playwright). Tambem aparece quando o
Playwright e' atualizado depois, porque cada versao pede um build proprio do
navegador. A solucao e' a mesma nos dois casos:

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
```

**A janela preta abre e fecha num piscar**

Algum erro na inicializacao. Rode pelo terminal para ler a mensagem, que fica na
tela:

```powershell
.\.venv\Scripts\python.exe -m webapp
```

**A interface nao abre no navegador**

O servidor pode ter subido mesmo assim. O terminal escreve o endereco na
primeira linha (`Prospectador rodando em ...`) — abra ele na mao. Sem
`PROSPECTADOR_PORTA` no `.env`, o programa procura sozinho uma porta livre a
partir da 8765, entao nem sempre e' a 8765. Com `PROSPECTADOR_PORTA=9000`, ele
usa exatamente a 9000 e falha se estiver ocupada.

**A busca termina com 0 leads**

Rode com o navegador visivel para ver o que acontece na tela:

```powershell
.\.venv\Scripts\python.exe run.py --nicho "pizzarias" --local "Campinas, SP" --max 5 --ver-navegador
```

Quase sempre e' CAPTCHA do Google (rodadas grandes ou muito seguidas — espere e
tente com `--max` menor) ou o filtro de site apertado demais para o nicho. Se a
tela mostrar a lista normalmente e ainda assim vier vazio, o Google mudou o
layout e os seletores do scraper precisam de ajuste.

**Os textos vem genericos, sem cara de IA**

O Ollama nao esta sendo usado. Ele precisa estar rodando **e** com o modelo
exato de `PROSPECTADOR_MODELO` ja baixado — Ollama no ar com outro modelo conta
como indisponivel. Confira com `ollama list` e baixe com
`ollama pull llama3.1:8b`. O programa nao quebra por isso: cai para as regras
locais e segue.

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
