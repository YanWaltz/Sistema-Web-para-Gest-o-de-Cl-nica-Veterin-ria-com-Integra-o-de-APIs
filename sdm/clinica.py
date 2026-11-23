"""API privada e entrada da interface web."""
import re
import sqlite3
from contextlib import asynccontextmanager
from datetime import date
import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from .base import GOV_KEY, GOV_URL, ROOT, db
from . import modelos as m
from .integracao import enfileirar, enviar
from .seguranca import admin, autenticar, criar_usuarios, sessao

@asynccontextmanager
async def lifespan(app):
    with db() as c:
        c.executescript((ROOT / 'schema.sql').read_text(encoding='utf-8'))
        criar_usuarios(c)
    yield

app = FastAPI(title='SDM | Clínica veterinária', version='1.0.0', lifespan=lifespan)
app.mount('/web', StaticFiles(directory=ROOT / 'web'), name='web')

@app.exception_handler(sqlite3.IntegrityError)
async def integridade(request: Request, exc: sqlite3.IntegrityError):
    detalhe = 'Cadastro duplicado ou vínculo inválido. Confira os dados.'
    if 'FOREIGN KEY' in str(exc):
        detalhe = 'O vínculo não existe, a raça não pertence à espécie ou o cadastro está em uso.'
    elif 'animais.microchip' in str(exc):
        detalhe = 'Este microchip já está vinculado a um animal.'
    return JSONResponse(status_code=409, content={'detail': detalhe})

@app.get('/', include_in_schema=False)
def home():
    return FileResponse(ROOT / 'web' / 'index.html')

@app.get('/saude', tags=['Sistema'])
def saude():
    return {'servico': 'clinica'}

@app.post('/api/login', tags=['Acesso'])
def login(dados: m.Login):
    return autenticar(dados.usuario, dados.senha)

@app.get('/api/me', tags=['Acesso'])
def eu(u=Depends(sessao)):
    return {k: u[k] for k in ('usuario','papel')}

@app.post('/api/logout', status_code=204, tags=['Acesso'])
def logout(u=Depends(sessao)):
    with db() as c:
        c.execute('DELETE FROM sessoes WHERE token_hash=?', (u['token_hash'],))
    return Response(status_code=204)


def item(c, tabela, id):
    r = c.execute(f'SELECT * FROM {tabela} WHERE id=?', (id,)).fetchone()
    if r is None:
        raise HTTPException(404, 'Registro não encontrado.')
    return dict(r)


def inserir(c, tabela, dados):
    campos = ','.join(dados)
    vals = ','.join('?' for _ in dados)
    return c.execute(f'INSERT INTO {tabela}({campos}) VALUES ({vals})', tuple(dados.values())).lastrowid


def atualizar(c, tabela, id, dados):
    campos = ','.join(k+'=?' for k in dados)
    c.execute(f'UPDATE {tabela} SET {campos} WHERE id=?', (*dados.values(),id))


def cadastrar_crud(tabela, modelo):
    # Os nomes de tabela e de colunas vêm do código, não da requisição.
    base = f'/api/{tabela}'
    def listar(u=Depends(sessao)):
        with db() as c:
            return [dict(x) for x in c.execute(f'SELECT * FROM {tabela} ORDER BY id DESC')]
    def consultar(id: int, u=Depends(sessao)):
        with db() as c:
            return item(c,tabela,id)
    def criar(dados: modelo, u=Depends(sessao)):
        with db() as c:
            return item(c,tabela,inserir(c,tabela,dados.model_dump(mode='json')))
    def editar(id: int, dados: modelo, u=Depends(sessao)):
        with db() as c:
            item(c,tabela,id)
            atualizar(c,tabela,id,dados.model_dump(mode='json'))
            return item(c,tabela,id)
    def excluir(id: int, u=Depends(admin)):
        with db() as c:
            item(c,tabela,id)
            c.execute(f'DELETE FROM {tabela} WHERE id=?',(id,))
        return Response(status_code=204)
    for met, path, func, status in [('GET',base,listar,200), ('POST',base,criar,201), ('GET',base+'/{id}',consultar,200), ('PUT',base+'/{id}',editar,200), ('DELETE',base+'/{id}',excluir,204)]:
        app.add_api_route(path,func,methods=[met],status_code=status,tags=[tabela.capitalize()],operation_id=f'{tabela}_{func.__name__}')

for tab, model in [('enderecos',m.Endereco),('tutores',m.Tutor),('especies',m.Nome),('racas',m.Raca),('veterinarios',m.Veterinario)]:
    cadastrar_crud(tab,model)


def evento_animal(c, r, tipo):
    especie = item(c,'especies',r['especie_id'])['nome']
    dados = {'animal_id': r['id'], 'versao': r['versao'], 'nome': r['nome'], 'especie': especie, 'microchip': r['microchip'], 'ativo': bool(r['ativo'])}
    enfileirar(c,tipo,dados,f"animal-{r['id']}-v{r['versao']}")


def validar_animal(dados):
    if not re.fullmatch(r'[0-9]{15}',dados.microchip):
        raise HTTPException(422, 'Informe 15 dígitos no microchip.')
    if dados.nascimento and dados.nascimento > date.today():
        raise HTTPException(422, 'Nascimento não pode estar no futuro.')

@app.get('/api/animais', tags=['Animais'])
def listar_animais(q: str = Query(default='', max_length=100), u=Depends(sessao)):
    with db() as c:
        return [dict(x) for x in c.execute('''SELECT a.*, t.nome AS tutor, e.nome AS especie, r.nome AS raca
            FROM animais a JOIN tutores t ON a.tutor_id=t.id JOIN especies e ON a.especie_id=e.id
            LEFT JOIN racas r ON a.raca_id=r.id WHERE a.nome LIKE ? OR a.microchip LIKE ? ORDER BY a.id DESC''',(f'%{q}%', f'%{q}%'))]

@app.get('/api/animais/{id}', tags=['Animais'])
def animal(id: int, u=Depends(sessao)):
    with db() as c:
        return item(c,'animais',id)

@app.post('/api/animais', status_code=201, tags=['Animais'])
def criar_animal(dados: m.Animal, background: BackgroundTasks, u=Depends(sessao)):
    validar_animal(dados)
    with db() as c:
        r = item(c,'animais',inserir(c,'animais',dados.model_dump(mode='json')))
        evento_animal(c,r,'CADASTRO_ANIMAL')
    background.add_task(enviar,r['id'])
    return r

@app.put('/api/animais/{id}', tags=['Animais'])
def editar_animal(id: int, dados: m.Animal, background: BackgroundTasks, u=Depends(sessao)):
    validar_animal(dados)
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        anterior = item(c,'animais',id)
        if not anterior['ativo']:
            raise HTTPException(409, 'Animal inativo.')
        atualizar(c,'animais',id,dados.model_dump(mode='json') | {'versao':anterior['versao']+1})
        r = item(c,'animais',id)
        evento_animal(c,r,'ATUALIZACAO_ANIMAL')
    background.add_task(enviar,id)
    return r

@app.delete('/api/animais/{id}', status_code=204, tags=['Animais'])
def desativar(id: int, background: BackgroundTasks, u=Depends(admin)):
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        r = item(c,'animais',id)
        if r['ativo']:
            atualizar(c,'animais',id,{'ativo':0,'versao':r['versao']+1})
            evento_animal(c,item(c,'animais',id),'INATIVACAO_ANIMAL')
            background.add_task(enviar,id)
    return Response(status_code=204)


def atendimento(tabela, dados, background):
    if dados.data > date.today():
        raise HTTPException(422, 'A data do atendimento não pode estar no futuro.')
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        a = item(c,'animais',dados.animal_id)
        if not a['ativo']:
            raise HTTPException(409,'Animal inativo.')
        if a['nascimento'] and dados.data.isoformat() < a['nascimento']:
            raise HTTPException(422,'Atendimento anterior ao nascimento.')
        id = inserir(c,tabela,dados.model_dump(mode='json'))
        r = item(c,tabela,id)
        if tabela == 'vacinas' and dados.antirrabica:
            evt = {k:r[k] for k in ('animal_id','nome','lote','data')}
            enfileirar(c,'VACINA_ANTIRRABICA',evt | {'vacina_id':id},f'vacina-{id}')
            background.add_task(enviar,a['id'])
    return r

@app.post('/api/consultas', status_code=201, tags=['Atendimento'])
def consulta(dados:m.Consulta, background:BackgroundTasks, u=Depends(sessao)):
    return atendimento('consultas',dados,background)

@app.post('/api/vacinas', status_code=201, tags=['Atendimento'])
def vacina(dados:m.Vacina, background:BackgroundTasks, u=Depends(sessao)):
    return atendimento('vacinas',dados,background)

@app.get('/api/animais/{id}/historico', tags=['Atendimento'])
def historico(id:int, u=Depends(sessao)):
    with db() as c:
        r = item(c,'animais',id)
        return {'animal':r, **{t: [dict(x) for x in c.execute(f'''SELECT a.*, v.nome AS veterinario FROM {t} a
                            JOIN veterinarios v ON v.id=a.veterinario_id WHERE a.animal_id=? ORDER BY a.data DESC,a.id DESC''',(id,))] for t in ('consultas','vacinas')}}

@app.get('/api/cep/{cep}', tags=['ViaCEP'])
def buscar_cep(cep: str, u=Depends(sessao)):
    if not re.fullmatch(r'[0-9]{5}-?[0-9]{3}',cep):
        raise HTTPException(422,'Informe um CEP com 8 dígitos.')
    try:
        r = httpx.get(f"https://viacep.com.br/ws/{cep.replace('-', '')}/json/",timeout=4.0)
        r.raise_for_status()
        x = r.json()
        if not isinstance(x,dict):
            raise ValueError()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(503,'ViaCEP indisponível. Preencha o endereço manualmente.')
    if str(x.get('erro','')).lower() == 'true':
        raise HTTPException(404,'CEP não encontrado.')
    return {'cep':x.get('cep',cep),'logradouro':x.get('logradouro',''),'bairro':x.get('bairro',''),'cidade':x.get('localidade',''),'uf':x.get('uf','')}

@app.get('/api/integracao', tags=['Integração'])
def operacoes(u=Depends(sessao)):
    with db() as c:
        return [dict(x) for x in c.execute('''SELECT o.id,o.animal_id,a.nome AS animal,o.tipo,o.status,o.tentativas,
                   o.protocolo,o.erro,o.criado,o.atualizado FROM operacoes o JOIN animais a ON a.id=o.animal_id ORDER BY o.id DESC''')]

@app.post('/api/integracao/reenviar', tags=['Integração'])
def reenviar(u=Depends(admin)):
    return enviar()

@app.put('/api/integracao/simulacao', tags=['Integração'])
def simular(indisponivel:bool, u=Depends(admin)):
    try:
        r = httpx.put(f'{GOV_URL}/simulacao',params={'indisponivel':str(indisponivel).lower()},headers={'X-API-Key':GOV_KEY},timeout=3)
        r.raise_for_status()
        return r.json()
    except (httpx.HTTPError,ValueError):
        raise HTTPException(503,'Verifique se a API governamental está rodando.')
