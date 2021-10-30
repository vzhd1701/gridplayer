from PyQt5.QtCore import QEvent, QObject


class ManagerBase(QObject):
    def __init__(self, context, **kwargs):
        super().__init__(**kwargs)

        self._context = context
        self._event_map = {}

    def eventFilter(self, event_object, event) -> bool:
        event_function = self._event_map.get(event.type())
        if event_function is not None:
            return event_function(event) is True

        return False
