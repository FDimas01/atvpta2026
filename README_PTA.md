# PTA – Servidor TCP de transferência de arquivos

Implementação do servidor do Protocolo de Transferência de Arquivos (PTA) descrito em `pta.pdf`, desenvolvida em Python.

## Requisitos

- Python **3.9 ou superior** (3.10, 3.11, 3.12 e 3.13 também são adequados).
- Somente bibliotecas padrão do Python (`socket`, `socketserver`, `pathlib`, `select`, `argparse`). **Não exige `pip install`.**
- Git para clonar/publicar o fork (não necessário para executar o servidor).
- A porta TCP **11550** deve estar disponível.

## Estrutura no fork do professor

Os arquivos originais `pta.pdf`, `pta-client.py`, `pta-server/users.txt` e TODO o conteúdo de `pta-server/files/` devem ser preservados, sem substituições.

```text
pta/
├── pta.pdf                    [original]
├── pta-client.py              [original]
├── README.md                  [original]
├── README_PTA.md              [adicionado]
├── testes_pta.py              [adicionado]
└── pta-server/
    ├── pta-server.py          [adicionado]
    ├── users.txt              [original]
    └── files/                 [original; não modificar]
```

O servidor encontra os caminhos de `users.txt` e `files/` relativos ao script, de modo que pode ser executado de qualquer diretório.

## Execução local

Abra um terminal na raiz do fork (`pta/`) e execute:

**Windows (PowerShell):**

```powershell
py -3 pta-server/pta-server.py
```

**Linux/macOS:**

```bash
python3 pta-server/pta-server.py
```

O servidor imprime o endereço de escuta e mantém o processo rodando. Por padrão, escuta em `0.0.0.0:11550` (todas as interfaces). Para limitar apenas à máquina local: `--host 127.0.0.1`. Encerre com **Ctrl+C**.

## Teste com o cliente original do professor

**Não feche o terminal do servidor.** Abra **outro terminal**, também na raiz do fork, e execute:

**Windows:**

```powershell
py -3 pta-client.py 127.0.0.1 11550 user1
```

**Linux/macOS:**

```bash
python3 pta-client.py 127.0.0.1 11550 user1
```

`user1` é uma das entradas de `pta-server/users.txt` do repositório consultado. Substitua pelo nome literal de algum usuário realmente presente em seu fork, se necessário.

A linha final esperada no cliente é **`Points: 6/6`**, seguida da mensagem **`TERM is OK!`**. O cliente original **salva o arquivo baixado no diretório atual**: confira `git status` e não adicione esse arquivo gerado ao commit acidentalmente. O cliente original lê os bytes do arquivo como texto e pode falhar em arquivos binários ou incompatíveis com UTF-8, embora o servidor envie os bytes corretamente; nesse caso, use os testes adicionais abaixo.

## Testes extras automatizados

Com o servidor original ainda em execução ou não, execute na raiz do fork:

**Windows:** `py -3 testes_pta.py`

**Linux/macOS:** `python3 testes_pta.py`

Os testes adicionais **iniciam outro servidor em uma porta temporária**, criam usuários e arquivos em um diretório temporário e NÃO alteram `pta-server/users.txt` nem `pta-server/files/`. Verificam autenticação, caixa das letras, listagem, download binário e vazio, arquivo inexistente, proteção contra caminhos relativos, ordem de sequência, erros de formato, estados, fechamento, conexões simultâneas e segmento TCP fragmentado.

O resultado esperado é `Ran 14 tests` e `OK`.

## Exemplos das mensagens de protocolo

```text
Cliente -> 10 CUMP user1
Servidor -> 10 OK
Cliente -> 11 LIST
Servidor -> 11 ARQS 2 exemplo.txt,outro.txt
Cliente -> 12 PEGA exemplo.txt
Servidor -> 12 ARQ 5 hello        (5 bytes exatos após o espaço)
Cliente -> 13 PEGA inexistente.txt
Servidor -> 13 NOK
Cliente -> 14 TERM
Servidor -> 14 OK                (servidor fecha a conexão)
```

As respostas `ARQ` possuem corpo binário: não acrescente uma quebra de linha após o conteúdo do arquivo. O contador de tamanho deve refletir os **bytes**, e não os caracteres. Após `CUMP` falho, o servidor envia `NOK` e fecha a conexão; após comandos inválidos em estado autenticado, responde `NOK` e continua aberto.

## Observação sobre o enquadramento TCP

O documento especifica o formato dos campos, mas não define terminador ou tamanho para a **requisição**. O cliente original envia cada pedido sem `\n` e aguarda a resposta antes do próximo. Esta implementação acumula fragmentos recebidos e considera o pedido completo após 50 ms sem novos bytes; admite também `\r\n` no fim do pedido. Consequentemente, **não suporta requisições simultâneas/pipelined na mesma conexão**, nem pode garantir o enquadramento correto caso o cliente faça pausas superiores a esse intervalo no meio de uma requisição. A limitação decorre da ausência de um delimitador no protocolo especificado; o cliente fornecido segue o padrão request/response sequencial.

## Publicação no GitHub

1. Acesse <https://github.com/glaucogoncalves/pta> e clique em **Fork**.
2. Clone **o seu fork** com `git clone https://github.com/SEU_USUARIO/pta.git` e entre na pasta com `cd pta`.
3. Copie `pta-server/pta-server.py`, `README_PTA.md` e `testes_pta.py` deste pacote para os caminhos equivalentes em seu fork. **Não substitua arquivos originais do professor.**
4. Teste localmente conforme instruções anteriores.
5. Use `git status` para conferir somente os arquivos pretendidos.
6. Execute `git add pta-server/pta-server.py README_PTA.md testes_pta.py`, `git commit -m "Implementa servidor PTA"` e `git push origin master` (ou a branch padrão do seu fork).
7. Copie o link do **seu fork**, e não o repositório do professor, e envie-o no SIGAA.

Opcionalmente, execute com flags `--port`, `--host`, `--users` e `--files` para testar configurações diferentes. Na avaliação com os arquivos originais, basta executar o script sem flags.
