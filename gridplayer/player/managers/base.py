import inspect

from PyQt5.QtCore import QObject


class ManagerBase(QObject):
    def __init__(self, context, **kwargs):
        super().__init__(**kwargs)

        self._ctx = context

    def eventFilter(self, event_object, event) -> bool:
        try:
            event_function = self.event_map.get(event.type())
        except AttributeError:
            return False

        if event_function is not None:
            if not inspect.signature(event_function).parameters:
                return event_function() is True
            return event_function(event) is True

        return False
