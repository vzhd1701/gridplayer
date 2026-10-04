"""A player process that dies must not leave its videos waiting forever.

An access violation in VLC takes the whole process down at once: nothing runs
on the way out, and the pipes to it do not break, because both of their ends
are held in the player as well. The process exiting is the only sign there is,
and the manager is the one watching for it.
"""

import os
import time
from multiprocessing import Process, Value
from threading import Event
from unittest.mock import MagicMock

import pytest

from gridplayer.multiprocess.process_manager import (
    ProcessManager,
    describe_exit_code,
)
from gridplayer.vlc_player.video_driver_base_threaded import (
    VLCVideoDriverThreaded,
)
from gridplayer.widgets.video_frame_vlc_hw import VideoDriverVLCHW

CRASH_EXIT_CODE = 7

WAIT_S = 30


class _Instance:
    """A process that only exits, and what the manager reads off it."""

    def __init__(self, exit_code, is_dead=False):
        self.id = f"instance-{exit_code}-{time.monotonic_ns()}"
        self.options = ()
        self.process = Process(target=os._exit, args=(exit_code,), daemon=True)
        self.player_count = Value("i", 0)
        self.is_dead = Value("i", int(is_dead))

    def request_new_player(self, init_data, pipe):
        self.player_count.value += 1
        return f"player-{self.player_count.value}"

    def cleanup_player_shared_data(self, player_id): ...


class _Manager(ProcessManager):
    def __init__(self, instances, **kwargs):
        self._next_instances = list(instances)

        super().__init__(**kwargs)

    def create_instance(self, options):
        return self._next_instances.pop(0)


@pytest.fixture
def make_manager(mocker):
    # The real one reaches for a QSettings that other tests in the suite have
    # already taken down with their QApplication.
    mocker.patch(
        "gridplayer.multiprocess.process_manager.Settings",
        return_value=MagicMock(get=MagicMock(return_value=4)),
    )

    managers = []

    def _make(*instances):
        manager = _Manager(instances, instance_class=MagicMock())
        managers.append(manager)
        return manager

    yield _make

    for manager in managers:
        manager.cleanup()


class _Crashes:
    def __init__(self):
        self.codes = []
        self.reported = Event()

    def __call__(self, exit_code):
        self.codes.append(exit_code)
        self.reported.set()


def _wait_for_exit(manager, instance):
    end = time.monotonic() + WAIT_S
    while time.monotonic() < end:
        with manager.instances_lock:
            if (
                instance.id not in manager.instances
                and instance.id not in manager._exiting_instances
            ):
                return
        time.sleep(0.05)

    raise AssertionError("the manager never saw the process exit")


def test_players_hear_of_their_process_dying(make_manager):
    instance = _Instance(CRASH_EXIT_CODE)
    manager = make_manager(instance)
    crashes = _Crashes()

    manager.init_player({}, None, (), on_crash=crashes)

    assert crashes.reported.wait(WAIT_S)
    assert crashes.codes == [CRASH_EXIT_CODE]


def test_every_player_of_the_process_hears_of_it(make_manager):
    instance = _Instance(CRASH_EXIT_CODE)
    manager = make_manager(instance)
    first, second = _Crashes(), _Crashes()

    manager.init_player({}, None, (), on_crash=first)
    manager.init_player({}, None, (), on_crash=second)

    assert first.reported.wait(WAIT_S)
    assert second.reported.wait(WAIT_S)


def test_a_dead_process_is_not_handed_new_players(make_manager):
    dead, fresh = _Instance(CRASH_EXIT_CODE), _Instance(0)
    manager = make_manager(dead, fresh)
    crashes = _Crashes()

    manager.init_player({}, None, (), on_crash=crashes)
    assert crashes.reported.wait(WAIT_S)
    _wait_for_exit(manager, dead)

    assert manager.get_instance(()) is fresh


def test_a_process_whose_players_were_all_released_exits_quietly(make_manager):
    instance = _Instance(0, is_dead=True)
    manager = make_manager(instance)
    crashes = _Crashes()

    manager.init_player({}, None, (), on_crash=crashes)
    _wait_for_exit(manager, instance)

    assert crashes.codes == []


def test_a_process_that_said_it_was_done_exits_quietly(make_manager):
    instance = _Instance(0)
    manager = make_manager(instance)
    crashes = _Crashes()

    manager.init_player({}, None, (), on_crash=crashes)
    manager.cleanup_instance(instance.id)
    _wait_for_exit(manager, instance)

    assert crashes.codes == []


def test_a_released_player_is_not_told(make_manager):
    instance = _Instance(CRASH_EXIT_CODE)
    manager = make_manager(instance)
    crashes = _Crashes()

    player = manager.init_player({}, None, (), on_crash=crashes)
    player.cleanup()
    _wait_for_exit(manager, instance)

    assert crashes.codes == []


def test_a_failing_listener_does_not_stop_the_rest(make_manager):
    instance = _Instance(CRASH_EXIT_CODE)
    manager = make_manager(instance)
    crashes = _Crashes()

    manager.init_player({}, None, (), on_crash=MagicMock(side_effect=RuntimeError))
    manager.init_player({}, None, (), on_crash=crashes)

    assert crashes.reported.wait(WAIT_S)


def test_processes_taken_down_after_a_crash_elsewhere_are_not_crashes(
    make_manager, mocker
):
    """The player is on its way down with an error dialog by then."""
    instance = _Instance(0)
    instance.process = Process(target=time.sleep, args=(WAIT_S,), daemon=True)
    manager = make_manager(instance)
    crashes = _Crashes()
    manager.init_player({}, None, (), on_crash=crashes)
    mocker.patch(
        "gridplayer.multiprocess.process_manager.force_terminate_children_all",
        side_effect=instance.process.terminate,
    )

    manager.crash_all("Traceback")
    _wait_for_exit(manager, instance)

    assert crashes.codes == []


@pytest.mark.parametrize(
    ("exit_code", "text"),
    [
        (None, "unknown"),
        (0, "0"),
        (1, "1"),
        (-9, "signal 9"),
        (0xC0000005, "0xc0000005"),
    ],
)
def test_exit_codes_read_as_the_platform_writes_them(exit_code, text):
    assert describe_exit_code(exit_code) == text


class _Driver(VLCVideoDriverThreaded):
    def snapshot(self): ...

    def screenshot(self): ...


@pytest.fixture
def driver():
    driver = _Driver()
    yield driver
    driver.cmd_loop_terminate()


def test_a_driver_reports_its_process_dying_as_a_video_error(driver):
    errors = []
    driver.error.connect(errors.append)

    driver.process_crashed(0xC0000005)

    assert errors == ["Video process crashed"]


def test_a_driver_already_closing_keeps_quiet(driver):
    errors = []
    driver.error.connect(errors.append)
    driver.cleanup_start()

    driver.process_crashed(0xC0000005)

    assert errors == []


def test_closing_a_hardware_driver_does_not_wait_on_a_dead_player(mocker):
    """It would sit out the whole timeout for a release that never comes."""
    manager = MagicMock()
    driver = VideoDriverVLCHW(win_id=0, process_manager=manager, vlc_options=())
    on_crash = manager.init_player.call_args.kwargs["on_crash"]

    on_crash(0xC0000005)

    start = time.monotonic()
    driver.cleanup()
    assert time.monotonic() - start < 1
