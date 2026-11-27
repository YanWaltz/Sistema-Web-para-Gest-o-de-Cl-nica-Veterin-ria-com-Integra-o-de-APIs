# Passo a passo (demonstração)
1. `python iniciar.py` e abrir http://127.0.0.1:8000.
2. Entrar com demo@clinica.local / ClinicaDemo!26. (Ou "Criar conta": o código aparece no terminal e na tela — e-mail simulado.)
3. Cadastros › Endereços › Novo: digitar CEP, "Buscar no ViaCEP", informar o número. Cadastrar outro endereço no mesmo CEP: os dados do CEP não se repetem.
4. Cadastros › Tutores: CPF válido (ex.: 390.533.447-05). Tente repetir o CPF: erro.
5. Cadastros › Espécies e Raças. Animais › Novo animal (com microchip de 15 dígitos).
6. Atendimentos: registrar consulta e vacina antirrábica (animal precisa de microchip).
7. Integração: ver CONFIRMADA com protocolo. "Simular governo fora do ar", registrar nova antirrábica (fica PENDENTE), "Restabelecer governo" e "Reenviar pendências".
8. Animais › Histórico: substituir microchip e ver o histórico preservado.
