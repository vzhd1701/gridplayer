"""Commands of a VideoBlock that only make sense for some videos, left
undone, quietly, for the rest."""


class VideoBlockPart:
    """A part of a VideoBlock taken out into an object of its own, its
    commands reached as "part.command" (see ActiveBlockManager.cmd_active).

    The guards below ask the block it belongs to.
    """

    def __init__(self, block):
        self._block = block


def _block_of(obj):
    return obj._block if isinstance(obj, VideoBlockPart) else obj


def only_initialized(func):
    def wrapper(*args, **kwargs):
        block = _block_of(args[0])
        if not block.is_video_initialized:
            return None
        return func(*args, **kwargs)

    return wrapper


def only_seekable(func):
    def wrapper(*args, **kwargs):
        block = _block_of(args[0])
        if block.is_live:
            return None
        return func(*args, **kwargs)

    return wrapper


def only_with_video_tacks(func):
    def wrapper(*args, **kwargs):
        block = _block_of(args[0])
        if not block.video_tracks:
            return None
        return func(*args, **kwargs)

    return wrapper


def only_live(func):
    def wrapper(*args, **kwargs):
        block = _block_of(args[0])
        if not block.is_live:
            return None
        return func(*args, **kwargs)

    return wrapper


def only_local_file(func):
    def wrapper(*args, **kwargs):
        block = _block_of(args[0])
        if not block.is_local_file:
            return None
        return func(*args, **kwargs)

    return wrapper


def only_navigable(func):
    """Only for a video with others to go on to: the files of its folder, or
    the items of its list, links among them."""

    def wrapper(*args, **kwargs):
        block = _block_of(args[0])
        if not block.is_navigable:
            return None
        return func(*args, **kwargs)

    return wrapper


def only_streamable(func):
    def wrapper(*args, **kwargs):
        block = _block_of(args[0])
        if not block.streams:
            return None
        return func(*args, **kwargs)

    return wrapper
