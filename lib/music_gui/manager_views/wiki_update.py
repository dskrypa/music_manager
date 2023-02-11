"""
View that separates common album fields from common fields that are usually different between tracks.
"""

from __future__ import annotations

import logging
from abc import ABC
from traceback import format_exc
from typing import TYPE_CHECKING, Mapping, Any

from ds_tools.caching.decorators import cached_property
from db_cache.utils import get_user_cache_dir
from ds_tools.output.printer import Printer

from tk_gui.elements import HorizontalSeparator, Text, Button
from tk_gui.event_handling import button_handler
from tk_gui.options import GuiOptions
from tk_gui.popups import popup_ok, popup_error
from tk_gui.tasks import run_task_with_spinner

from music.manager.config import UpdateConfig
from music.manager.wiki_update import WikiUpdater
from music_gui.elements.helpers import IText, nav_button
from music_gui.utils import AlbumIdentifier, get_album_info
from .base import BaseView

if TYPE_CHECKING:
    from tkinter import Event
    from tk_gui.enums import CallbackAction
    from tk_gui.typing import Layout
    from music.manager.update import AlbumInfo

__all__ = ['WikiUpdateView']
log = logging.getLogger(__name__)

ALL_SITES = ('kpop.fandom.com', 'www.generasia.com', 'wiki.d-addicts.com', 'en.wikipedia.org')


class WikiUpdateView(BaseView, ABC, title='Music Manager - Wiki Update'):
    window_kwargs = BaseView.window_kwargs | {'exit_on_esc': True}

    def __init__(self, album: AlbumIdentifier, options: GuiOptions | Mapping[str, Any] = None, **kwargs):
        super().__init__(**kwargs)
        self.album: AlbumInfo = get_album_info(album)
        self._options = options

    # region Layout Generation

    @cached_property
    def options(self) -> GuiOptions:
        config = self.window.config
        gui_options = GuiOptions(None)
        with gui_options.column(None) as options:
            options.add_input('album_url', 'Album URL', size=(80, 1), tooltip='A wiki URL')
            options.add_input(
                'artist_url', 'Artist URL', size=(80, 1), row=1,
                tooltip='Force the use of the given artist instead of an automatically discovered one'
            )
        with gui_options.row(2) as options:
            options.add_dropdown(
                'collab_mode', 'Collab Mode', choices=('title', 'artist', 'both'), default='artist',
                tooltip='List collaborators in the artist tag, the title tag, or both (default: artist)'
            )
        with gui_options.row(3) as options:
            options.add_bool('soloist', 'Soloist', tooltip='For solo artists, use only their name instead of including their group, and do not sort them with their group')
            options.add_bool('artist_only', 'Artist Match Only', tooltip='Only match the artist / only use the artist URL if provided')
            options.add_bool('hide_edition', 'Hide Edition', tooltip='Exclude the edition from the album title, if present (default: include it)')
        with gui_options.row(4) as options:
            options.add_bool('update_cover', 'Update Cover', tooltip='Update the cover art for the album if it does not match an image in the matched wiki page')
            options.add_bool('ignore_genre', 'Ignore Genre', tooltip='Ignore genre instead of combining/replacing genres')
            options.add_bool('title_case', 'Title Case', tooltip='Fix track and album names to use Title Case when they are all caps')
        with gui_options.row(5) as options:
            options.add_bool('all_images', 'DL All Images', tooltip='When updating the cover, download all images (default: only those with "cover" in the title)')
            options.add_bool('no_album_move', 'Do Not Move Album', tooltip='Do not rename the album directory')
            options.add_bool('part_in_title', 'Use Part in Title', default=True, tooltip='Use the part name in the title when available')
        with gui_options.row(6) as options:
            options.add_bool('ignore_language', 'Ignore Language', tooltip='Ignore detected language')

        with gui_options.column(1) as options:
            artist_sites = config.get('wiki_update:artist_sites', ALL_SITES[:-1])
            album_sites = config.get('wiki_update:album_sites', ALL_SITES[:-1])
            options.add_listbox(
                'artist_sites', 'Artist Sites', choices=ALL_SITES, default=artist_sites,
                tooltip='The wiki sites to search', label_size=(9, 1)
            )
            options.add_listbox(
                'album_sites', 'Album Sites', choices=ALL_SITES, default=album_sites,
                tooltip='The wiki sites to search', row=1, label_size=(9, 1)
            )

        gui_options.update(self._options)
        return gui_options

    @cached_property
    def next_button(self) -> Button | None:
        return nav_button('right')

    def get_inner_layout(self) -> Layout:
        yield [HorizontalSeparator(), Text('Wiki Match Options'), HorizontalSeparator()]
        yield [Text()]
        yield [Text('Selected Album Path:'), IText(self.album.path, size=(150, 1))]
        yield [Text()]
        yield [self.options.as_frame()]
        yield [Text()]

    # endregion

    # region Event Handlers

    @button_handler('next_view')
    def find_match(self, event: Event, key=None) -> CallbackAction | None:
        from .diff import AlbumDiffView

        options = self.options.parse(self.window.results)
        update_config = self._get_update_config(options)
        try:
            new_info = run_task_with_spinner(self._get_album_info, (update_config, options))
        except Exception:  # noqa
            error_str = f'Error finding a wiki match for {self.album}:\n{format_exc()}'
            log.error(error_str)
            popup_error(error_str, multiline=True)
            return None
        else:
            old_info = self.album.clean()
            if old_info != new_info:
                return self.set_next_view(view_cls=AlbumDiffView, old_info=old_info, new_info=new_info)
            else:
                popup_ok('No changes are necessary - there is nothing to save')
                return None

    # endregion

    def _get_update_config(self, parsed: dict[str, Any]) -> UpdateConfig:
        config = self.window.config
        log.info(f'Parsed options:')

        Printer('json-pretty').pprint(parsed)
        if set(parsed['artist_sites']) != set(config.get('wiki_update:artist_sites', ())):
            config['wiki_update:artist_sites'] = sorted(parsed['artist_sites'])
        if set(parsed['album_sites']) != set(config.get('wiki_update:album_sites', ())):
            config['wiki_update:album_sites'] = sorted(parsed['album_sites'])

        return UpdateConfig(
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

    def _get_album_info(self, config: UpdateConfig, parsed: dict[str, Any]) -> AlbumInfo:
        updater = WikiUpdater([self.album.path], config, artist_url=parsed['artist_url'] or None)
        album_dir, processor = updater.get_album_info(parsed['album_url'] or None)
        return processor.to_album_info()
