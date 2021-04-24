"""
View for choosing Wiki update options

:author: Doug Skrypa
"""

import traceback
from typing import Any, Optional

from PySimpleGUI import Text, Element, HSep

from ds_tools.output.printer import Printer
from ...files.album import AlbumDir
from ...manager.update import AlbumInfo
from ...manager.wiki_update import WikiUpdater
from ..options import GuiOptions
from .base import event_handler
from .formatting import AlbumBlock
from .main import MainView
from .popups.text import popup_error
from .thread_tasks import start_task
from .utils import DarkInput as Input

__all__ = ['WikiUpdateView']
ALL_SITES = ('kpop.fandom.com', 'www.generasia.com', 'wiki.d-addicts.com', 'en.wikipedia.org')


class WikiUpdateView(MainView, view_name='wiki_update'):
    back_tooltip = 'Go back to Wiki update options'

    def __init__(self, album: AlbumDir, album_block: AlbumBlock = None, options: GuiOptions = None, **kwargs):
        super().__init__(**kwargs)
        self.album = album
        self.album_block = album_block or AlbumBlock(self, self.album)
        self.album_block.view = self

        if options is not None and options.view.name == self.name:
            self.options = options
        else:
            self.options = GuiOptions(self, disable_on_parsed=False, submit=None)
            with self.options.column(None) as options:
                options.add_input('album_url', 'Album URL', size=(80, 1), tooltip='A wiki URL')
                options.add_input('artist_url', 'Artist URL', size=(80, 1), row=1, tooltip='Force the use of the given artist instead of an automatically discovered one')

            with self.options.row(2) as options:
                options.add_dropdown('collab_mode', 'Collab Mode', choices=('title', 'artist', 'both'), default='artist', tooltip='List collaborators in the artist tag, the title tag, or both (default: artist)')
            with self.options.row(3) as options:
                options.add_bool('soloist', 'Soloist', tooltip='For solo artists, use only their name instead of including their group, and do not sort them with their group')
                options.add_bool('artist_only', 'Artist Match Only', tooltip='Only match the artist / only use the artist URL if provided')
                options.add_bool('hide_edition', 'Hide Edition', tooltip='Exclude the edition from the album title, if present (default: include it)')
            with self.options.row(4) as options:
                # TODO: Make the update cover prompt give a popup instead of opening a browser
                options.add_bool('update_cover', 'Update Cover', tooltip='Update the cover art for the album if it does not match an image in the matched wiki page')
                options.add_bool('replace_genre', 'Replace Genre', tooltip='Replace genre instead of combining genres')
                options.add_bool('title_case', 'Title Case', tooltip='Fix track and album names to use Title Case when they are all caps')
            with self.options.row(5) as options:
                options.add_bool('no_album_move', 'Do Not Move Album', tooltip='Do not rename the album directory')

            with self.options.column(1) as options:
                options.add_listbox('sites', 'Sites', choices=ALL_SITES, default=ALL_SITES[:-1], tooltip='The wiki sites to search')

            self.options.update(options)

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

    @event_handler('btn::back')
    def back_to_album(self, event: str, data: dict[str, Any]):
        from .album import AlbumView

        return AlbumView(self.album, self.album_block, last_view=self)

    @event_handler('btn::next')
    def find_match(self, event: str, data: dict[str, Any]):
        from .diff import AlbumDiffView

        parsed = self.options.parse(data)
        self.log.info(f'Parsed options:')
        Printer('json-pretty').pprint(parsed)

        updater = WikiUpdater(
            [self.album.path],
            parsed['collab_mode'],
            parsed['sites'],
            parsed['soloist'],
            parsed['hide_edition'],
            parsed['title_case'],
            parsed['update_cover'],
            parsed['artist_url'] or None,
        )

        processor = None
        album_info: Optional[AlbumInfo] = None
        error = None

        def get_album_info():
            nonlocal processor, error, album_info
            try:
                album_dir, processor = updater.get_album_info(parsed['album_url'] or None, parsed['artist_only'])
                album_info = processor.to_album_info()
            except Exception as e:
                error = traceback.format_exc()
                self.log.error(str(e), exc_info=True)

        start_task(get_album_info)

        if album_info is not None:
            return AlbumDiffView(self.album, album_info, self.album_block, options=self.options, last_view=self)
        else:
            error_str = f'Error finding a wiki match for {self.album}:\n{error}'
            popup_error(error_str, multiline=True, auto_size=True)
