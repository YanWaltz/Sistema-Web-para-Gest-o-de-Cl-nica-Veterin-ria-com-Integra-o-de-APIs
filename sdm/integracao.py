"""Outbox persistente: o registro local NÃO depende do serviço governamental estar no ar.

Fluxo: a API grava o dado e a solicitação (tabela integracoes_governo) na mesma transação;
depois tenta enviar. Se o governo estiver fora, a solicitação continua guardada e pode ser reenviada.
"""
import json
from threading import Lock

import httpx

from .base import GOV_KEY, GOV_URL, db

lock = Lock()


def enfileirar(c, animal_id, tipo, dados, chave, vacina_id=None):
    c.execute('''INSERT INTO integracoes_governo(animal_id,vacina_id,tipo,payload,chave_idempotencia)
                 VALUES (?,?,?,?,?)''',
              (animal_id, vacina_id, tipo, json.dumps(dados, ensure_ascii=False), f'sdm-{chave}'))


def _detalhe(resposta):
    try:
        d = resposta.json().get('detail')
        return str(d)[:300] if d else ''
    except (ValueError, AttributeError):
        return ''


def _tentar(op):
    """Faz UMA tentativa de envio. Devolve (situacao, protocolo, mensagem_de_erro, houve_resposta)."""
    payload = json.loads(op['payload'])
    headers = {'X-API-Key': GOV_KEY, 'Idempotency-Key': op['chave_idempotencia']}
    if op['tipo'] == 'VACINA_ANTIRRABICA':
        metodo, url = 'POST', f'{GOV_URL}/api/governo/vacinacoes-antirrabicas'
    elif op['tipo'] == 'CADASTRO_ANIMAL':
        metodo, url = 'POST', f'{GOV_URL}/api/governo/animais'
    else:
        metodo, url = 'PUT', f"{GOV_URL}/api/governo/animais/{payload['microchip']}"
    try:
        r = httpx.request(metodo, url, json=payload, headers=headers, timeout=2.0)
    except (httpx.ConnectError, httpx.ConnectTimeout):
        return 'PENDENTE', None, 'API governamental indisponível (sem conexão). Será reenviada.', False
    except httpx.HTTPError:
        return ('ENVIADA', None,
                'A requisição foi enviada, mas a resposta não foi conclusiva. O reenvio usa a mesma chave de idempotência.',
                False)
    if r.is_success:
        try:
            protocolo = r.json().get('protocolo')
        except (ValueError, AttributeError):
            protocolo = None
        if isinstance(protocolo, str) and protocolo:
            return 'CONFIRMADA', protocolo, None, True
        return 'ENVIADA', None, 'Resposta do governo sem protocolo.', True
    if r.status_code >= 500:
        return 'PENDENTE', None, f'Governo indisponível (HTTP {r.status_code}). {_detalhe(r)}'.strip(), True
    return 'FALHA', None, f'Governo recusou a solicitação (HTTP {r.status_code}). {_detalhe(r)}'.strip(), True


def enviar(animal_id=None):
    """Tenta enviar tudo o que ainda não foi CONFIRMADO (novos envios e reenvios)."""
    with lock:  # um envio por vez nesta instância
        with db() as c:
            filtro = ' AND animal_id=?' if animal_id is not None else ''
            ops = c.execute("SELECT * FROM integracoes_governo WHERE situacao<>'CONFIRMADA'" + filtro + ' ORDER BY id',
                            (animal_id,) if filtro else ()).fetchall()
        bloqueados = set()  # animais cujo cadastro/atualização ainda não chegou ao governo
        confirmadas = 0
        for op in ops:
            vacina = op['tipo'] == 'VACINA_ANTIRRABICA'
            # Atualizações do mesmo animal seguem a ordem. A vacina é independente: a comunicação é
            # obrigatória mesmo que o animal ainda não esteja cadastrado no governo.
            if not vacina and op['animal_id'] in bloqueados:
                continue
            situacao, protocolo, erro, respondeu = _tentar(op)
            with db() as c:
                c.execute('''UPDATE integracoes_governo SET situacao=?, protocolo_externo=COALESCE(?,protocolo_externo),
                             mensagem_erro=?, tentativas=tentativas+1,
                             data_resposta=CASE WHEN ? THEN CURRENT_TIMESTAMP ELSE data_resposta END WHERE id=?''',
                          (situacao, protocolo, erro, int(respondeu), op['id']))
            if situacao == 'CONFIRMADA':
                confirmadas += 1
            elif situacao in ('PENDENTE', 'ENVIADA') and not vacina:
                bloqueados.add(op['animal_id'])
        with db() as c:
            r = c.execute("""SELECT SUM(situacao IN ('PENDENTE','ENVIADA')), SUM(situacao='FALHA')
                             FROM integracoes_governo WHERE situacao<>'CONFIRMADA'""").fetchone()
        return {'confirmadas': confirmadas, 'pendentes': r[0] or 0, 'falhas': r[1] or 0}
