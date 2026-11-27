"""Funções puras de validação (não dependem de framework, por isso são fáceis de testar)."""
import re


def so_digitos(texto):
    """Remove tudo que não for número: '529.982.247-25' vira '52998224725'."""
    return re.sub(r'\D', '', texto or '')


def cpf_valido(cpf):
    """Confere o CPF pelos dois dígitos verificadores.

    1. Precisa ter 11 números e não pode ser uma sequência repetida (111.111.111-11).
    2. O 10º número é calculado a partir dos 9 primeiros; o 11º, a partir dos 10 primeiros.
    """
    numeros = so_digitos(cpf)
    if len(numeros) != 11 or numeros == numeros[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(numeros[i]) * (tamanho + 1 - i) for i in range(tamanho))
        if (soma * 10 % 11) % 10 != int(numeros[tamanho]):
            return False
    return True
