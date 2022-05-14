from cli_command_parser import Command, Counter, Flag

from ..__version__ import __author_email__, __version__, __author__, __url__  # noqa


class Clock(Command, description='Clock'):
    seconds = Flag('--no_seconds', '-S', default=True, help='Hide seconds')
    slim = Flag('-s', help='Use thinner numbers')
    verbose = Counter('-v', help='Increase logging verbosity (can specify multiple times)')

    def main(self):
        from ds_tools.logging import init_logging

        from ..gui.popups.clock import ClockView

        init_logging(self.verbose, log_path=None, names=None, millis=True, set_levels={'PIL': 30})
        ClockView(seconds=self.seconds, slim=self.slim).get_result()
