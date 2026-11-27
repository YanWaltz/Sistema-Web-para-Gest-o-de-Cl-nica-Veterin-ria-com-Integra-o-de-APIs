# Roteiro de apresentação (26/11)
1. Problema e arquitetura: dois serviços (clínica + governo simulado), bancos separados, API privada com token.
2. Login: hash PBKDF2, confirmação por código, inativos bloqueados.
3. CPF: validação por dígitos verificadores e unicidade (tutor e veterinário).
4. Endereço (correção do professor): `ceps` + `enderecos`, sem duplicar milhares de CEPs; ViaCEP com tratamento de erro.
5. Animal e microchip: histórico de substituição preservado.
6. Antirrábica: outbox + idempotência; governo fora do ar → PENDENTE → reenvio sem duplicar.
7. Testes automatizados e Swagger (/docs).
8. Limitações: SQLite em vez de MySQL; e-mail simulado; governo fictício.
