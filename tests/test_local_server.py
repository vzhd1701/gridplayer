import socket
from http.server import BaseHTTPRequestHandler

from gridplayer.utils.local_server import LocalHTTPServer
from gridplayer.utils.stream_proxy.server import StreamProxyServer


def test_a_local_server_starts_without_looking_its_host_up(mocker):
    # on a Mac whose lookup goes unanswered, it took 35 s
    lookup = mocker.patch.object(socket, "getfqdn")

    server = LocalHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    try:
        assert server.server_name == "127.0.0.1"
        assert server.server_port == server.server_address[1] > 0
    finally:
        server.server_close()

    lookup.assert_not_called()


def test_the_stream_proxy_is_one():
    assert issubclass(StreamProxyServer, LocalHTTPServer)
