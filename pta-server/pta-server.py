
#!/usr/bin/env python3
"""Servidor do Protocolo de Transferência de Arquivos (PTA).

Compatível com Python 3.9+ e biblioteca padrão.

O protocolo utiliza TCP e mantém compatibilidade com o cliente do professor,
que não utiliza terminador explícito nas mensagens de pedido.
"""

import argparse
import select
import socketserver
import threading
from pathlib import Path
from typing import List, Optional, Set, Tuple


DEFAULT_DIR = Path(__file__).resolve().parent
MAX_REQUEST = 16 * 1024
RECEIVE_IDLE_SECONDS = 0.05


def load_users(path: Path) -> Set[str]:
    """Carrega os usuários permitidos, respeitando maiúsculas e minúsculas."""
    with path.open("r", encoding="ascii") as stream:
        return {
            line.rstrip("\r\n")
            for line in stream
            if line.rstrip("\r\n")
        }


def available_files(directory: Path) -> List[str]:
    """Lista arquivos regulares diretamente no diretório, em ordem estável."""
    return sorted(
        entry.name
        for entry in directory.iterdir()
        if entry.is_file()
        and entry.resolve().parent == directory.resolve()
    )


def parse_request(
    raw: bytes,
) -> Tuple[str, Optional[str], Optional[str]]:
    """Retorna (sequência, comando, argumento), ou comando None se inválido."""
    raw = raw.rstrip(b"\r\n")

    try:
        message = raw.decode("ascii")
    except UnicodeDecodeError:
        return "0", None, None

    fields = message.split(" ")

    if (
        not fields
        or not fields[0]
        or not fields[0].isascii()
        or not fields[0].isdecimal()
    ):
        return "0", None, None

    sequence = fields[0]

    if len(fields) < 2:
        return sequence, None, None

    command = fields[1]

    if command in ("CUMP", "PEGA"):
        if len(fields) != 3 or not fields[2]:
            return sequence, None, None

        return sequence, command, fields[2]

    if command in ("LIST", "TERM"):
        if len(fields) != 2:
            return sequence, None, None

        return sequence, command, None

    # Comando desconhecido com formato simples: poderá receber NOK.
    if len(fields) == 2:
        return sequence, command, None

    return sequence, None, None


class PTAHandler(socketserver.BaseRequestHandler):

    def read_request(self) -> Optional[bytes]:
        """Lê uma requisição compatível com o cliente original do professor.

        Como o protocolo não define terminador nem tamanho para pedidos,
        aguarda um intervalo configurável sem novos dados. Isso é uma
        heurística de compatibilidade, não uma delimitação TCP garantida.
        """
        first = self.request.recv(4096)

        if not first:
            return None

        data = bytearray(first)
        idle_seconds = self.server.receive_idle_seconds

        while len(data) <= MAX_REQUEST:
            ready, _, _ = select.select(
                [self.request], [], [], idle_seconds
            )

            if not ready:
                return bytes(data)

            chunk = self.request.recv(4096)

            if not chunk:
                return bytes(data)

            data.extend(chunk)

        return bytes(data)

    def reply(self, sequence: str, response: str) -> None:
        """Envia uma resposta simples do protocolo."""
        self.request.sendall(
            f"{sequence} {response}".encode("ascii")
        )

    def send_listing(self, sequence: str) -> None:
        """Envia a quantidade de arquivos e seus nomes separados por vírgula."""
        try:
            names = available_files(self.server.files_dir)
            names_bytes = ",".join(names).encode("utf-8")
            header = f"{sequence} ARQS {len(names)} ".encode("ascii")

        except (OSError, UnicodeEncodeError):
            self.reply(sequence, "NOK")
            return

        self.request.sendall(header + names_bytes)

    def send_file(self, sequence: str, filename: str) -> None:
        """Transmite um arquivo binário precedido pelo tamanho em bytes."""
        # Impede caminhos absolutos, subdiretórios e travessia de pastas.
        if (
            filename in (".", "..")
            or "/" in filename
            or "\\" in filename
        ):
            self.reply(sequence, "NOK")
            return

        path = self.server.files_dir / filename
        header_sent = False

        try:
            if (
                not path.is_file()
                or path.resolve().parent
                != self.server.files_dir.resolve()
            ):
                self.reply(sequence, "NOK")
                return

            # Abre antes de enviar o cabeçalho.
            with path.open("rb") as source:
                size = source.seek(0, 2)
                source.seek(0)

                header = f"{sequence} ARQ {size} ".encode("ascii")
                self.request.sendall(header)
                header_sent = True

                while True:
                    chunk = source.read(64 * 1024)

                    if not chunk:
                        break

                    self.request.sendall(chunk)

        except OSError:
            # Não é possível inserir NOK depois de começar a transmitir
            # os bytes do arquivo.
            if not header_sent:
                self.reply(sequence, "NOK")
            else:
                raise

    def handle(self) -> None:
        self.request.settimeout(60)

        authenticated = False

        # Armazena a próxima sequência esperada.
        # A primeira sequência pode ser escolhida pelo cliente.
        expected_sequence = None

        try:
            while True:
                raw = self.read_request()

                if raw is None:
                    return

                sequence, command, argument = parse_request(raw)

                first_field = raw.partition(b" ")[0]

                valid_number = (
                    first_field.isascii()
                    and first_field.isdigit()
                    and len(first_field) <= 64
                )

                # Verifica se a sequência recebida é a esperada.
                # Uma sequência incorreta recebe NOK.
                if valid_number:
                    number = int(sequence)

                    if (
                        expected_sequence is not None
                        and number != expected_sequence
                    ):
                        self.reply(sequence, "NOK")

                        if not authenticated:
                            return

                        continue

                    expected_sequence = number + 1

                # Rejeita mensagens inválidas.
                if (
                    len(raw) > MAX_REQUEST
                    or command is None
                    or not valid_number
                ):
                    self.reply(sequence, "NOK")

                    if not authenticated:
                        return

                    continue

                # A apresentação deve ser a primeira operação válida.
                if not authenticated:
                    with self.server.operation_lock:
                        if (
                            command != "CUMP"
                            or argument not in self.server.allowed_users
                        ):
                            self.reply(sequence, "NOK")
                            return

                        self.reply(sequence, "OK")
                        authenticated = True

                    continue

                # Serializa as operações entre conexões diferentes.
                with self.server.operation_lock:

                    if command == "LIST":
                        self.send_listing(sequence)

                    elif command == "PEGA":
                        self.send_file(sequence, argument)

                    elif command == "TERM":
                        self.reply(sequence, "OK")
                        return

                    else:
                        # Comando inválido após a autenticação:
                        # responde NOK sem fechar a conexão.
                        self.reply(sequence, "NOK")

        except (
            BrokenPipeError,
            ConnectionError,
            TimeoutError,
            OSError,
        ):
            # Cliente desconectado, falha de transmissão ou inatividade.
            return


class PTAServer(
    socketserver.ThreadingMixIn,
    socketserver.TCPServer,
):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(
        self,
        address: Tuple[str, int],
        users: Path,
        files: Path,
        receive_idle_seconds: float = RECEIVE_IDLE_SECONDS,
    ) -> None:

        self.allowed_users = load_users(users)

        if not files.is_dir():
            raise NotADirectoryError(
                f"Diretório de arquivos não encontrado: {files}"
            )

        if receive_idle_seconds <= 0:
            raise ValueError(
                "O intervalo de leitura deve ser maior que zero."
            )

        self.files_dir = files.resolve()
        self.receive_idle_seconds = receive_idle_seconds

        # Bloqueio global para executar uma operação do PTA por vez.
        self.operation_lock = threading.Lock()

        super().__init__(address, PTAHandler)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Servidor TCP para o protocolo PTA"
    )

    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="IP de escuta (padrão: 0.0.0.0)",
    )

    parser.add_argument(
        "--port",
        default=11550,
        type=int,
        help="Porta TCP (padrão: 11550)",
    )

    parser.add_argument(
        "--users",
        type=Path,
        default=DEFAULT_DIR / "users.txt",
        help="Arquivo com a lista de usuários autorizados",
    )

    parser.add_argument(
        "--files",
        type=Path,
        default=DEFAULT_DIR / "files",
        help="Diretório dos arquivos disponibilizados",
    )

    parser.add_argument(
        "--receive-idle",
        type=float,
        default=RECEIVE_IDLE_SECONDS,
        help=(
            "Intervalo de silêncio em segundos para concluir "
            "a leitura de um pedido (padrão: 0.05)"
        ),
    )

    args = parser.parse_args()

    with PTAServer(
        (args.host, args.port),
        args.users,
        args.files,
        args.receive_idle,
    ) as server:

        print(
            f"PTA ouvindo em {args.host}:{server.server_address[1]}",
            flush=True,
        )

        print(
            f"Usuários carregados: {len(server.allowed_users)}",
            flush=True,
        )

        print(
            f"Arquivos disponíveis em: {server.files_dir}",
            flush=True,
        )

        print(
            f"Intervalo de leitura: {server.receive_idle_seconds}s",
            flush=True,
        )

        try:
            server.serve_forever(poll_interval=0.1)

        except KeyboardInterrupt:
            print("\nServidor encerrado.")


if __name__ == "__main__":
    main()
