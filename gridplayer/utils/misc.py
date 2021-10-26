from PyQt5.QtWidgets import QApplication


def dict_swap_items(d, id1, id2):
    new_dict = {}
    for k, v in d.items():
        if k == id1:
            new_dict[id2] = d[id2]
        elif k == id2:
            new_dict[id1] = d[id1]
        elif k not in {id1, id2}:
            new_dict[k] = v
    return new_dict


def is_modal_open():
    return bool(QApplication.activeModalWidget() or QApplication.activePopupWidget())


def qt_connect(*connections):
    for c_sig, c_slot in connections:
        c_sig.connect(c_slot)
