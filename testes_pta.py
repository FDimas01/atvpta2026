#!/usr/bin/env python3
"""Testes de integração do servidor PTA, sem tocar nos arquivos do professor.
Execute na raiz do fork: python testes_pta.py
"""

import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SERVER = ROOT / "pta-server" / "pta-server.py"


class TesteIntegracaoPTA(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="pta-test-")
        folder = Path(cls.temporary.name)
        files = folder / "files"
        files.mkdir()
        (folder / "users.txt").write_text("user1\nuser2\nuser3\n", encoding="ascii")
        cls.contents = {
            "a.txt": b"arquivo simples\n",
            "dados.bin": bytes(range(256)) * 20,
            "vazio.txt": b"",
        }
        for name, content in cls.contents.items():
            (files / name).write_bytes(content)
        # Porta aleatória livre; o teste somente usa 127.0.0.1.
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            cls.port = probe.getsockname()[1]
        cls.proc = subprocess.Popen(
            [sys.executable, str(SERVER), "--host", "127.0.0.1",
             "--port", str(cls.port), "--users", str(folder / "users.txt"),
             "--files", str(files)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        for _ in range(100):
            if cls.proc.poll() is not None:
                error = cls.proc.stderr.read().decode(errors="replace")
                raise RuntimeError(f"O servidor terminou antes dos testes: {error}")
            try:
                with socket.create_connection(("127.0.0.1", cls.port), timeout=0.05):
                    break
            except OSError:
                time.sleep(0.03)
        else:
            raise RuntimeError("Tempo esgotado aguardando servidor local")

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        try:
            cls.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            cls.proc.kill()
            cls.proc.wait()
        cls.proc.stderr.close()
        cls.temporary.cleanup()

    def connect(self):
        conn = socket.create_connection(("127.0.0.1", self.port), timeout=3)
        conn.settimeout(3)
        self.addCleanup(conn.close)
        return conn

    def exchange(self, conn, request, reply):
        conn.sendall(request.encode("ascii"))
        received = conn.recv(4096)
        self.assertEqual(received, reply.encode("ascii"))

    def auth(self, conn, start=0):
        self.exchange(conn, f"{start} CUMP user1", f"{start} OK")

    @staticmethod
    def read_exact(sock, count):
        chunks = []
        remaining = count
        while remaining:
            block = sock.recv(remaining)
            if not block:
                raise EOFError(f"Faltam {remaining} bytes")
            chunks.append(block)
            remaining -= len(block)
        return b"".join(chunks)

    def test_01_comando_antes_cump_fecha(self):
        s = self.connect()
        self.exchange(s, "7 LIST", "7 NOK")
        self.assertEqual(s.recv(1), b"")

    def test_02_usuario_inexistente_fecha(self):
        s = self.connect()
        self.exchange(s, "0 CUMP laser1212", "0 NOK")
        self.assertEqual(s.recv(1), b"")

    def test_03_usuario_case_sensitive(self):
        s = self.connect()
        self.exchange(s, "0 CUMP User1", "0 NOK")
        self.assertEqual(s.recv(1), b"")

    def test_04_listagem_e_sequencia(self):
        s = self.connect()
        self.auth(s, 72)
        self.exchange(s, "73 LIST", "73 ARQS 3 a.txt,dados.bin,vazio.txt")
        self.exchange(s, "74 TERM", "74 OK")
        self.assertEqual(s.recv(1), b"")

    def test_05_pega_arquivo_binario_por_tamanho(self):
        s = self.connect()
        self.auth(s)
        s.sendall(b"1 PEGA dados.bin")
        expected = self.contents["dados.bin"]
        # Leitura deliberadamente por tamanho para nao assumir fronteiras TCP.
        self.assertEqual(self.read_exact(s, len(b"1 ARQ 5120 ") + len(expected)),
                         b"1 ARQ 5120 " + expected)
        self.exchange(s, "2 TERM", "2 OK")

    def test_06_arquivo_vazio(self):
        s = self.connect()
        self.auth(s)
        self.exchange(s, "1 PEGA vazio.txt", "1 ARQ 0 ")
        self.exchange(s, "2 TERM", "2 OK")

    def test_07_arquivo_inexistente_e_depois_valido(self):
        s = self.connect()
        self.auth(s)
        self.exchange(s, "1 PEGA inexistente.txt", "1 NOK")
        self.exchange(s, "2 LIST", "2 ARQS 3 a.txt,dados.bin,vazio.txt")

    def test_08_tentativa_de_traversal(self):
        s = self.connect()
        self.auth(s)
        self.exchange(s, "1 PEGA ../users.txt", "1 NOK")
        self.exchange(s, "2 LIST", "2 ARQS 3 a.txt,dados.bin,vazio.txt")

    def test_09_comando_desconhecido_sem_fechar(self):
        s = self.connect()
        self.auth(s)
        self.exchange(s, "1 TRAP", "1 NOK")
        self.exchange(s, "2 LIST", "2 ARQS 3 a.txt,dados.bin,vazio.txt")

    def test_10_formato_invalido_sem_fechar(self):
        s = self.connect()
        self.auth(s)
        self.exchange(s, "1 LIST argumento", "1 NOK")
        self.exchange(s, "2 LIST", "2 ARQS 3 a.txt,dados.bin,vazio.txt")

    def test_11_sequencia_incorreta(self):
        s = self.connect()
        self.auth(s, 4)
        self.exchange(s, "6 LIST", "6 NOK")
        self.exchange(s, "5 LIST", "5 ARQS 3 a.txt,dados.bin,vazio.txt")

    def test_12_cump_repetido(self):
        s = self.connect()
        self.auth(s)
        self.exchange(s, "1 CUMP user2", "1 NOK")
        self.exchange(s, "2 TERM", "2 OK")

    def test_13_conexoes_independentes(self):
        a, b = self.connect(), self.connect()
        self.auth(a, 100)
        self.auth(b, 500)
        self.exchange(a, "101 LIST", "101 ARQS 3 a.txt,dados.bin,vazio.txt")
        self.exchange(b, "501 TERM", "501 OK")
        self.exchange(a, "102 TERM", "102 OK")

    def test_14_comando_fragmentado(self):
        s = self.connect()
        s.sendall(b"9 CU")
        s.sendall(b"MP user1")
        self.assertEqual(s.recv(4096), b"9 OK")
        self.exchange(s, "10 TERM", "10 OK")


if __name__ == "__main__":
    unittest.main(verbosity=2)
