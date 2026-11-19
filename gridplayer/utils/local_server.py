import socketserver
from http.server import ThreadingHTTPServer


class LocalHTTPServer(ThreadingHTTPServer):
    """An HTTP server on this machine, started without looking up its host's
    name, as HTTPServer does: on a Mac whose lookup goes unanswered that took
    35 s (GitHub's, 2026-11-19), the first stream waiting on it."""

    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]
