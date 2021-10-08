from ..__version__ import __author_email__, __version__  # noqa
from ds_tools.argparsing import ArgParser
from ds_tools.core.main import wrap_main
from ds_tools.logging import init_logging
from pypod.shell import iDeviceShell


def parser():
    parser = ArgParser(description='iPod Shell')
    parser.include_common_args('verbosity')
    return parser


@wrap_main
def main():
    args = parser().parse_args()
    init_logging(args.verbose or 1, log_path=None, names=None)

    from music import ipod_shell_cmds  # Necessary to load them
    iDeviceShell().cmdloop()
