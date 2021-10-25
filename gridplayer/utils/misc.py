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


class ModalWindow(object):
    def __init__(self, parent):
        self.parent = parent

    def __enter__(self):
        self.parent.is_modal_open = True

        self.parent.mouse_timer.stop()
        self.parent.mouse_reset()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.parent.is_modal_open = False

        self.parent.mouse_reset()
