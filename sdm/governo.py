"""API governamental FICTÍCIA, executada em processo e banco próprios (separados da clínica).

O animal é identificado pelo microchip. Não é uma integração oficial com sistemas reais.
"""
import hashlib
import json
import secrets
from contextlib import asynccontextmanager
from datetime import date

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.security import APIKeyHeader

from .base import GOV_KEY, db
from .modelos import GovAnimal, GovVacina

DDL = '''
CREATE TABLE IF NOT EXISTS animais (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  microchip TEXT NOT NULL UNIQUE,
  animal_id INTEGER,
  versao INTEGER NOT NULL DEFAULT 0,
  origem TEXT NOT NULL CHECK(origem IN ('CADASTRO','VACINA')),
  situacao TEXT NOT NULL DEFAULT 'ATIVO' CHECK(situacao IN ('ATIVO','INATIVO','OBITO','SUBSTITUIDO')),
  dados TEXT NOT NULL,
  criado TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS vacinacoes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  animal_gov_id INTEGER NOT NULL REFERENCES animais(id),
  vacina_id INTEGER NOT NULL UNIQUE,
  dados TEXT NOT NULL,
  protocolo TEXT NOT NULL,
  criado TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS operacoes (
  protocolo TEXT PRIMARY KEY,
  chave TEXT NOT NULL UNIQUE,
  hash TEXT NOT NULL,
  tipo TEXT NOT NULL,
  microchip TEXT,
  resultado TEXT NOT NULL,
  mensagem TEXT,
  criado TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS configuracao (
  id INTEGER PRIMARY KEY CHECK(id=1),
  indisponivel INTEGER NOT NULL DEFAULT 0);
INSERT OR IGNORE INTO configuracao(id) VALUES (1);
'''


@asynccontextmanager
async def lifespan(app):
    with db('governo') as c:
        colunas = [r[1] for r in c.execute('PRAGMA table_info(animais)')]
        if colunas and 'origem' not in colunas:
            raise RuntimeError('Banco governamental antigo detectado em data/. Apague a pasta data/ e inicie de novo.')
        c.executescript(DDL)
    yield


app = FastAPI(title='SDM | Governo simulado', version='2.0.0', lifespan=lifespan)


def credencial(chave=Depends(APIKeyHeader(name='X-API-Key', auto_error=False))):
    if not chave or not secrets.compare_digest(chave.encode(), GOV_KEY.encode()):
        raise HTTPException(401, 'Chave de integração inválida.')


def processar(tipo, entrada, chave, acao):
    """Núcleo da idempotência: a mesma chave + mesmo conteúdo devolve o MESMO protocolo, sem duplicar nada."""
    dados = entrada.model_dump(mode='json')
    bruto = json.dumps(dados, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(f'{tipo}:{bruto}'.encode()).hexdigest()
    with db('governo') as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute('SELECT indisponivel FROM configuracao WHERE id=1').fetchone()[0]:
            raise HTTPException(503, 'Indisponibilidade simulada.')
        anterior = c.execute('SELECT * FROM operacoes WHERE chave=?', (chave,)).fetchone()
        if anterior:
            if anterior['hash'] != digest:
                raise HTTPException(409, 'Chave já usada para outro conteúdo.')
            return {'protocolo': anterior['protocolo'], 'repetido': True, 'resultado': anterior['resultado']}
        protocolo = 'GOV-' + secrets.token_hex(8).upper()
        resultado = acao(c, entrada, bruto, protocolo)  # pode recusar (HTTPException): nada é gravado
        c.execute('INSERT INTO operacoes(protocolo,chave,hash,tipo,microchip,resultado) VALUES (?,?,?,?,?,?)',
                  (protocolo, chave, digest, tipo, entrada.microchip, resultado))
        return {'protocolo': protocolo, 'repetido': False, 'resultado': resultado}


def por_microchip(c, microchip):
    return c.execute('SELECT * FROM animais WHERE microchip=?', (microchip,)).fetchone()


def acao_cadastro(c, e, bruto, protocolo):
    if e.microchip_anterior == e.microchip:
        raise HTTPException(422, 'O microchip anterior não pode ser igual ao novo.')
    atual = por_microchip(c, e.microchip)
    if atual and atual['origem'] == 'CADASTRO':
        raise HTTPException(409, 'Microchip já cadastrado no serviço governamental. Use PUT para atualizar.')
    if atual:  # existia só como pré-cadastro criado por uma vacina: agora completa o cadastro
        c.execute('''UPDATE animais SET animal_id=?, versao=?, origem='CADASTRO', situacao=?, dados=?,
                     atualizado=CURRENT_TIMESTAMP WHERE id=?''', (e.animal_id, e.versao, e.situacao, bruto, atual['id']))
        resultado = 'CADASTRO_COMPLETADO'
    else:
        c.execute('''INSERT INTO animais(microchip,animal_id,versao,origem,situacao,dados)
                     VALUES (?,?,?,'CADASTRO',?,?)''', (e.microchip, e.animal_id, e.versao, e.situacao, bruto))
        resultado = 'CADASTRO_CRIADO'
    if e.microchip_anterior:  # troca de microchip: o registro antigo fica preservado como SUBSTITUIDO
        c.execute("UPDATE animais SET situacao='SUBSTITUIDO', atualizado=CURRENT_TIMESTAMP WHERE microchip=?",
                  (e.microchip_anterior,))
    return resultado


def acao_atualizacao(c, e, bruto, protocolo):
    atual = por_microchip(c, e.microchip)
    if atual is None:
        raise HTTPException(404, 'Animal não cadastrado. Use POST para cadastrar.')
    if e.versao <= atual['versao']:
        raise HTTPException(409, 'Versão já registrada ou desatualizada.')
    c.execute('''UPDATE animais SET animal_id=?, versao=?, origem='CADASTRO', situacao=?, dados=?,
                 atualizado=CURRENT_TIMESTAMP WHERE id=?''', (e.animal_id, e.versao, e.situacao, bruto, atual['id']))
    return 'ATUALIZADO'


def acao_vacina(c, e, bruto, protocolo):
    if e.data_aplicacao > date.today():
        raise HTTPException(422, 'A data de aplicação não pode estar no futuro.')
    if c.execute('SELECT 1 FROM vacinacoes WHERE vacina_id=?', (e.vacina_id,)).fetchone():
        raise HTTPException(409, 'Vacinação já registrada com outra chave.')
    animal = por_microchip(c, e.microchip)
    resultado = 'VACINACAO_REGISTRADA'
    if animal is None:
        # A comunicação é obrigatória mesmo que o animal ainda não esteja cadastrado aqui:
        # criamos um pré-cadastro mínimo, que o cadastro completo depois preenche.
        stub = json.dumps({'microchip': e.microchip, 'animal_id': e.animal_id, 'nome': e.animal_nome}, ensure_ascii=False)
        gid = c.execute("INSERT INTO animais(microchip,animal_id,versao,origem,dados) VALUES (?,?,0,'VACINA',?)",
                        (e.microchip, e.animal_id, stub)).lastrowid
        resultado = 'VACINACAO_REGISTRADA_COM_PRE_CADASTRO'
    else:
        gid = animal['id']
    c.execute('INSERT INTO vacinacoes(animal_gov_id,vacina_id,dados,protocolo) VALUES (?,?,?,?)',
              (gid, e.vacina_id, bruto, protocolo))
    return resultado


@app.get('/saude')
def saude():
    return {'servico': 'governo simulado'}


@app.post('/api/governo/animais', status_code=201, dependencies=[Depends(credencial)], tags=['Animais'])
def cadastrar_animal(entrada: GovAnimal, chave: str = Header(alias='Idempotency-Key', min_length=8, max_length=120)):
    return processar('animal-cadastro', entrada, chave, acao_cadastro)


@app.get('/api/governo/animais/{microchip}', dependencies=[Depends(credencial)], tags=['Animais'])
def consultar_animal(microchip: str):
    with db('governo') as c:
        a = por_microchip(c, microchip)
        if a is None:
            raise HTTPException(404, 'Animal não encontrado para este microchip.')
        vacinas = [json.loads(x['dados']) | {'protocolo': x['protocolo']} for x in
                   c.execute('SELECT dados, protocolo FROM vacinacoes WHERE animal_gov_id=? ORDER BY id', (a['id'],))]
        return {'microchip': a['microchip'], 'origem': a['origem'], 'situacao': a['situacao'], 'versao': a['versao'],
                'atualizado': a['atualizado'], 'dados': json.loads(a['dados']), 'vacinacoes': vacinas}


@app.put('/api/governo/animais/{microchip}', dependencies=[Depends(credencial)], tags=['Animais'])
def atualizar_animal(microchip: str, entrada: GovAnimal,
                     chave: str = Header(alias='Idempotency-Key', min_length=8, max_length=120)):
    if microchip != entrada.microchip:
        raise HTTPException(422, 'O microchip da URL e o do corpo da requisição não coincidem.')
    return processar('animal-atualizacao', entrada, chave, acao_atualizacao)


@app.post('/api/governo/vacinacoes-antirrabicas', status_code=201, dependencies=[Depends(credencial)], tags=['Vacinação'])
def registrar_vacinacao(entrada: GovVacina, chave: str = Header(alias='Idempotency-Key', min_length=8, max_length=120)):
    return processar('vacina-antirrabica', entrada, chave, acao_vacina)


@app.get('/api/governo/operacoes/{protocolo}', dependencies=[Depends(credencial)], tags=['Operações'])
def consultar_operacao(protocolo: str):
    with db('governo') as c:
        o = c.execute('SELECT protocolo,tipo,microchip,resultado,mensagem,criado FROM operacoes WHERE protocolo=?',
                      (protocolo,)).fetchone()
    if o is None:
        raise HTTPException(404, 'Protocolo não encontrado.')
    return dict(o)


@app.put('/api/governo/simulacao', dependencies=[Depends(credencial)], tags=['Simulação'])
def simular(indisponivel: bool):
    with db('governo') as c:
        c.execute('UPDATE configuracao SET indisponivel=? WHERE id=1', (int(indisponivel),))
    return {'indisponivel': indisponivel}


@app.get('/api/governo/registros', dependencies=[Depends(credencial)], tags=['Simulação'])
def registros():
    with db('governo') as c:
        return {'animais': [json.loads(x[0]) for x in c.execute('SELECT dados FROM animais ORDER BY id')],
                'vacinacoes': [json.loads(x[0]) | {'protocolo': x[1]} for x in
                               c.execute('SELECT dados, protocolo FROM vacinacoes ORDER BY id')]}
