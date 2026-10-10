"""What went wrong, said in a dialog before the player quits; during a
drag, once the drag is called off: the system holds the mouse for one, and
a dialog shown from inside it could not be clicked."""

import pytest

from gridplayer.utils import excepthook as hook_module


@pytest.fixture
def told(mocker):
    told = []

    dialog = mocker.patch.object(hook_module, "ExceptionDialog")
    dialog.side_effect = lambda text: told.append(text) or dialog.return_value
    mocker.patch.object(hook_module, "force_terminate")
    mocker.patch.object(hook_module.QApplication, "topLevelWidgets", return_value=[])
    mocker.patch.object(hook_module, "_untold", None)

    return told


def _broken(text):
    raise RuntimeError(text)


def _raise(text):
    try:
        _broken(text)
    except RuntimeError as e:
        return type(e), e, e.__traceback__


def test_said_at_once(told):
    hook_module.excepthook(*_raise("broken"))

    assert len(told) == 1
    assert "broken" in told[0]
    hook_module.force_terminate.assert_called_once()


def test_during_a_drag_the_drag_is_called_off(told, mocker):
    cancel = mocker.patch.object(hook_module.QDrag, "cancel")

    with hook_module.dragging():
        hook_module.excepthook(*_raise("broken"))

        cancel.assert_called_once()
        assert told == []
        hook_module.force_terminate.assert_not_called()

    assert len(told) == 1
    assert "broken" in told[0]
    hook_module.force_terminate.assert_called_once()


def test_the_first_said_of_several(told, mocker):
    mocker.patch.object(hook_module.QDrag, "cancel")

    with hook_module.dragging():
        hook_module.excepthook(*_raise("first"))
        hook_module.excepthook(*_raise("second"))

    assert len(told) == 1
    assert "first" in told[0]


def test_a_drag_with_nothing_wrong_says_nothing(told):
    with hook_module.dragging():
        pass

    assert told == []
