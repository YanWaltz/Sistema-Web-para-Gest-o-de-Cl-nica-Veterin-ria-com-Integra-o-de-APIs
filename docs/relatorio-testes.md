# Relatório de testes e evidências

**Resultado observado:** seis testes automatizados passaram. A execução usou bancos temporários e os dois serviços em processos separados. O resultado bruto está em [evidencias-testes.txt](evidencias-testes.txt).

| Teste | Cenário | Verificação |
|---|---|---|
| 01 | Acesso, contrato e arquivos da interface | Página, JavaScript e Swagger são servidos; acesso sem token, senha errada e permissões insuficientes são recusados; logout invalida o token. |
| 02 | Fluxo clínico com indisponibilidade e reenvio | Cadastros ligados; CRUD de veterinário; vínculo inválido, microchip duplicado ou inválido e data futura recusados; histórico com consulta e duas vacinas. Cadastro, vacina antirrábica e atualização reenviados com protocolos; vacina comum não é transmitida; inativação preserva o histórico. |
| 03 | Idempotência da API governamental | Repetição devolve o mesmo protocolo; mesma chave com carga diferente retorna 409; acesso sem chave negado. |
| 04 | ViaCEP: sucesso com resposta controlada | CEP com hífen é normalizado, e `localidade` preenche `cidade`. |
| 05 | ViaCEP: CEP inexistente e formato inválido | HTTP 404 e HTTP 422, respectivamente. |
| 06 | ViaCEP: indisponibilidade | Falha de rede vira HTTP 503 com orientação para preencher manualmente. |

**Limites da evidência:** ViaCEP foi testado com respostas controladas, sem consultar o serviço público ao vivo. Os testes verificaram a entrega dos arquivos estáticos via HTTP, não cliques em um navegador nem o atalho em Windows. Na máquina da apresentação, execute o roteiro, confirme o preenchimento do CEP em rede e use endereço manual se necessário. O governo é simulado, não é uma integração oficial.
