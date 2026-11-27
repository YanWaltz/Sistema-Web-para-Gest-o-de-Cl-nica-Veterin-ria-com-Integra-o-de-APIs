"""API privada da clínica e entrada da interface web."""
import os
import re
import sqlite3
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Optional

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import modelos as m
from .base import GOV_KEY, GOV_URL, ROOT, db
from .integracao import enfileirar, enviar
from .seguranca import autenticar, confirmar_codigo, criar_demo, novo_codigo, registrar_veterinario, sessao
from .validacao import so_digitos


@asynccontextmanager
async def lifespan(app):
    with db() as c:
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='usuarios'").fetchone():
            raise RuntimeError('Banco antigo detectado em data/. Apague a pasta data/ e inicie de novo.')
        c.executescript((ROOT / 'schema.sql').read_text(encoding='utf-8'))
        criar_demo(c)
    yield


app = FastAPI(title='SDM | Clínica veterinária', version='2.0.0', lifespan=lifespan)
app.mount('/web', StaticFiles(directory=ROOT / 'web'), name='web')

# Mensagens amigáveis para violações de unicidade (o banco é a última barreira contra duplicidade).
UNICOS = {
    'tutores.cpf': 'Já existe um tutor cadastrado com este CPF.',
    'veterinarios.cpf': 'Já existe um veterinário cadastrado com este CPF.',
    'veterinarios.email': 'Já existe um veterinário cadastrado com este e-mail.',
    'veterinarios.crmv_numero': 'Este CRMV já está cadastrado nesta UF.',
    'vinculos_microchip.codigo': 'Este microchip já foi utilizado por um animal.',
    'vinculos_microchip.animal_id': 'O animal já possui um microchip ativo.',
    'especies.nome': 'Já existe uma espécie com este nome.',
    'racas.nome': 'Já existe uma raça com este nome nesta espécie.',
}


@app.exception_handler(sqlite3.IntegrityError)
async def integridade(request: Request, exc: sqlite3.IntegrityError):
    texto = str(exc)
    detalhe = 'Cadastro duplicado ou vínculo inválido. Confira os dados.'
    if 'FOREIGN KEY' in texto:
        detalhe = 'O vínculo informado não existe, a raça não pertence à espécie ou o cadastro está em uso.'
    else:
        for trecho, mensagem in UNICOS.items():
            if trecho in texto:
                detalhe = mensagem
                break
    return JSONResponse(status_code=409, content={'detail': detalhe})


@app.get('/', include_in_schema=False)
def home():
    return FileResponse(ROOT / 'web' / 'index.html')


@app.get('/saude', tags=['Sistema'])
def saude():
    return {'servico': 'clinica'}


# ================================================================ acesso (3.1)
def expor_codigo(resposta, codigo):
    # Envio de e-mail SIMULADO (permitido pelo enunciado): o código aparece no terminal da API
    # e, para facilitar a demonstração, também na resposta. Para desligar: SDM_CODIGO_NA_RESPOSTA=0.
    if os.environ.get('SDM_CODIGO_NA_RESPOSTA', '1') == '1':
        resposta['codigo_confirmacao_simulado'] = codigo
    return resposta


@app.post('/api/auth/registro', status_code=201, tags=['Acesso'])
def registro(dados: m.VeterinarioNovo):
    with db() as c:
        vid, codigo = registrar_veterinario(c, dados)
    print(f'[E-MAIL SIMULADO] Código de confirmação para {dados.email}: {codigo}', flush=True)
    return expor_codigo({'id': vid, 'email': dados.email,
                         'mensagem': 'Cadastro criado. Confirme a senha com o código enviado ao e-mail (envio simulado).'}, codigo)


@app.post('/api/auth/reenviar-codigo', tags=['Acesso'])
def reenviar_codigo(dados: m.ReenvioCodigo):
    codigo = novo_codigo(dados.email)
    resposta = {'mensagem': 'Se o e-mail estiver aguardando confirmação, um novo código foi enviado (envio simulado).'}
    if codigo:
        print(f'[E-MAIL SIMULADO] Novo código de confirmação para {dados.email}: {codigo}', flush=True)
        expor_codigo(resposta, codigo)
    return resposta


@app.post('/api/auth/confirmar', tags=['Acesso'])
def confirmar(dados: m.Confirmacao):
    confirmar_codigo(dados.email, dados.codigo)
    return {'mensagem': 'Senha confirmada. Você já pode entrar.'}


@app.post('/api/auth/login', tags=['Acesso'])
def login(dados: m.Login):
    return autenticar(dados.email, dados.senha)


@app.get('/api/auth/me', tags=['Acesso'])
def eu(u=Depends(sessao)):
    return {k: u[k] for k in ('id', 'nome', 'email', 'crmv_numero', 'crmv_uf')}


@app.post('/api/auth/logout', status_code=204, tags=['Acesso'])
def logout(u=Depends(sessao)):
    with db() as c:
        c.execute('DELETE FROM sessoes WHERE token_hash=?', (u['token_hash'],))
    return Response(status_code=204)


# ================================================================ funções de apoio
def item(c, tabela, id, colunas='*'):
    # Os nomes de tabela e de colunas vêm do código, nunca da requisição.
    r = c.execute(f'SELECT {colunas} FROM {tabela} WHERE id=?', (id,)).fetchone()
    if r is None:
        raise HTTPException(404, 'Registro não encontrado.')
    return dict(r)


def inserir(c, tabela, dados):
    campos = ','.join(dados)
    vals = ','.join('?' for _ in dados)
    return c.execute(f'INSERT INTO {tabela}({campos}) VALUES ({vals})', tuple(dados.values())).lastrowid


def atualizar(c, tabela, id, dados):
    campos = ','.join(k + '=?' for k in dados)
    c.execute(f'UPDATE {tabela} SET {campos} WHERE id=?', (*dados.values(), id))


def valores(dados):
    """Converte o modelo em dicionário; 'situacao' só entra se foi informada (não reativa sem querer)."""
    d = dados.model_dump(mode='json')
    if d.get('situacao') is None:
        d.pop('situacao', None)
    return d


# ================================================================ cadastros com exclusão lógica
def cadastrar_crud(tabela, modelo, lista_sql=None, em_uso=None):
    base = f'/api/{tabela}'
    lista_sql = lista_sql or f'SELECT * FROM {tabela} ORDER BY id DESC'

    def listar(u=Depends(sessao)):
        with db() as c:
            return [dict(x) for x in c.execute(lista_sql)]

    def consultar(id: int, u=Depends(sessao)):
        with db() as c:
            return item(c, tabela, id)

    def criar(dados: modelo, u=Depends(sessao)):
        with db() as c:
            return item(c, tabela, inserir(c, tabela, valores(dados)))

    def editar(id: int, dados: modelo, u=Depends(sessao)):
        with db() as c:
            item(c, tabela, id)
            atualizar(c, tabela, id, valores(dados))
            return item(c, tabela, id)

    def inativar(id: int, u=Depends(sessao)):
        with db() as c:
            item(c, tabela, id)
            if em_uso and c.execute(em_uso, (id,)).fetchone()[0]:
                raise HTTPException(409, 'Há animais ativos vinculados a este cadastro. Inative-os primeiro.')
            c.execute(f"UPDATE {tabela} SET situacao='INATIVO' WHERE id=?", (id,))
        return Response(status_code=204)

    for met, path, func, status in [('GET', base, listar, 200), ('POST', base, criar, 201),
                                    ('GET', base + '/{id}', consultar, 200), ('PUT', base + '/{id}', editar, 200),
                                    ('DELETE', base + '/{id}', inativar, 204)]:
        app.add_api_route(path, func, methods=[met], status_code=status, tags=[tabela.capitalize()],
                          operation_id=f'{tabela}_{func.__name__}')

LISTA_RACAS = '''SELECT r.*, e.nome AS especie FROM racas r JOIN especies e ON e.id=r.especie_id ORDER BY r.id DESC'''
EM_USO = "SELECT COUNT(*) FROM animais WHERE {}=? AND situacao='ATIVO'"


cadastrar_crud('especies', m.Especie, em_uso=EM_USO.format('especie_id'))
cadastrar_crud('racas', m.Raca, LISTA_RACAS, EM_USO.format('raca_id'))

# ================================================================ endereços (3.3)
# O endereço NÃO é um cadastro à parte: ele é informado junto com o tutor.
# O CEP é gravado uma única vez em "ceps" e endereços iguais são reaproveitados.
def obter_endereco(c, dados):
    """Devolve o id do endereço, criando CEP e endereço só se ainda não existirem (get-or-create)."""
    cep = so_digitos(dados.cep)
    complemento = (dados.complemento or '').strip()
    r = c.execute('SELECT id FROM ceps WHERE cep=?', (cep,)).fetchone()
    if r:  # CEP já conhecido: reaproveita os dados guardados
        cep_id = r['id']
    else:
        faltam = [k for k in ('logradouro', 'bairro', 'cidade', 'uf') if not getattr(dados, k)]
        if faltam:
            raise HTTPException(422, 'CEP ainda não cadastrado: informe ' + ', '.join(faltam)
                                + ' (ou use a consulta ao ViaCEP).')
        cep_id = c.execute('INSERT INTO ceps(cep,logradouro,bairro,cidade,uf,codigo_ibge) VALUES (?,?,?,?,?,?)',
                           (cep, dados.logradouro, dados.bairro, dados.cidade, dados.uf, dados.codigo_ibge)).lastrowid
    e = c.execute('SELECT id FROM enderecos WHERE cep_id=? AND numero=? AND complemento=?',
                  (cep_id, dados.numero, complemento)).fetchone()
    if e:
        return e['id']
    return c.execute('INSERT INTO enderecos(cep_id,numero,complemento) VALUES (?,?,?)',
                     (cep_id, dados.numero, complemento)).lastrowid


# ================================================================ tutores (3.2)
SQL_TUTOR = '''SELECT t.id, t.nome, t.cpf, t.data_nascimento, t.email, t.telefone, t.data_cadastro, t.situacao,
                t.endereco_id, c.cep, c.logradouro, e.numero, NULLIF(e.complemento,'') AS complemento,
                c.bairro, c.cidade, c.uf, c.codigo_ibge,
                c.logradouro || ', ' || e.numero || ' - ' || c.cidade || '/' || c.uf AS endereco
                FROM tutores t JOIN enderecos e ON e.id=t.endereco_id JOIN ceps c ON c.id=e.cep_id'''


def tutor_completo(c, id):
    r = c.execute(SQL_TUTOR + ' WHERE t.id=?', (id,)).fetchone()
    if r is None:
        raise HTTPException(404, 'Registro não encontrado.')
    return dict(r)


@app.get('/api/tutores', tags=['Tutores'])
def listar_tutores(u=Depends(sessao)):
    with db() as c:
        return [dict(x) for x in c.execute(SQL_TUTOR + ' ORDER BY t.id DESC')]


@app.get('/api/tutores/{id}', tags=['Tutores'])
def consultar_tutor(id: int, u=Depends(sessao)):
    with db() as c:
        return tutor_completo(c, id)


@app.post('/api/tutores', status_code=201, tags=['Tutores'])
def criar_tutor(dados: m.Tutor, u=Depends(sessao)):
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        campos = valores(dados)
        campos.pop('endereco')
        campos['endereco_id'] = obter_endereco(c, dados.endereco)
        return tutor_completo(c, inserir(c, 'tutores', campos))


@app.put('/api/tutores/{id}', tags=['Tutores'])
def editar_tutor(id: int, dados: m.Tutor, u=Depends(sessao)):
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        item(c, 'tutores', id)
        campos = valores(dados)
        campos.pop('endereco')
        campos['endereco_id'] = obter_endereco(c, dados.endereco)
        atualizar(c, 'tutores', id, campos)
        return tutor_completo(c, id)


@app.delete('/api/tutores/{id}', status_code=204, tags=['Tutores'])
def inativar_tutor(id: int, u=Depends(sessao)):
    with db() as c:
        item(c, 'tutores', id)
        if c.execute(EM_USO.format('tutor_id'), (id,)).fetchone()[0]:
            raise HTTPException(409, 'Há animais ativos vinculados a este cadastro. Inative-os primeiro.')
        c.execute("UPDATE tutores SET situacao='INATIVO' WHERE id=?", (id,))
    return Response(status_code=204)

@app.get('/api/enderecos', tags=['Enderecos'])
def listar_enderecos(u=Depends(sessao)):
    with db() as c:
        return [dict(x) for x in c.execute(VISAO_ENDERECO + ' ORDER BY e.id DESC')]


@app.get('/api/enderecos/{id}', tags=['Enderecos'])
def consultar_endereco(id: int, u=Depends(sessao)):
    with db() as c:
        r = c.execute(VISAO_ENDERECO + ' WHERE e.id=?', (id,)).fetchone()
    if r is None:
        raise HTTPException(404, 'Registro não encontrado.')
    return dict(r)


@app.post('/api/enderecos', status_code=201, tags=['Enderecos'])
def criar_endereco(dados: m.EnderecoNovo, u=Depends(sessao)):
    cep = so_digitos(dados.cep)
    complemento = (dados.complemento or '').strip()
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        r = c.execute('SELECT id FROM ceps WHERE cep=?', (cep,)).fetchone()
        if r:  # CEP já conhecido: reaproveita os dados guardados
            cep_id = r['id']
        else:
            faltam = [k for k in ('logradouro', 'bairro', 'cidade', 'uf') if not getattr(dados, k)]
            if faltam:
                raise HTTPException(422, 'CEP ainda não cadastrado: informe ' + ', '.join(faltam)
                                    + ' (ou use a consulta ao ViaCEP).')
            cep_id = c.execute('INSERT INTO ceps(cep,logradouro,bairro,cidade,uf,codigo_ibge) VALUES (?,?,?,?,?,?)',
                               (cep, dados.logradouro, dados.bairro, dados.cidade, dados.uf, dados.codigo_ibge)).lastrowid
        e = c.execute('SELECT id FROM enderecos WHERE cep_id=? AND numero=? AND complemento=?',
                      (cep_id, dados.numero, complemento)).fetchone()
        reaproveitado = e is not None
        eid = e['id'] if e else c.execute('INSERT INTO enderecos(cep_id,numero,complemento) VALUES (?,?,?)',
                                          (cep_id, dados.numero, complemento)).lastrowid
        return dict(c.execute(VISAO_ENDERECO + ' WHERE e.id=?', (eid,)).fetchone()) | {'reaproveitado': reaproveitado}


@app.get('/api/cep/{cep}', tags=['ViaCEP'])
def buscar_cep(cep: str, u=Depends(sessao)):
    if not re.fullmatch(r'[0-9]{5}-?[0-9]{3}', cep):
        raise HTTPException(422, 'Informe um CEP com 8 dígitos.')
    try:
        r = httpx.get(f"https://viacep.com.br/ws/{cep.replace('-', '')}/json/", timeout=4.0)
        r.raise_for_status()
        x = r.json()
        if not isinstance(x, dict):
            raise ValueError()
    except httpx.TimeoutException:
        raise HTTPException(504, 'O ViaCEP demorou demais para responder. Tente de novo ou preencha o endereço manualmente.')
    except (httpx.HTTPError, ValueError):
        raise HTTPException(503, 'ViaCEP indisponível. Preencha o endereço manualmente.')
    if str(x.get('erro', '')).lower() == 'true':
        raise HTTPException(404, 'CEP não encontrado.')
    return {'cep': x.get('cep', cep), 'logradouro': x.get('logradouro', ''), 'bairro': x.get('bairro', ''),
            'cidade': x.get('localidade', ''), 'uf': x.get('uf', ''), 'codigo_ibge': x.get('ibge') or None}


# ================================================================ veterinários (3.6)
LISTA_VETS = '''SELECT id,nome,cpf,crmv_numero,crmv_uf,crmv_numero || '/' || crmv_uf AS crmv,email,telefone,
                senha_confirmada,data_confirmacao,data_cadastro,situacao,ultimo_acesso FROM veterinarios'''


@app.get('/api/veterinarios', tags=['Veterinarios'])
def listar_veterinarios(u=Depends(sessao)):
    with db() as c:
        return [dict(x) for x in c.execute(LISTA_VETS + ' ORDER BY id DESC')]


@app.get('/api/veterinarios/{id}', tags=['Veterinarios'])
def consultar_veterinario(id: int, u=Depends(sessao)):
    with db() as c:
        r = c.execute(LISTA_VETS + ' WHERE id=?', (id,)).fetchone()
    if r is None:
        raise HTTPException(404, 'Registro não encontrado.')
    return dict(r)


@app.put('/api/veterinarios/{id}', tags=['Veterinarios'])
def editar_veterinario(id: int, dados: m.VeterinarioEdicao, u=Depends(sessao)):
    if id == u['id'] and dados.situacao == 'INATIVO':
        raise HTTPException(422, 'Você não pode inativar o próprio cadastro.')
    with db() as c:
        item(c, 'veterinarios', id, 'id')
        atualizar(c, 'veterinarios', id, valores(dados))
        return dict(c.execute(LISTA_VETS + ' WHERE id=?', (id,)).fetchone())


@app.delete('/api/veterinarios/{id}', status_code=204, tags=['Veterinarios'])
def inativar_veterinario(id: int, u=Depends(sessao)):
    if id == u['id']:
        raise HTTPException(422, 'Você não pode inativar o próprio cadastro.')
    with db() as c:
        item(c, 'veterinarios', id, 'id')
        c.execute("UPDATE veterinarios SET situacao='INATIVO' WHERE id=?", (id,))
        c.execute('DELETE FROM sessoes WHERE veterinario_id=?', (id,))  # derruba as sessões abertas
    return Response(status_code=204)


# ================================================================ animais e microchip (3.7)
SQL_ANIMAL = '''SELECT a.*, t.nome AS tutor, e.nome AS especie, r.nome AS raca, v.codigo AS microchip,
    (SELECT CASE WHEN COUNT(*)=0 THEN 'SEM_ENVIO'
                 WHEN SUM(i.situacao='FALHA')>0 THEN 'FALHA'
                 WHEN SUM(i.situacao='ENVIADA')>0 THEN 'ENVIADA'
                 WHEN SUM(i.situacao='PENDENTE')>0 THEN 'PENDENTE'
                 ELSE 'CONFIRMADA' END
     FROM integracoes_governo i WHERE i.animal_id=a.id) AS integracao
    FROM animais a JOIN tutores t ON t.id=a.tutor_id JOIN especies e ON e.id=a.especie_id
    LEFT JOIN racas r ON r.id=a.raca_id
    LEFT JOIN vinculos_microchip v ON v.animal_id=a.id AND v.situacao='ATIVO' '''


def animal_completo(c, id):
    r = c.execute(SQL_ANIMAL + ' WHERE a.id=?', (id,)).fetchone()
    if r is None:
        raise HTTPException(404, 'Registro não encontrado.')
    return dict(r)


def chip_ativo(c, animal_id):
    return c.execute("SELECT * FROM vinculos_microchip WHERE animal_id=? AND situacao='ATIVO'", (animal_id,)).fetchone()


def validar_vinculos_animal(c, d):
    """Regras: tutor e espécie existem e estão ativos; a raça (opcional) pertence à espécie informada."""
    for tabela, valor, nome in (('tutores', d.tutor_id, 'Tutor'), ('especies', d.especie_id, 'Espécie')):
        r = c.execute(f'SELECT situacao FROM {tabela} WHERE id=?', (valor,)).fetchone()
        if r is None:
            raise HTTPException(422, f'{nome} não encontrado(a).')
        if r['situacao'] != 'ATIVO':
            raise HTTPException(422, f'{nome} inativo(a).')
    if d.raca_id is not None:
        r = c.execute('SELECT especie_id, situacao FROM racas WHERE id=?', (d.raca_id,)).fetchone()
        if r is None:
            raise HTTPException(422, 'Raça não encontrada.')
        if r['especie_id'] != d.especie_id:
            raise HTTPException(422, 'A raça selecionada não pertence à espécie informada.')
        if r['situacao'] != 'ATIVO':
            raise HTTPException(422, 'Raça inativa.')
    if d.nascimento and d.nascimento > date.today():
        raise HTTPException(422, 'Nascimento não pode estar no futuro.')


def evento_animal(c, a, tipo, chip, anterior=None):
    """Registra na fila de integração o cadastro/atualização do animal (identificado pelo microchip)."""
    especie = item(c, 'especies', a['especie_id'], 'nome')['nome']
    raca = item(c, 'racas', a['raca_id'], 'nome')['nome'] if a['raca_id'] else None
    dados = {'microchip': chip, 'animal_id': a['id'], 'versao': a['versao'], 'nome': a['nome'], 'especie': especie,
             'raca': raca, 'sexo': a['sexo'], 'nascimento': a['nascimento'], 'situacao': a['situacao']}
    if anterior:
        dados['microchip_anterior'] = anterior
    enfileirar(c, a['id'], tipo, dados, f"animal-{a['id']}-v{a['versao']}")


def vincular_microchip(c, animal_id, codigo, vet, motivo):
    """Vincula (ou substitui) o microchip. O vínculo antigo NÃO é apagado: vira SUBSTITUIDO (histórico)."""
    a = item(c, 'animais', animal_id)
    if a['situacao'] != 'ATIVO':
        raise HTTPException(409, 'Animal inativo.')
    usado = c.execute('SELECT animal_id, situacao FROM vinculos_microchip WHERE codigo=?', (codigo,)).fetchone()
    if usado:
        if usado['animal_id'] == animal_id and usado['situacao'] == 'ATIVO':
            raise HTTPException(409, 'Este microchip já é o microchip ativo deste animal.')
        raise HTTPException(409, 'Este microchip já foi utilizado e não pode ser vinculado novamente.')
    atual = chip_ativo(c, animal_id)
    if atual:
        c.execute('''UPDATE vinculos_microchip SET situacao='SUBSTITUIDO', data_substituicao=CURRENT_TIMESTAMP,
                     motivo_substituicao=? WHERE id=?''', (motivo or 'Substituição de microchip', atual['id']))
    vid = c.execute('INSERT INTO vinculos_microchip(animal_id,codigo,veterinario_id) VALUES (?,?,?)',
                    (animal_id, codigo, vet['id'])).lastrowid
    c.execute('UPDATE animais SET versao=versao+1 WHERE id=?', (animal_id,))
    evento_animal(c, item(c, 'animais', animal_id), 'CADASTRO_ANIMAL', codigo, atual['codigo'] if atual else None)
    return item(c, 'vinculos_microchip', vid)


@app.get('/api/animais', tags=['Animais'])
def listar_animais(q: str = Query(default='', max_length=100), u=Depends(sessao)):
    with db() as c:
        return [dict(x) for x in c.execute(
            SQL_ANIMAL + ''' WHERE a.nome LIKE ? OR a.id IN (SELECT animal_id FROM vinculos_microchip WHERE codigo LIKE ?)
                             ORDER BY a.id DESC''', (f'%{q}%', f'%{q}%'))]


@app.get('/api/animais/{id}', tags=['Animais'])
def consultar_animal(id: int, u=Depends(sessao)):
    """Dados do animal e a situação da integração governamental (regra 6 do cadastro de animais)."""
    with db() as c:
        a = animal_completo(c, id)
        a['operacoes'] = [dict(x) for x in c.execute(
            '''SELECT id,tipo,situacao,protocolo_externo,tentativas,mensagem_erro,data_solicitacao,data_resposta
               FROM integracoes_governo WHERE animal_id=? ORDER BY id DESC''', (id,))]
        return a


@app.post('/api/animais', status_code=201, tags=['Animais'])
def criar_animal(dados: m.AnimalNovo, background: BackgroundTasks, u=Depends(sessao)):
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        validar_vinculos_animal(c, dados)
        aid = inserir(c, 'animais', dados.model_dump(mode='json', exclude={'microchip', 'situacao'}))
        if dados.microchip:  # vínculo feito pelo veterinário logado
            vincular_microchip(c, aid, dados.microchip, u, None)
        a = animal_completo(c, aid)
    if dados.microchip:
        background.add_task(enviar, aid)
    return a


@app.put('/api/animais/{id}', tags=['Animais'])
def editar_animal(id: int, dados: m.AnimalBase, background: BackgroundTasks, u=Depends(sessao)):
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        anterior = item(c, 'animais', id)
        if anterior['situacao'] != 'ATIVO' and (dados.situacao or anterior['situacao']) != 'ATIVO':
            raise HTTPException(409, 'Animal inativo. Envie situacao ATIVO para reativá-lo.')
        validar_vinculos_animal(c, dados)
        campos = valores(dados) | {'versao': anterior['versao'] + 1}
        atualizar(c, 'animais', id, campos)
        chip = chip_ativo(c, id)
        if chip:
            evento_animal(c, item(c, 'animais', id), 'ATUALIZACAO_ANIMAL', chip['codigo'])
        r = animal_completo(c, id)
    if chip:
        background.add_task(enviar, id)
    return r


@app.delete('/api/animais/{id}', status_code=204, tags=['Animais'])
def inativar_animal(id: int, background: BackgroundTasks, u=Depends(sessao)):
    enviar_ao_governo = False
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        a = item(c, 'animais', id)
        chip = chip_ativo(c, id)
        if a['situacao'] == 'ATIVO':
            atualizar(c, 'animais', id, {'situacao': 'INATIVO', 'versao': a['versao'] + 1})
            if chip:
                evento_animal(c, item(c, 'animais', id), 'ATUALIZACAO_ANIMAL', chip['codigo'])
                enviar_ao_governo = True
    if enviar_ao_governo:
        background.add_task(enviar, id)
    return Response(status_code=204)


@app.post('/api/animais/{id}/microchip', status_code=201, tags=['Animais'])
def vincular(id: int, dados: m.MicrochipNovo, background: BackgroundTasks, u=Depends(sessao)):
    """Vincula ou substitui o microchip. O responsável é o veterinário autenticado (ativo e confirmado)."""
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        anterior = chip_ativo(c, id)
        vinculo = vincular_microchip(c, id, dados.codigo, u, dados.motivo)
    background.add_task(enviar, id)
    return vinculo | {'microchip_anterior': anterior['codigo'] if anterior else None}


@app.get('/api/animais/{id}/microchips', tags=['Animais'])
def historico_microchips(id: int, u=Depends(sessao)):
    with db() as c:
        item(c, 'animais', id, 'id')
        return [dict(x) for x in c.execute(
            '''SELECT m.*, v.nome AS veterinario FROM vinculos_microchip m JOIN veterinarios v ON v.id=m.veterinario_id
               WHERE m.animal_id=? ORDER BY m.id DESC''', (id,))]


# ================================================================ consultas e vacinas (3.8 e 3.9)
def veterinario_responsavel(c, informado, u):
    v = c.execute('SELECT id,nome,crmv_numero,crmv_uf,situacao,senha_confirmada FROM veterinarios WHERE id=?',
                  (informado or u['id'],)).fetchone()
    if v is None:
        raise HTTPException(422, 'Veterinário não encontrado.')
    if v['situacao'] != 'ATIVO' or not v['senha_confirmada']:
        raise HTTPException(422, 'Veterinário inativo ou sem senha confirmada.')
    return v


def animal_para_atendimento(c, animal_id, dia):
    a = item(c, 'animais', animal_id)
    if a['situacao'] != 'ATIVO':
        raise HTTPException(409, 'Animal inativo.')
    if a['nascimento'] and dia.isoformat() < a['nascimento']:
        raise HTTPException(422, 'Atendimento anterior ao nascimento do animal.')
    return a


def validar_datas_vacina(data_aplicacao, validade, aplicada):
    if aplicada and data_aplicacao > date.today():
        raise HTTPException(422, 'Vacina aplicada não pode ter data futura. Use a situação AGENDADA.')
    if aplicada and validade and validade < data_aplicacao:
        raise HTTPException(422, 'O lote estava vencido na data de aplicação.')


def enfileirar_vacina(c, v, animal, chip, vet):
    """Toda vacina antirrábica efetivamente aplicada gera uma solicitação ao governo (premissa do item 4)."""
    dados = {'microchip': chip, 'animal_id': animal['id'], 'animal_nome': animal['nome'], 'vacina_id': v['id'],
             'nome': v['nome'], 'fabricante': v['fabricante'], 'lote': v['lote'], 'data_aplicacao': v['data_aplicacao'],
             'veterinario_nome': vet['nome'], 'veterinario_crmv': f"{vet['crmv_numero']}/{vet['crmv_uf']}"}
    enfileirar(c, animal['id'], 'VACINA_ANTIRRABICA', dados, f"vacina-{v['id']}", v['id'])


@app.post('/api/consultas', status_code=201, tags=['Atendimento'])
def criar_consulta(dados: m.ConsultaNova, u=Depends(sessao)):
    if dados.situacao == 'REALIZADA' and dados.data_hora > datetime.now():
        raise HTTPException(422, 'Consulta realizada não pode estar no futuro. Use a situação AGENDADA.')
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        animal_para_atendimento(c, dados.animal_id, dados.data_hora.date())
        vet = veterinario_responsavel(c, dados.veterinario_id, u)
        campos = dados.model_dump(mode='json', exclude={'veterinario_id'}) | {'veterinario_id': vet['id']}
        return item(c, 'consultas', inserir(c, 'consultas', campos))


@app.put('/api/consultas/{id}/situacao', tags=['Atendimento'])
def situacao_consulta(id: int, dados: m.ConsultaSituacao, u=Depends(sessao)):
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        atual = item(c, 'consultas', id)
        if atual['situacao'] != 'AGENDADA':
            raise HTTPException(409, 'Somente consultas AGENDADAS podem mudar de situação.')
        if dados.situacao == 'REALIZADA' and datetime.fromisoformat(atual['data_hora']) > datetime.now():
            raise HTTPException(422, 'A consulta ainda não aconteceu.')
        atualizar(c, 'consultas', id, {'situacao': dados.situacao})
        return item(c, 'consultas', id)


@app.post('/api/vacinas', status_code=201, tags=['Atendimento'])
def criar_vacina(dados: m.VacinaNova, background: BackgroundTasks, u=Depends(sessao)):
    aplicada = dados.situacao == 'APLICADA'
    validar_datas_vacina(dados.data_aplicacao, dados.validade_lote, aplicada)
    gera_envio = aplicada and dados.antirrabica
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        animal = animal_para_atendimento(c, dados.animal_id, dados.data_aplicacao)
        vet = veterinario_responsavel(c, dados.veterinario_id, u)
        chip = chip_ativo(c, animal['id'])
        if gera_envio and chip is None:
            raise HTTPException(422, 'Vincule um microchip ao animal antes de registrar a vacina antirrábica '
                                     '(o envio ao governo exige o microchip).')
        campos = dados.model_dump(mode='json', exclude={'veterinario_id'}) | {'veterinario_id': vet['id']}
        v = item(c, 'vacinas', inserir(c, 'vacinas', campos))
        if gera_envio:
            enfileirar_vacina(c, v, animal, chip['codigo'], vet)
    if gera_envio:
        background.add_task(enviar, animal['id'])
    return v


@app.put('/api/vacinas/{id}/situacao', tags=['Atendimento'])
def situacao_vacina(id: int, dados: m.VacinaSituacao, background: BackgroundTasks, u=Depends(sessao)):
    """Muda uma vacina AGENDADA para APLICADA (gera o envio, se antirrábica) ou CANCELADA."""
    gera_envio = False
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        v = item(c, 'vacinas', id)
        if v['situacao'] != 'AGENDADA':
            raise HTTPException(409, 'Somente vacinas AGENDADAS podem mudar de situação.')
        novo = {'situacao': dados.situacao}
        if dados.situacao == 'APLICADA':
            dia = dados.data_aplicacao or date.today()
            validade = date.fromisoformat(v['validade_lote']) if v['validade_lote'] else None
            validar_datas_vacina(dia, validade, True)
            animal = animal_para_atendimento(c, v['animal_id'], dia)
            chip = chip_ativo(c, animal['id'])
            if v['antirrabica'] and chip is None:
                raise HTTPException(422, 'Vincule um microchip ao animal antes de aplicar a vacina antirrábica.')
            novo['data_aplicacao'] = dia.isoformat()
        atualizar(c, 'vacinas', id, novo)
        v = item(c, 'vacinas', id)
        if dados.situacao == 'APLICADA' and v['antirrabica']:
            vet = c.execute('SELECT id,nome,crmv_numero,crmv_uf FROM veterinarios WHERE id=?',
                            (v['veterinario_id'],)).fetchone()
            enfileirar_vacina(c, v, animal, chip['codigo'], vet)
            gera_envio = True
    if gera_envio:
        background.add_task(enviar, v['animal_id'])
    return v


SQL_CONSULTAS = '''SELECT c.*, v.nome AS veterinario FROM consultas c JOIN veterinarios v ON v.id=c.veterinario_id
                   WHERE c.animal_id=? ORDER BY c.data_hora DESC, c.id DESC'''
SQL_VACINAS = '''SELECT a.*, v.nome AS veterinario FROM vacinas a JOIN veterinarios v ON v.id=a.veterinario_id
                 WHERE a.animal_id=? ORDER BY a.data_aplicacao DESC, a.id DESC'''


def vacinas_do_animal(c, id):
    return [dict(x) | {'antirrabica': bool(x['antirrabica'])} for x in c.execute(SQL_VACINAS, (id,))]


@app.get('/api/animais/{id}/consultas', tags=['Atendimento'])
def consultas_do_animal(id: int, u=Depends(sessao)):
    with db() as c:
        item(c, 'animais', id, 'id')
        return [dict(x) for x in c.execute(SQL_CONSULTAS, (id,))]


@app.get('/api/animais/{id}/vacinas', tags=['Atendimento'])
def vacinas_por_animal(id: int, u=Depends(sessao)):
    with db() as c:
        item(c, 'animais', id, 'id')
        return vacinas_do_animal(c, id)


@app.get('/api/animais/{id}/historico', tags=['Atendimento'])
def historico(id: int, u=Depends(sessao)):
    with db() as c:
        return {'animal': animal_completo(c, id), 'consultas': [dict(x) for x in c.execute(SQL_CONSULTAS, (id,))],
                'vacinas': vacinas_do_animal(c, id),
                'microchips': [dict(x) for x in c.execute(
                    '''SELECT m.*, v.nome AS veterinario FROM vinculos_microchip m
                       JOIN veterinarios v ON v.id=m.veterinario_id WHERE m.animal_id=? ORDER BY m.id DESC''', (id,))]}


@app.get('/api/vacinas/proximas-doses', tags=['Atendimento'])
def proximas_doses(animal_id: Optional[int] = None, u=Depends(sessao)):
    """Doses previstas a partir de hoje (vacinas aplicadas com data_proxima_dose preenchida)."""
    hoje = date.today()
    filtro = ' AND a.animal_id=?' if animal_id is not None else ''
    with db() as c:
        linhas = c.execute('''SELECT a.id AS vacina_id, a.nome AS vacina, a.data_proxima_dose, a.dose_etapa,
                              an.id AS animal_id, an.nome AS animal
                              FROM vacinas a JOIN animais an ON an.id=a.animal_id
                              WHERE a.situacao='APLICADA' AND an.situacao='ATIVO' AND a.data_proxima_dose >= ?'''
                           + filtro + ' ORDER BY a.data_proxima_dose',
                           (hoje.isoformat(), animal_id) if filtro else (hoje.isoformat(),)).fetchall()
    return [dict(x) | {'dias_restantes': (date.fromisoformat(x['data_proxima_dose']) - hoje).days} for x in linhas]


# ================================================================ integração com o governo (itens 4 e 5)
SQL_INTEGRACAO = '''SELECT i.id, i.animal_id, a.nome AS animal, i.vacina_id, i.tipo, i.situacao, i.tentativas,
                    i.protocolo_externo, i.chave_idempotencia, i.mensagem_erro, i.data_solicitacao, i.data_resposta
                    FROM integracoes_governo i JOIN animais a ON a.id=i.animal_id'''


@app.get('/api/integracao', tags=['Integração'])
def operacoes(animal_id: Optional[int] = None, u=Depends(sessao)):
    filtro = ' WHERE i.animal_id=?' if animal_id is not None else ''
    with db() as c:
        return [dict(x) for x in c.execute(SQL_INTEGRACAO + filtro + ' ORDER BY i.id DESC',
                                           (animal_id,) if filtro else ())]


@app.get('/api/integracao/{id}', tags=['Integração'])
def consultar_operacao(id: int, u=Depends(sessao)):
    """Estado de uma comunicação (regra 8 do item 4)."""
    with db() as c:
        r = c.execute(SQL_INTEGRACAO + ' WHERE i.id=?', (id,)).fetchone()
    if r is None:
        raise HTTPException(404, 'Registro não encontrado.')
    return dict(r)


@app.post('/api/integracao/reenviar', tags=['Integração'])
def reenviar(animal_id: Optional[int] = None, u=Depends(sessao)):
    return enviar(animal_id)


@app.put('/api/integracao/simulacao', tags=['Integração'])
def simular(indisponivel: bool, u=Depends(sessao)):
    """Liga/desliga a indisponibilidade simulada da API governamental (para a demonstração)."""
    try:
        r = httpx.put(f'{GOV_URL}/api/governo/simulacao', params={'indisponivel': str(indisponivel).lower()},
                      headers={'X-API-Key': GOV_KEY}, timeout=3)
        r.raise_for_status()
        return r.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(503, 'Verifique se a API governamental está rodando.')
