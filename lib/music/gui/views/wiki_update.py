"""
View: Album + track tag values.  Allows editing, after which the view transitions to the diff view.

:author: Doug Skrypa
"""

from dataclasses import fields
from itertools import chain
from pathlib import Path
from typing import Any

from PySimpleGUI import Text, Input, HorizontalSeparator, Column, Element, Button, popup_get_text, HSep

from ds_tools.output.printer import Printer
from ...files.album import AlbumDir
from ...manager.update import AlbumInfo, TrackInfo
from ...manager.wiki_update import update_tracks
from ..constants import LoadingSpinner
from ..options import GuiOptions
from ..progress import Spinner
from .base import event_handler
from .formatting import AlbumBlock, split_key
from .main import MainView
from .popups.simple import popup_ok

__all__ = ['WikiUpdateView']
ALL_SITES = ('kpop.fandom.com', 'www.generasia.com', 'wiki.d-addicts.com', 'en.wikipedia.org')

"""
update_tracks(
    args.path, args.dry_run, args.soloist, args.hide_edition, args.collab_mode, args.url, bpm,
    args.destination, args.title_case, args.sites, args.dump, args.load, args.artist, args.update_cover,
    args.no_album_move, args.artist_only, not args.replace_genre
)
"""


class WikiUpdateView(MainView, view_name='wiki_update'):
    def __init__(self, album: AlbumDir, album_block: AlbumBlock = None):
        super().__init__()
        self.album = album
        self.album_block = album_block or AlbumBlock(self, self.album)
        self.album_block.view = self

        self.options = GuiOptions(self, disable_on_parsed=False, submit=None)

        self.options.add_input('album_url', 'Album URL', size=(80, 1), col=None, tooltip='A wiki URL')
        self.options.add_input('artist_url', 'Artist URL', size=(80, 1), row=1, col=None, tooltip='Force the use of the given artist instead of an automatically discovered one')

        self.options.add_dropdown('collab_mode', 'Collab Mode', row=2, choices=('title', 'artist', 'both'), default='artist', tooltip='List collaborators in the artist tag, the title tag, or both (default: artist)')

        self.options.add_bool('soloist', 'Soloist', row=3, tooltip='For solo artists, use only their name instead of including their group, and do not sort them with their group')
        self.options.add_bool('artist_only', 'Artist Match Only', row=3, tooltip='Only match the artist / only use the artist URL if provided')
        self.options.add_bool('hide_edition', 'Hide Edition', row=3, tooltip='Exclude the edition from the album title, if present (default: include it)')

        self.options.add_bool('update_cover', 'Update Cover', row=4, tooltip='Update the cover art for the album if it does not match an image in the matched wiki page')
        self.options.add_bool('replace_genre', 'Replace Genre', row=4, tooltip='Replace genre instead of combining genres')
        self.options.add_bool('title_case', 'Title Case', row=4, tooltip='Fix track and album names to use Title Case when they are all caps')

        self.options.add_listbox('sites', 'Sites', col=1, choices=ALL_SITES, default=ALL_SITES[:-1], tooltip='The wiki sites to search')
        self.options.add_bool('no_album_move', 'Do Not Move Album', row=5, tooltip='Do not rename the album directory')

    def get_render_args(self) -> tuple[list[list[Element]], dict[str, Any]]:
        full_layout, kwargs = super().get_render_args()
        layout = [
            [HSep(), Text('Wiki Match Options'), HSep()],
            [Text()],
            [Text('Selected Album Path:'), Input(self.album.path.as_posix(), disabled=True, size=(150, 1))],
            [Text()],
            [self.options.as_frame('find_match')],
            [Text()],
        ]

        workflow = self.as_workflow(layout, back_tooltip='Cancel Changes', next_tooltip='Find Match')
        full_layout.append(workflow)
        return full_layout, kwargs

    @event_handler('btn::back')  # noqa
    def back_to_album(self, event: str, data: dict[str, Any]):
        from .album import AlbumView

        return AlbumView(self.album, self.album_block)

    @event_handler('btn::next')  # noqa
    def find_match(self, event: str, data: dict[str, Any]):
        parsed = self.options.parse(data)
        self.log.info(f'Parsed options:')
        Printer('json-pretty').pprint(parsed)
