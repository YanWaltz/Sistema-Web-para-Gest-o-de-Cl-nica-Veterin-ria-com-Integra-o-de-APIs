# Sistema Web para Gestão de Clínica Veterinária com Integração de APIs

Projeto A3 · Sistemas Distribuídos e Mobile · IBMR. Projeto acadêmico com dados fictícios.

Dois serviços independentes em Python (FastAPI):
- **Clínica** (porta 8000): API privada REST + interface web. Banco `data/clinica.db`.
- **Governo simulado** (porta 8001): API fictícia que recebe cadastro de animais e vacinas antirrábicas. Banco próprio `data/governo.db`.

## Como rodar
```
python -m venv .venv
.venv\Scripts\activate          (Windows)   |   source .venv/bin/activate   (Linux/macOS)
python -m pip install -r requirements.txt
python iniciar.py
```
Abra http://127.0.0.1:8000. Login de teste: `demo@clinica.local` / `ClinicaDemo!26`.
Swagger: http://127.0.0.1:8000/docs (clínica) e http://127.0.0.1:8001/docs (governo).
Se você já rodou uma versão anterior, **apague a pasta `data/`** antes de iniciar.

## Testes
```
python -m unittest discover -s tests -v
```

## O que o sistema faz
- Login do veterinário por e-mail e senha (hash PBKDF2), confirmação por código (e-mail simulado), bloqueio de inativos/não confirmados, logout e endpoints protegidos por token.
- Tutor e veterinário com **CPF validado (dígitos verificadores) e único**.
- **Endereço normalizado**: cada CEP é guardado uma única vez (`ceps`); o endereço guarda só número e complemento, e endereços iguais são reaproveitados. Consulta ao ViaCEP com preenchimento manual se falhar.
- Espécies, raças (compatíveis com a espécie ou "sem raça"), animais, microchip com histórico de substituição.
- Consultas e vacinas com histórico e próximas doses.
- Vacina antirrábica aplicada é enviada ao governo com idempotência, protocolo, estados PENDENTE/ENVIADA/CONFIRMADA/FALHA e reenvio sem duplicar.

Documentação em `docs/` (requisitos, modelagem, testes, apresentação, coleção Postman).
