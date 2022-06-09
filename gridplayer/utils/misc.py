import re
from multiprocessing.process import active_children


def force_terminate_children():
    for p in active_children():
        p.terminate()


def is_url(s) -> bool:
    return bool(re.match("^[a-z]+://", s))
