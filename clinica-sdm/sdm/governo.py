"""API governamental ficticia, executada em processo e banco proprios."""
import hashlib
import json
import re
import secrets
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.security import APIKeyHeader
from .base import GOV_KEY, db
from .modelos import GovAnimal, GovVacina

@asynccontextmanager
async def lifespan(app):
    with db('governo') as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS animais (id INTEGER PRIMARY KEY, versao INTEGER NOT NULL, microchip TEXT NOT NULL UNIQUE, dados TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS vacinas (id INTEGER PRIMARY KEY, animal_id INTEGER NOT NULL REFERENCES animais(id), dados TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS protocolos (chave TEXT PRIMARY KEY, hash TEXT NOT NULL, protocolo TEXT UNIQUE NOT NULL);
        CREATE TABLE IF NOT EXISTS configuracao (id INTEGER PRIMARY KEY CHECK(id=1), indisponivel INTEGER NOT NULL DEFAULT 0);
        INSERT OR IGNORE INTO configuracao(id) VALUES (1);''')
    yield

app = FastAPI(title='SDM | Governo simulado', version='1.0.0', lifespan=lifespan)


def credencial(chave=Depends(APIKeyHeader(name='X-API-Key', auto_error=False))):
    if not chave or not secrets.compare_digest(chave.encode(), GOV_KEY.encode()):
        raise HTTPException(401, 'Chave de integracao invalida.')


def registrar(tipo, entrada, chave):
    dados = entrada.model_dump(mode='json')
    raw = json.dumps(dados, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(f'{tipo}:{raw}'.encode()).hexdigest()
    with db('governo') as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute('SELECT indisponivel FROM configuracao WHERE id=1').fetchone()[0]:
            raise HTTPException(503, 'Indisponibilidade simulada.')
        anterior = c.execute('SELECT * FROM protocolos WHERE chave=?', (chave,)).fetchone()
        if anterior:
            if anterior['hash'] != digest:
                raise HTTPException(409, 'Chave ja usada para outro conteudo.')
            return {'protocolo': anterior['protocolo'], 'repetido': True}
        if tipo == 'animal':
            if not re.fullmatch(r'[0-9]{15}', entrada.microchip):
                raise HTTPException(422, 'Microchip deve ter 15 digitos.')
            duplicado = c.execute('SELECT id FROM animais WHERE microchip=? AND id<>?', (entrada.microchip, entrada.animal_id)).fetchone()
            if duplicado:
                raise HTTPException(409, 'Microchip ja vinculado a outro animal.')
            prev = c.execute('SELECT versao FROM animais WHERE id=?', (entrada.animal_id,)).fetchone()
            if prev and entrada.versao <= prev['versao']:
                raise HTTPException(409, 'Versao ja registrada ou desatualizada.')
            c.execute('''INSERT INTO animais VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE
            SET versao=excluded.versao,microchip=excluded.microchip,dados=excluded.dados''', (entrada.animal_id, entrada.versao, entrada.microchip, raw))
        else:
            if not c.execute('SELECT id FROM animais WHERE id=?', (entrada.animal_id,)).fetchone():
                raise HTTPException(409, 'Cadastre o animal antes da vacina.')
            if c.execute('SELECT id FROM vacinas WHERE id=?', (entrada.vacina_id,)).fetchone():
                raise HTTPException(409, 'Vacina ja registrada com outra chave.')
            c.execute('INSERT INTO vacinas VALUES (?,?,?)', (entrada.vacina_id, entrada.animal_id, raw))
        protocolo = 'GOV-' + secrets.token_hex(8).upper()
        c.execute('INSERT INTO protocolos VALUES (?,?,?)', (chave, digest, protocolo))
        return {'protocolo': protocolo, 'repetido': False}

@app.get('/saude')
def saude():
    return {'servico': 'governo simulado'}

@app.put('/animais/{animal_id}', dependencies=[Depends(credencial)])
def animal(animal_id: int, entrada: GovAnimal, chave: str = Header(alias='Idempotency-Key', min_length=8, max_length=120)):
    if animal_id != entrada.animal_id:
        raise HTTPException(422, 'IDs de animal nao coincidem.')
    return registrar('animal', entrada, chave)

@app.post('/vacinas-antirrabicas', dependencies=[Depends(credencial)])
def vacina(entrada: GovVacina, chave: str = Header(alias='Idempotency-Key', min_length=8, max_length=120)):
    return registrar('vacina', entrada, chave)

@app.put('/simulacao', dependencies=[Depends(credencial)])
def simular(indisponivel: bool):
    with db('governo') as c:
        c.execute('UPDATE configuracao SET indisponivel=? WHERE id=1', (indisponivel,))
    return {'indisponivel': indisponivel}

@app.get('/registros', dependencies=[Depends(credencial)])
def registros():
    with db('governo') as c:
        return {t: [json.loads(x[0]) for x in c.execute(f'SELECT dados FROM {t} ORDER BY id')] for t in ('animais','vacinas')}
