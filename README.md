# Servidor PTA

Implementação do servidor do Protocolo de Transferência de Arquivos (PTA), desenvolvido em Python para a atividade da disciplina.

O servidor utiliza TCP na porta 11550 e implementa os comandos de autenticação (`CUMP`), listagem de arquivos (`LIST`), transferência de arquivos (`PEGA`) e encerramento da conexão (`TERM`), conforme a especificação disponível em `pta.pdf`.

## Requisitos

* Python 3.9 ou superior.
* Porta TCP 11550 disponível.
* Arquivos `users.txt` e diretório `files/` fornecidos no repositório original.

O projeto utiliza apenas bibliotecas padrão do Python, portanto não é necessário instalar dependências adicionais.

## Estrutura do projeto

Os arquivos originais do repositório foram mantidos. O código do servidor está localizado em `pta-server/pta-server.py`.

```text
pta/
├── pta.pdf
├── pta-client.py
├── README.md
├── testes_pta.py
└── pta-server/
    ├── pta-server.py
    ├── users.txt
    └── files/
```

O arquivo `users.txt` contém os usuários autorizados a acessar o servidor. Já o diretório `files/` contém os arquivos disponibilizados para download.

## Como executar

Abra um terminal na pasta principal do projeto.

No Windows (PowerShell):

```powershell
py -3 pta-server/pta-server.py
```

No Linux ou macOS:

```bash
python3 pta-server/pta-server.py
```

O servidor será iniciado na porta 11550 e permanecerá aguardando conexões. Para encerrar, utilize `Ctrl+C`.

Por padrão, o servidor escuta em `0.0.0.0`, permitindo conexões pelas interfaces de rede disponíveis. Para executar apenas localmente, utilize:

```powershell
py -3 pta-server/pta-server.py --host 127.0.0.1
```

## Como testar

### Cliente fornecido pelo professor

Com o servidor em execução, abra outro terminal na pasta principal do projeto.

No Windows:

```powershell
py -3 pta-client.py 127.0.0.1 11550 user1
```

No Linux ou macOS:

```bash
python3 pta-client.py 127.0.0.1 11550 user1
```

O último argumento corresponde ao usuário utilizado na autenticação. Caso necessário, substitua `user1` por um usuário presente em `pta-server/users.txt`.

O resultado esperado, caso todos os testes do cliente sejam aprovados, é:

```text
Points: 6/6
TERM is OK!
```

O cliente pode salvar arquivos baixados no diretório atual. Antes de enviar as alterações ao GitHub, verifique se algum arquivo foi gerado durante os testes.

### Testes adicionais

Também foi criado o arquivo `testes_pta.py`, com testes automatizados para verificar o funcionamento do servidor.

Execute na pasta principal do projeto:

```powershell
py -3 testes_pta.py
```

Os testes utilizam uma instância separada do servidor, em uma porta temporária, e não modificam os arquivos originais do repositório.

São verificados os seguintes casos:

* Autenticação de usuários válidos e inválidos.
* Diferenciação entre letras maiúsculas e minúsculas.
* Listagem e transferência de arquivos.
* Transferência de arquivos binários e vazios.
* Tratamento de arquivos inexistentes e comandos inválidos.
* Validação dos números de sequência.
* Encerramento da conexão e atendimento de múltiplos clientes.
* Recebimento de uma requisição dividida em fragmentos TCP.

O resultado esperado é:

```text
Ran 14 tests

OK
```

## Funcionamento do protocolo

As mensagens enviadas pelo cliente seguem o formato:

```text
SEQ_NUM COMMAND ARGS
```

O número de sequência é definido inicialmente pelo cliente e incrementado a cada nova requisição. O servidor utiliza esse mesmo número na resposta.

Exemplo de comunicação:

```text
Cliente:  10 CUMP user1
Servidor: 10 OK

Cliente:  11 LIST
Servidor: 11 ARQS 2 exemplo.txt,outro.txt

Cliente:  12 PEGA exemplo.txt
Servidor: 12 ARQ 5 hello

Cliente:  13 PEGA inexistente.txt
Servidor: 13 NOK

Cliente:  14 TERM
Servidor: 14 OK
```

No comando `PEGA`, o servidor informa o tamanho do arquivo em bytes e envia seu conteúdo em seguida. Os arquivos são lidos em modo binário para preservar os dados originais.

O cliente precisa se autenticar antes de utilizar os demais comandos. Uma apresentação inválida resulta em `NOK` e no fechamento da conexão. Após a autenticação, comandos inválidos recebem `NOK`, mas a conexão permanece aberta.

O comando `TERM` encerra a sessão após o envio da resposta `OK`.

## Observações

O protocolo não define um delimitador ou campo de tamanho para as mensagens de requisição. Nesta implementação, o servidor acumula os dados recebidos e considera a requisição completa após um intervalo de 50 ms sem novos bytes.

Essa abordagem atende ao modelo de comunicação sequencial utilizado pelo cliente fornecido, mas não oferece suporte a múltiplas requisições simultâneas na mesma conexão. Pausas maiores que esse intervalo durante o envio de uma mensagem também podem comprometer sua interpretação.

Para utilizar configurações diferentes, o servidor aceita os argumentos `--host`, `--port`, `--users` e `--files`. Na execução padrão, não é necessário informar nenhum deles.
