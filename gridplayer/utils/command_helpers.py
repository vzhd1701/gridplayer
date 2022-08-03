class LOGIC(object):
    def __init__(self, *args):
        self.args = args


class LOGIC_UNARY(object):
    def __init__(self, arg):
        self.arg = arg


class NOT(LOGIC_UNARY):
    ...


class AND(LOGIC):
    ...


class OR(LOGIC):
    ...
