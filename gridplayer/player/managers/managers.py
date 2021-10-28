class ManagersManager(object):
    def __init__(self, parent, commands, managers):
        self._parent = parent

        self.global_event_filters = []

        self._context = {
            "commands": commands,
            "video_blocks": parent.video_blocks,
            "grid_mode": parent.grid_mode,
        }

        self._connections = None
        self._event_filters = None

        for manager_name, manager_cls in managers.items():
            manager = manager_cls(context=self._context, parent=self._parent)

            setattr(self, manager_name, manager)
            self._register_commands(manager_name, manager)

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

    @property
    def commands(self):
        return self._context["commands"]

    @commands.setter
    def commands(self, commands):
        self._register_commands("_root", commands)

    def global_event_filter(self, event_object, event):
        return any(
            getattr(self, ef).eventFilter(event_object, event)
            for ef in self.global_event_filters
        )

    def _get_manager_function(self, manager, signature):
        if "." in signature:
            manager, function = signature.split(".")
        else:
            function = signature

        manager = self._parent if manager == "s" else getattr(self, manager)

        return getattr(manager, function)

    def _register_commands(self, manager_name, manager):
        if not hasattr(manager, "commands"):
            return

        command_collisions = set(self._context["commands"]) & set(manager.commands)

        if command_collisions:
            raise ValueError(
                f"{manager_name} has conflicting commands: {command_collisions}"
            )

        self._context["commands"].update(manager.commands)
