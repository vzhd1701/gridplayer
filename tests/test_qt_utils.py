import pytest
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.utils.qt import topmost


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


def test_the_topmost_widget_is_the_one_raised_last():
    parent = QWidget()
    a, b, c = QWidget(parent), QWidget(parent), QWidget(parent)

    assert topmost([a, b]) is b
    a.raise_()
    assert topmost([a, b, c]) is a
    assert topmost([c]) is c
    assert topmost([]) is None
