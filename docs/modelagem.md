# Modelo de dados

## Endereço normalizado (correção pedida pelo professor)
Antes cada endereço repetia logradouro, bairro, cidade e UF. Com milhares de moradores, isso gera milhares de cópias do mesmo CEP.
Agora:
- `ceps(id, cep UNIQUE, logradouro, bairro, cidade, uf, codigo_ibge)` — uma linha por CEP.
- `enderecos(id, cep_id FK, numero, complemento, UNIQUE(cep_id, numero, complemento))` — só o que varia por moradia.
- `tutores.endereco_id` aponta para `enderecos`. Vários tutores da mesma casa compartilham o mesmo registro.
A API (`POST /api/enderecos`) faz *get-or-create*: se o CEP já existe só é preciso informar número/complemento.

## CPF
`tutores.cpf` e `veterinarios.cpf`: 11 dígitos, `UNIQUE`, validados pelos dígitos verificadores antes de gravar.

## Tabelas
| Tabela | Principais colunas |
|---|---|
| veterinarios | nome, cpf UNIQUE, crmv_numero+crmv_uf UNIQUE, email UNIQUE, telefone, senha_hash, senha_confirmada, data_confirmacao, data_cadastro, situacao, ultimo_acesso |
| sessoes | token_hash, veterinario_id FK, expira |
| ceps / enderecos | ver acima |
| tutores | nome, cpf UNIQUE, data_nascimento, email, telefone, endereco_id FK, data_cadastro, situacao |
| especies / racas | racas.especie_id FK; (raca_id, especie_id) é FK composta em animais |
| animais | nome, nascimento ou idade_estimada_meses, sexo, cor, peso_atual, tutor_id, especie_id, raca_id (opcional), situacao, versao |
| vinculos_microchip | animal_id, codigo UNIQUE, veterinario_id, data_vinculo, situacao ATIVO/SUBSTITUIDO, índice único parcial (1 ativo por animal) |
| consultas | animal_id, veterinario_id, data_hora, motivo, anamnese, sintomas, diagnostico, tratamento, prescricao, peso_registrado, temperatura, observacoes, situacao |
| vacinas | animal_id, veterinario_id, nome, tipo, antirrabica, fabricante, lote, validade_lote, data_aplicacao, dose_etapa, via_aplicacao, data_proxima_dose, observacoes, situacao |
| integracoes_governo | animal_id, vacina_id, tipo, payload, protocolo_externo, chave_idempotencia UNIQUE, situacao PENDENTE/ENVIADA/CONFIRMADA/FALHA, tentativas, mensagem_erro, datas |

Os PDFs do modelo relacional/EER/conceitual precisam refletir `ceps` (ver entregas).
