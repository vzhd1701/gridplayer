"""A decoder process must never outlive the player that spawned it.

Nothing of ours gets to run when the player dies of an access violation, so
the guarantee cannot come from a cleanup path. It comes from two things that
hold without us: the kernel, which kills the children outright, and a watchdog
in each child, for the moments the kernel cannot cover.
"""

import os
import signal
import subprocess
import sys
import time
from unittest.mock import MagicMock

import pytest

from gridplayer.multiprocess.instance_process import (
    ORPHANED_EXIT_CODE,
    InstanceProcess,
)
from gridplayer.multiprocess.job_object import create_kill_on_close_job
from gridplayer.multiprocess.process_manager import ProcessManager
from gridplayer.params import env

_MODULE = "gridplayer.multiprocess.instance_process"


class _StubInstance(InstanceProcess):
    def init_instance(self): ...

    def cleanup_instance(self): ...

    def new_player(self, player_id, init_data, pipe): ...

    def init_player_shared_data(self, player_id): ...

    def release_player_shared_data(self, player_id): ...


class _RecordingInstance:
    def __init__(self, events):
        self._events = events

        self.id = "recording-instance"
        self.process = MagicMock()
        self.process.pid = 4321
        self.process.start.side_effect = lambda: self._events.append("start")


class _RecordingManager(ProcessManager):
    def __init__(self, events, **kwargs):
        self._events = events

        super().__init__(**kwargs)

    def create_instance(self, options):
        return _RecordingInstance(self._events)


@pytest.fixture
def instance():
    return _StubInstance(
        players_per_instance=1, pm_callback_pipe=MagicMock(), options=()
    )


@pytest.fixture
def no_exit(mocker):
    exit_codes = []
    mocker.patch.object(os, "_exit", side_effect=exit_codes.append)

    return exit_codes


@pytest.fixture
def manager(mocker):
    # The real one reaches for a QSettings that other tests in the suite have
    # already taken down with their QApplication.
    mocker.patch(
        "gridplayer.multiprocess.process_manager.Settings",
        return_value=MagicMock(get=MagicMock(return_value=4)),
    )

    events = []
    recording_manager = _RecordingManager(events, instance_class=MagicMock())
    recording_manager._job = MagicMock()

    yield recording_manager, events

    # Nothing real was started, and cleanup would otherwise sit out its
    # five second wait for an instance that does not exist.
    recording_manager.instances.clear()
    recording_manager.cleanup()


def test_the_watchdog_waits_for_the_parent(instance, no_exit, mocker):
    parent = mocker.patch(f"{_MODULE}.parent_process", return_value=MagicMock())

    instance._watch_parent()

    parent.return_value.join.assert_called_once_with()


def test_the_watchdog_terminates_the_child_when_the_parent_is_gone(
    instance, no_exit, mocker
):
    mocker.patch(f"{_MODULE}.parent_process", return_value=MagicMock())

    instance._watch_parent()

    assert no_exit == [ORPHANED_EXIT_CODE]


def test_the_watchdog_stands_down_outside_a_child_process(instance, no_exit, mocker):
    """parent_process() is None in the player itself."""
    mocker.patch(f"{_MODULE}.parent_process", return_value=None)

    instance._watch_parent()

    assert no_exit == []


def test_the_child_arms_both_guards(instance, mocker):
    armed = mocker.patch(f"{_MODULE}.arm_parent_death_signal")
    thread = mocker.patch(f"{_MODULE}.Thread")

    instance._guard_against_orphaning()

    armed.assert_called_once()
    assert thread.call_args.kwargs["target"] == instance._watch_parent
    assert thread.call_args.kwargs["daemon"] is True
    thread.return_value.start.assert_called_once()


def test_the_watchdog_runs_in_the_background(instance, no_exit, mocker):
    """It has to do its waiting off the command loop's thread."""
    mocker.patch(f"{_MODULE}.arm_parent_death_signal")
    mocker.patch(f"{_MODULE}.parent_process", return_value=MagicMock())

    instance._guard_against_orphaning()

    for _ in range(50):
        if no_exit:
            break
        time.sleep(0.1)

    assert no_exit == [ORPHANED_EXIT_CODE]


def test_the_child_guards_itself_before_anything_that_can_block(instance, mocker):
    order = []
    mocker.patch.object(
        instance, "_guard_against_orphaning", side_effect=lambda: order.append("guard")
    )
    mocker.patch.object(
        instance, "process_body", side_effect=lambda: order.append("body")
    )

    instance.run()

    assert order == ["guard", "body"]


def test_started_process_is_put_under_the_job(manager):
    recording_manager, _events = manager

    recording_manager.get_instance(options=())

    recording_manager._job.assign.assert_called_once_with(4321)


@pytest.mark.skipif(not env.IS_WINDOWS, reason="job objects are Windows only")
def test_job_terminates_its_processes_when_it_is_dropped():
    job = create_kill_on_close_job()

    assert job.is_active

    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])

    try:
        job.assign(process.pid)

        job.close()

        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pytest.fail("the process outlived the job it belonged to")
    finally:
        if process.poll() is None:
            process.kill()


def test_job_is_a_noop_where_there_are_none(mocker):
    mocker.patch.object(env, "IS_WINDOWS", False)

    job = create_kill_on_close_job()

    assert not job.is_active


@pytest.mark.skipif(not env.IS_LINUX, reason="PR_SET_PDEATHSIG is Linux only")
def test_parent_death_signal_is_armed():
    """Read the signal back out of the kernel, from a process we can spare.

    Arming it in the test runner would leave pytest itself set up to be killed.
    """
    armed = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-c",
            "import ctypes;"
            "from gridplayer.multiprocess.parent_death_signal import"
            " arm_parent_death_signal;"
            "arm_parent_death_signal();"
            "armed = ctypes.c_int();"
            "ctypes.CDLL('libc.so.6').prctl(2, ctypes.byref(armed));"
            "print(armed.value)",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert armed.stdout.strip() == str(int(signal.SIGKILL)), armed.stderr


def test_parent_death_signal_is_a_noop_where_there_is_none(mocker):
    mocker.patch.object(env, "IS_LINUX", False)
    libc = mocker.patch("ctypes.CDLL")

    from gridplayer.multiprocess.parent_death_signal import arm_parent_death_signal

    arm_parent_death_signal()

    libc.assert_not_called()
