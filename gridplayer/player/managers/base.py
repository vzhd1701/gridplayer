import inspect
import logging

from PyQt5.QtCore import QObject


class ManagerBase(QObject):
    def __init__(self, context, **kwargs):
        super().__init__(**kwargs)

        self._log = logging.getLogger(self.__class__.__name__)

        self._ctx = context

    def eventFilter(self, event_object, event) -> bool:
        try:
            event_function = self.event_map.get(event.type())
        except AttributeError:
            return False

        if event_function is not None:
            nparams = len(inspect.signature(event_function).parameters)
            if nparams == 0:
                result = event_function()
            elif nparams == 1:
                result = event_function(event)
            else:
                result = event_function(event, event_object)
            return result is True

        return False
