import hashlib
import os
import secrets
import time
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer
from .base import db

bearer = HTTPBearer(auto_error=False)
DEMO = 'ClinicaDemo!26'


def hash_senha(senha, sal=None):
    sal = sal or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac('sha256', senha.encode(), bytes.fromhex(sal), 600_000).hex()
    return f'{sal}:{h}'


def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def criar_usuarios(c):
    for usuario, papel, env in [('admin','admin','SDM_ADMIN_PASSWORD'), ('clinica','clinica','SDM_CLINIC_PASSWORD')]:
        if not c.execute('SELECT id FROM usuarios WHERE usuario=?', (usuario,)).fetchone():
            senha = os.environ.get(env, DEMO)
            if not 8 <= len(senha) <= 128:
                raise RuntimeError(f'{env}: use entre 8 e 128 caracteres')
            c.execute('INSERT INTO usuarios(usuario,senha_hash,papel) VALUES (?,?,?)', (usuario, hash_senha(senha), papel))


def autenticar(usuario, senha):
    with db() as c:
        u = c.execute('SELECT * FROM usuarios WHERE usuario=?', (usuario,)).fetchone()
        calcular = hash_senha(senha, u['senha_hash'].split(':')[0] if u else '0'*32)
        if not u or not secrets.compare_digest(calcular, u['senha_hash']):
            raise HTTPException(401, 'Usuario ou senha invalida.')
        token = secrets.token_urlsafe(32)
        agora = int(time.time())
        c.execute('DELETE FROM sessoes WHERE expira<=?', (agora,))
        c.execute('INSERT INTO sessoes VALUES (?,?,?)', (hash_token(token), u['id'], agora+8*3600))
        return {'access_token': token, 'token_type': 'bearer', 'usuario': u['usuario'], 'papel': u['papel']}


def sessao(cab=Depends(bearer)):
    h = hash_token(cab.credentials) if cab else ''
    with db() as c:
        u = c.execute('''SELECT u.id,u.usuario,u.papel,s.token_hash FROM sessoes s JOIN usuarios u
                       ON u.id=s.usuario_id WHERE s.token_hash=? AND s.expira>?''', (h, int(time.time()))).fetchone()
    if not u:
        raise HTTPException(401, 'Entre com seu usuario e senha.', headers={'WWW-Authenticate': 'Bearer'})
    return dict(u)


def admin(u=Depends(sessao)):
    if u['papel'] != 'admin':
        raise HTTPException(403, 'Somente o perfil administrador pode executar esta acao.')
    return u
