import inspect

from PyQt5.QtCore import QObject


class ManagerBase(QObject):
    def __init__(self, context, **kwargs):
        super().__init__(**kwargs)

        self._context = context
        self._event_map = {}

    def eventFilter(self, event_object, event) -> bool:
        event_function = self._event_map.get(event.type())
        if event_function is not None:
            if not inspect.signature(event_function).parameters:
                return event_function() is True
            return event_function(event) is True

        return False
