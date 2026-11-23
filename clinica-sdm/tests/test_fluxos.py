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
from fastapi.testclient import TestClient
from sdm.base import GOV_KEY
from sdm.clinica import app, buscar_cep
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
        env=os.environ | {'SDM_DATA_DIR':cls.tmp.name,'SDM_GOV_URL':cls.gov,'SDM_GOV_KEY':GOV_KEY,'SDM_ADMIN_PASSWORD':'ClinicaDemo!26','SDM_CLINIC_PASSWORD':'ClinicaDemo!26'}
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

    def call(self,m,path,code,body=None,auth=None):
        r=self.client.request(m,path,json=body,headers=auth)
        self.assertEqual(r.status_code,code,r.text)
        return r.json() if r.content else None

    def login(self,user='admin'):
        x=self.call('POST','/api/login',200,{'usuario':user,'senha':'ClinicaDemo!26'})
        return {'Authorization':'Bearer '+x['access_token']}

    def test_01_acesso_documentacao_e_interface(self):
        self.assertIn('Entre para começar',self.client.get('/').text)
        self.assertIn('async function integracao',self.client.get('/web/app.js').text)
        self.assertIn('stylesheet',self.client.get('/').text)
        self.assertEqual(self.client.get('/docs').status_code,200)
        spec=self.call('GET','/openapi.json',200)
        self.assertIn('HTTPBearer',spec['components']['securitySchemes'])
        self.assertIn('/vacinas-antirrabicas',self.remote.get('/openapi.json').json()['paths'])
        self.call('GET','/api/animais',401)
        self.call('POST','/api/login',401,{'usuario':'admin','senha':'senha-errada'})
        perfil=self.login('clinica')
        self.call('DELETE','/api/especies/1',403,auth=perfil)
        self.call('POST','/api/integracao/reenviar',403,auth=perfil)
        self.call('POST','/api/logout',204,auth=perfil)
        self.call('GET','/api/me',401,auth=perfil)

    def test_02_fluxo_clinico_e_reenvio(self):
        a=self.login(); call=lambda m,p,s,b=None:self.call(m,'/api'+p,s,b,a)
        e=call('POST','/enderecos',201,{'cep':'01001-000','logradouro':'Praça da Sé','numero':'10','bairro':'Sé','cidade':'São Paulo','uf':'SP'})
        tutor=call('POST','/tutores',201,{'nome':'Tutor fictício','telefone':'2100000000','endereco_id':e['id']})
        esp=call('POST','/especies',201,{'nome':'Canina'}); fel=call('POST','/especies',201,{'nome':'Felina'})
        raca=call('POST','/racas',201,{'nome':'SRD','especie_id':esp['id']})
        vet=call('POST','/veterinarios',201,{'nome':'Veterinário fictício','crmv':'DEMO-001'})
        vet2=call('POST','/veterinarios',201,{'nome':'Cadastro temporário','crmv':'DEMO-002'})
        call('PUT',f"/veterinarios/{vet2['id']}",200,{'nome':'Alterado','crmv':'DEMO-002'})
        call('GET',f"/veterinarios/{vet2['id']}",200);call('DELETE',f"/veterinarios/{vet2['id']}",204)
        call('DELETE',f"/enderecos/{e['id']}",409)
        payload={'nome':'Luna','nascimento':'2022-01-01','tutor_id':tutor['id'],'especie_id':esp['id'],'raca_id':raca['id'],'microchip':'000000000000123'}
        call('POST','/animais',409,payload|{'especie_id':fel['id']})
        call('POST','/animais',422,payload|{'microchip':'ABCDEFGHIJKLMNO'})
        call('PUT','/integracao/simulacao?indisponivel=true',200)
        animal=call('POST','/animais',201,payload); id=animal['id']; day=date.today().isoformat()
        call('POST','/animais',409,payload|{'nome':'Outro'})
        self.assertEqual(call('GET','/animais?q=000000000000123',200)[0]['id'],id)
        call('POST','/consultas',422,{'animal_id':id,'veterinario_id':vet['id'],'data':(date.today()+timedelta(days=1)).isoformat(),'descricao':'Não deve entrar'})
        call('POST','/consultas',201,{'animal_id':id,'veterinario_id':vet['id'],'data':day,'descricao':'Consulta de demonstração'})
        regular={'animal_id':id,'veterinario_id':vet['id'],'data':day,'nome':'Vacina de demonstração','lote':'D01'}
        call('POST','/vacinas',201,regular);call('POST','/vacinas',201,regular|{'nome':'Antirrábica','antirrabica':True})
        h=call('GET',f'/animais/{id}/historico',200);self.assertEqual((len(h['consultas']),len(h['vacinas'])),(1,2))
        call('PUT',f'/animais/{id}',200,payload|{'nome':'Luna Atualizada'})
        ops=call('GET','/integracao',200);self.assertEqual(len(ops),3)
        for _ in range(40):
            ops=call('GET','/integracao',200)
            if any(x['status']=='FALHA' for x in ops): break
            time.sleep(.05)
        self.assertTrue(any(x['status']=='FALHA' for x in ops))
        self.assertEqual(self.remote.get('/registros').json(),{'animais':[],'vacinas':[]})
        call('PUT','/integracao/simulacao?indisponivel=false',200)
        call('POST','/integracao/reenviar',200)
        ops=call('GET','/integracao',200);self.assertTrue(all(x['status']=='ENVIADO' and x['protocolo'].startswith('GOV-') for x in ops))
        self.assertEqual(call('POST','/integracao/reenviar',200)['enviadas'],0)
        governo=self.remote.get('/registros').json();self.assertEqual(len(governo['vacinas']),1)
        self.assertEqual(governo['animais'][0]['nome'],'Luna Atualizada')
        self.assertNotIn('tutor_id',governo['animais'][0])
        call('DELETE',f'/animais/{id}',204);self.assertEqual(call('GET',f'/animais/{id}',200)['ativo'],0)
        call('POST','/vacinas',409,regular)
        print('EVIDÊNCIA: animal e vacina gravados localmente durante HTTP 503; três operações reenviadas com protocolo; segundo reenvio não duplicou registros.',flush=True)

    def test_03_idempotencia_remota(self):
        payload={'animal_id':900,'versao':1,'nome':'Teste remoto','especie':'Canina','microchip':'999999999999999','ativo':True}
        h={'Idempotency-Key':'teste-idempotencia-900'}
        a=self.remote.put('/animais/900',json=payload,headers=h);b=self.remote.put('/animais/900',json=payload,headers=h)
        self.assertEqual((a.status_code,b.status_code),(200,200));self.assertFalse(a.json()['repetido']);self.assertTrue(b.json()['repetido']);self.assertEqual(a.json()['protocolo'],b.json()['protocolo'])
        self.assertEqual(self.remote.put('/animais/900',json=payload|{'nome':'Outra carga'},headers=h).status_code,409)
        self.assertEqual(httpx.get(self.gov+'/registros').status_code,401)
        print('EVIDÊNCIA: repetição da chave devolveu o mesmo protocolo; carga diferente com a mesma chave foi rejeitada.',flush=True)

class ViaCEP(unittest.TestCase):
    def test_01_sucesso(self):
        req=httpx.Request('GET','https://viacep.com.br/ws/01001000/json/')
        with patch('sdm.clinica.httpx.get',return_value=httpx.Response(200,request=req,json={'cep':'01001-000','logradouro':'Praça da Sé','bairro':'Sé','localidade':'São Paulo','uf':'SP'})) as get:
            self.assertEqual(buscar_cep('01001-000',{})['cidade'],'São Paulo')
            get.assert_called_once_with(str(req.url),timeout=4.0)

    def test_02_ausente_e_formato_invalido(self):
        req=httpx.Request('GET','https://viacep.com.br')
        with patch('sdm.clinica.httpx.get',return_value=httpx.Response(200,request=req,json={'erro':True})) as get:
            for cep,code in [('99999999',404),('xyz',422)]:
                with self.assertRaises(HTTPException) as exc: buscar_cep(cep,{})
                self.assertEqual(exc.exception.status_code,code)
            self.assertEqual(get.call_count,1)

    def test_03_indisponivel(self):
        with patch('sdm.clinica.httpx.get',side_effect=httpx.ReadTimeout('timeout')):
            with self.assertRaises(HTTPException) as exc: buscar_cep('01001000',{})
            self.assertEqual(exc.exception.status_code,503)

if __name__=='__main__': unittest.main()
