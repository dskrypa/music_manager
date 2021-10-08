from ..__version__ import __author_email__, __version__, __author__, __url__  # noqa
from ds_tools.argparsing import ArgParser
from ds_tools.core.main import wrap_main
from ds_tools.logging import init_logging


def parser():
    parser = ArgParser(description='Plex Manager GUI')
    parser.include_common_args('verbosity')
    return parser


@wrap_main
def main():
    args = parser().parse_args(req_subparser_value=False)
    init_logging(args.verbose, names=None, millis=True, set_levels={'PIL': 30})
    launch_gui(args)


def launch_gui(args):
    from music.common.prompts import set_ui_mode, UIMode
    from music.files.patches import apply_mutagen_patches
    from music.gui.patches import patch_all
    from music.gui.plex_views.main import PlexView

    apply_mutagen_patches()
    patch_all()
    set_ui_mode(UIMode.GUI)

    start_kwargs = dict(title='Plex Manager', resizable=True, size=(1700, 750), element_justification='center')
    start_kwargs['init_event'] = ('init_view', {'view': 'search'})
    # start_kwargs['init_event'] = ('init_view', {'view': 'player'})
    PlexView.start(**start_kwargs)
