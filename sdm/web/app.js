'use strict';
// Interface do SDM. Todo texto vindo da API entra na tela por textContent (nunca innerHTML).
const $ = (s) => document.querySelector(s);
const node = (tag, text, cls) => { const n = document.createElement(tag); if (text != null) n.textContent = text; if (cls) n.className = cls; return n; };
let token = '', epoch = 0;
const screen = $('#screen');

const ROTULOS = {
  id: 'ID', nome: 'Nome', cpf: 'CPF', email: 'E-mail', telefone: 'Telefone', crmv: 'CRMV', cep: 'CEP', logradouro: 'Logradouro',
  numero: 'Número', complemento: 'Compl.', bairro: 'Bairro', cidade: 'Cidade', uf: 'UF', codigo_ibge: 'IBGE', situacao: 'Situação',
  tutor: 'Tutor', especie: 'Espécie', raca: 'Raça', microchip: 'Microchip', integracao: 'Governo', endereco: 'Endereço',
  descricao: 'Descrição', animal: 'Animal', tipo: 'Operação', tentativas: 'Tentativas', protocolo_externo: 'Protocolo',
  mensagem_erro: 'Mensagem', data_cadastro: 'Cadastro', ultimo_acesso: 'Último acesso', senha_confirmada: 'Confirmado',
  data_nascimento: 'Nascimento', codigo: 'Microchip', data_vinculo: 'Vinculado em', veterinario: 'Veterinário', motivo: 'Motivo',
  data_hora: 'Data/hora', fabricante: 'Fabricante', lote: 'Lote', data_aplicacao: 'Aplicação', data_proxima_dose: 'Próxima dose',
  dose_etapa: 'Dose', vacina: 'Vacina', dias_restantes: 'Dias', data_solicitacao: 'Solicitado em'
};
const TIPOS = { CADASTRO_ANIMAL: 'Cadastro de animal', ATUALIZACAO_ANIMAL: 'Atualização de animal', VACINA_ANTIRRABICA: 'Vacina antirrábica' };
const CLASSE = { CONFIRMADA: 'ok', ATIVO: 'ok', APLICADA: 'ok', REALIZADA: 'ok', FALHA: 'fail', CANCELADA: 'fail', INATIVO: 'fail',
                 PENDENTE: 'pending', ENVIADA: 'pending', AGENDADA: 'pending', SUBSTITUIDO: 'pending' };

function msg(text, error = false) { const n = $('#notice'); n.textContent = text; n.className = error ? 'error' : ''; n.hidden = !text; }
function erro(e) { msg(e.message, true); }
function btn(text, fn, cls = 'secondary') {
  const b = node('button', text, cls); b.type = 'button';
  b.addEventListener('click', async () => { b.disabled = true; try { await fn(); } catch (e) { erro(e); } finally { b.disabled = false; } });
  return b;
}
async function api(path, method = 'GET', body) {
  const res = await fetch('/api' + path, { method, headers: { ...(token ? { Authorization: 'Bearer ' + token } : {}), ...(body ? { 'Content-Type': 'application/json' } : {}) }, body: body ? JSON.stringify(body) : undefined });
  if (res.status === 204) return;
  const data = await res.json();
  if (!res.ok) {
    if (res.status === 401 && token) showLogin();
    throw Error(Array.isArray(data.detail) ? data.detail.map(x => `${x.loc.at(-1)}: ${x.msg}`).join('; ') : data.detail || 'Falha na operação.');
  }
  return data;
}

// ------------------------------------------------------------------ acesso
function trocarForm(id) {
  for (const f of ['loginForm', 'registroForm', 'confirmaForm']) $('#' + f).hidden = f !== id;
}
document.querySelectorAll('#authTabs button').forEach(b => b.addEventListener('click', () => trocarForm(b.dataset.f)));
function showLogin() {
  epoch++; token = '';
  $('#login').hidden = false; $('#workspace').hidden = true; $('#logout').hidden = true;
  $('#who').textContent = 'Ambiente de demonstração'; trocarForm('loginForm');
}
function enviar(form, fn) {
  form.addEventListener('submit', async (e) => {
    e.preventDefault(); const b = form.querySelector('button'); b.disabled = true;
    try { await fn(Object.fromEntries(new FormData(form))); } catch (x) { erro(x); } finally { b.disabled = false; }
  });
}
enviar($('#loginForm'), async (d) => {
  const p = await api('/auth/login', 'POST', d); token = p.access_token; msg('');
  $('#loginForm').reset(); $('#login').hidden = true; $('#workspace').hidden = false; $('#logout').hidden = false;
  $('#who').textContent = p.nome; await go('Animais');
});
enviar($('#registroForm'), async (d) => {
  if (!d.telefone) delete d.telefone;
  const r = await api('/auth/registro', 'POST', d);
  $('#registroForm').reset(); $('#confirmaForm').email.value = d.email; trocarForm('confirmaForm');
  msg(r.mensagem + (r.codigo_confirmacao_simulado ? ` [E-mail simulado] Seu código: ${r.codigo_confirmacao_simulado}` : ''));
});
enviar($('#confirmaForm'), async (d) => { const r = await api('/auth/confirmar', 'POST', d); $('#confirmaForm').reset(); trocarForm('loginForm'); msg(r.mensagem); });
$('#reenviar').addEventListener('click', async () => {
  try {
    const email = $('#confirmaForm').email.value; if (!email) throw Error('Informe o e-mail.');
    const r = await api('/auth/reenviar-codigo', 'POST', { email });
    msg(r.mensagem + (r.codigo_confirmacao_simulado ? ` [E-mail simulado] Novo código: ${r.codigo_confirmacao_simulado}` : ''));
  } catch (e) { erro(e); }
});
$('#logout').addEventListener('click', async () => { try { await api('/auth/logout', 'POST'); } catch (e) { /* encerra localmente */ } showLogin(); msg('Sessão encerrada.'); });

// ------------------------------------------------------------------ componentes
function start(title, description) {
  screen.replaceChildren(); const h = node('h1', title); h.id = 'title'; screen.append(h);
  if (description) screen.append(node('p', description, 'muted'));
}
function celula(td, k, v) {
  if (v == null || v === '') td.textContent = '—';
  else if (k === 'tipo') td.textContent = TIPOS[v] || v;
  else if (typeof v === 'boolean' || k === 'senha_confirmada') td.textContent = v ? 'Sim' : 'Não';
  else if (['situacao', 'integracao'].includes(k)) td.append(node('span', v.replace('_', ' '), 'tag ' + (CLASSE[v] || '')));
  else td.textContent = v;
}
function table(rows, keys, action) {
  if (!rows.length) return node('p', 'Nenhum registro encontrado.', 'muted');
  const box = node('div', null, 'tablebox'), t = node('table'), hd = node('thead'), tr = node('tr'), body = node('tbody');
  keys.forEach(k => { const th = node('th', ROTULOS[k] || k); th.scope = 'col'; tr.append(th); });
  if (action) tr.append(node('th', 'Ações'));
  hd.append(tr); t.append(hd, body);
  for (const r of rows) {
    const row = node('tr');
    for (const k of keys) { const td = node('td'); celula(td, k, r[k]); row.append(td); }
    if (action) { const td = node('td'); td.append(action(r)); row.append(td); }
    body.append(row);
  }
  box.append(t); return box;
}
// Formulário genérico. campo = [nome, rótulo, tipo, opções]; tipo: text|date|number|datetime|textarea|checkbox|select
async function formulario(campos, valores, ao_salvar, ao_cancelar, rotuloSalvar = 'Salvar') {
  const f = node('form'), g = node('div', null, 'grid');
  for (const [nome, rotulo, tipo = 'text', extra] of campos) {
    const l = node('label', rotulo); let i;
    if (tipo === 'select') {
      i = node('select'); i.append(new Option('— selecione —', ''));
      for (const o of extra) i.append(new Option(o[1], o[0]));
    } else if (tipo === 'textarea') i = node('textarea');
    else { i = node('input'); i.type = tipo === 'datetime' ? 'datetime-local' : tipo; if (tipo === 'number') i.step = 'any'; }
    i.name = nome;
    const v = valores?.[nome];
    if (tipo === 'checkbox') i.checked = !!v; else if (v != null) i.value = tipo === 'datetime' ? String(v).slice(0, 16) : v;
    l.append(i); g.append(l);
  }
  const acoes = node('div', null, 'toolbar'), ok = node('button', rotuloSalvar); acoes.append(ok);
  if (ao_cancelar) acoes.append(btn('Cancelar', ao_cancelar));
  f.append(g, acoes);
  f.addEventListener('submit', async (e) => {
    e.preventDefault(); ok.disabled = true;
    const d = {};
    for (const [nome, , tipo] of campos) {
      const el = f.elements[nome];
      if (tipo === 'checkbox') d[nome] = el.checked;
      else if (el.value === '') d[nome] = null;
      else if (tipo === 'number' || (tipo === 'select' && /^\d+$/.test(el.value))) d[nome] = Number(el.value);
      else d[nome] = el.value;
    }
    try { await ao_salvar(d); } catch (x) { erro(x); } finally { ok.disabled = false; }
  });
  return f;
}
const opcoes = async (tab, rotulo) => (await api('/' + tab)).filter(x => x.situacao !== 'INATIVO').map(x => [x.id, rotulo(x)]);

// ------------------------------------------------------------------ navegação
async function go(s) {
  const v = ++epoch; msg(''); const nav = $('#nav'); nav.replaceChildren();
  for (const a of ['Animais', 'Cadastros', 'Atendimentos', 'Integração']) {
    const b = btn(a, () => go(a)); if (a === s) b.setAttribute('aria-current', 'page'); nav.append(b);
  }
  start(s, 'Carregando…');
  if (s === 'Animais') return listaAnimais('', v);
  if (s === 'Cadastros') return cadastros('tutores', v);
  if (s === 'Atendimentos') return atendimentos(v);
  return integracao(v);
}

// ------------------------------------------------------------------ animais
async function listaAnimais(q = '', v = ++epoch) {
  const rows = await api('/animais?q=' + encodeURIComponent(q)); if (v !== epoch) return;
  start('Animais', 'Cadastre animais com microchip e consulte o histórico clínico e a situação no governo.');
  const bar = node('div', null, 'toolbar');
  bar.append(btn('Novo animal', () => formAnimal(null), ''));
  const l = node('label', 'Nome ou microchip'), i = node('input'); i.value = q; i.maxLength = 100; l.append(i);
  i.addEventListener('keydown', e => { if (e.key === 'Enter') listaAnimais(i.value).catch(erro); });
  bar.append(l, btn('Buscar', () => listaAnimais(i.value)));
  screen.append(bar, table(rows, ['id', 'nome', 'tutor', 'especie', 'raca', 'microchip', 'situacao', 'integracao'], (r) => {
    const s = node('div', null, 'toolbar');
    s.append(btn('Histórico', () => historico(r.id)), btn('Editar', () => formAnimal(r)));
    if (r.situacao === 'ATIVO') s.append(btn('Inativar', async () => { await api('/animais/' + r.id, 'DELETE'); await listaAnimais(q); }, 'danger'));
    return s;
  }));
}
async function formAnimal(a) {
  const [tutores, especies, racas] = await Promise.all([opcoes('tutores', t => `${t.nome} (${t.cpf})`), opcoes('especies', e => e.nome), api('/racas')]);
  start(a ? 'Editar animal' : 'Novo animal', 'Informe a data de nascimento ou a idade estimada. A raça deve ser da espécie escolhida (ou deixe "sem raça").');
  const campos = [['nome', 'Nome'], ['nascimento', 'Nascimento', 'date'], ['idade_estimada_meses', 'Idade estimada (meses)', 'number'],
    ['sexo', 'Sexo', 'select', [['M', 'Macho'], ['F', 'Fêmea']]], ['cor', 'Cor'], ['peso_atual', 'Peso atual (kg)', 'number'],
    ['tutor_id', 'Tutor', 'select', tutores], ['especie_id', 'Espécie', 'select', especies],
    ['raca_id', 'Raça (opcional)', 'select', racas.filter(r => r.situacao === 'ATIVO').map(r => [r.id, `${r.nome} — ${r.especie}`])]];
  if (a) campos.push(['situacao', 'Situação', 'select', [['ATIVO', 'Ativo'], ['INATIVO', 'Inativo'], ['OBITO', 'Óbito']]]);
  else campos.push(['microchip', 'Microchip (15 dígitos, opcional)']);
  screen.append(await formulario(campos, a, async (d) => {
    if (a) { await api('/animais/' + a.id, 'PUT', d); msg('Animal atualizado.'); } else { const r = await api('/animais', 'POST', d); msg('Animal cadastrado.'); a = r; }
    await listaAnimais();
  }, () => listaAnimais()));
}
async function historico(id) {
  const [h, ops] = await Promise.all([api(`/animais/${id}/historico`), api('/integracao?animal_id=' + id)]);
  const an = h.animal; start(`Animal: ${an.nome}`, `${an.especie}${an.raca ? ' • ' + an.raca : ' • sem raça'} • tutor ${an.tutor} • microchip ativo: ${an.microchip || 'nenhum'}`);
  screen.append(node('p', 'Situação no governo: '), (() => { const s = node('span', an.integracao.replace('_', ' '), 'tag ' + (CLASSE[an.integracao] || '')); return s; })());
  const bar = node('div', null, 'toolbar'); bar.append(btn('Voltar', () => listaAnimais()));
  screen.append(bar);
  screen.append(node('h3', an.microchip ? 'Substituir microchip' : 'Vincular microchip'));
  screen.append(await formulario([['codigo', 'Novo microchip (15 dígitos)'], ['motivo', 'Motivo']], null, async (d) => {
    await api(`/animais/${id}/microchip`, 'POST', d); msg('Microchip vinculado. O anterior foi mantido no histórico.'); await historico(id);
  }, null, an.microchip ? 'Substituir' : 'Vincular'));
  screen.append(node('h3', 'Histórico de microchips'), table(h.microchips, ['codigo', 'situacao', 'data_vinculo', 'veterinario', 'motivo_substituicao']));
  screen.append(node('h3', 'Consultas'), table(h.consultas, ['data_hora', 'motivo', 'diagnostico', 'veterinario', 'situacao'], (r) => {
    const s = node('div', null, 'toolbar');
    if (r.situacao === 'AGENDADA') for (const x of [['Realizada', 'REALIZADA'], ['Cancelar', 'CANCELADA'], ['Não compareceu', 'NAO_COMPARECEU']])
      s.append(btn(x[0], async () => { await api(`/consultas/${r.id}/situacao`, 'PUT', { situacao: x[1] }); await historico(id); }));
    return s;
  }));
  screen.append(node('h3', 'Vacinas'), table(h.vacinas.map(v => ({ ...v, antirrabica: v.antirrabica ? 'Sim' : 'Não' })),
    ['nome', 'tipo', 'antirrabica', 'fabricante', 'lote', 'data_aplicacao', 'dose_etapa', 'data_proxima_dose', 'situacao'], (r) => {
      const s = node('div', null, 'toolbar');
      if (r.situacao === 'AGENDADA') s.append(btn('Aplicar', async () => { await api(`/vacinas/${r.id}/situacao`, 'PUT', { situacao: 'APLICADA' }); await historico(id); }),
        btn('Cancelar', async () => { await api(`/vacinas/${r.id}/situacao`, 'PUT', { situacao: 'CANCELADA' }); await historico(id); }, 'danger'));
      return s;
    }));
  screen.append(node('h3', 'Comunicações com o governo'), table(ops, ['tipo', 'situacao', 'tentativas', 'protocolo_externo', 'mensagem_erro', 'data_solicitacao']));
}

// ------------------------------------------------------------------ cadastros
const CAD = {
  tutores: { titulo: 'Tutores', cols: ['id', 'nome', 'cpf', 'email', 'telefone', 'endereco', 'cep', 'situacao'] },

  especies: { titulo: 'Espécies', cols: ['id', 'nome', 'descricao', 'situacao'] },
  racas: { titulo: 'Raças', cols: ['id', 'nome', 'especie', 'situacao'] },
  veterinarios: { titulo: 'Veterinários', cols: ['id', 'nome', 'cpf', 'crmv', 'email', 'senha_confirmada', 'situacao', 'ultimo_acesso'] }
};
async function cadastros(tab, v = ++epoch) {
  const rows = await api('/' + tab); if (v !== epoch) return;
  start('Cadastros', 'Exclusão é lógica: o cadastro fica INATIVO e o histórico é preservado.');
  const sub = node('div', null, 'toolbar');
  for (const k of Object.keys(CAD)) { const b = btn(CAD[k].titulo, () => cadastros(k)); if (k === tab) b.setAttribute('aria-current', 'page'); sub.append(b); }
  screen.append(sub, (() => { const b = node('div', null, 'toolbar'); b.append(btn('Novo cadastro', () => formCadastro(tab, null), '')); return b; })());
  screen.append(table(rows, CAD[tab].cols, (r) => {
    const s = node('div', null, 'toolbar'); s.append(btn('Editar', () => formCadastro(tab, r)));
    if (r.situacao === 'ATIVO') s.append(btn('Inativar', async () => { await api(`/${tab}/${r.id}`, 'DELETE'); await cadastros(tab); }, 'danger'));
    return s;
  }));
}
async function formCadastro(tab, r) {
  start((r ? 'Editar ' : 'Novo ') + CAD[tab].titulo.toLowerCase());
  const volta = () => cadastros(tab);
  let campos;
  if (tab === 'tutores') return formTutor(r);
  else if (tab === 'especies') campos = [['nome', 'Nome'], ['descricao', 'Descrição', 'textarea']];
  else if (tab === 'racas') campos = [['nome', 'Nome'], ['descricao', 'Descrição', 'textarea'], ['especie_id', 'Espécie', 'select', await opcoes('especies', e => e.nome)]];
  else {
    campos = [['nome', 'Nome'], ['cpf', 'CPF'], ['crmv_numero', 'CRMV (número)'], ['crmv_uf', 'UF do CRMV'], ['email', 'E-mail', 'email'], ['telefone', 'Telefone']];
    if (r) campos.push(['situacao', 'Situação', 'select', [['ATIVO', 'Ativo'], ['INATIVO', 'Inativo']]]);
    else campos.push(['senha', 'Senha inicial (mín. 8)', 'password']);
  }
  if (tab === 'veterinarios' && !r) {
    screen.append(node('p', 'O novo veterinário só entra depois de confirmar a senha com o código enviado ao e-mail (simulado).', 'muted'));
  }
  const dados = r ? { ...r, crmv_numero: r.crmv_numero, crmv_uf: r.crmv_uf } : null;
  screen.append(await formulario(campos, dados, async (d) => {
    if (r) await api(`/${tab}/${r.id}`, 'PUT', d);
    else if (tab === 'veterinarios') { const x = await api('/auth/registro', 'POST', d); msg(x.mensagem + (x.codigo_confirmacao_simulado ? ` Código (simulado): ${x.codigo_confirmacao_simulado}` : '')); await volta(); return; }
    else await api('/' + tab, 'POST', d);
    msg('Salvo com sucesso.'); await volta();
  }, volta));
}
// O endereço é digitado junto com o tutor: não existe cadastro nem lista de endereços.
async function formTutor(r) {
  start(r ? 'Editar tutor' : 'Novo tutor', 'Informe o CEP e use "Buscar no ViaCEP". Se o ViaCEP estiver fora do ar ou o CEP não existir, preencha o endereço manualmente.');
  const campos = [['nome', 'Nome'], ['cpf', 'CPF'], ['data_nascimento', 'Data de nascimento', 'date'], ['email', 'E-mail', 'email'], ['telefone', 'Telefone'],
    ['cep', 'CEP'], ['numero', 'Número'], ['complemento', 'Complemento'], ['logradouro', 'Logradouro'], ['bairro', 'Bairro'],
    ['cidade', 'Cidade'], ['uf', 'UF'], ['codigo_ibge', 'Código IBGE']];
  if (r) campos.push(['situacao', 'Situação', 'select', [['ATIVO', 'Ativo'], ['INATIVO', 'Inativo']]]);
  const volta = () => cadastros('tutores');
  const f = await formulario(campos, r, async (d) => {
    const tutor = { nome: d.nome, cpf: d.cpf, data_nascimento: d.data_nascimento, email: d.email, telefone: d.telefone, situacao: d.situacao,
      endereco: { cep: d.cep, numero: d.numero, complemento: d.complemento, logradouro: d.logradouro, bairro: d.bairro, cidade: d.cidade, uf: d.uf, codigo_ibge: d.codigo_ibge } };
    if (!r) delete tutor.situacao;
    if (r) await api('/tutores/' + r.id, 'PUT', tutor); else await api('/tutores', 'POST', tutor);
    msg('Tutor salvo com sucesso.'); await volta();
  }, volta);
  const busca = btn('Buscar CEP no ViaCEP', async () => {
    const cep = f.elements.cep.value.trim(); if (!cep) throw Error('Informe o CEP.');
    const x = await api('/cep/' + encodeURIComponent(cep));
    for (const k of ['logradouro', 'bairro', 'cidade', 'uf', 'codigo_ibge']) f.elements[k].value = x[k] || '';
    msg('Endereço preenchido pelo ViaCEP. Complete o número.');
  });
  f.querySelector('.toolbar').prepend(busca);
  screen.append(f);
}

// ------------------------------------------------------------------ atendimentos
async function atendimentos(v = ++epoch) {
  const animais = (await api('/animais')).filter(a => a.situacao === 'ATIVO'); if (v !== epoch) return;
  const prox = await api('/vacinas/proximas-doses'); if (v !== epoch) return;
  start('Atendimentos', 'Registre consultas e vacinas. O veterinário responsável é quem está logado.');
  const sel = animais.map(a => [a.id, `${a.nome} — ${a.tutor}`]);
  screen.append(node('h3', 'Nova consulta'), await formulario([
    ['animal_id', 'Animal', 'select', sel], ['data_hora', 'Data e hora', 'datetime'], ['motivo', 'Motivo'], ['anamnese', 'Anamnese', 'textarea'],
    ['sintomas', 'Sintomas', 'textarea'], ['diagnostico', 'Diagnóstico', 'textarea'], ['tratamento', 'Tratamento', 'textarea'],
    ['prescricao', 'Prescrição', 'textarea'], ['peso_registrado', 'Peso (kg)', 'number'], ['temperatura', 'Temperatura (°C)', 'number'],
    ['observacoes', 'Observações', 'textarea'],
    ['situacao', 'Situação', 'select', [['REALIZADA', 'Realizada'], ['AGENDADA', 'Agendada'], ['CANCELADA', 'Cancelada'], ['NAO_COMPARECEU', 'Não compareceu']]]
  ], { situacao: 'REALIZADA' }, async (d) => { await api('/consultas', 'POST', d); msg('Consulta registrada.'); await atendimentos(); }, null, 'Registrar consulta'));
  screen.append(node('h3', 'Nova vacina'), await formulario([
    ['animal_id', 'Animal', 'select', sel], ['nome', 'Vacina'], ['tipo', 'Tipo (ex.: Raiva, Múltipla)'], ['antirrabica', 'É antirrábica (envio obrigatório ao governo)', 'checkbox'],
    ['fabricante', 'Fabricante'], ['lote', 'Lote'], ['validade_lote', 'Validade do lote', 'date'], ['data_aplicacao', 'Data de aplicação/agendamento', 'date'],
    ['dose_etapa', 'Dose'], ['via_aplicacao', 'Via de aplicação'], ['data_proxima_dose', 'Próxima dose', 'date'], ['observacoes', 'Observações', 'textarea'],
    ['situacao', 'Situação', 'select', [['APLICADA', 'Aplicada'], ['AGENDADA', 'Agendada'], ['CANCELADA', 'Cancelada']]]
  ], { situacao: 'APLICADA' }, async (d) => {
    await api('/vacinas', 'POST', d); msg(d.antirrabica && d.situacao === 'APLICADA' ? 'Vacina registrada. O envio ao governo foi iniciado; veja o status em Integração.' : 'Vacina registrada.'); await atendimentos();
  }, null, 'Registrar vacina'));
  screen.append(node('h3', 'Próximas doses'), table(prox, ['animal', 'vacina', 'dose_etapa', 'data_proxima_dose', 'dias_restantes']));
}

// ------------------------------------------------------------------ integração
async function integracao(v = ++epoch) {
  const ops = await api('/integracao'); if (v !== epoch) return;
  start('Integração com o governo', 'Registro local e confirmação governamental são coisas diferentes: PENDENTE (governo fora do ar), ENVIADA (resposta inconclusiva), CONFIRMADA (com protocolo) e FALHA (recusada).');
  const bar = node('div', null, 'toolbar');
  bar.append(btn('Reenviar pendências', async () => { const r = await api('/integracao/reenviar', 'POST'); msg(`Confirmadas: ${r.confirmadas} • pendentes: ${r.pendentes} • falhas: ${r.falhas}`); await integracao(); }, ''),
    btn('Simular governo fora do ar', async () => { await api('/integracao/simulacao?indisponivel=true', 'PUT'); msg('Governo simulado: INDISPONÍVEL.'); }),
    btn('Restabelecer governo', async () => { await api('/integracao/simulacao?indisponivel=false', 'PUT'); msg('Governo simulado: DISPONÍVEL.'); }),
    btn('Atualizar', () => integracao()));
  screen.append(bar, table(ops, ['id', 'animal', 'tipo', 'situacao', 'tentativas', 'protocolo_externo', 'mensagem_erro', 'data_solicitacao']));
}

showLogin();
