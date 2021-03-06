"""
View for choosing Wiki update options

:author: Doug Skrypa
"""

import traceback
from pathlib import Path
from typing import Optional

from PySimpleGUI import Text, HSep

from db_cache.utils import get_user_cache_dir
from ds_tools.output.printer import Printer
from ...files.album import AlbumDir
from ...manager.update import AlbumInfo
from ...manager.wiki_update import WikiUpdater
from ..base_view import event_handler, Event, EventData, RenderArgs
from ..elements.inputs import ExtInput
from ..options import GuiOptions
from ..popups.text import popup_error
from .formatting import AlbumFormatter
from .main import MainView

__all__ = ['WikiUpdateView']
ALL_SITES = ('kpop.fandom.com', 'www.generasia.com', 'wiki.d-addicts.com', 'en.wikipedia.org')


class WikiUpdateView(MainView, view_name='wiki_update'):
    back_tooltip = 'Go back to Wiki update options'

    def __init__(self, album: AlbumDir, album_formatter: AlbumFormatter = None, options: GuiOptions = None, **kwargs):
        super().__init__(**kwargs)
        self.menu.insert(-1, ['Wiki &Options', ['Reset Page Cache']])
        self.album = album
        self.album_formatter = album_formatter or AlbumFormatter(self, self.album)
        self.album_formatter.view = self
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
                options.add_bool('update_cover', 'Update Cover', tooltip='Update the cover art for the album if it does not match an image in the matched wiki page')
                options.add_bool('replace_genre', 'Replace Genre', tooltip='Replace genre instead of combining genres')
                options.add_bool('title_case', 'Title Case', tooltip='Fix track and album names to use Title Case when they are all caps')
            with self.options.row(5) as options:
                options.add_bool('no_album_move', 'Do Not Move Album', tooltip='Do not rename the album directory')

            with self.options.column(1) as options:
                sites = self.config.get('wiki_update:sites', ALL_SITES[:-1])
                options.add_listbox('sites', 'Sites', choices=ALL_SITES, default=sites, tooltip='The wiki sites to search')

            self.options.update(options)

    def get_render_args(self) -> RenderArgs:
        full_layout, kwargs = super().get_render_args()
        layout = [
            [HSep(), Text('Wiki Match Options'), HSep()],
            [Text()],
            [Text('Selected Album Path:'), ExtInput(self.album.path.as_posix(), disabled=True, size=(150, 1))],
            [Text()],
            [self.options.as_frame('find_match')],
            [Text()],
        ]

        workflow = self.as_workflow(layout, back_tooltip='Cancel Changes', next_tooltip='Find Match')
        full_layout.append(workflow)
        return full_layout, kwargs

    @event_handler('btn::back')
    def back_to_album(self, event: Event, data: EventData):
        from .album import AlbumView

        return AlbumView(self.album, self.album_formatter, last_view=self)

    @event_handler('btn::next')
    def find_match(self, event: Event, data: EventData):
        from .diff import AlbumDiffView

        parsed = self.options.parse(data)
        self.log.info(f'Parsed options:')
        Printer('json-pretty').pprint(parsed)
        if set(parsed['sites']) != set(self.config.get('wiki_update:sites', ())):
            self.config['wiki_update:sites'] = sorted(parsed['sites'])

        updater = WikiUpdater(
            [self.album.path],
            parsed['collab_mode'],
            parsed['sites'],
            parsed['soloist'],
            parsed['hide_edition'],
            parsed['title_case'],
            False,
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

        self.start_task(get_album_info)

        if album_info is not None:
            if parsed['update_cover']:
                self.album_formatter.album_info = album_info
                album_info.cover_path = self.album_formatter.get_wiki_cover_choice()

            return AlbumDiffView(self.album, album_info, self.album_formatter, options=self.options, last_view=self)
        else:
            error_str = f'Error finding a wiki match for {self.album}:\n{error}'
            popup_error(error_str, multiline=True, auto_size=True)

    @event_handler
    def reset_page_cache(self, event: Event, data: EventData):
        from wiki_nodes.http import MediaWikiClient

        options = GuiOptions(self)
        wiki_cache_dir = Path(get_user_cache_dir('wiki'))
        for site_dir in wiki_cache_dir.iterdir():
            if site_dir.is_dir():
                with options.next_row():
                    options.add_bool(site_dir.name, f'Reset cache: {site_dir.name}')

        if results := options.as_popup():
            for site, clear in results.items():
                if clear:
                    client = MediaWikiClient(site)
                    self.log.info(f'Resetting cache for {site}')
                    client.reset_caches(hard=True)
