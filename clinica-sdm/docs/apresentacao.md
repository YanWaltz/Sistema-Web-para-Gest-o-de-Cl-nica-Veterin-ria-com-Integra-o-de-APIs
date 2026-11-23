# Apresentação final | SDM Clínica

**Duração:** 5 a 7 minutos. Antes, deixe o sistema rodando e abra `docs/modelagem.md` e o Swagger da clínica. Use dados fictícios.

## Abertura · 40 segundos

> O SDM Clínica cadastra animais e registra os atendimentos. O projeto também mostra como continuar atendendo quando o sistema externo fica fora do ar e como reenviar o que ficou pendente.

Mostre a arquitetura: navegador, clínica e banco; ViaCEP para consultar endereços; segundo serviço com outro banco para simular o governo.

## Cadastro e atendimento · 2 minutos

1. **Cadastros → Endereços → Novo cadastro:** consulte `01001-000`. Complete com número `10`. Se o serviço estiver fora, digite Praça da Sé, Sé, São Paulo, SP. Para economizar tempo, deixe os cadastros de apoio prontos antes da apresentação.
2. Crie **Tutor Demo**, telefone `2100000000`; espécie **Canina**; raça **SRD**, escolhendo Canina; e veterinário **Vet Demo**, CRMV fictício `DEMO-001`.
3. Em **Animais**, crie **Luna** e selecione esses cadastros. Use microchip fictício `000000000000123` ou outro de 15 dígitos se já usou esse no ensaio.
4. Em **Atendimentos**, registre uma consulta com a descrição `Consulta demonstrativa`. Mostre **Animais → Histórico**.

## Indisponibilidade e reenvio · 2 minutos

1. Abra **Integração** e confirme que o cadastro da Luna está `ENVIADO`. Se necessário, aguarde e clique em **Atualizar lista**.
2. Clique **Simular indisponibilidade**. Em **Atendimentos**, registre `Antirrábica de demonstração`, lote `DEMO-01`, com **Enviar como antirrábica** marcado.
3. Mostre a vacina salva em **Animais → Histórico**, mesmo com o serviço fora. Volte a **Integração** e atualize até ver `FALHA` e `HTTP 503`.
4. Clique **Restaurar serviço**, depois **Reenviar pendências**. Mostre `ENVIADO`, as tentativas e o protocolo `GOV-...`. Repita o reenvio: ele deve mostrar zero novas operações.

> A clínica salva primeiro no próprio banco. Quando o governo volta, reenvia a operação com a mesma chave; repetir a chave não cria outro registro.

## Encerramento · 45 segundos

Mostre `/docs` para apresentar as rotas e `docs/relatorio-testes.md` para apresentar os testes. Explique que ViaCEP foi testado com respostas controladas e que a consulta ao vivo depende de internet. O governo é simulado e não recebe dados reais.

**Antes de entregar:** ensaie no computador da apresentação, confirme o CEP, confira se há outro enunciado além da imagem e verifique se o código aparece na branch que você vai entregar.
