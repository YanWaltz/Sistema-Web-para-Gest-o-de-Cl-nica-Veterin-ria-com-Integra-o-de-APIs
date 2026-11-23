# SDM | Sistema de Gestão de Clínica Veterinária

Projeto acadêmico de desenvolvimento web com uma API privada para a clínica, a API pública ViaCEP e uma API governamental simulada. Entrega prevista no cronograma: **quinta-feira, 26/11/2026**.

## Comece aqui

**Windows:** instale [Python 3.10 ou superior](https://www.python.org/downloads/) se ainda não tiver. Extraia todo o ZIP, abra a pasta que contém este arquivo e dê dois cliques em **`iniciar.bat`**. Na primeira execução, a instalação das dependências precisa de internet. Deixe a janela de terminal aberta.

**macOS / Linux:** abra o terminal na pasta do projeto e execute:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python iniciar.py
```

Em qualquer sistema, se a página não abrir sozinha, acesse [Clínica no navegador](http://127.0.0.1:8000). Entre com **`admin`** e **`ClinicaDemo!26`**. A conta **`clinica`** usa a mesma senha demonstrativa, mas não pode excluir, simular falha ou reenviar pendências. Pressione `Ctrl+C` no terminal para encerrar.

| Endereço local | Para que serve |
|---|---|
| [Clínica](http://127.0.0.1:8000) | Tela do sistema |
| [Swagger da clínica](http://127.0.0.1:8000/docs) / [OpenAPI JSON](http://127.0.0.1:8000/openapi.json) | Contrato da API privada |
| [Swagger do governo simulado](http://127.0.0.1:8001/docs) / [OpenAPI JSON](http://127.0.0.1:8001/openapi.json) | Contrato do segundo serviço |

No Swagger da clínica, execute `POST /api/login`, copie `access_token` sem as aspas, clique em **Authorize** e cole o token sem escrever `Bearer`. No Swagger do governo, use **Authorize** com a chave de demonstração `somente-demonstracao-local`; nas operações de escrita, forneça também `Idempotency-Key`. O Swagger busca arquivos de interface por CDN. Os contratos em JSON continuam disponíveis localmente. Consulte a [documentação do FastAPI](https://fastapi.tiangolo.com/pt/reference/openapi/docs/).

## Ordem dos cadastros

1. Em **Cadastros**, crie **Endereço** (pode consultar o CEP), **Tutor**, **Espécie**, **Raça** e **Veterinário**, nessa ordem. Raça é opcional no animal.
2. Em **Animais**, use **Novo cadastro** e vincule os dados. Exemplo de microchip fictício: `000000000000123`.
3. Em **Atendimentos**, registre uma consulta e uma vacina. Marque **Enviar como antirrábica** apenas na vacina que pretende enviar.
4. Em **Animais → Histórico**, confira os dois registros. Em **Integração**, confira os protocolos e teste a falha simulada conforme o roteiro.

## Arquivos da entrega

| Arquivo | Conteúdo |
|---|---|
| [Requisitos e regras](docs/requisitos.md) | Escopo dos cinco marcos e escolhas de implementação |
| [Modelagem e arquitetura](docs/modelagem.md) | MER, modelo relacional e comunicação das APIs |
| [Roteiro de apresentação](docs/apresentacao.md) | Falas, ordem dos cliques e dados fictícios da demonstração |
| [Explicação para iniciantes](docs/passo-a-passo.md) | Como foi construído, onde mexer e como subir no Git |
| [Relatório](docs/relatorio-testes.md) / [Registro da execução](docs/evidencias-testes.txt) | Testes e evidência automatizada |
| [Coleção Postman](docs/sdm.postman_collection.json) | Requisições de login, cadastros, atendimento, envio e reenvio |

## Rodar os testes

Na pasta do projeto, depois de instalar as dependências:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

No macOS/Linux, substitua `.\.venv\Scripts\python.exe` por `.venv/bin/python`. Os testes integrados sobem serviços em portas livres e usam bancos temporários; não alteram seus cadastros.

## Notas de ambiente

- Os bancos SQLite são criados em `data/` e não devem ser versionados. Use apenas dados fictícios. APIs vinculadas a `127.0.0.1`, sem deploy público.
- Se a janela mostrar que 8000 ou 8001 está em uso, encerre a instância anterior antes de abrir outra. Para usar outros endereços, rode o Uvicorn manualmente e configure `SDM_GOV_URL` na clínica.
- Variáveis opcionais: `SDM_DATA_DIR`, `SDM_GOV_URL`, `SDM_GOV_KEY`, `SDM_ADMIN_PASSWORD` e `SDM_CLINIC_PASSWORD`. A chave deve ser a mesma nos dois serviços. As senhas configuradas são usadas na criação inicial das contas. Credenciais padrão do README são exemplos locais, não segredos de produção.
- Em caso de indisponibilidade do [ViaCEP](https://viacep.com.br/), preencha o endereço manualmente. O sistema não envia dados ao governo real.
