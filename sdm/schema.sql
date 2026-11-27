-- Banco da clínica (SQLite). Executado automaticamente ao iniciar a API privada.
-- Exclusão lógica: a coluna "situacao" substitui o DELETE nas entidades de cadastro.

CREATE TABLE IF NOT EXISTS veterinarios (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nome TEXT NOT NULL,
  cpf TEXT NOT NULL UNIQUE,                       -- só números, validado pela API
  crmv_numero TEXT NOT NULL,
  crmv_uf TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,                     -- usado como login
  telefone TEXT,
  senha_hash TEXT NOT NULL,                       -- PBKDF2 com sal; nunca a senha pura
  senha_confirmada INTEGER NOT NULL DEFAULT 0 CHECK(senha_confirmada IN (0,1)),
  codigo_hash TEXT,                               -- hash do código de confirmação (envio simulado)
  codigo_expira INTEGER,
  data_confirmacao TEXT,
  data_cadastro TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  situacao TEXT NOT NULL DEFAULT 'ATIVO' CHECK(situacao IN ('ATIVO','INATIVO')),
  ultimo_acesso TEXT,
  UNIQUE(crmv_numero, crmv_uf)
);

CREATE TABLE IF NOT EXISTS sessoes (
  token_hash TEXT PRIMARY KEY,
  veterinario_id INTEGER NOT NULL REFERENCES veterinarios(id),
  expira INTEGER NOT NULL
);

-- Dados do CEP: guardados UMA vez por CEP, mesmo que milhares de pessoas morem nele.
CREATE TABLE IF NOT EXISTS ceps (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cep TEXT NOT NULL UNIQUE,                       -- 8 números
  logradouro TEXT NOT NULL,
  bairro TEXT NOT NULL,
  cidade TEXT NOT NULL,
  uf TEXT NOT NULL,
  codigo_ibge TEXT
);

-- Endereço = CEP (compartilhado) + número + complemento. Endereços idênticos são reaproveitados.
CREATE TABLE IF NOT EXISTS enderecos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cep_id INTEGER NOT NULL REFERENCES ceps(id),
  numero TEXT NOT NULL,
  complemento TEXT NOT NULL DEFAULT '',
  UNIQUE(cep_id, numero, complemento)
);

CREATE TABLE IF NOT EXISTS tutores (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nome TEXT NOT NULL,
  cpf TEXT NOT NULL UNIQUE,
  data_nascimento TEXT NOT NULL,
  email TEXT NOT NULL,
  telefone TEXT NOT NULL,
  endereco_id INTEGER NOT NULL REFERENCES enderecos(id),
  data_cadastro TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  situacao TEXT NOT NULL DEFAULT 'ATIVO' CHECK(situacao IN ('ATIVO','INATIVO'))
);

CREATE TABLE IF NOT EXISTS especies (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nome TEXT NOT NULL UNIQUE,
  descricao TEXT,
  situacao TEXT NOT NULL DEFAULT 'ATIVO' CHECK(situacao IN ('ATIVO','INATIVO'))
);

CREATE TABLE IF NOT EXISTS racas (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nome TEXT NOT NULL,
  descricao TEXT,
  especie_id INTEGER NOT NULL REFERENCES especies(id),
  situacao TEXT NOT NULL DEFAULT 'ATIVO' CHECK(situacao IN ('ATIVO','INATIVO')),
  UNIQUE(nome, especie_id),
  UNIQUE(id, especie_id)                          -- permite a chave composta abaixo
);

CREATE TABLE IF NOT EXISTS animais (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nome TEXT NOT NULL,
  nascimento TEXT,
  idade_estimada_meses INTEGER,
  sexo TEXT NOT NULL CHECK(sexo IN ('M','F')),
  cor TEXT,
  peso_atual REAL,
  tutor_id INTEGER NOT NULL REFERENCES tutores(id),
  especie_id INTEGER NOT NULL REFERENCES especies(id),
  raca_id INTEGER,                                -- NULL = sem raça definida
  situacao TEXT NOT NULL DEFAULT 'ATIVO' CHECK(situacao IN ('ATIVO','INATIVO','OBITO')),
  versao INTEGER NOT NULL DEFAULT 1,              -- ordena as atualizações enviadas ao governo
  FOREIGN KEY(raca_id, especie_id) REFERENCES racas(id, especie_id)  -- a raça precisa ser da espécie
);

-- O microchip NÃO fica em "animais": cada vínculo é uma linha, para preservar o histórico.
CREATE TABLE IF NOT EXISTS vinculos_microchip (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  animal_id INTEGER NOT NULL REFERENCES animais(id),
  codigo TEXT NOT NULL UNIQUE,                    -- um microchip nunca é usado duas vezes
  veterinario_id INTEGER NOT NULL REFERENCES veterinarios(id),
  data_vinculo TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  situacao TEXT NOT NULL DEFAULT 'ATIVO' CHECK(situacao IN ('ATIVO','SUBSTITUIDO')),
  data_substituicao TEXT,
  motivo_substituicao TEXT
);
-- No máximo UM vínculo ATIVO por animal (o banco garante, mesmo que a API falhe).
CREATE UNIQUE INDEX IF NOT EXISTS uq_vinculo_ativo ON vinculos_microchip(animal_id) WHERE situacao='ATIVO';

CREATE TABLE IF NOT EXISTS consultas (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  animal_id INTEGER NOT NULL REFERENCES animais(id),
  veterinario_id INTEGER NOT NULL REFERENCES veterinarios(id),
  data_hora TEXT NOT NULL,
  motivo TEXT NOT NULL,
  anamnese TEXT,
  sintomas TEXT,
  diagnostico TEXT,
  tratamento TEXT,
  prescricao TEXT,
  peso_registrado REAL,
  temperatura REAL,
  observacoes TEXT,
  situacao TEXT NOT NULL DEFAULT 'REALIZADA' CHECK(situacao IN ('AGENDADA','REALIZADA','CANCELADA','NAO_COMPARECEU'))
);

CREATE TABLE IF NOT EXISTS vacinas (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  animal_id INTEGER NOT NULL REFERENCES animais(id),
  veterinario_id INTEGER NOT NULL REFERENCES veterinarios(id),
  nome TEXT NOT NULL,
  tipo TEXT NOT NULL,
  antirrabica INTEGER NOT NULL DEFAULT 0 CHECK(antirrabica IN (0,1)),  -- classificação estruturada
  fabricante TEXT NOT NULL,
  lote TEXT NOT NULL,
  data_aplicacao TEXT NOT NULL,
  dose_etapa TEXT,
  via_aplicacao TEXT,
  data_proxima_dose TEXT,
  validade_lote TEXT,
  observacoes TEXT,
  situacao TEXT NOT NULL DEFAULT 'APLICADA' CHECK(situacao IN ('AGENDADA','APLICADA','CANCELADA'))
);

-- Controle das comunicações com a API governamental (outbox persistente).
--   PENDENTE   = ainda não chegou ao governo (nunca tentou ou o serviço estava fora)
--   ENVIADA    = a requisição foi transmitida, mas a resposta não foi conclusiva
--   CONFIRMADA = o governo respondeu com sucesso e devolveu o protocolo
--   FALHA      = o governo recusou a solicitação (erro de validação/duplicidade)
CREATE TABLE IF NOT EXISTS integracoes_governo (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  animal_id INTEGER NOT NULL REFERENCES animais(id),
  vacina_id INTEGER REFERENCES vacinas(id),       -- só para vacina antirrábica
  tipo TEXT NOT NULL CHECK(tipo IN ('CADASTRO_ANIMAL','ATUALIZACAO_ANIMAL','VACINA_ANTIRRABICA')),
  payload TEXT NOT NULL,
  protocolo_externo TEXT,
  chave_idempotencia TEXT NOT NULL UNIQUE,
  situacao TEXT NOT NULL DEFAULT 'PENDENTE' CHECK(situacao IN ('PENDENTE','ENVIADA','CONFIRMADA','FALHA')),
  data_solicitacao TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  data_resposta TEXT,
  tentativas INTEGER NOT NULL DEFAULT 0,
  mensagem_erro TEXT
);

CREATE INDEX IF NOT EXISTS idx_integracoes_animal ON integracoes_governo(animal_id, id);
CREATE INDEX IF NOT EXISTS idx_consultas_animal ON consultas(animal_id, data_hora);
CREATE INDEX IF NOT EXISTS idx_vacinas_animal ON vacinas(animal_id, data_aplicacao);
