from datetime import date
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

class Login(Entrada):
    usuario: str = Field(min_length=1, max_length=60)
    senha: str = Field(min_length=8, max_length=128)

class Nome(Entrada):
    nome: str = Field(min_length=1, max_length=120)

class Endereco(Entrada):
    cep: str = Field(pattern=r'^\d{5}-?\d{3}$')
    logradouro: str = Field(min_length=1, max_length=120)
    numero: str = Field(min_length=1, max_length=20)
    complemento: Optional[str] = Field(default=None, max_length=120)
    bairro: str = Field(min_length=1, max_length=100)
    cidade: str = Field(min_length=1, max_length=100)
    uf: str = Field(min_length=2, max_length=2)

class Tutor(Nome):
    telefone: str = Field(min_length=8, max_length=24)
    endereco_id: int = Field(gt=0)

class Raca(Nome):
    especie_id: int = Field(gt=0)

class Veterinario(Nome):
    crmv: str = Field(min_length=3, max_length=30)

class Animal(Nome):
    nascimento: Optional[date] = None
    tutor_id: int = Field(gt=0)
    especie_id: int = Field(gt=0)
    raca_id: Optional[int] = Field(default=None, gt=0)
    microchip: str = Field(min_length=15, max_length=15)

class Atendimento(Entrada):
    animal_id: int = Field(gt=0)
    veterinario_id: int = Field(gt=0)
    data: date

class Consulta(Atendimento):
    descricao: str = Field(min_length=1, max_length=2000)

class Vacina(Atendimento):
    nome: str = Field(min_length=1, max_length=120)
    lote: str = Field(min_length=1, max_length=60)
    antirrabica: bool = False

class GovAnimal(Nome):
    animal_id: int = Field(gt=0)
    versao: int = Field(gt=0)
    especie: str = Field(min_length=1, max_length=120)
    microchip: str = Field(min_length=15, max_length=15)
    ativo: bool

class GovVacina(Entrada):
    animal_id: int = Field(gt=0)
    vacina_id: int = Field(gt=0)
    nome: str = Field(min_length=1, max_length=120)
    lote: str = Field(min_length=1, max_length=60)
    data: date
