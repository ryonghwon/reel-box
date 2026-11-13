"""HTTPS CONNECT proxy: resolve once, reject non-public IPs, connect to the checked IP.
No credentials, request bodies or signed media URLs are logged.
"""

import ipaddress
import select
import socket
import socketserver


class Proxy(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(30)
        try:
            line = self.rfile.readline(8192).decode("ascii").strip().split()
            if len(line) != 3:
                return
            method, authority, _ = line
            for _ in range(80):
                if self.rfile.readline(8192) in (b"\r\n", b"\n", b""):
                    break
            else:
                return
            if method != "CONNECT":
                self.wfile.write(b"HTTP/1.1 403 HTTPS required\r\n\r\n")
                return
            host, port = authority.rsplit(":", 1)
            if port != "443":
                raise ValueError("port denied")
            addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            if not addresses or any(
                not ipaddress.ip_address(x[4][0]).is_global for x in addresses
            ):
                raise ValueError("private destination")
            family, kind, proto, _, addr = addresses[0]
            with socket.socket(family, kind, proto) as upstream:
                upstream.settimeout(20)
                upstream.connect(addr)
                self.wfile.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                self.wfile.flush()
                pair = [self.connection, upstream]
                while True:
                    readable, _, _ = select.select(pair, [], [], 60)
                    if not readable:
                        break
                    for src in readable:
                        data = src.recv(65536)
                        if not data:
                            return
                        (
                            upstream if src is self.connection else self.connection
                        ).sendall(data)
        except (OSError, ValueError, UnicodeError):
            try:
                self.wfile.write(b"HTTP/1.1 502 Connection rejected\r\n\r\n")
            except OSError:
                pass


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    with Server(("0.0.0.0", 8899), Proxy) as server:
        server.serve_forever()
