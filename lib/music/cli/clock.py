from ds_tools.argparsing import ArgParser
from ds_tools.core.main import wrap_main
from ds_tools.logging import init_logging

from ..__version__ import __author_email__, __version__, __author__, __url__  # noqa
from ..gui.popups.clock import ClockView


def parser():
    parser = ArgParser(description='Clock')
    parser.add_argument('--no_seconds', '-S', dest='seconds', action='store_false', help='Hide seconds')
    parser.add_argument('--slim', '-s', action='store_true', help='Use thinner numbers')
    parser.include_common_args('verbosity')
    return parser


@wrap_main
def main():
    args = parser().parse_args(req_subparser_value=False)
    init_logging(args.verbose, log_path=None, names=None, millis=True, set_levels={'PIL': 30})

    ClockView(seconds=args.seconds, slim=args.slim).get_result()
