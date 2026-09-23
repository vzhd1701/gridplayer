"""Which way out of the machine a video's sound is sent.

A device is remembered by two names because neither is enough on its own.
The id is what the output module in force calls it, and it means nothing to
any other module: one jack is ``{7DA058ED-...}`` to directsound and
``{0.0.0.00000000}.{7da058ed-...}`` to mmdevice. The description is what
both of them call it, word for word, so it is what carries a playlist to a
machine whose ids belong to somebody else.

An id that is no longer there is the case worth guarding against. libVLC
takes one without complaint, reports it back afterwards as the device in
force, and then plays the video in silence: the time advances, nothing is
muted, a track is selected, and no sound is made anywhere. Nothing about
the player says anything is wrong. So an id is never passed on without
being found in the list first.
"""

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict

# what libVLC takes for "whichever way out the machine is using", which is
# not the same as asking for nothing: asking for nothing leaves a player
# wherever it already was
SYSTEM_DEFAULT_DEVICE_ID = ""


class AudioDevice(BaseModel):
    """A way out of the machine, as the output module hands it over.

    A value, not a record: two of the same device are the same device.
    """

    model_config = ConfigDict(frozen=True)

    id: str

    # what a person reading a menu would call it, and what the choice is
    # found again by where the ids have changed; see the module docstring
    name: str = ""


def resolve_device_id(
    device: AudioDevice | None, available: Iterable[AudioDevice]
) -> str | None:
    """The id to ask for, or nothing where there is nothing to ask for.

    Nothing is what a video that never chose gets, and it is what a choice
    that cannot be honoured falls back to as well. The way out the machine
    is already using is the one that can be relied on to make a sound, and
    a video playing out of the wrong speaker beats one playing silently.
    """

    if device is None:
        return None

    available = tuple(available)

    if any(offered.id == device.id for offered in available):
        return device.id

    return _found_by_name(device, available)


def _found_by_name(device: AudioDevice, available: tuple[AudioDevice, ...]):
    """The same device under an id it did not have the last time.

    Which is what changing the output module does to every id at once,
    and what opening a playlist on another machine does.
    """

    if not device.name:
        return None

    return next(
        (offered.id for offered in available if offered.name == device.name), None
    )
