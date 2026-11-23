# Passo a passo | Entenda e publique o SDM

## Como foi feito

1. **Requisitos:** separei no cronograma o que precisava existir no banco, na tela, nas integrações e na entrega. `docs/requisitos.md` explica as regras escolhidas nos pontos que a imagem não detalha.
2. **Modelagem:** cada tipo de cadastro virou uma tabela. Exemplo: `tutores.endereco_id` aponta para um endereço. Veja o diagrama em `docs/modelagem.md` e as tabelas em `sdm/schema.sql`.
3. **API privada e login:** `sdm/clinica.py` recebe os pedidos da tela e acessa o banco. `sdm/modelos.py` valida os dados e `sdm/seguranca.py` confere a senha e o perfil. Depois de entrar, a tela usa um token, que identifica a sessão sem reenviar a senha a cada ação.
4. **Interface e CEP:** `sdm/web/` contém HTML (estrutura), CSS (aparência) e JavaScript (ações). Para preencher um endereço, a tela chama a clínica e ela consulta o ViaCEP; número e complemento continuam manuais.
5. **Governo simulado:** `sdm/governo.py` é um segundo serviço HTTP, com banco separado. A clínica grava o cadastro e a operação a enviar juntos. `sdm/integracao.py` tenta enviar e registra o resultado. Se falhar, você pode reenviar. Usar a mesma chave evita criar a mesma operação duas vezes: é a idempotência.
6. **Verificação:** `tests/test_fluxos.py` testa a comunicação entre dois processos separados, em bancos temporários. Em `docs/` ficam o relatório, as evidências e o roteiro para apresentar.

## Subir no repositório que você já tem

1. No navegador, abra o repositório. Em **Code**, copie o endereço HTTPS. No terminal, rode `git clone "COLE_O_ENDERECO_HTTPS_AQUI"`. Se já tem uma cópia local, entre nela em vez de clonar de novo.
2. Abra o terminal **dentro da pasta clonada**, rode `git switch -c entrega-sdm` e copie a pasta extraída `clinica-sdm` inteira para dentro do repositório. Se a branch já existir, use `git switch entrega-sdm`. Se a pasta já estiver lá, compare os arquivos antes de substituir.
3. Rode, uma linha por vez:

   ```sh
   git add -- clinica-sdm/
   git status --short
   git diff --cached --stat
   git commit -m "Entrega SDM Clinica Veterinaria"
   git push -u origin entrega-sdm
   ```

   Confira que nenhum `.env`, `.venv/`, `data/`, dado real ou senha real aparece no `git status`. Não envie o ZIP: envie o código extraído. Se o Git pedir login ou identificação, use a conta autorizada para o repositório. Não use `push --force`.
4. Volte ao navegador, selecione a branch `entrega-sdm` e abra `clinica-sdm/README.md`. Se o trabalho exige a entrega na branch principal, abra um pull request e siga a regra de aprovação do repositório. Envie o link solicitado na entrega.

Referência: [publicar código local no GitHub](https://docs.github.com/github/importing-your-projects-to-github/adding-an-existing-project-to-github-using-the-command-line?platform=windows).
