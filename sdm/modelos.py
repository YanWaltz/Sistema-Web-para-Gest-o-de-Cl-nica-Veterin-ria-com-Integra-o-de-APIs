"""Modelos de entrada (Pydantic): validam os dados ANTES de chegarem às regras de negócio."""
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .validacao import cpf_valido, so_digitos

EMAIL = r'^[^@\s]+@[^@\s]+\.[^@\s]+$'
CPF = r'^\d{3}\.?\d{3}\.?\d{3}-?\d{2}$'
UFS = {'AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MT', 'MS', 'MG', 'PA', 'PB', 'PR', 'PE', 'PI',
       'RJ', 'RN', 'RS', 'RO', 'RR', 'SC', 'SP', 'SE', 'TO'}
Situacao = Literal['ATIVO', 'INATIVO']


class Entrada(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


def _cpf(valor):
    if not cpf_valido(valor):
        raise ValueError('CPF inválido.')
    return so_digitos(valor)  # guarda só os 11 números: com ou sem pontuação, é o mesmo CPF


def _uf(valor):
    if valor is None:
        return valor
    valor = valor.upper()
    if valor not in UFS:
        raise ValueError('UF inválida.')
    return valor


# ---------------------------------------------------------------- acesso e veterinários
class Login(Entrada):
    email: str = Field(pattern=EMAIL, max_length=120)
    senha: str = Field(min_length=1, max_length=128)

    @field_validator('email')
    @classmethod
    def _email(cls, v):
        return v.lower()


class Confirmacao(Entrada):
    email: str = Field(pattern=EMAIL, max_length=120)
    codigo: str = Field(pattern=r'^\d{6}$')

    @field_validator('email')
    @classmethod
    def _email(cls, v):
        return v.lower()


class ReenvioCodigo(Entrada):
    email: str = Field(pattern=EMAIL, max_length=120)

    @field_validator('email')
    @classmethod
    def _email(cls, v):
        return v.lower()


class VeterinarioBase(Entrada):
    nome: str = Field(min_length=3, max_length=150)
    cpf: str = Field(pattern=CPF)
    crmv_numero: str = Field(pattern=r'^[A-Za-z0-9-]{2,15}$')
    crmv_uf: str = Field(min_length=2, max_length=2)
    email: str = Field(pattern=EMAIL, max_length=120)
    telefone: Optional[str] = Field(default=None, min_length=8, max_length=24)

    @field_validator('cpf')
    @classmethod
    def _cpf_ok(cls, v):
        return _cpf(v)

    @field_validator('crmv_uf')
    @classmethod
    def _uf_ok(cls, v):
        return _uf(v)

    @field_validator('crmv_numero')
    @classmethod
    def _crmv(cls, v):
        return v.upper()

    @field_validator('email')
    @classmethod
    def _email(cls, v):
        return v.lower()


class VeterinarioNovo(VeterinarioBase):
    senha: str = Field(min_length=8, max_length=128)


class VeterinarioEdicao(VeterinarioBase):
    situacao: Optional[Situacao] = None

class EnderecoNovo(Entrada):
    cep: str = Field(pattern=r'^\d{5}-?\d{3}$')
    numero: str = Field(min_length=1, max_length=20)
    complemento: Optional[str] = Field(default=None, max_length=120)
    # Os campos abaixo só são obrigatórios quando o CEP ainda não está na base
    # (preenchidos pelo ViaCEP ou manualmente).
    logradouro: Optional[str] = Field(default=None, max_length=120)
    bairro: Optional[str] = Field(default=None, max_length=100)
    cidade: Optional[str] = Field(default=None, max_length=100)
    uf: Optional[str] = Field(default=None, min_length=2, max_length=2)
    codigo_ibge: Optional[str] = Field(default=None, pattern=r'^\d{7}$')

    @field_validator('uf')
    @classmethod
    def _uf_ok(cls, v):
        return _uf(v)
# ---------------------------------------------------------------- tutor, endereço e catálogos
class Tutor(Entrada):
    nome: str = Field(min_length=3, max_length=150)
    cpf: str = Field(pattern=CPF)
    data_nascimento: date
    email: str = Field(pattern=EMAIL, max_length=120)
    telefone: str = Field(min_length=8, max_length=24)
    endereco: EnderecoNovo
    situacao: Optional[Situacao] = None

    @field_validator('cpf')
    @classmethod
    def _cpf_ok(cls, v):
        return _cpf(v)

    @field_validator('data_nascimento')
    @classmethod
    def _nascimento(cls, v):
        if v > date.today() or v.year < 1900:
            raise ValueError('Data de nascimento inválida.')
        return v

    @field_validator('email')
    @classmethod
    def _email(cls, v):
        return v.lower()





class Especie(Entrada):
    nome: str = Field(min_length=1, max_length=60)
    descricao: Optional[str] = Field(default=None, max_length=255)
    situacao: Optional[Situacao] = None


class Raca(Especie):
    especie_id: int = Field(gt=0)


# ---------------------------------------------------------------- animal e microchip
class AnimalBase(Entrada):
    nome: str = Field(min_length=1, max_length=80)
    nascimento: Optional[date] = None
    idade_estimada_meses: Optional[int] = Field(default=None, ge=0, le=600)
    sexo: Literal['M', 'F']
    cor: Optional[str] = Field(default=None, max_length=40)
    peso_atual: Optional[float] = Field(default=None, gt=0, le=1500)
    tutor_id: int = Field(gt=0)
    especie_id: int = Field(gt=0)
    raca_id: Optional[int] = Field(default=None, gt=0)
    situacao: Optional[Literal['ATIVO', 'INATIVO', 'OBITO']] = None

    @model_validator(mode='after')
    def _idade(self):
        if self.nascimento is None and self.idade_estimada_meses is None:
            raise ValueError('Informe a data de nascimento ou a idade estimada.')
        return self


class AnimalNovo(AnimalBase):
    microchip: Optional[str] = Field(default=None, pattern=r'^\d{15}$')


class MicrochipNovo(Entrada):
    codigo: str = Field(pattern=r'^\d{15}$')
    motivo: Optional[str] = Field(default=None, max_length=255)


# ---------------------------------------------------------------- consulta e vacina
class ConsultaNova(Entrada):
    animal_id: int = Field(gt=0)
    veterinario_id: Optional[int] = Field(default=None, gt=0)  # padrão: o veterinário logado
    data_hora: datetime
    motivo: str = Field(min_length=1, max_length=255)
    anamnese: Optional[str] = Field(default=None, max_length=4000)
    sintomas: Optional[str] = Field(default=None, max_length=4000)
    diagnostico: Optional[str] = Field(default=None, max_length=4000)
    tratamento: Optional[str] = Field(default=None, max_length=4000)
    prescricao: Optional[str] = Field(default=None, max_length=4000)
    peso_registrado: Optional[float] = Field(default=None, gt=0, le=1500)
    temperatura: Optional[float] = Field(default=None, ge=30, le=45)
    observacoes: Optional[str] = Field(default=None, max_length=4000)
    situacao: Literal['AGENDADA', 'REALIZADA', 'CANCELADA', 'NAO_COMPARECEU'] = 'REALIZADA'

    @field_validator('data_hora')
    @classmethod
    def _sem_fuso(cls, v):
        return v.replace(tzinfo=None)


class ConsultaSituacao(Entrada):
    situacao: Literal['REALIZADA', 'CANCELADA', 'NAO_COMPARECEU']


class VacinaNova(Entrada):
    animal_id: int = Field(gt=0)
    veterinario_id: Optional[int] = Field(default=None, gt=0)  # padrão: o veterinário logado
    nome: str = Field(min_length=1, max_length=100)
    tipo: str = Field(min_length=1, max_length=60)
    antirrabica: bool = False
    fabricante: str = Field(min_length=1, max_length=100)
    lote: str = Field(min_length=1, max_length=40)
    data_aplicacao: date
    dose_etapa: Optional[str] = Field(default=None, max_length=30)
    via_aplicacao: Optional[str] = Field(default=None, max_length=30)
    data_proxima_dose: Optional[date] = None
    validade_lote: Optional[date] = None
    observacoes: Optional[str] = Field(default=None, max_length=2000)
    situacao: Literal['AGENDADA', 'APLICADA', 'CANCELADA'] = 'APLICADA'

    @model_validator(mode='after')
    def _proxima(self):
        if self.data_proxima_dose and self.data_proxima_dose <= self.data_aplicacao:
            raise ValueError('A próxima dose precisa ser depois da data de aplicação.')
        return self


class VacinaSituacao(Entrada):
    situacao: Literal['APLICADA', 'CANCELADA']
    data_aplicacao: Optional[date] = None  # usado ao marcar como aplicada (padrão: hoje)


# ---------------------------------------------------------------- API governamental (serviço separado)
class GovAnimal(Entrada):
    microchip: str = Field(pattern=r'^\d{15}$')
    animal_id: int = Field(gt=0)
    versao: int = Field(gt=0)
    nome: str = Field(min_length=1, max_length=80)
    especie: str = Field(min_length=1, max_length=60)
    raca: Optional[str] = Field(default=None, max_length=80)
    sexo: Literal['M', 'F']
    nascimento: Optional[date] = None
    situacao: Literal['ATIVO', 'INATIVO', 'OBITO'] = 'ATIVO'
    microchip_anterior: Optional[str] = Field(default=None, pattern=r'^\d{15}$')


class GovVacina(Entrada):
    microchip: str = Field(pattern=r'^\d{15}$')
    animal_id: int = Field(gt=0)
    animal_nome: str = Field(min_length=1, max_length=80)
    vacina_id: int = Field(gt=0)
    nome: str = Field(min_length=1, max_length=100)
    fabricante: str = Field(min_length=1, max_length=100)
    lote: str = Field(min_length=1, max_length=40)
    data_aplicacao: date
    veterinario_nome: str = Field(min_length=1, max_length=150)
    veterinario_crmv: str = Field(min_length=3, max_length=30)
