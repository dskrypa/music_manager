"""
View that separates common album fields from common fields that are usually different between tracks.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from traceback import format_exc
from typing import TYPE_CHECKING, Mapping, Any, Optional

from requests import RequestException

from ds_tools.caching.decorators import cached_property
from db_cache.utils import get_user_cache_dir
from ds_tools.output.printer import Printer

from tk_gui.elements import Text, Button, Spacer, EventButton
from tk_gui.event_handling import button_handler
from tk_gui.options import GuiOptions, OptionColumn, OptionGrid
from tk_gui.options.options import InputOption, BoolOption, DropdownOption, ListboxOption, SubmitOption
from tk_gui.popups import ChooseImagePopup, SpinnerPopup, popup_ok, popup_error
from wiki_nodes.http import MediaWikiClient

from music.manager.config import UpdateConfig
from music.manager.wiki_update import WikiUpdater
from music_gui.elements.helpers import IText, nav_button, section_header
from music_gui.utils import AlbumIdentifier, get_album_info, LogAndPopupHelper
from .base import BaseView

if TYPE_CHECKING:
    from tkinter import Event
    from tk_gui.enums import CallbackAction
    from tk_gui.typing import Layout
    from tk_gui.views.view import ViewSpec
    from music.manager.update import AlbumInfo

__all__ = ['WikiUpdateView']
log = logging.getLogger(__name__)

ALL_SITES = ('kpop.fandom.com', 'www.generasia.com', 'wiki.d-addicts.com', 'en.wikipedia.org')


class WikiUpdateView(BaseView, title='Music Manager - Wiki Update'):
    default_window_kwargs = BaseView.default_window_kwargs | {'exit_on_esc': True}

    def __init__(self, album: AlbumIdentifier, options: GuiOptions | Mapping[str, Any] = None, **kwargs):
        super().__init__(**kwargs)
        self.album: AlbumInfo = get_album_info(album)
        self._options = options

    # region Options & Option Layout

    @cached_property
    def options(self) -> GuiOptions:
        gui_options = GuiOptions(self._prepare_option_layout())
        gui_options.update(self._options)
        return gui_options

    def _prepare_option_layout(self):
        yield [InputOption('album_url', 'Album URL', label_size=(11, 1), size=(80, 1), tooltip='A wiki URL')]
        artist_url_tip = 'Force the use of the given artist instead of an automatically discovered one'
        yield [InputOption('artist_url', 'Artist URL', label_size=(11, 1), size=(80, 1), tooltip=artist_url_tip)]

        collab_mode_tip = 'List collaborators in the artist tag, the title tag, or both (default: artist)'
        collab_mode_opt = DropdownOption(
            'collab_mode', 'Collab Mode', 'artist', choices=('title', 'artist', 'both'),
            label_size=(11, 1), tooltip=collab_mode_tip
        )
        yield [
            OptionColumn([collab_mode_opt, OptionGrid(self._prepare_option_grid())]),
            OptionColumn(self._prepare_site_options()),
        ]

    def _prepare_option_grid(self):  # noqa
        yield [
            BoolOption('soloist', 'Soloist', tooltip='For solo artists, use only their name instead of including their group, and do not sort them with their group'),
            BoolOption('artist_only', 'Artist Match Only', tooltip='Only match the artist / only use the artist URL if provided'),
            BoolOption('hide_edition', 'Hide Edition', tooltip='Exclude the edition from the album title, if present (default: include it)'),
        ]
        # TODO: If cover was missing, make update_cover default to True
        yield [
            BoolOption('update_cover', 'Update Cover', tooltip='Update the cover art for the album if it does not match an image in the matched wiki page'),
            BoolOption('ignore_genre', 'Ignore Genre', tooltip='Ignore genre instead of combining/replacing genres'),
            BoolOption('title_case', 'Title Case', tooltip='Fix track and album names to use Title Case when they are all caps'),
        ]
        yield [
            BoolOption('all_images', 'DL All Images', tooltip='When updating the cover, download all images (default: only those with "cover" in the title)'),
            BoolOption('no_album_move', 'Do Not Move Album', tooltip='Do not rename the album directory'),
            BoolOption('part_in_title', 'Use Part in Title', default=True, tooltip='Use the part name in the title when available'),
        ]
        yield [BoolOption('ignore_language', 'Ignore Language', tooltip='Ignore detected language')]

    def _prepare_site_options(self):
        config = self.window.config
        artist_sites = config.get('wiki_update:artist_sites', ALL_SITES[:-1])
        album_sites = config.get('wiki_update:album_sites', ALL_SITES[:-1])
        kwargs = {'choices': ALL_SITES, 'label_size': (9, 1), 'tooltip': 'The wiki sites to search'}
        yield ListboxOption('artist_sites', 'Artist Sites', default=artist_sites, **kwargs)
        yield ListboxOption('album_sites', 'Album Sites', default=album_sites, **kwargs)

    # endregion

    # region Layout Generation

    @cached_property
    def next_button(self) -> Button | None:
        return nav_button('right')

    def get_inner_layout(self) -> Layout:
        yield section_header('Wiki Match Options')
        yield [Text()]
        yield [Text('Selected Album Path:'), IText(self.album.path, size=(150, 1))]
        yield [Text()]
        yield [self.options.as_frame(side='t')]
        yield [Text()]
        yield section_header('Advanced Options')
        yield [Text()]
        yield [EventButton('Reset Page Cache...', key='reset_page_cache', side='t')]
        yield [Spacer((10, 500), side='t')]

    # endregion

    # region Event Handlers

    @button_handler('next_view')
    def find_match(self, event: Event, key=None) -> CallbackAction | None:
        from .diff import AlbumDiffView

        options = self.options.parse(self.window.results)
        update_config = self._get_update_config(options)
        if not (new_info := GuiWikiUpdater(self.album, update_config, options).get_album_info()):
            return None

        log.debug(f'Found {new_info=}')
        old_info = self.album.clean()
        if old_info != new_info:
            log.debug(f'Switching to diff view for {self.album}')
            return self.set_next_view(
                view_cls=AlbumDiffView,
                old_info=old_info,
                new_info=new_info,
                manually_edited=False,
                options={key: options[key] for key in ('title_case', 'no_album_move')},
            )
        else:
            log.debug(f'No changes are necessary for {self.album}')
            popup_ok('No changes are necessary - there is nothing to save')
            return None

    @button_handler('reset_page_cache')
    def reset_page_cache(self, event: Event, key=None):
        from wiki_nodes.http import MediaWikiClient

        sites = OptionColumn(
            BoolOption(site_dir.name, f'Reset cache: {site_dir.name}')
            for site_dir in Path(get_user_cache_dir('wiki')).iterdir()
            if site_dir.is_dir()
        )
        opt_layout = [[sites, OptionColumn([BoolOption('dry_run', 'Dry Run'), SubmitOption()], anchor_elements='n')]]
        results = GuiOptions(opt_layout).run_popup(title="Reset which sites' page caches?")
        with LogAndPopupHelper(
            'Clear Cache Results', results.pop('dry_run'), 'No sites were selected for the cache to be cleared'
        ) as lph:
            for site, clear in results.items():
                if clear:
                    lph.write('reset', f'page cache for {site}')
                    if not lph.dry_run:
                        MediaWikiClient(site)._cache.reset_caches(hard=True)

    # endregion

    def get_prev_view(self) -> ViewSpec | None:
        if self.prev_view_name == 'AlbumDiffView':
            from .album import AlbumView

            return AlbumView, (), {'album': self.album}
        else:
            return super().get_prev_view()

    def _get_update_config(self, parsed: dict[str, Any]) -> UpdateConfig:
        log.info(f'Parsed options:')
        Printer('json-pretty').pprint(parsed)

        config = self.window.config
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


class GuiWikiUpdater:
    def __init__(self, src_album_info: AlbumInfo, config: UpdateConfig, parsed: dict[str, Any]):
        self.src_album_info = src_album_info
        self.config = config
        self.parsed = parsed

    def get_album_info(self) -> AlbumInfo | None:
        album_info = self.dst_album_info
        if album_info and self.parsed['update_cover'] and (cover_path := self.get_wiki_cover_choice()):
            album_info.cover_path = cover_path
        return album_info

    @cached_property
    def dst_album_info(self) -> AlbumInfo | None:
        try:
            return SpinnerPopup(size=(200, 200)).run_task_in_thread(self._get_album_info)
        except Exception:  # noqa
            _log_and_popup_error(f'Error finding a wiki match for {self.src_album_info}:')
            return None

    def _get_album_info(self) -> AlbumInfo:
        updater = WikiUpdater(
            [self.src_album_info.path], self.config, artist_url=self.parsed['artist_url'] or None
        )
        album_dir, processor = updater.get_album_info(self.parsed['album_url'] or None)
        return processor.to_album_info()

    @cached_property
    def wiki_client(self) -> Optional[MediaWikiClient]:
        if wiki_album_url := self.dst_album_info.wiki_album:
            if wiki_album_url.startswith('https://music.bugs.co.kr'):
                return None
            return MediaWikiClient(wiki_album_url, nopath=True)
        return None

    @cached_property
    def wiki_image_urls(self) -> Optional[dict[str, str]]:
        if not (client := self.wiki_client):
            return None
        try:
            page = client.get_page(client.article_url_to_title(self.dst_album_info.wiki_album))
        except RequestException as e:
            log.error(f'Error retrieving images from {self.dst_album_info.wiki_album}: {e}')
        else:
            if image_titles := client.get_page_image_titles(page.title)[page.title]:
                log.debug(f'Found {len(image_titles)} images on page={page.title!r}: {image_titles}')
                return client.get_image_urls(image_titles)

        return None

    @cached_property
    def wiki_cover_images(self) -> dict[str, bytes]:
        log.debug(f'Starting thread to download wiki cover images for {self.dst_album_info.wiki_album}')
        spinner = SpinnerPopup(size=(200, 200), text='Downloading images...')
        try:
            return spinner.run_task_in_thread(self._get_wiki_cover_images)
        except Exception:  # noqa
            _log_and_popup_error(f'Error finding a wiki cover images for {self.dst_album_info}:')
            return {}

    def _get_wiki_cover_images(self) -> dict[str, bytes]:
        if not (urls := self.wiki_image_urls):
            log.debug('Found 0 wiki image URLs')
            return {}

        log.debug(f'Found {len(urls)} wiki image URLs')
        if not self.parsed['all_images']:
            # TODO: Sometimes there are cases where an album may have up to 16 images, all with 'cover' in the name...
            #  Maybe paginate or prompt first for which to view in cases where there are still >5?
            orig_len = len(urls)
            urls = {title: url for title, url in urls.items() if 'cover' in title.lower()}
            log.debug(f'Filtered image URLs from old={orig_len} to new={len(urls)} with "cover" in the title')

        title_bytes_map = {}
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(self.wiki_client.get_image, title): title for title in urls}
            for future in as_completed(futures):
                title = futures[future]
                try:
                    title_bytes_map[title] = future.result()
                except Exception as e:
                    log.error(f'Error retrieving image={title!r}: {e}')

        return title_bytes_map

    def _get_wiki_cover_choice(self) -> Optional[tuple[str, bytes]]:
        if not (images := self.wiki_cover_images):
            return None

        log.debug(f'Found {len(images)} wiki images')
        if len(images) == 1:
            title, data = next(iter(images.items()))
        else:
            try:
                title, data = ChooseImagePopup.with_auto_prompt(images).run()
            except TypeError:  # No image was selected
                return None
        return title, data

    def get_wiki_cover_choice(self) -> Optional[Path]:
        try:
            title, data = self._get_wiki_cover_choice()
        except TypeError:  # No image was selected
            return None

        name = title.split(':', 1)[1] if title.lower().startswith('file:') else title
        path = get_user_cache_dir('music_manager/cover_art').joinpath(name)
        if not path.is_file():
            log.debug(f'Saving wiki cover choice in cache: {path.as_posix()}')
            # path.write_bytes(self.wiki_client.get_image(title))
            path.write_bytes(data)
        return path


def _log_and_popup_error(message: str, exc_info: bool = True):
    if exc_info:
        message += '\n' + format_exc()
    log.error(message)
    popup_error(message, multiline=True)
