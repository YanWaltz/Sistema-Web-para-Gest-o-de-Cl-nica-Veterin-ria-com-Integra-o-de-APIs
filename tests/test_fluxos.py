"""Testes com as duas APIs em processos separados e bancos descartáveis."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import date, timedelta
from unittest.mock import patch
import httpx
from sdm.base import GOV_KEY
from sdm.clinica import buscar_cep
from fastapi import HTTPException


def porta():
    with socket.socket() as s:
        s.bind(('127.0.0.1',0))
        return s.getsockname()[1]

class Integrado(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(); cls.addClassCleanup(cls.tmp.cleanup)
        pr,pg=porta(),porta()
        while pr==pg: pg=porta()
        cls.url=f'http://127.0.0.1:{pr}'; cls.gov=f'http://127.0.0.1:{pg}'
        env=os.environ | {'SDM_DATA_DIR':cls.tmp.name,'SDM_GOV_URL':cls.gov,'SDM_GOV_KEY':GOV_KEY,'SDM_DEMO_PASSWORD':'ClinicaDemo!26'}
        for modulo,p,url in [('governo',pg,cls.gov),('clinica',pr,cls.url)]:
            proc=subprocess.Popen([sys.executable,'-m','uvicorn',f'sdm.{modulo}:app','--port',str(p),'--log-level','warning'],env=env)
            cls.addClassCleanup(cls.fechar,proc)
            for _ in range(100):
                try:
                    if httpx.get(url+'/saude',timeout=.25).is_success: break
                except httpx.HTTPError: pass
                if proc.poll() is not None: raise RuntimeError(f'{modulo} encerrou no início')
                time.sleep(.05)
            else: raise RuntimeError(f'{modulo} não subiu')
        cls.client=httpx.Client(base_url=cls.url,timeout=12); cls.addClassCleanup(cls.client.close)
        cls.remote=httpx.Client(base_url=cls.gov,timeout=5,headers={'X-API-Key':GOV_KEY}); cls.addClassCleanup(cls.remote.close)

    @staticmethod
    def fechar(proc):
        if proc.poll() is None: proc.terminate()
        try: proc.wait(timeout=5)
        except subprocess.TimeoutExpired: proc.kill(); proc.wait()

    def call(self, m, path, code, body=None, auth=None, headers=None):
        r = self.client.request(m, path, json=body, headers=(auth or {}) | (headers or {}))
        self.assertEqual(r.status_code, code, r.text)
        return r.json() if r.content else None

    def login(self, email='demo@clinica.local', senha='ClinicaDemo!26'):
        x = self.call('POST', '/api/auth/login', 200, {'email': email, 'senha': senha})
        return {'Authorization': 'Bearer ' + x['access_token']}

    def esperar(self, auth, animal_id, situacao, n=1):
        for _ in range(80):
            ops = self.call('GET', f'/api/integracao?animal_id={animal_id}', 200, auth=auth)
            if len([o for o in ops if o['situacao'] == situacao]) >= n:
                return ops
            time.sleep(.1)
        self.fail(f'Esperava {n} operação(ões) {situacao}: {ops}')

    # ---------- 1. acesso
    def test_01_login_e_protecao(self):
        self.assertIn('Entre', self.client.get('/').text)
        self.assertEqual(self.client.get('/docs').status_code, 200)
        self.call('GET', '/api/animais', 401)
        self.call('POST', '/api/auth/login', 401, {'email': 'demo@clinica.local', 'senha': 'errada123'})
        self.call('POST', '/api/auth/login', 401, {'email': 'naoexiste@x.com', 'senha': 'qualquer123'})
        a = self.login()
        self.assertEqual(self.call('GET', '/api/auth/me', 200, auth=a)['email'], 'demo@clinica.local')
        self.call('POST', '/api/auth/logout', 204, auth=a)
        self.call('GET', '/api/auth/me', 401, auth=a)

    def test_02_veterinario_cpf_confirmacao_e_bloqueios(self):
        a = self.login()
        vet = {'nome': 'Vet Novo', 'cpf': '529.982.247-25', 'crmv_numero': '777', 'crmv_uf': 'sp',
               'email': 'novo@clinica.local', 'senha': 'SenhaForte123'}
        self.call('POST', '/api/auth/registro', 422, vet | {'cpf': '111.111.111-11'})
        self.call('POST', '/api/auth/registro', 422, vet | {'cpf': '529.982.247-24'})
        r = self.call('POST', '/api/auth/registro', 201, vet)
        # CPF, e-mail e CRMV+UF são únicos
        self.call('POST', '/api/auth/registro', 409, vet | {'email': 'outro@clinica.local', 'crmv_numero': '778'})
        self.call('POST', '/api/auth/registro', 409, vet | {'cpf': '39053344705', 'crmv_numero': '779'})
        # senha não confirmada: não entra
        self.call('POST', '/api/auth/login', 403, {'email': 'novo@clinica.local', 'senha': 'SenhaForte123'})
        self.call('POST', '/api/auth/confirmar', 400, {'email': 'novo@clinica.local', 'codigo': '000000'}) \
            if r['codigo_confirmacao_simulado'] != '000000' else None
        self.call('POST', '/api/auth/confirmar', 200, {'email': 'novo@clinica.local', 'codigo': r['codigo_confirmacao_simulado']})
        novo = self.login('novo@clinica.local', 'SenhaForte123')
        vets = self.call('GET', '/api/veterinarios', 200, auth=a)
        mine = [v for v in vets if v['email'] == 'novo@clinica.local'][0]
        self.assertNotIn('senha_hash', mine)
        self.assertEqual(mine['cpf'], '52998224725')
        self.assertTrue(mine['senha_confirmada'] and mine['data_confirmacao'] and mine['ultimo_acesso'])
        # inativo: não entra e a sessão aberta cai
        self.call('DELETE', f"/api/veterinarios/{mine['id']}", 204, auth=a)
        self.call('GET', '/api/auth/me', 401, auth=novo)
        self.call('POST', '/api/auth/login', 403, {'email': 'novo@clinica.local', 'senha': 'SenhaForte123'})

    # ---------- 2. tutor, CPF e endereço
    def test_03_tutor_cpf_e_endereco_sem_duplicar(self):
        a = self.login()
        end = {'cep': '20040-020', 'numero': '10', 'logradouro': 'Rua Teste', 'bairro': 'Centro', 'cidade': 'Rio de Janeiro',
               'uf': 'RJ', 'codigo_ibge': '3304557'}
        e1 = self.call('POST', '/api/enderecos', 201, end, a)
        # mesmo CEP em outro número: não repete os dados do CEP; só informe o número
        e2 = self.call('POST', '/api/enderecos', 201, {'cep': '20040020', 'numero': '20'}, a)
        self.assertEqual((e1['cep_id'], e2['logradouro']), (e2['cep_id'], 'Rua Teste'))
        self.assertNotEqual(e1['id'], e2['id'])
        # mesmo CEP + número + complemento: reaproveita o registro
        e3 = self.call('POST', '/api/enderecos', 201, {'cep': '20040020', 'numero': '10'}, a)
        self.assertEqual(e3['id'], e1['id'])
        self.assertTrue(e3['reaproveitado'])
        self.call('POST', '/api/enderecos', 422, {'cep': '30130-010', 'numero': '1'}, a)  # CEP novo exige dados
        t = {'nome': 'Maria Tutora', 'cpf': '390.533.447-05', 'data_nascimento': '1990-05-10', 'email': 'MARIA@x.com',
             'telefone': '21999990001', 'endereco_id': e1['id']}
        self.call('POST', '/api/tutores', 422, t | {'cpf': '123.456.789-00'}, a)
        self.call('POST', '/api/tutores', 422, t | {'cpf': '000.000.000-00'}, a)
        ok = self.call('POST', '/api/tutores', 201, t, a)
        self.assertEqual((ok['cpf'], ok['situacao'], ok['email']), ('39053344705', 'ATIVO', 'maria@x.com'))
        self.assertTrue(ok['data_cadastro'])
        self.call('POST', '/api/tutores', 409, t | {'cpf': '39053344705', 'nome': 'Outra Pessoa'}, a)
        # dois tutores moram no mesmo endereço: só existe UM endereço no banco
        t2 = self.call('POST', '/api/tutores', 201, t | {'cpf': '52998224725', 'email': 'b@x.com'}, a)
        self.assertEqual(t2['endereco_id'], ok['endereco_id'])
        n = [x for x in self.call('GET', '/api/enderecos', 200, auth=a) if x['cep'] == '20040020' and x['numero'] == '10']
        self.assertEqual(len(n), 1)
        self.call('DELETE', f"/api/tutores/{t2['id']}", 204, auth=a)
        self.assertEqual(self.call('GET', f"/api/tutores/{t2['id']}", 200, auth=a)['situacao'], 'INATIVO')

    # ---------- 3. animais, raça/espécie, microchip e histórico
    def test_04_animais_microchip_e_historico(self):
        a = self.login()
        e = self.call('POST', '/api/enderecos', 201, {'cep': '01001-000', 'numero': '1', 'logradouro': 'Praça da Sé',
                      'bairro': 'Sé', 'cidade': 'São Paulo', 'uf': 'SP'}, a)
        tutor = self.call('POST', '/api/tutores', 201, {'nome': 'Tutor Animais', 'cpf': '11144477735', 'data_nascimento': '1985-01-01',
                          'email': 't@x.com', 'telefone': '1100000000', 'endereco_id': e['id']}, a)
        cao = self.call('POST', '/api/especies', 201, {'nome': 'Canina'}, a)
        gato = self.call('POST', '/api/especies', 201, {'nome': 'Felina'}, a)
        raca = self.call('POST', '/api/racas', 201, {'nome': 'Poodle', 'especie_id': cao['id']}, a)
        p = {'nome': 'Luna', 'nascimento': '2022-01-01', 'sexo': 'F', 'tutor_id': tutor['id'], 'especie_id': cao['id'],
             'raca_id': raca['id']}
        self.call('POST', '/api/animais', 422, p | {'especie_id': gato['id']}, a)  # raça incompatível com a espécie
        self.call('POST', '/api/animais', 422, {k: v for k, v in p.items() if k != 'nascimento'}, a)  # sem idade
        self.call('POST', '/api/animais', 422, p | {'microchip': 'ABC'}, a)
        sem_raca = self.call('POST', '/api/animais', 201, p | {'raca_id': None, 'nome': 'SRD'}, a)  # "sem raça"
        self.assertIsNone(sem_raca['raca'])
        animal = self.call('POST', '/api/animais', 201, p | {'microchip': '000000000000001'}, a)
        id = animal['id']
        self.assertEqual(animal['microchip'], '000000000000001')
        self.call('POST', '/api/animais', 409, p | {'nome': 'Clone', 'microchip': '000000000000001'}, a)  # chip único
        self.call('POST', f'/api/animais/{sem_raca["id"]}/microchip', 409, {'codigo': '000000000000001'}, a)
        self.esperar(a, id, 'CONFIRMADA')
        # substituição: o chip antigo permanece no histórico
        novo = self.call('POST', f'/api/animais/{id}/microchip', 201, {'codigo': '000000000000002', 'motivo': 'Chip com defeito'}, a)
        self.assertEqual(novo['microchip_anterior'], '000000000000001')
        hist = self.call('GET', f'/api/animais/{id}/microchips', 200, auth=a)
        self.assertEqual([(h['codigo'], h['situacao']) for h in hist],
                         [('000000000000002', 'ATIVO'), ('000000000000001', 'SUBSTITUIDO')])
        self.call('POST', f'/api/animais/{id}/microchip', 409, {'codigo': '000000000000001'}, a)  # não reutiliza chip antigo
        self.assertEqual(self.call('GET', f'/api/animais?q=000000000000002', 200, auth=a)[0]['id'], id)
        det = self.call('GET', f'/api/animais/{id}', 200, auth=a)
        self.assertIn(det['integracao'], ('PENDENTE', 'ENVIADA', 'CONFIRMADA'))
        # consultas e vacinas
        hoje = date.today().isoformat()
        amanha = (date.today() + timedelta(days=1)).isoformat()
        c = {'animal_id': id, 'data_hora': hoje + 'T09:00:00', 'motivo': 'Rotina', 'situacao': 'REALIZADA'}
        self.call('POST', '/api/consultas', 422, c | {'data_hora': amanha + 'T09:00:00'}, a)
        self.call('POST', '/api/consultas', 201, c, a)
        ag = self.call('POST', '/api/consultas', 201, c | {'data_hora': amanha + 'T09:00:00', 'situacao': 'AGENDADA'}, a)
        self.call('PUT', f"/api/consultas/{ag['id']}/situacao", 200, {'situacao': 'CANCELADA'}, a)
        self.call('PUT', f"/api/consultas/{ag['id']}/situacao", 409, {'situacao': 'REALIZADA'}, a)
        v = {'animal_id': id, 'nome': 'V10', 'tipo': 'Múltipla', 'fabricante': 'Lab', 'lote': 'L1',
             'data_aplicacao': hoje, 'data_proxima_dose': (date.today() + timedelta(days=30)).isoformat()}
        self.call('POST', '/api/vacinas', 201, v, a)  # não antirrábica: não vai ao governo
        self.call('POST', '/api/vacinas', 422, v | {'data_aplicacao': amanha, 'data_proxima_dose': None}, a)
        self.call('POST', '/api/vacinas', 422, {k: val for k, val in v.items() if k != 'fabricante'}, a)
        self.call('POST', '/api/vacinas', 422, v | {'antirrabica': True, 'animal_id': sem_raca['id']}, a)  # sem microchip
        h = self.call('GET', f'/api/animais/{id}/historico', 200, auth=a)
        self.assertEqual((len(h['consultas']), len(h['vacinas']), len(h['microchips'])), (2, 1, 2))
        prox = self.call('GET', f'/api/vacinas/proximas-doses?animal_id={id}', 200, auth=a)
        self.assertEqual(len(prox), 1)
        ops = self.call('GET', f'/api/integracao?animal_id={id}', 200, auth=a)
        self.assertTrue(all(o['tipo'] != 'VACINA_ANTIRRABICA' for o in ops))
        self.call('DELETE', f'/api/tutores/{tutor["id"]}', 409, auth=a)  # tutor com animal ativo

    # ---------- 4. integração com o governo
    def test_05_antirrabica_governo_indisponivel_reenvio_e_idempotencia(self):
        a = self.login()
        e = self.call('POST', '/api/enderecos', 201, {'cep': '70040-010', 'numero': '5', 'logradouro': 'Esplanada',
                      'bairro': 'Zona Cívico-Administrativa', 'cidade': 'Brasília', 'uf': 'DF'}, a)
        tutor = self.call('POST', '/api/tutores', 201, {'nome': 'Tutor Gov', 'cpf': '86288366757', 'data_nascimento': '1980-02-02',
                          'email': 'g@x.com', 'telefone': '6100000000', 'endereco_id': e['id']}, a)
        esp = self.call('POST', '/api/especies', 201, {'nome': 'Canina Gov'}, a)
        p = {'nome': 'Rex', 'nascimento': '2021-03-03', 'sexo': 'M', 'tutor_id': tutor['id'], 'especie_id': esp['id']}
        self.addCleanup(lambda: self.client.put('/api/integracao/simulacao?indisponivel=false', headers=a))
        self.call('PUT', '/api/integracao/simulacao?indisponivel=true', 200, auth=a)
        animal = self.call('POST', '/api/animais', 201, p | {'microchip': '000000000000777'}, a)
        id = animal['id']
        hoje = date.today().isoformat()
        v = {'animal_id': id, 'nome': 'Antirrábica', 'tipo': 'Raiva', 'antirrabica': True, 'fabricante': 'Lab', 'lote': 'R9',
             'data_aplicacao': hoje}
        vac = self.call('POST', '/api/vacinas', 201, v, a)  # registro local acontece mesmo com governo fora
        self.assertEqual(vac['situacao'], 'APLICADA')
        ops = self.esperar(a, id, 'PENDENTE', 2)
        self.assertTrue(all(o['protocolo_externo'] is None for o in ops))
        antes = self.remote.get('/api/governo/registros').json()
        self.assertFalse([x for x in antes['animais'] if x.get('microchip') == '000000000000777'])
        self.assertFalse([x for x in antes['vacinacoes'] if x['lote'] == 'R9'])
        self.call('PUT', '/api/integracao/simulacao?indisponivel=false', 200, auth=a)
        r = self.call('POST', f'/api/integracao/reenviar?animal_id={id}', 200, auth=a)
        self.assertEqual((r['pendentes'], r['falhas']), (0, 0))
        ops = self.call('GET', f'/api/integracao?animal_id={id}', 200, auth=a)
        self.assertTrue(all(o['situacao'] == 'CONFIRMADA' and o['protocolo_externo'].startswith('GOV-') for o in ops))
        um = self.call('GET', f"/api/integracao/{ops[0]['id']}", 200, auth=a)
        self.assertEqual(um['situacao'], 'CONFIRMADA')
        self.call('POST', f'/api/integracao/reenviar?animal_id={id}', 200, auth=a)  # segundo reenvio: nada novo
        reg = self.remote.get('/api/governo/registros').json()
        self.assertEqual(len([x for x in reg['animais'] if x['microchip'] == '000000000000777']), 1)
        self.assertEqual(len([x for x in reg['vacinacoes'] if x['lote'] == 'R9']), 1)
        self.assertEqual(self.remote.get('/api/governo/animais/000000000000777').json()['vacinacoes'][0]['lote'], 'R9')
        # o registro local da vacina e a confirmação governamental são coisas distintas
        self.assertIn('protocolo_externo', ops[0])

    def test_06_governo_idempotencia_e_vacina_sem_cadastro(self):
        h = {'Idempotency-Key': 'teste-idem-0001', 'X-API-Key': GOV_KEY}
        vac = {'microchip': '000000000000888', 'animal_id': 900, 'animal_nome': 'Solto', 'vacina_id': 900, 'nome': 'Antirrábica',
               'fabricante': 'Lab', 'lote': 'X1', 'data_aplicacao': date.today().isoformat(),
               'veterinario_nome': 'Vet', 'veterinario_crmv': '123/RJ'}
        a = self.remote.post('/api/governo/vacinacoes-antirrabicas', json=vac, headers=h)
        b = self.remote.post('/api/governo/vacinacoes-antirrabicas', json=vac, headers=h)
        self.assertEqual((a.status_code, b.status_code), (201, 201))
        self.assertEqual(a.json()['protocolo'], b.json()['protocolo'])
        self.assertTrue(b.json()['repetido'])
        self.assertEqual(self.remote.post('/api/governo/vacinacoes-antirrabicas', json=vac | {'lote': 'X2'}, headers=h).status_code, 409)
        # animal ainda não cadastrado no governo: a vacinação é aceita mesmo assim
        self.assertEqual(self.remote.get('/api/governo/animais/000000000000888', headers={'X-API-Key': GOV_KEY}).status_code, 200)
        self.assertEqual(self.remote.get('/api/governo/operacoes/' + a.json()['protocolo'], headers={'X-API-Key': GOV_KEY}).status_code, 200)
        self.assertEqual(self.remote.get('/api/governo/operacoes/GOV-NAOEXISTE', headers={'X-API-Key': GOV_KEY}).status_code, 404)
        self.assertEqual(httpx.post(self.gov + '/api/governo/vacinacoes-antirrabicas', json=vac, headers={'Idempotency-Key': 'sem-chave-api'}).status_code, 401)


class ViaCEP(unittest.TestCase):
    def test_01_sucesso(self):
        req = httpx.Request('GET', 'https://viacep.com.br/ws/01001000/json/')
        corpo = {'cep': '01001-000', 'logradouro': 'Praça da Sé', 'bairro': 'Sé', 'localidade': 'São Paulo', 'uf': 'SP', 'ibge': '3550308'}
        with patch('sdm.clinica.httpx.get', return_value=httpx.Response(200, request=req, json=corpo)):
            r = buscar_cep('01001-000', {})
        self.assertEqual((r['cidade'], r['codigo_ibge']), ('São Paulo', '3550308'))

    def test_02_inexistente_e_formato_invalido(self):
        req = httpx.Request('GET', 'https://viacep.com.br')
        with patch('sdm.clinica.httpx.get', return_value=httpx.Response(200, request=req, json={'erro': True})) as get:
            for cep, code in [('99999999', 404), ('xyz', 422)]:
                with self.assertRaises(HTTPException) as exc:
                    buscar_cep(cep, {})
                self.assertEqual(exc.exception.status_code, code)
            self.assertEqual(get.call_count, 1)

    def test_03_timeout_e_indisponibilidade(self):
        for erro, code in [(httpx.ReadTimeout('t'), 504), (httpx.ConnectError('c'), 503)]:
            with patch('sdm.clinica.httpx.get', side_effect=erro):
                with self.assertRaises(HTTPException) as exc:
                    buscar_cep('01001000', {})
                self.assertEqual(exc.exception.status_code, code)


class Validacao(unittest.TestCase):
    def test_cpf(self):
        from sdm.validacao import cpf_valido
        self.assertTrue(cpf_valido('390.533.447-05') and cpf_valido('39053344705'))
        self.assertFalse(any(cpf_valido(x) for x in ('111.111.111-11', '390.533.447-06', '123', '')))


if __name__ == '__main__':
    unittest.main()
