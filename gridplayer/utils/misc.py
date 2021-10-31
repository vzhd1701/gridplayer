from multiprocessing.process import active_children

from PyQt5.QtWidgets import QApplication


def is_modal_open():
    return bool(QApplication.activeModalWidget() or QApplication.activePopupWidget())


def qt_connect(*connections):
    for c_sig, c_slot in connections:
        c_sig.connect(c_slot)


def force_terminate_children():
    for p in active_children():
        p.terminate()
