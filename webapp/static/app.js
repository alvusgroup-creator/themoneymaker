/* Prospectador - interface local */
'use strict';

const $ = (sel) => document.querySelector(sel);

const estado = {
  base: 'geral',     // 'geral' ou o id de uma base
  bases: [],
  jobId: null,
  rodando: false,
  leads: [],
  fonte: null,       // EventSource ativo
  etapaAtual: 0,
  arrastando: null,  // chave do lead sendo arrastado
};

const PREFERENCIAS = 'prospectador.form';
const CAMPOS_FORM = [
  'nicho', 'local', 'oferta', 'max_leads', 'n_queries', 'max_por_query',
  'filtro_site', 'filtro_brasileiro', 'base_busca', 'pular_conhecidos',
  'usar_ia', 'enriquecer', 'ver_navegador',
];

// ------------------------------------------------------------ utilidades

async function api(caminho, opcoes = {}) {
  const resposta = await fetch(caminho, {
    headers: { 'Content-Type': 'application/json' },
    ...opcoes,
  });
  if (!resposta.ok) {
    let detalhe = `Erro ${resposta.status}`;
    try {
      const corpo = await resposta.json();
      if (corpo.detail) detalhe = corpo.detail;
    } catch (_) { /* resposta sem JSON */ }
    throw new Error(detalhe);
  }
  return resposta.status === 204 ? null : resposta.json();
}

let temporizadorAviso = null;
function avisar(texto) {
  const caixa = $('#aviso-flutuante');
  caixa.textContent = texto;
  caixa.classList.remove('oculto');
  clearTimeout(temporizadorAviso);
  temporizadorAviso = setTimeout(() => caixa.classList.add('oculto'), 4000);
}

function valorCampo(id) {
  const el = document.getElementById(id);
  return el.type === 'checkbox' ? el.checked : el.value;
}

function definirCampo(id, valor) {
  const el = document.getElementById(id);
  if (!el) return;
  if (el.type === 'checkbox') el.checked = Boolean(valor);
  else if (valor !== undefined && valor !== null && valor !== '') el.value = valor;
}

function salvarPreferencias() {
  const dados = {};
  CAMPOS_FORM.forEach((id) => { dados[id] = valorCampo(id); });
  localStorage.setItem(PREFERENCIAS, JSON.stringify(dados));
}

function carregarPreferencias() {
  try {
    const dados = JSON.parse(localStorage.getItem(PREFERENCIAS) || '{}');
    CAMPOS_FORM.forEach((id) => {
      if (id in dados) definirCampo(id, dados[id]);
    });
  } catch (_) { /* preferências inválidas: ignora */ }
}

function baseAtual() {
  return estado.bases.find((b) => b.id === estado.base) || null;
}

// ------------------------------------------------------------- progresso

const NOMES_ETAPA = { 1: 'Planejando', 2: 'Coletando', 3: 'Enriquecendo', 4: 'Qualificando' };

function mostrarProgresso(visivel) {
  $('#progresso').classList.toggle('oculto', !visivel);
}

function textoVazio(titulo, detalhe) {
  $('#vazio').querySelector('.vazio-titulo').textContent = titulo;
  $('#vazio').querySelector('p:last-child').innerHTML = detalhe;
}

function registrar(texto, classe = '') {
  if (!texto) return;
  const registro = $('#registro');
  const linha = document.createElement('div');
  if (classe) linha.className = classe;
  linha.textContent = texto;
  registro.appendChild(linha);
  while (registro.childElementCount > 300) registro.removeChild(registro.firstChild);
  registro.scrollTop = registro.scrollHeight;
}

function marcarEtapa(numero) {
  estado.etapaAtual = numero;
  document.querySelectorAll('#etapas li').forEach((li) => {
    const n = Number(li.dataset.etapa);
    li.classList.toggle('atual', n === numero);
    li.classList.toggle('feita', n < numero);
  });
}

function atualizarBarra(atual, total) {
  const barra = $('#barra');
  if (!total) {
    barra.classList.add('indeterminada');
    $('#etapa-contador').textContent = '';
    return;
  }
  barra.classList.remove('indeterminada');
  barra.style.width = `${Math.min(100, (atual / total) * 100)}%`;
  $('#etapa-contador').textContent = `${atual}/${total}`;
}

function tratarEvento(ev) {
  switch (ev.tipo) {
    case 'etapa':
      marcarEtapa(ev.etapa);
      $('#etapa-titulo').textContent = ev.texto;
      atualizarBarra(0, ev.total);
      registrar(`── ${NOMES_ETAPA[ev.etapa] || ''}: ${ev.texto}`);
      break;
    case 'progresso':
      atualizarBarra(ev.atual, ev.total);
      break;
    case 'log':
      registrar(ev.texto);
      break;
    case 'resumo':
      registrar(ev.texto, 'resumo');
      break;
    case 'aviso':
      registrar(ev.texto, 'aviso');
      break;
    case 'erro':
      registrar(ev.texto, 'erro');
      break;
    case 'fim':
      finalizarBusca(ev);
      break;
  }
}

// ------------------------------------------------------------------ bases

function montarAbasBases() {
  const barra = $('#abas-bases');
  barra.textContent = '';

  const total = estado.bases.reduce((soma, b) => soma + b.total, 0);
  const abas = [{ id: 'geral', nome: 'Geral', total: null }, ...estado.bases];

  abas.forEach((base) => {
    const aba = document.createElement('button');
    aba.type = 'button';
    aba.className = 'aba-base';
    aba.dataset.base = base.id;
    aba.setAttribute('role', 'tab');
    aba.classList.toggle('ativa', base.id === estado.base);

    const nome = document.createElement('span');
    nome.textContent = base.nome;
    aba.appendChild(nome);

    const contagem = document.createElement('span');
    contagem.className = 'contagem';
    contagem.textContent = base.id === 'geral' ? String(total) : String(base.total);
    aba.appendChild(contagem);

    aba.addEventListener('click', () => trocarBase(base.id));
    barra.appendChild(aba);
  });

  const nova = document.createElement('button');
  nova.type = 'button';
  nova.className = 'aba-base nova';
  nova.textContent = '+ Nova base';
  nova.addEventListener('click', criarBase);
  barra.appendChild(nova);
}

function preencherSeletorDeBase() {
  const seletor = $('#base_busca');
  const escolhido = seletor.value;
  seletor.textContent = '';

  const nenhuma = document.createElement('option');
  nenhuma.value = '';
  nenhuma.textContent = 'Nenhuma — só no Geral';
  seletor.appendChild(nenhuma);

  estado.bases.forEach((base) => {
    const opcao = document.createElement('option');
    opcao.value = base.id;
    opcao.textContent = base.nome;
    seletor.appendChild(opcao);
  });

  // A base pode ter sido apagada enquanto estava escolhida no formulário.
  seletor.value = estado.bases.some((b) => b.id === escolhido) ? escolhido : '';
}

async function carregarBases() {
  try {
    const dados = await api('/api/bases');
    estado.bases = dados.bases;
    if (estado.base !== 'geral' && !estado.bases.some((b) => b.id === estado.base)) {
      estado.base = 'geral';
    }
    montarAbasBases();
    preencherSeletorDeBase();
  } catch (e) {
    avisar(e.message);
  }
}

async function criarBase() {
  const nome = prompt('Nome da base (ex.: Flooring em North Carolina)');
  if (nome === null || !nome.trim()) return;
  try {
    const base = await api('/api/bases', {
      method: 'POST',
      body: JSON.stringify({ nome: nome.trim() }),
    });
    await carregarBases();
    definirCampo('base_busca', base.id);
    salvarPreferencias();
    trocarBase(base.id);
  } catch (e) {
    avisar(e.message);
  }
}

async function renomearBase() {
  const base = baseAtual();
  if (!base) return;
  const nome = prompt('Novo nome da base', base.nome);
  if (nome === null || !nome.trim()) return;
  try {
    await api(`/api/bases/${base.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ nome: nome.trim() }),
    });
    await carregarBases();
    renderizar();
  } catch (e) {
    avisar(e.message);
  }
}

async function apagarBase() {
  const base = baseAtual();
  if (!base) return;
  const aviso = base.total
    ? `Apagar a base "${base.nome}"?\n\nOs ${base.total} leads NÃO são apagados: eles continuam no Geral, sem base.`
    : `Apagar a base "${base.nome}"?`;
  if (!confirm(aviso)) return;
  try {
    await api(`/api/bases/${base.id}`, { method: 'DELETE' });
    estado.base = 'geral';
    await carregarBases();
    await carregarLeads();
  } catch (e) {
    avisar(e.message);
  }
}

async function criarFase() {
  const base = baseAtual();
  if (!base) return;
  const nome = prompt('Nome da nova fase');
  if (nome === null || !nome.trim()) return;
  try {
    await api(`/api/bases/${base.id}/fases`, {
      method: 'POST',
      body: JSON.stringify({ nome: nome.trim() }),
    });
    await carregarBases();
    renderizar();
  } catch (e) {
    avisar(e.message);
  }
}

async function renomearFase(fase) {
  const base = baseAtual();
  if (!base) return;
  const nome = prompt('Novo nome da fase', fase.nome);
  if (nome === null || !nome.trim()) return;
  try {
    await api(`/api/bases/${base.id}/fases/${fase.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ nome: nome.trim() }),
    });
    await carregarBases();
    renderizar();
  } catch (e) {
    avisar(e.message);
  }
}

async function apagarFase(fase) {
  const base = baseAtual();
  if (!base) return;
  const quantos = base.por_fase[fase.id] || 0;
  const aviso = quantos
    ? `Apagar a fase "${fase.nome}"?\n\nOs ${quantos} leads dela vão para a primeira coluna.`
    : `Apagar a fase "${fase.nome}"?`;
  if (!confirm(aviso)) return;
  try {
    await api(`/api/bases/${base.id}/fases/${fase.id}`, { method: 'DELETE' });
    await carregarBases();
    await carregarLeads();
  } catch (e) {
    avisar(e.message);
  }
}

function trocarBase(id) {
  estado.base = id;
  montarAbasBases();
  $('#acoes-base').classList.toggle('oculto', id === 'geral');

  // Abrir uma base é dizer "estou trabalhando aqui": a próxima busca cai nela.
  // O Geral não mexe na escolha — passar por lá não pode desfazer o destino.
  if (id !== 'geral') {
    definirCampo('base_busca', id);
    salvarPreferencias();
  }
  if (!estado.rodando) {
    textoVazio(
      id === 'geral' ? 'Nenhum lead ainda' : 'Base vazia',
      id === 'geral'
        ? 'Preencha o nicho e a região ao lado e clique em <strong>Buscar leads</strong>.'
        : 'Escolha esta base no formulário ao lado antes de buscar, ou mova leads do Geral para cá.',
    );
  }
  carregarLeads();
}

// ----------------------------------------------------------------- busca

function corpoDaBusca() {
  return {
    nicho: valorCampo('nicho').trim(),
    local: valorCampo('local').trim(),
    oferta: valorCampo('oferta').trim()
      || 'servicos de marketing digital para pequenas e medias empresas',
    max_leads: Number(valorCampo('max_leads')) || 60,
    n_queries: Number(valorCampo('n_queries')) || 6,
    max_por_query: Number(valorCampo('max_por_query')) || 60,
    filtro_site: valorCampo('filtro_site'),
    filtro_brasileiro: valorCampo('filtro_brasileiro'),
    base: valorCampo('base_busca'),
    pular_conhecidos: valorCampo('pular_conhecidos'),
    usar_ia: valorCampo('usar_ia'),
    enriquecer: valorCampo('enriquecer'),
    ver_navegador: valorCampo('ver_navegador'),
  };
}

function alternarControles(rodando) {
  estado.rodando = rodando;
  $('#btn-buscar').disabled = rodando;
  $('#btn-buscar').textContent = rodando ? 'Buscando…' : 'Buscar leads';
  $('#btn-cancelar').classList.toggle('oculto', !rodando);
}

async function iniciarBusca(evento) {
  evento.preventDefault();
  if (estado.rodando) return;

  salvarPreferencias();
  // O botão fica no pé de um formulário longo, então clicar nele deixa a página
  // rolada para baixo — com o progresso e o quadro fora da tela, justamente o
  // que a pessoa quer olhar agora.
  window.scrollTo({ top: 0, behavior: 'smooth' });
  $('#registro').textContent = '';
  mostrarProgresso(true);
  marcarEtapa(0);
  $('#etapa-titulo').textContent = 'Iniciando…';
  atualizarBarra(0, 0);

  try {
    const resposta = await api('/api/buscar', {
      method: 'POST',
      body: JSON.stringify(corpoDaBusca()),
    });
    estado.jobId = resposta.job_id;
    alternarControles(true);
    textoVazio('Buscando…', 'Os leads aparecem aqui conforme a busca termina cada etapa.');
    // Abre a base que vai receber os leads, para o resultado cair à vista.
    trocarBase(resposta.base || 'geral');
    conectarEventos(resposta.job_id);
  } catch (e) {
    mostrarProgresso(false);
    avisar(e.message);
  }
}

function conectarEventos(jobId) {
  if (estado.fonte) estado.fonte.close();
  const fonte = new EventSource(`/api/eventos/${jobId}`);
  estado.fonte = fonte;

  fonte.onmessage = (msg) => {
    try {
      tratarEvento(JSON.parse(msg.data));
    } catch (_) { /* linha malformada: ignora */ }
  };
  fonte.onerror = () => {
    // O navegador tenta reconectar sozinho; só reagimos se a busca acabou.
    if (!estado.rodando) fonte.close();
  };
}

async function finalizarBusca(ev) {
  if (estado.fonte) { estado.fonte.close(); estado.fonte = null; }
  alternarControles(false);
  marcarEtapa(5);
  $('#etapa-titulo').textContent = ev.texto || 'Concluído';
  registrar(ev.texto, ev.dados && ev.dados.estado === 'erro' ? 'erro' : 'resumo');
  textoVazio(
    'Nenhum lead nesta busca',
    'Tente outro nicho ou região — ou desmarque <strong>Não repetir leads já prospectados</strong>.',
  );

  await carregarBases();
  await Promise.all([carregarLeads(), atualizarCabecalho()]);
  const total = (ev.dados && ev.dados.encontrados) || 0;
  if (total) avisar(`${total} leads nesta busca.`);
}

async function cancelarBusca() {
  try {
    await api('/api/cancelar', { method: 'POST' });
    registrar('Cancelamento pedido; encerrando a etapa atual…', 'aviso');
    $('#btn-cancelar').disabled = true;
  } catch (e) {
    avisar(e.message);
  }
}

// ------------------------------------------------------------ resultados

function classeScore(score) {
  if (score === null || score === undefined) return '';
  if (score >= 80) return 'quente';
  if (score >= 60) return 'morno';
  return '';
}

function criarContato(rotulo, valor, href) {
  const el = document.createElement(href ? 'a' : 'span');
  el.textContent = `${rotulo} ${valor}`.trim();
  el.title = valor;
  if (href) {
    el.href = href;
    if (href.startsWith('http')) { el.target = '_blank'; el.rel = 'noopener'; }
  }
  return el;
}

function preencherContatos(caixa, lead) {
  caixa.textContent = '';
  const itens = [];

  if (lead.telefone) itens.push(criarContato('☎', lead.telefone, `tel:${lead.telefone.replace(/[^\d+]/g, '')}`));
  if (lead.whatsapp && lead.whatsapp !== lead.telefone) itens.push(criarContato('WhatsApp', lead.whatsapp, null));
  const emails = Array.isArray(lead.emails) ? lead.emails : String(lead.emails || '').split(',').filter(Boolean);
  if (emails.length) itens.push(criarContato('✉', emails[0].trim(), `mailto:${emails[0].trim()}`));
  if (lead.site) itens.push(criarContato('🔗', lead.site.replace(/^https?:\/\//, '').replace(/\/$/, ''), lead.site));
  if (lead.instagram) itens.push(criarContato('@', lead.instagram, `https://instagram.com/${lead.instagram}`));
  if (lead.maps_url) itens.push(criarContato('📍', 'Maps', lead.maps_url));

  if (!itens.length) {
    const vazio = document.createElement('span');
    vazio.className = 'ausente';
    vazio.textContent = 'sem contato encontrado';
    itens.push(vazio);
  }
  itens.forEach((item) => caixa.appendChild(item));
}

function preencherMoverParaBase(caixa, lead) {
  const seletor = caixa.querySelector('[data-campo="destino"]');
  seletor.textContent = '';

  const nenhuma = document.createElement('option');
  nenhuma.value = '';
  nenhuma.textContent = lead.base ? '(tirar da base)' : '(sem base)';
  seletor.appendChild(nenhuma);

  estado.bases.forEach((base) => {
    const opcao = document.createElement('option');
    opcao.value = base.id;
    opcao.textContent = base.nome;
    seletor.appendChild(opcao);
  });
  seletor.value = lead.base || '';

  seletor.addEventListener('change', () => moverParaBase(lead, seletor.value));
  caixa.classList.remove('oculto');
}

function montarCartao(lead, arrastavel) {
  const no = $('#modelo-lead').content.cloneNode(true);
  const artigo = no.querySelector('.lead');
  artigo.dataset.chave = lead.chave;

  const score = no.querySelector('[data-campo="score"]');
  score.textContent = lead.score === null || lead.score === undefined ? '—' : lead.score;
  score.className = `score ${classeScore(lead.score)}`;

  no.querySelector('[data-campo="nome"]').textContent = lead.nome || '(sem nome)';

  const meta = [lead.categoria, lead.endereco].filter(Boolean).join(' · ');
  const nota = lead.nota ? `★ ${lead.nota}${lead.avaliacoes ? ` (${lead.avaliacoes})` : ''}` : '';
  no.querySelector('[data-campo="meta"]').textContent = [nota, meta].filter(Boolean).join(' — ');

  no.querySelector('[data-campo="motivo"]').textContent = lead.motivo_score || '';
  preencherContatos(no.querySelector('[data-campo="contatos"]'), lead);

  // O palpite de público brasileiro vem com o porquê no title: é um palpite
  // sobre sinais do Maps, não um dado sobre a nacionalidade de ninguém.
  const sinal = Number(lead.sinal_brasileiro) || 0;
  if (sinal >= 30) {
    const selo = no.querySelector('[data-campo="selo-br"]');
    selo.textContent = `🇧🇷 público brasileiro · ${sinal}`;
    selo.title = lead.motivo_brasileiro || '';
    selo.classList.remove('oculto');
  }

  // No Geral o card mostra de onde veio e em que fase está, já que ali as
  // colunas de uma base não fazem sentido ao lado das de outra.
  if (estado.base === 'geral') {
    const etiquetas = no.querySelector('[data-campo="etiquetas"]');
    etiquetas.textContent = [lead.base_nome || 'sem base', lead.fase_nome]
      .filter(Boolean).join(' · ');
    etiquetas.classList.remove('oculto');
    preencherMoverParaBase(no.querySelector('[data-campo="mover"]'), lead);
  }

  const editada = Boolean(lead.mensagem_editada);
  const area = no.querySelector('[data-campo="mensagem"]');
  area.value = lead.mensagem_editada || lead.mensagem_abordagem || '';
  no.querySelector('[data-campo="marca-edicao"]').textContent = editada ? 'editada' : '';

  // O textarea cresce com o conteúdo: a abordagem inteira precisa ficar à vista.
  const ajustarAltura = () => {
    area.style.height = 'auto';
    area.style.height = `${Math.min(area.scrollHeight + 2, 320)}px`;
  };
  no.querySelector('.bloco-mensagem').addEventListener('toggle', (ev) => {
    if (ev.target.open) ajustarAltura();
  });

  let atraso = null;
  const salvar = () => {
    clearTimeout(atraso);
    atraso = setTimeout(() => salvarMensagem(artigo, lead, area.value), 600);
  };
  area.addEventListener('input', () => { ajustarAltura(); salvar(); });
  area.addEventListener('blur', () => { clearTimeout(atraso); salvarMensagem(artigo, lead, area.value); });

  no.querySelector('[data-campo="restaurar"]').addEventListener('click', () => {
    area.value = lead.mensagem_abordagem || '';
    salvarMensagem(artigo, lead, area.value);
  });

  if (arrastavel) ligarArraste(artigo, lead);
  return no;
}

// -------------------------------------------------------- arrastar cards

function ligarArraste(artigo, lead) {
  artigo.draggable = true;
  artigo.addEventListener('dragstart', (ev) => {
    estado.arrastando = lead.chave;
    artigo.classList.add('arrastando');
    ev.dataTransfer.effectAllowed = 'move';
    // Alguns navegadores só iniciam o arraste se houver dado no evento.
    ev.dataTransfer.setData('text/plain', lead.chave);
  });
  artigo.addEventListener('dragend', () => {
    estado.arrastando = null;
    artigo.classList.remove('arrastando');
    document.querySelectorAll('.coluna-corpo.recebendo')
      .forEach((c) => c.classList.remove('recebendo'));
  });
}

function ligarSoltura(corpo, fase) {
  corpo.addEventListener('dragover', (ev) => {
    if (!estado.arrastando) return;
    ev.preventDefault();
    ev.dataTransfer.dropEffect = 'move';
    corpo.classList.add('recebendo');
  });
  corpo.addEventListener('dragleave', (ev) => {
    if (!corpo.contains(ev.relatedTarget)) corpo.classList.remove('recebendo');
  });
  corpo.addEventListener('drop', (ev) => {
    ev.preventDefault();
    corpo.classList.remove('recebendo');
    const chave = estado.arrastando || ev.dataTransfer.getData('text/plain');
    if (chave) moverParaFase(chave, fase, corpo);
  });
}

async function moverParaFase(chave, fase, corpo) {
  const lead = estado.leads.find((l) => l.chave === chave);
  const artigo = document.querySelector(`.lead[data-chave="${CSS.escape(chave)}"]`);
  if (!lead || !artigo || lead.fase === fase.id) return;

  const faseAnterior = lead.fase;
  const origem = artigo.parentElement;

  // Move na tela primeiro: arrastar tem que parecer instantâneo. Se o servidor
  // recusar, o card volta para a coluna de onde saiu.
  corpo.appendChild(artigo);
  lead.fase = fase.id;
  lead.fase_nome = fase.nome;
  atualizarContagens();

  try {
    const registro = await api(`/api/leads/${chave}/fase`, {
      method: 'POST',
      body: JSON.stringify({ fase: fase.id }),
    });
    Object.assign(lead, registro);
    await carregarBases();
  } catch (e) {
    lead.fase = faseAnterior;
    origem.appendChild(artigo);
    atualizarContagens();
    avisar(e.message);
  }
}

async function moverParaBase(lead, baseId) {
  try {
    const registro = await api(`/api/leads/${lead.chave}/base`, {
      method: 'POST',
      body: JSON.stringify({ base: baseId }),
    });
    Object.assign(lead, registro);
    await carregarBases();
    await carregarLeads();
    avisar(baseId ? 'Lead movido de base.' : 'Lead ficou sem base.');
  } catch (e) {
    avisar(e.message);
  }
}

// ------------------------------------------------------------- mensagens

async function salvarMensagem(artigo, lead, texto) {
  if ((lead.mensagem_editada || lead.mensagem_abordagem || '') === texto) return;
  try {
    const registro = await api(`/api/leads/${lead.chave}/mensagem`, {
      method: 'POST',
      body: JSON.stringify({ texto }),
    });
    Object.assign(lead, registro);
    artigo.querySelector('[data-campo="marca-edicao"]').textContent =
      registro.mensagem_editada ? 'editada' : '';
    const aviso = artigo.querySelector('[data-campo="salvo"]');
    aviso.textContent = 'salvo';
    aviso.classList.add('visivel');
    setTimeout(() => aviso.classList.remove('visivel'), 1600);
  } catch (e) {
    avisar(e.message);
  }
}

// ------------------------------------------------------------ renderizar

function atualizarContagens() {
  document.querySelectorAll('.coluna').forEach((coluna) => {
    const corpo = coluna.querySelector('[data-campo="corpo"]');
    const visiveis = corpo.querySelectorAll('.lead:not(.oculto)').length;
    coluna.querySelector('[data-campo="contagem"]').textContent = String(visiveis);
  });
}

function montarQuadro() {
  const base = baseAtual();
  const quadro = $('#quadro');
  quadro.textContent = '';
  if (!base) return;

  const porFase = new Map(base.fases.map((f) => [f.id, []]));
  const orfaos = [];
  estado.leads.forEach((lead) => {
    if (porFase.has(lead.fase)) porFase.get(lead.fase).push(lead);
    else orfaos.push(lead);
  });
  // Fase apagada por outra aba do navegador: não some com o lead da tela.
  if (orfaos.length && base.fases.length) {
    porFase.get(base.fases[0].id).push(...orfaos);
  }

  const fragmento = document.createDocumentFragment();
  base.fases.forEach((fase) => {
    const no = $('#modelo-coluna').content.cloneNode(true);
    const coluna = no.querySelector('.coluna');
    coluna.dataset.fase = fase.id;
    no.querySelector('[data-campo="nome"]').textContent = fase.nome;
    no.querySelector('[data-campo="contagem"]').textContent =
      String((porFase.get(fase.id) || []).length);

    no.querySelector('[data-campo="renomear"]')
      .addEventListener('click', () => renomearFase(fase));
    no.querySelector('[data-campo="apagar"]')
      .addEventListener('click', () => apagarFase(fase));

    const corpo = no.querySelector('[data-campo="corpo"]');
    (porFase.get(fase.id) || []).forEach((lead) => corpo.appendChild(montarCartao(lead, true)));
    ligarSoltura(corpo, fase);

    fragmento.appendChild(no);
  });
  quadro.appendChild(fragmento);
}

function montarLista() {
  const lista = $('#lista');
  lista.textContent = '';
  const fragmento = document.createDocumentFragment();
  estado.leads.forEach((lead) => fragmento.appendChild(montarCartao(lead, false)));
  lista.appendChild(fragmento);
}

function renderizar() {
  const noGeral = estado.base === 'geral';
  $('#quadro').classList.toggle('oculto', noGeral);
  $('#lista').classList.toggle('oculto', !noGeral);
  // Esconder o container não basta: deixar os cards antigos no DOM faz a
  // contagem somar os dois lados e `querySelector` por chave achar o card
  // invisível na hora de arrastar.
  if (noGeral) {
    $('#quadro').textContent = '';
    montarLista();
  } else {
    $('#lista').textContent = '';
    montarQuadro();
  }
  aplicarFiltros();
}

function aplicarFiltros() {
  const termo = $('#filtro-texto').value.trim().toLowerCase();
  const container = estado.base === 'geral' ? $('#lista') : $('#quadro');
  let visiveis = 0;

  container.querySelectorAll('.lead').forEach((artigo) => {
    const lead = estado.leads.find((l) => l.chave === artigo.dataset.chave);
    if (!lead) return;
    const alvo = [lead.nome, lead.categoria, lead.endereco, lead.nicho, lead.local]
      .filter(Boolean).join(' ').toLowerCase();
    const passa = !termo || alvo.includes(termo);
    artigo.classList.toggle('oculto', !passa);
    if (passa) visiveis += 1;
  });

  const total = estado.leads.length;
  const base = baseAtual();
  const onde = base ? base.nome : 'todas as bases';
  $('#resumo-lista').textContent = total
    ? `${visiveis} de ${total} leads · ${onde}`
    : '';
  $('#vazio').classList.toggle('oculto', total > 0);
  if (estado.base !== 'geral') atualizarContagens();
}

async function carregarLeads() {
  const params = new URLSearchParams({
    base: estado.base,
    escopo: valorCampo('filtro-busca') ? 'busca' : 'todos',
  });
  if (estado.jobId) params.set('job_id', estado.jobId);
  try {
    const dados = await api(`/api/leads?${params}`);
    estado.leads = dados.leads;
    renderizar();
    atualizarLinksDownload();
  } catch (e) {
    avisar(e.message);
  }
}

function atualizarLinksDownload() {
  const params = new URLSearchParams({
    base: estado.base,
    escopo: valorCampo('filtro-busca') ? 'busca' : 'todos',
  });
  if (estado.jobId) params.set('job_id', estado.jobId);
  $('#baixar-csv').href = `/api/baixar/csv?${params}`;
  $('#baixar-xlsx').href = `/api/baixar/xlsx?${params}`;
}

// ---------------------------------------------------------- cabeçalho

async function atualizarCabecalho() {
  try {
    const dados = await api('/api/estado');
    $('#status-historico').textContent = `histórico: ${dados.historico_total}`;
    return dados;
  } catch (_) {
    return null;
  }
}

async function verificarOllama() {
  const pilula = $('#status-ia');
  try {
    const dados = await api('/api/ollama');
    pilula.classList.toggle('ligada', dados.ativo);
    pilula.classList.toggle('desligada', !dados.ativo);
    $('#status-ia-texto').textContent = dados.ativo
      ? `IA local: ${dados.modelo}`
      : 'IA local desligada — usando regras';
    pilula.title = dados.erro || `Modelo ${dados.modelo} disponível no Ollama.`;
  } catch (_) {
    pilula.classList.add('desligada');
    $('#status-ia-texto').textContent = 'IA local: indisponível';
  }
}

// ------------------------------------------------------------- arranque

async function iniciar() {
  carregarPreferencias();

  $('#form-busca').addEventListener('submit', iniciarBusca);
  $('#btn-cancelar').addEventListener('click', cancelarBusca);
  $('#filtro-texto').addEventListener('input', aplicarFiltros);
  $('#filtro-busca').addEventListener('change', carregarLeads);
  $('#btn-nova-fase').addEventListener('click', criarFase);
  $('#btn-renomear-base').addEventListener('click', renomearBase);
  $('#btn-apagar-base').addEventListener('click', apagarBase);

  verificarOllama();
  await carregarBases();
  const dados = await atualizarCabecalho();

  // Recarregou a página no meio de uma busca? Reconecta em vez de perder tudo.
  if (dados && dados.job) {
    estado.jobId = dados.job.job_id;
    if (dados.job.rodando) {
      alternarControles(true);
      mostrarProgresso(true);
      conectarEventos(dados.job.job_id);
    }
    if (dados.job.base) estado.base = dados.job.base;
  }
  trocarBase(estado.base);
}

iniciar();
