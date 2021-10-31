from PyQt5.QtCore import QObject


class Commands(object):
    def __init__(self):
        self._commands = {}

    def __setattr__(self, command_name, command_func):
        if command_name == "_commands":
            super().__setattr__(command_name, command_func)
        self._commands[command_name] = command_func

    def __getattr__(self, command_name):
        return self._commands[command_name]

    def __iter__(self):
        return iter(self._commands)

    def update(self, commands):
        self._commands.update(commands)

    def resolve(self, command):
        if isinstance(command, tuple):
            command_name = command[0]
            command_args = command[1:]

            command_func = self._commands[command_name]

            return lambda: command_func(*command_args)

        command_name = command

        return self._commands[command_name]


class Context(object):
    def __init__(self):
        self._context = {}

    def __setattr__(self, var_name, var_value):
        if var_name == "_context":
            super().__setattr__(var_name, var_value)
        self._context[var_name] = var_value

    def __getattr__(self, var_name):
        if callable(self._context[var_name]):
            return self._context[var_name]()
        return self._context[var_name]


class ManagersManager(QObject):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.global_event_filters = []

        self._context = Context()
        self._context.commands = Commands()

        self._managers = {}
        self._connections = None
        self._event_filters = None

    def init(self):
        for m in self._managers.values():
            m_init = getattr(m, "init", None)
            if m_init is None:
                continue

            m_init()

    def eventFilter(self, event_object, event):
        if event_object is not self:
            return False

        return any(
            self._managers[ef].eventFilter(event_object, event)
            for ef in self.global_event_filters
        )

    @property
    def managers(self):
        return self._managers

    @managers.setter
    def managers(self, managers):
        for manager_name, manager_cls in managers.items():
            manager = manager_cls(context=self._context, parent=self)

            self._managers[manager_name] = manager
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
            self.installEventFilter(self._managers[ef])

    @property
    def commands(self):
        return self._context.commands

    @commands.setter
    def commands(self, commands):
        self._register_commands("_root", commands)

    def filter_event(self, event):
        return any(
            self._managers[ef].eventFilter(self, event) for ef in self._event_filters
        )

    def _get_manager_function(self, manager, signature):
        if "." in signature:
            manager, function = signature.split(".")
        else:
            function = signature

        manager = self if manager == "s" else self._managers[manager]

        return getattr(manager, function)

    def _register_commands(self, manager_name, manager):
        try:
            command_collisions = set(self._context.commands) & set(manager.commands)
        except AttributeError:
            return

        if command_collisions:
            raise ValueError(
                f"{manager_name} has conflicting commands: {command_collisions}"
            )

        self._context.commands.update(manager.commands)
