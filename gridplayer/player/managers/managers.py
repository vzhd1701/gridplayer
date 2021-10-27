class ManagersManager(object):
    def __init__(self, parent, **kwargs):
        self._parent = parent

        self._connections = None
        self._event_filters = None

        for k, v in kwargs.items():
            setattr(self, k, v)

    @property
    def connections(self):
        return self._connections

    @connections.setter
    def connections(self, connections):
        self._connections = connections

        for c_manager, c_list in connections.items():
            for c_sig, c_slot in c_list:
                c_sig = self._get_manager_function(c_manager, c_sig)
                c_slot = self._get_manager_function(c_manager, c_slot)

                c_sig.connect(c_slot)

    @property
    def event_filters(self):
        return self._event_filters

    @event_filters.setter
    def event_filters(self, event_filters):
        self._event_filters = event_filters

        for ef in event_filters:
            self._parent.installEventFilter(getattr(self, ef))

    def _get_manager_function(self, manager, signature):
        if "." in signature:
            manager, function = signature.split(".")
        else:
            function = signature

        manager = self._parent if manager == "s" else getattr(self, manager)

        return getattr(manager, function)
