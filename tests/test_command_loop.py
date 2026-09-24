"""Commands between a player and the process that drives it."""

from multiprocessing import get_context
from threading import Thread

from gridplayer.multiprocess.command_loop import CommandLoop

MESSAGES_PER_THREAD = 500

# big enough that a send takes a while, and two of them can meet
PAYLOAD = b"x" * 64 * 1024


def test_two_threads_can_send_at_once():
    """A player sends from its command thread and VLC's event thread both.

    A connection takes one message at a time, and two at once used to
    kill the command thread with "concurrent send_bytes() calls are not
    supported" -- most readily while a dead input flooded it with status.
    """

    loop = CommandLoop()
    receiving_end = loop._self_pipe

    received = []
    errors = []

    def receive():
        received.extend(receiving_end.recv() for _ in range(2 * MESSAGES_PER_THREAD))

    def send(name):
        try:
            for _ in range(MESSAGES_PER_THREAD):
                loop.cmd_send(name, PAYLOAD)
        except Exception as e:
            errors.append(e)

    receiver = Thread(target=receive)
    receiver.start()

    senders = [Thread(target=send, args=(name,)) for name in ("a", "b")]
    for sender in senders:
        sender.start()
    for sender in senders:
        sender.join()

    receiver.join(timeout=30)

    assert errors == []
    assert len(received) == 2 * MESSAGES_PER_THREAD
    assert all(args == (PAYLOAD,) for _, args in received)


def _send_from_child(loop):
    loop.cmd_send("hello", "from the child")


def test_it_can_still_be_handed_to_a_child_process():
    """A player process is pickled whole into its child; a lock cannot be."""

    loop = CommandLoop()

    child = get_context("spawn").Process(target=_send_from_child, args=(loop,))
    child.start()
    child.join(timeout=60)

    assert child.exitcode == 0
    assert loop._self_pipe.poll(10)
    assert loop._self_pipe.recv() == ("hello", ("from the child",))
