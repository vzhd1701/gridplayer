"""Commands of a VideoBlock that only make sense for some videos, left
undone, quietly, for the rest."""


def only_initialized(func):
    def wrapper(*args, **kwargs):
        self = args[0]
        if not self.is_video_initialized:
            return None
        return func(*args, **kwargs)

    return wrapper


def only_seekable(func):
    def wrapper(*args, **kwargs):
        self = args[0]
        if self.is_live:
            return None
        return func(*args, **kwargs)

    return wrapper


def only_with_video_tacks(func):
    def wrapper(*args, **kwargs):
        self = args[0]
        if not self.video_tracks:
            return None
        return func(*args, **kwargs)

    return wrapper


def only_live(func):
    def wrapper(*args, **kwargs):
        self = args[0]
        if not self.is_live:
            return None
        return func(*args, **kwargs)

    return wrapper


def only_local_file(func):
    def wrapper(*args, **kwargs):
        self = args[0]
        if not self.is_local_file:
            return None
        return func(*args, **kwargs)

    return wrapper


def only_navigable(func):
    """Only for a video with others to go on to: the files of its folder, or
    the items of its list, links among them."""

    def wrapper(*args, **kwargs):
        self = args[0]
        if not self.is_navigable:
            return None
        return func(*args, **kwargs)

    return wrapper


def only_streamable(func):
    def wrapper(*args, **kwargs):
        self = args[0]
        if not self.streams:
            return None
        return func(*args, **kwargs)

    return wrapper
