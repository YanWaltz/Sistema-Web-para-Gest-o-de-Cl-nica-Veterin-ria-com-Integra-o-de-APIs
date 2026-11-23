"""Outbox persistente: a gravação local não depende do serviço remoto."""
import json
from threading import Lock
import httpx
from .base import GOV_KEY, GOV_URL, db

lock = Lock()


def enfileirar(c, tipo, dados, chave):
    c.execute('INSERT INTO operacoes(animal_id,tipo,payload,chave) VALUES (?,?,?,?)',
              (dados['animal_id'], tipo, json.dumps(dados, ensure_ascii=False), f'sdm-{chave}'))


def enviar(animal_id=None):
    # Um worker por instância local. Protocolo remoto cobre resposta perdida.
    with lock:
        with db() as c:
            filtro = ' AND animal_id=?' if animal_id is not None else ''
            ops = c.execute("SELECT * FROM operacoes WHERE status<>'ENVIADO'" + filtro+' ORDER BY id', (animal_id,) if filtro else ()).fetchall()
        bloqueados = set()
        enviados = 0
        for op in ops:
            aid = op['animal_id']
            if aid in bloqueados:
                continue  # Nunca enviar vacina/atualização à frente da operação anterior.
            headers = {'X-API-Key': GOV_KEY, 'Idempotency-Key': op['chave']}
            protocolo = erro = None
            try:
                animal = op['tipo'] != 'VACINA_ANTIRRABICA'
                resposta = httpx.request('PUT' if animal else 'POST', GOV_URL + (f'/animais/{aid}' if animal else '/vacinas-antirrabicas'), json=json.loads(op['payload']), headers=headers, timeout=2.0)
                if resposta.is_success:
                    protocolo = resposta.json().get('protocolo')
                    if not isinstance(protocolo, str) or not protocolo:
                        protocolo = None
                        erro = 'Resposta sem protocolo.'
                else:
                    erro = f'Governo respondeu HTTP {resposta.status_code}.'
            except (httpx.HTTPError, ValueError, AttributeError):
                erro = 'Nao foi possivel comunicar com a API governamental.'
            with db() as c:
                c.execute('UPDATE operacoes SET status=?,protocolo=?,erro=?,tentativas=tentativas+1,atualizado=CURRENT_TIMESTAMP WHERE id=?',
                          ('ENVIADO' if protocolo else 'FALHA', protocolo, erro, op['id']))
            if protocolo:
                enviados += 1
            else:
                bloqueados.add(aid)
        return {'enviadas': enviados, 'animais_com_falha': len(bloqueados)}
