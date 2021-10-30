from PyQt5.QtWidgets import QApplication


def swap_list_items(_list, item1, item2):
    idx_1, idx_2 = _list.index(item1), _list.index(item2)
    _list[idx_2], _list[idx_1] = _list[idx_1], _list[idx_2]


def is_modal_open():
    return bool(QApplication.activeModalWidget() or QApplication.activePopupWidget())


def qt_connect(*connections):
    for c_sig, c_slot in connections:
        c_sig.connect(c_slot)
