from threading import Lock

from gridplayer.models.stream import Stream
from gridplayer.player.managers.base import ManagerBase
from gridplayer.utils.stream_proxy.stream_proxy import StreamProxy


class StreamProxyManager(ManagerBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._stream_proxy_lock = Lock()
        self._stream_proxy = None

    @property
    def stream_proxy(self):
        with self._stream_proxy_lock:
            if self._stream_proxy is None:
                self._stream_proxy = StreamProxy(parent=self)
                self._stream_proxy.start()

        return self._stream_proxy

    @property
    def commands(self):
        return {
            "add_stream": self.cmd_add_stream,
        }

    def cmd_add_stream(self, stream: Stream) -> str:
        return self.stream_proxy.add_stream(stream)

    def cleanup(self):
        if self._stream_proxy is not None:
            self._stream_proxy.cleanup()
            self._stream_proxy = None
