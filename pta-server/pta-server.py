#!/usr/bin/env python3
"""Servidor do Protocolo de Transferência de Arquivos (PTA).

Python 3.9+, somente biblioteca padrão.
O enquadramento das requisições segue o cliente disponibilizado pelo professor:
um comando por troca request/response, sem terminador obrigatório. Consulte o README_PTA.md.
"""

from __future__ import annotations

import argparse
import select
import socket
import socketserver
from pathlib import Path


DEFAULT_DIR = Path(__file__).resolve().parent
MAX_REQUEST = 16 * 1024
RECEIVE_IDLE_SECONDS = 0.05


def load_users(path: Path) -> set[str]:
    """Cada linha não vazia de users.txt representa um usuário exato (case-sensitive)."""
    with path.open("r", encoding="ascii") as stream:
        return {line.rstrip("\r\n") for line in stream if line.rstrip("\r\n")}


def available_files(directory: Path) -> list[str]:
    """Lista apenas arquivos regulares diretamente em files/, em ordem estável."""
    return sorted(
        entry.name
        for entry in directory.iterdir()
        if entry.is_file() and entry.resolve().parent == directory.resolve()
    )


def parse_request(raw: bytes) -> tuple[str, str | None, str | None]:
    """Retorna (sequência ecoável, comando, argumento), ou comando None se inválido."""
    # O cliente original não envia '\n'; toleramos CRLF de clientes interativos.
    raw = raw.rstrip(b"\r\n")
    try:
        message = raw.decode("ascii")
    except UnicodeDecodeError:
        return "0", None, None

    fields = message.split(" ")
    sequence = fields[0] if fields and fields[0].isascii() and fields[0].isdecimal() else "0"
    if not fields or not fields[0].isascii() or not fields[0].isdecimal():
        return sequence, None, None

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
    # Comando desconhecido: o servidor deve responder NOK.
    return (sequence, command, None) if len(fields) == 2 else (sequence, None, None)


class PTAHandler(socketserver.BaseRequestHandler):
    def read_request(self) -> bytes | None:
        """Lê um pedido do cliente de exemplo, que não usa delimitador de mensagens.

        Aguarda a primeira parte e junta os demais segmentos TCP que chegarem antes
        de um intervalo de silêncio. O PTA não define comprimento do pedido nem
        terminador: clientes precisam esperar a resposta antes de enviar outro pedido.
        """
        first = self.request.recv(4096)
        if not first:
            return None
        data = bytearray(first)
        while len(data) <= MAX_REQUEST:
            ready, _, _ = select.select([self.request], [], [], RECEIVE_IDLE_SECONDS)
            if not ready:
                return bytes(data)
            chunk = self.request.recv(4096)
            if not chunk:
                return bytes(data)
            data.extend(chunk)
        return bytes(data)

    def reply(self, sequence: str, response: str) -> None:
        self.request.sendall(f"{sequence} {response}".encode("ascii"))

    def send_listing(self, sequence: str) -> None:
        try:
            names = available_files(self.server.files_dir)
            names_bytes = ",".join(names).encode("utf-8")
            header = f"{sequence} ARQS {len(names)} ".encode("ascii")
        except (OSError, UnicodeEncodeError):
            self.reply(sequence, "NOK")
            return
        self.request.sendall(header + names_bytes)

    def send_file(self, sequence: str, filename: str) -> None:
        # Sem subdiretórios, caminhos absolutos ou links simbólicos para fora.
        if filename in (".", "..") or "/" in filename or "\\" in filename:
            self.reply(sequence, "NOK")
            return
        path = self.server.files_dir / filename
        header_sent = False
        try:
            if not path.is_file() or path.resolve().parent != self.server.files_dir.resolve():
                self.reply(sequence, "NOK")
                return
            # Abre ANTES de enviar o cabeçalho: erros de leitura normais geram NOK.
            with path.open("rb") as source:
                size = source.seek(0, 2)
                source.seek(0)
                self.request.sendall(f"{sequence} ARQ {size} ".encode("ascii"))
                header_sent = True
                while True:
                    chunk = source.read(64 * 1024)
                    if not chunk:
                        break
                    self.request.sendall(chunk)
        except OSError:
            # Se o envio já começou, não se pode inserir NOK entre os bytes do arquivo.
            # Um fechamento prematuro indica falha de transmissão para o cliente.
            if not header_sent:
                self.reply(sequence, "NOK")
            else:
                raise

    def handle(self) -> None:
        self.request.settimeout(60)
        authenticated = False
        expected_sequence: int | None = None
        try:
            while True:
                raw = self.read_request()
                if raw is None:
                    return
                sequence, command, argument = parse_request(raw)
                # Uma requisicao com sequencia numerica consome um passo, mesmo
                # quando seu comando ou formato é inválido.
                first_field = raw.partition(b" ")[0]
                valid_number = first_field.isdigit() and len(first_field) <= 64
                if valid_number:
                    number = int(sequence)
                    if expected_sequence is not None and number != expected_sequence:
                        self.reply(sequence, "NOK")
                        if not authenticated:
                            return
                        continue
                    expected_sequence = number + 1

                if len(raw) > MAX_REQUEST or command is None or not valid_number:
                    self.reply(sequence, "NOK")
                    if not authenticated:
                        return
                    continue

                if not authenticated:
                    if command != "CUMP" or argument not in self.server.allowed_users:
                        self.reply(sequence, "NOK")
                        return
                    self.reply(sequence, "OK")
                    authenticated = True
                    continue

                if command == "LIST":
                    self.send_listing(sequence)
                elif command == "PEGA":
                    self.send_file(sequence, argument)
                elif command == "TERM":
                    self.reply(sequence, "OK")
                    return
                else:
                    self.reply(sequence, "NOK")
        except (BrokenPipeError, ConnectionError, TimeoutError, OSError):
            # Cliente desconectado, envio interrompido ou cliente inativo.
            return


class PTAServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address: tuple[str, int], users: Path, files: Path):
        self.allowed_users = load_users(users)
        if not files.is_dir():
            raise NotADirectoryError(f"Diretório de arquivos não encontrado: {files}")
        self.files_dir = files.resolve()
        super().__init__(address, PTAHandler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Servidor TCP para o protocolo PTA")
    parser.add_argument("--host", default="0.0.0.0", help="IP de escuta (padrão: 0.0.0.0)")
    parser.add_argument("--port", default=11550, type=int, help="Porta TCP (padrão: 11550)")
    parser.add_argument("--users", type=Path, default=DEFAULT_DIR / "users.txt")
    parser.add_argument("--files", type=Path, default=DEFAULT_DIR / "files")
    args = parser.parse_args()
    with PTAServer((args.host, args.port), args.users, args.files) as server:
        print(f"PTA ouvindo em {args.host}:{server.server_address[1]}", flush=True)
        print(f"Usuarios carregados: {len(server.allowed_users)}", flush=True)
        print(f"Arquivos disponiveis em: {server.files_dir}", flush=True)
        try:
            server.serve_forever(poll_interval=0.1)
        except KeyboardInterrupt:
            print("\nServidor encerrado.")


if __name__ == "__main__":
    main()
