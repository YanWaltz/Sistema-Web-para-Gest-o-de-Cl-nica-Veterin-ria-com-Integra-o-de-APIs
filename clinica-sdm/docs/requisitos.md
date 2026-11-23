# Requisitos e regras de negócio

**Escopo:** implementar o sistema de clínica veterinária descrito no cronograma de 29/10 a 26/11/2026. O cronograma não especifica todos os campos nem todas as regras detalhadas. As decisões abaixo são deste projeto, não uma transcrição de um enunciado complementar.

| Marco | Requisitos cobertos |
|---|---|
| 29/10 · Modelagem e arquitetura | Levantamento de requisitos, regras, MER, modelo relacional e funções do navegador, da API da clínica e do governo simulado. |
| 05/11 · Banco e API privada | Persistir endereço, tutor, espécie, raça, veterinário e animal. Oferecer criar, listar, consultar, editar, excluir (ou inativar, no caso de animal), login, logout e controle de acesso. Coleção Postman e evidência. |
| 12/11 · Interface e clínica | Interface web; autopreenchimento de endereço por CEP; associação individual do microchip; registro de consulta e vacina; histórico por animal; filtro por nome ou microchip. |
| 19/11 · Integração distribuída | Serviço governamental simulado com banco separado; receber cadastro e atualização de animal e vacina antirrábica por HTTP; guardar protocolo, status e tentativas; simular falha, reenviar e impedir duplicidade de operações. |
| 26/11 · Entrega | Sistema executável, Swagger/OpenAPI, relatório e evidências de testes, instruções de instalação, arquivos para o Git e roteiro para apresentação ao vivo. |

## Regras implementadas

- Usuários são autenticados por senha com hash e token de sessão com validade de oito horas. Os perfis administrador e clínica cadastram e editam; somente administrador exclui, inativa, simula falha ou reenvia.
- Tutor deve ter um endereço. Animal deve ter tutor e espécie. Se informada, a raça precisa pertencer à espécie. CRMV é único na base local, sem validação cadastral externa.
- Microchip tem 15 dígitos e é único, inclusive entre animais inativados. Não há leitura por hardware.
- Consulta e vacina exigem animal ativo e veterinário cadastrado. A data não pode ser futura nem anterior ao nascimento quando ele foi informado.
- A exclusão física de um cadastro referenciado é bloqueada. Para preservar o histórico, excluir animal significa inativá-lo, sem apagar o registro.
- ViaCEP recebe apenas o CEP. Número e complemento são preenchidos manualmente; em caso de falha, o endereço inteiro pode ser preenchido sem consulta.
- O governo simulado recebe dados do animal e da vacina marcada como antirrábica. Não recebe nome, telefone ou endereço do tutor, nem consultas ou outras vacinas.
- A clínica grava o dado e a operação pendente na mesma transação. Um erro remoto não desfaz o dado local. O reenvio preserva a ordem por animal e reutiliza a mesma chave, sem duplicar registros. Repetir a chave com conteúdo diferente dá HTTP 409.

## Limites declarados

Demonstração local com dois processos, uma instância de envio e um banco por serviço. Não inclui cobrança, agenda, recuperação de senha, validação em cadastro real, implantação em produção ou reenvio periódico autônomo. O cronograma não determina tecnologias; Python/FastAPI, SQLite e HTML/CSS/JavaScript foram escolhidos para que seja possível executar o projeto sem instalar um servidor de banco separado.
