# Requisitos atendidos (A3 - SDM)

| Item do enunciado | Onde está |
|---|---|
| 3.1 Login do veterinário (e-mail/senha, hash, confirmação por código simulado, inativo/não confirmado bloqueado, logout, endpoints protegidos) | `sdm/seguranca.py`, `/api/auth/*` |
| 3.2 Tutor (CPF validado e único, nascimento, e-mail, telefone, endereço, cadastro, situação) | `sdm/validacao.py`, `/api/tutores` |
| 3.3 Endereço + ViaCEP (autofill, manual, CEP inexistente, timeout, indisponível, IBGE) | `/api/enderecos`, `/api/cep/{cep}` |
| 3.4 Espécies e 3.5 Raças (compatibilidade, "sem raça") | `/api/especies`, `/api/racas`, FK composta |
| 3.6 Veterinário (CPF, CRMV+UF, e-mail, telefone, hash, confirmação, ativo/inativo, último acesso) | `/api/veterinarios`, `/api/auth/registro` |
| 3.7 Animal e microchip (único, vínculo, responsável, substituição preserva histórico, consulta + integração) | `/api/animais`, `/api/animais/{id}/microchip` |
| 3.8 Consultas (campos clínicos, situação) | `/api/consultas`, `/api/animais/{id}/consultas` |
| 3.9 Vacinas (antirrábica estruturada, lote, dose, próxima dose, histórico) | `/api/vacinas`, `/api/vacinas/proximas-doses` |
| 4 API governamental simulada | `sdm/governo.py` (`/api/governo/...`) |
| 5 Comunicação obrigatória da antirrábica | `sdm/integracao.py`, `/api/integracao` |

Decisões: banco SQLite (sem servidor, roda em qualquer máquina; o modelo relacional é o mesmo e o script MySQL equivalente está em `docs/modelagem.md`/entregas); exclusão sempre lógica; senha e código de confirmação guardados só como hash.
