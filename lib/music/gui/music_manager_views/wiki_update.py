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

from music.files.album import AlbumDir
from music.manager.config import UpdateConfig
from music.manager.update import AlbumInfo
from music.manager.wiki_update import WikiUpdater
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
                options.add_bool('ignore_genre', 'Ignore Genre', tooltip='Ignore genre instead of combining/replacing genres')
                options.add_bool('title_case', 'Title Case', tooltip='Fix track and album names to use Title Case when they are all caps')
            with self.options.row(5) as options:
                options.add_bool('all_images', 'DL All Images', tooltip='When updating the cover, download all images (default: only those with "cover" in the title)')
                options.add_bool('no_album_move', 'Do Not Move Album', tooltip='Do not rename the album directory')
                options.add_bool('part_in_title', 'Use Part in Title', default=True, tooltip='Use the part name in the title when available')
            with self.options.row(6) as options:
                options.add_bool('ignore_language', 'Ignore Language', tooltip='Ignore detected language')

            with self.options.column(1) as options:
                artist_sites = self.config.get('wiki_update:artist_sites', ALL_SITES[:-1])
                album_sites = self.config.get('wiki_update:album_sites', ALL_SITES[:-1])
                options.add_listbox('artist_sites', 'Artist Sites', choices=ALL_SITES, default=artist_sites, tooltip='The wiki sites to search', label_size=(9, 1))
                options.add_listbox('album_sites', 'Album Sites', choices=ALL_SITES, default=album_sites, tooltip='The wiki sites to search', row=1, label_size=(9, 1))

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
        if set(parsed['artist_sites']) != set(self.config.get('wiki_update:artist_sites', ())):
            self.config['wiki_update:artist_sites'] = sorted(parsed['artist_sites'])
        if set(parsed['album_sites']) != set(self.config.get('wiki_update:album_sites', ())):
            self.config['wiki_update:album_sites'] = sorted(parsed['album_sites'])

        config = UpdateConfig(
            collab_mode=parsed['collab_mode'],
            soloist=parsed['soloist'],
            hide_edition=parsed['hide_edition'],
            title_case=parsed['title_case'],
            update_cover=False,
            artist_sites=parsed['artist_sites'],
            album_sites=parsed['album_sites'],
            artist_only=parsed['artist_only'],
            part_in_title=parsed['part_in_title'],
            ignore_genre=parsed['ignore_genre'],
            ignore_language=parsed['ignore_language'],
        )
        updater = WikiUpdater([self.album.path], config, artist_url=parsed['artist_url'] or None)

        processor = None
        album_info: Optional[AlbumInfo] = None
        error = None

        def get_album_info():
            nonlocal processor, error, album_info
            try:
                album_dir, processor = updater.get_album_info(parsed['album_url'] or None)
                album_info = processor.to_album_info()
            except Exception as e:
                error = traceback.format_exc()
                self.log.error(str(e), exc_info=True)

        self.start_task(get_album_info)

        if album_info is not None:
            if parsed['update_cover']:
                self.album_formatter.album_info = album_info
                album_info.cover_path = self.album_formatter.get_wiki_cover_choice(parsed['all_images'])

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
                    client._cache.reset_caches(hard=True)
