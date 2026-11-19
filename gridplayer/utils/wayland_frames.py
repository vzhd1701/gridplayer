"""Whether the Wayland compositor draws window frames, asked before Qt starts.

Where it does (KDE, sway and most others), Qt's windows look as they do on
X11. Where it doesn't (GNOME), Qt draws the frame itself: Qt 6's adwaita
decoration, in GNOME's colours and light or dark as GNOME is, not as the app's
theme is (Qt 5's was a thick flat band with no shadow). A compositor that
draws them offers xdg-decoration, which Qt asks for.

Asked of the compositor itself, a connection of its own listing what it
offers, with libwayland-client through ctypes: Qt can't be asked, as which
platform to start it on is what this decides.
"""

import ctypes
import functools
import logging
import threading

_DECORATION_MANAGER = b"zxdg_decoration_manager_v1"

# A compositor answers in a millisecond or two. One that doesn't is taken to
# draw none, and the app goes on, on X11, the asking left behind.
_ANSWER_WAIT_S = 0.5

# wl_display's request for its registry
_GET_REGISTRY = 1

_Global = ctypes.CFUNCTYPE(
    None,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_uint32,
    ctypes.c_char_p,
    ctypes.c_uint32,
)
_GlobalRemove = ctypes.CFUNCTYPE(
    None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32
)


class _RegistryListener(ctypes.Structure):
    _fields_ = [("global_", _Global), ("global_remove", _GlobalRemove)]


@functools.cache
def compositor_draws_frames() -> bool:
    """False if it doesn't, or if it can't be told: this runs before the app
    does, and nothing here may keep it from starting."""

    answer = []

    def ask():
        try:
            answer.append(_wayland_globals())
        except Exception:
            logging.getLogger(__name__).exception("Can't ask the Wayland compositor")
            answer.append(None)

    asking = threading.Thread(target=ask, name="wayland frames", daemon=True)
    asking.start()
    asking.join(_ANSWER_WAIT_S)

    if not answer:
        logging.getLogger(__name__).warning("The Wayland compositor didn't answer")
        return False

    offered = answer[0]

    return offered is not None and _DECORATION_MANAGER in offered


def _wayland_globals() -> set[bytes] | None:
    """What the compositor offers, by interface name. None if there's no
    Wayland display to connect to."""

    lib = ctypes.CDLL("libwayland-client.so.0")

    lib.wl_display_connect.restype = ctypes.c_void_p
    lib.wl_display_connect.argtypes = [ctypes.c_char_p]
    lib.wl_display_disconnect.argtypes = [ctypes.c_void_p]
    lib.wl_display_roundtrip.argtypes = [ctypes.c_void_p]
    lib.wl_proxy_add_listener.argtypes = [ctypes.c_void_p] * 3
    lib.wl_proxy_destroy.argtypes = [ctypes.c_void_p]

    display = lib.wl_display_connect(None)
    if not display:
        return None

    offered = set()

    def on_global(_data, _registry, _name, interface, _version):
        offered.add(interface)

    # kept alive for as long as libwayland may call them
    listener = _RegistryListener(_Global(on_global), _GlobalRemove(lambda *_: None))

    try:
        registry = _get_registry(lib, display)
        if not registry:
            return None

        lib.wl_proxy_add_listener(registry, ctypes.byref(listener), None)
        lib.wl_display_roundtrip(display)
        lib.wl_proxy_destroy(registry)
    finally:
        lib.wl_display_disconnect(display)

    return offered


def _get_registry(lib, display) -> int | None:
    """wl_display_get_registry, which is inline in libwayland's header: what
    it compiles to, with no new id's argument filled in."""

    interface = ctypes.addressof(ctypes.c_char.in_dll(lib, "wl_registry_interface"))

    # libwayland 1.20 and up
    if hasattr(lib, "wl_proxy_marshal_flags"):
        lib.wl_proxy_get_version.restype = ctypes.c_uint32
        lib.wl_proxy_get_version.argtypes = [ctypes.c_void_p]

        marshal = lib.wl_proxy_marshal_flags
        marshal.restype = ctypes.c_void_p
        marshal.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
        ]

        version = lib.wl_proxy_get_version(display)

        return marshal(display, _GET_REGISTRY, interface, version, 0, None)

    marshal = lib.wl_proxy_marshal_constructor
    marshal.restype = ctypes.c_void_p
    marshal.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]

    return marshal(display, _GET_REGISTRY, interface, None)
