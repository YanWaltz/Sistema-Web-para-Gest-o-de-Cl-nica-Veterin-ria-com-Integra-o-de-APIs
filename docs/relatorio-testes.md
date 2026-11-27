# Relatório de testes

Execução: `python -m unittest discover -s tests -v` (sobe as duas APIs em portas livres e bancos temporários).

| # | Teste | Resultado esperado |
|---|---|---|
| 1 | Login válido | token e `/auth/me` |
| 2 | Login inválido / e-mail inexistente | 401 |
| 3 | Endpoint protegido sem token / após logout | 401 |
| 4 | Veterinário não confirmado ou inativo | 403 |
| 5 | Confirmação de senha por código | 200; login liberado |
| 6 | CPF inválido (tutor e veterinário) | 422 |
| 7 | CPF duplicado (tutor e veterinário) | 409 |
| 8 | Endereço repetido não duplica; CEP conhecido só pede número | mesmo `id`, `reaproveitado` |
| 9 | ViaCEP: sucesso, CEP inexistente, timeout (504), indisponível (503) | tratado |
| 10 | Raça incompatível com a espécie / "sem raça" | 422 / 201 |
| 11 | Microchip duplicado; chip antigo não reutilizável | 409 |
| 12 | Substituição preserva histórico | ATIVO + SUBSTITUIDO |
| 13 | Consulta e vacina com histórico e próximas doses | listados |
| 14 | Antirrábica gera envio; não antirrábica não gera | operações |
| 15 | Governo fora do ar: registro local ok, operação PENDENTE; reenvio confirma sem duplicar | CONFIRMADA + protocolo |
| 16 | Idempotência no governo (mesma chave = mesmo protocolo; conteúdo diferente = 409) e vacina de animal ainda não cadastrado | 201 / 409 |

Resultado: 10 casos de teste automatizados (cobrem os 16 itens acima), 0 falhas.
