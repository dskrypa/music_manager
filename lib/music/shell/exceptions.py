class ExitLoop(StopIteration):
    pass


class CommandError(Exception):
    pass


class ArgError(CommandError):
    pass


class UnknownCommand(CommandError):
    def __str__(self):
        return f'Unknown command: {self.args[0]}'


class ExecutionError(CommandError):
    def __str__(self):
        return f'{self.args[0]}: error: {self.args[1]}'
