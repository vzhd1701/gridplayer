import os
import re
import signal
from multiprocessing.process import active_children

from gridplayer.params import env


def force_terminate_resource_tracker():
    # windows doesn't have resource tracker
    if env.IS_WINDOWS:
        return

    # kill resource_tracker first so it won't complain about leaked resources
    from multiprocessing.resource_tracker import _resource_tracker  # noqa: WPS450

    if _resource_tracker._pid is not None:  # noqa: WPS437
        os.kill(_resource_tracker._pid, signal.SIGKILL)  # noqa: WPS437


def force_terminate_children():
    for p in active_children():
        p.terminate()


def force_terminate_children_all():
    force_terminate_resource_tracker()
    force_terminate_children()


def force_terminate(exit_code: int = 0):
    if not env.IS_WINDOWS:
        force_terminate_children_all()

    os._exit(exit_code)  # noqa: WPS437


def is_url(s) -> bool:
    return bool(re.match("^[a-z]+://", s))
