VANIA'S PETSHOP CRM
====================

Sistema de atendimento e agenda para a Vania's Petshop.

Como abrir
----------
Abra o arquivo COMECA AQUI.txt primeiro. Ele explica tudo com passos simples.

O que funciona
--------------
- Conversas, pesquisa, filtros e envio de mensagens
- Clientes, agenda de banho e tosa e novos agendamentos
- Precos de servicos e mensagens para varios clientes
- Ligacao pelo botao de telefone
- Dados salvos neste navegador mesmo depois de fechar e abrir novamente

Importante
----------
Esta versao funciona no computador para testar o sistema. Para enviar mensagens reais pelo WhatsApp,
e preciso conectar a WhatsApp Business Platform, um servidor seguro e um banco de dados.

Servidor opcional
-----------------
Nesta pasta, execute:
  python3 -m http.server 8080
Depois abra http://localhost:8080

COMO PEGAR A API DO WHATSAPP
============================

A API e a "ponte" que permite o sistema conversar com o WhatsApp. Para conseguir essa ponte:

1. Entre em business.facebook.com e crie ou entre na conta da empresa.
2. Abra Meta Business Suite e confirme a empresa.
3. Entre em Configuracoes da empresa > Contas > Contas do WhatsApp.
4. Crie ou escolha a conta WhatsApp Business da Vania's Petshop.
5. Em WhatsApp > Configuracao da API, adicione o numero da loja.
6. Use um numero que nao esteja conectado ao aplicativo WhatsApp comum.
7. Confirme o numero com o codigo que chegar por SMS ou ligacao.
8. Crie um usuario do sistema e gere um token de acesso permanente.
9. Anote com cuidado estes dados: ID da conta WhatsApp, ID do numero, telefone e token.

O QUE FAZER COM ESSES DADOS
===========================

Nao coloque o token dentro do arquivo index.html e nao envie o token por WhatsApp.
Um desenvolvedor deve colocar os dados em um servidor seguro e conectar:

- mensagens recebidas: Meta envia para o servidor por um webhook;
- mensagens enviadas: o servidor chama a API da Meta;
- clientes e agenda: o servidor salva em um banco de dados;
- equipe: cada pessoa recebe seu proprio login.

MENSAGENS PARA VARIOS CLIENTES
==============================

A Meta exige modelos de mensagem aprovados para iniciar conversas com clientes.
No Gerenciador do WhatsApp, abra Modelos de mensagem, crie um modelo, envie para aprovacao
e aguarde a aprovacao. Depois o desenvolvedor conecta o modelo ao botao Mensagens em massa.

QUEM DEVE FAZER A CONFIGURACAO
==============================

O dono da loja pode criar a conta e confirmar o telefone. A parte do token, servidor,
banco de dados e webhook deve ser feita por um desenvolvedor. Nunca compartilhe o token
em telas publicas ou com pessoas que nao vao trabalhar no sistema.
