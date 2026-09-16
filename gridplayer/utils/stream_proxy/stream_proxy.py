import logging

from PyQt5.QtCore import QThread

from gridplayer.models.stream import Stream
from gridplayer.utils.stream_proxy.server import ProxyRequestHandler, StreamProxyServer
from gridplayer.utils.url_resolve.url_resolve import resolve_url


class StreamProxy(QThread):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._log = logging.getLogger(self.__class__.__name__)

        # the proxy resolves sources again by itself, on the thread that ran
        # into the expired URL; nothing on the UI side is waiting for it
        self.server = StreamProxyServer(
            ("127.0.0.1", 0), ProxyRequestHandler, resolve_source=resolve_url
        )

    def run(self) -> None:
        self._log.debug("Starting stream proxy server")

        self.server.serve_forever()

    def add_stream(self, stream: Stream) -> str:
        return self.server.add_stream(stream)

    def cleanup(self) -> None:
        self._log.debug("Shutting down stream proxy server")

        self.server.shutdown()
        self.wait()
