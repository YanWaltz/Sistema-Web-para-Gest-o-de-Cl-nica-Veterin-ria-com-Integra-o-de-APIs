"""Autenticação dos veterinários: senha com hash, confirmação por código, sessão com token."""
import hashlib
import os
import secrets
import time

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer

from .base import db

bearer = HTTPBearer(auto_error=False)
DEMO = 'ClinicaDemo!26'
VALIDADE_CODIGO = 30 * 60  # 30 minutos
VALIDADE_SESSAO = 8 * 3600  # 8 horas


def hash_senha(senha, sal=None):
    """PBKDF2-SHA256 com sal aleatório. Guardamos 'sal:hash', nunca a senha."""
    sal = sal or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac('sha256', senha.encode(), bytes.fromhex(sal), 600_000).hex()
    return f'{sal}:{h}'


def senha_confere(senha, armazenado):
    sal = armazenado.split(':')[0]
    return secrets.compare_digest(hash_senha(senha, sal), armazenado)


def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def gerar_codigo():
    return f'{secrets.randbelow(10 ** 6):06d}'


def registrar_veterinario(c, d):
    """Cria o veterinário (ativo, com senha NÃO confirmada) e devolve (id, código de confirmação)."""
    codigo = gerar_codigo()
    vid = c.execute(
        '''INSERT INTO veterinarios(nome,cpf,crmv_numero,crmv_uf,email,telefone,senha_hash,codigo_hash,codigo_expira)
           VALUES (?,?,?,?,?,?,?,?,?)''',
        (d.nome, d.cpf, d.crmv_numero, d.crmv_uf, d.email, d.telefone, hash_senha(d.senha),
         hash_token(codigo), int(time.time()) + VALIDADE_CODIGO)).lastrowid
    return vid, codigo


def novo_codigo(email):
    """Gera um novo código para quem ainda não confirmou. Devolve o código, ou None se não se aplica."""
    with db() as c:
        v = c.execute('SELECT id,senha_confirmada FROM veterinarios WHERE email=?', (email,)).fetchone()
        if v is None or v['senha_confirmada']:
            return None
        codigo = gerar_codigo()
        c.execute('UPDATE veterinarios SET codigo_hash=?, codigo_expira=? WHERE id=?',
                  (hash_token(codigo), int(time.time()) + VALIDADE_CODIGO, v['id']))
        return codigo


def confirmar_codigo(email, codigo):
    """Registra a confirmação da senha depois de validar o código enviado (simulado) ao e-mail."""
    with db() as c:
        v = c.execute('SELECT * FROM veterinarios WHERE email=?', (email,)).fetchone()
        if v is not None and v['senha_confirmada']:
            raise HTTPException(409, 'Esta senha já foi confirmada. Pode entrar normalmente.')
        valido = (v is not None and v['codigo_hash'] is not None and v['codigo_expira'] is not None
                  and v['codigo_expira'] > time.time()
                  and secrets.compare_digest(hash_token(codigo), v['codigo_hash']))
        if not valido:
            raise HTTPException(400, 'Código inválido ou expirado. Peça um novo código.')
        c.execute('''UPDATE veterinarios SET senha_confirmada=1, data_confirmacao=CURRENT_TIMESTAMP,
                     codigo_hash=NULL, codigo_expira=NULL WHERE id=?''', (v['id'],))


def criar_demo(c):
    """Cria um veterinário de demonstração (ativo e confirmado) se ainda não existir nenhum."""
    if c.execute('SELECT 1 FROM veterinarios LIMIT 1').fetchone():
        return
    senha = os.environ.get('SDM_DEMO_PASSWORD', DEMO)
    if not 8 <= len(senha) <= 128:
        raise RuntimeError('SDM_DEMO_PASSWORD: use entre 8 e 128 caracteres')
    c.execute('''INSERT INTO veterinarios(nome,cpf,crmv_numero,crmv_uf,email,telefone,senha_hash,senha_confirmada,data_confirmacao)
                 VALUES (?,?,?,?,?,?,?,1,CURRENT_TIMESTAMP)''',
              ('Veterinário Demonstração', '39053344705', '12345', 'RJ', 'demo@clinica.local',
               '21999990000', hash_senha(senha)))


def autenticar(email, senha):
    with db() as c:
        v = c.execute('SELECT * FROM veterinarios WHERE email=?', (email,)).fetchone()
        # Calcula o hash mesmo se o e-mail não existir, para não revelar (pelo tempo) quais e-mails existem.
        calculado = hash_senha(senha, v['senha_hash'].split(':')[0] if v else '0' * 32)
        if not v or not secrets.compare_digest(calculado, v['senha_hash']):
            raise HTTPException(401, 'E-mail ou senha inválidos.')
        if v['situacao'] != 'ATIVO':
            raise HTTPException(403, 'Veterinário inativo. Procure a administração da clínica.')
        if not v['senha_confirmada']:
            raise HTTPException(403, 'Senha ainda não confirmada. Informe o código enviado ao seu e-mail.')
        token = secrets.token_urlsafe(32)
        agora = int(time.time())
        c.execute('DELETE FROM sessoes WHERE expira<=?', (agora,))
        c.execute('INSERT INTO sessoes VALUES (?,?,?)', (hash_token(token), v['id'], agora + VALIDADE_SESSAO))
        c.execute('UPDATE veterinarios SET ultimo_acesso=CURRENT_TIMESTAMP WHERE id=?', (v['id'],))
        return {'access_token': token, 'token_type': 'bearer', 'id': v['id'], 'nome': v['nome'], 'email': v['email']}


def sessao(cab=Depends(bearer)):
    """Protege os endpoints privados: exige token válido de veterinário ATIVO e com senha confirmada."""
    h = hash_token(cab.credentials) if cab else ''
    with db() as c:
        v = c.execute('''SELECT v.id, v.nome, v.email, v.crmv_numero, v.crmv_uf, s.token_hash
                         FROM sessoes s JOIN veterinarios v ON v.id=s.veterinario_id
                         WHERE s.token_hash=? AND s.expira>? AND v.situacao='ATIVO' AND v.senha_confirmada=1''',
                      (h, int(time.time()))).fetchone()
    if not v:
        raise HTTPException(401, 'Entre com seu e-mail e senha.', headers={'WWW-Authenticate': 'Bearer'})
    return dict(v)
