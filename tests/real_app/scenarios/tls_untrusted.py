"""An HLS stream over HTTPS with a certificate nobody vouches for (#239).

Checked, as by default, it isn't added, and the box says why in a few words.
With "Verify TLS certificates" off it plays.

The certificate is made for the run by openssl: without it, nothing is tried.
"""

import shutil
import ssl
import subprocess
import threading
from functools import partial

from PyQt6.QtWidgets import QLabel

from tests.real_app.driver import LocalHTTPServer, QuietHandler


def scenario(d):
    if shutil.which("openssl") is None:
        d._step("no openssl here to make a certificate with: nothing tried")
        return

    url = f"{_serve_https(d, d.media.hls.parent)}/{d.media.hls.name}/master.m3u8"

    said = []
    d.through_modal(
        lambda: d.open(url),
        "untrusted",
        lambda box: said.extend(w.text() for w in box.findChildren(QLabel)),
    )
    d.check("checked, it isn't added", not d.cells, len(d.cells))
    d.check(
        "and the box says why in a few words",
        any(text.startswith("certificate not trusted") for text in said),
        said,
    )

    d.change_setting("network/verify_tls", False)
    d.open(url)
    b = d.wait_for_cell(url)
    start = b.time
    d.wait_until(lambda: b.time - start >= 1000, "unchecked, it plays")


def _serve_https(d, directory) -> str:
    cert, key = d.out / "cert.pem", d.out / "key.pem"
    subprocess.run(
        [
            *("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes"),
            *("-keyout", str(key), "-out", str(cert), "-days", "2"),
            *("-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1"),
        ],
        check=True,
        capture_output=True,
    )

    server = LocalHTTPServer(
        ("127.0.0.1", 0), partial(QuietHandler, directory=str(directory))
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    d._servers.append(server)

    return f"https://127.0.0.1:{server.server_address[1]}"
