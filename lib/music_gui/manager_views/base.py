"""

"""

from __future__ import annotations

import logging
from abc import ABC
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from ds_tools.caching.decorators import cached_property, ClearableCachedPropertyMixin
from tk_gui.elements import Frame, EventButton
from tk_gui.elements.menu import MenuProperty
from tk_gui.event_handling import button_handler
from tk_gui.popups import popup_input_invalid, pick_folder_popup
from tk_gui.popups.style import StylePopup
from tk_gui.views.view import View
from tk_gui.options import GuiOptions

from music.files.album import AlbumDir
from music.files.exceptions import InvalidAlbumDir
from music_gui.elements.menus import FullRightClickMenu, MusicManagerMenuBar

if TYPE_CHECKING:
    from tkinter import Event
    from tk_gui.typing import Layout
    from music.manager.update import AlbumInfo

__all__ = ['BaseView', 'InitialView']
log = logging.getLogger(__name__)

DEFAULT_CONFIG = {'output_base_dir': '~/Music/', 'size': (1700, 750)}


class BaseView(ClearableCachedPropertyMixin, View, ABC, title='Music Manager'):
    menu = MenuProperty(MusicManagerMenuBar)
    window_kwargs = {'right_click_menu': FullRightClickMenu(), 'config': DEFAULT_CONFIG}
    album: AlbumInfo | AlbumDir

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __repr__(self) -> str:
        try:
            path_str = self.album.path.as_posix()
        except AttributeError:
            path_str = ''
        return f'<{self.__class__.__name__}[{self.title}][{path_str}]>'

    # region Layout Generation

    def get_pre_window_layout(self) -> Layout:
        yield [self.menu]

    # endregion

    # region Configuration

    @menu['File']['Settings'].callback
    def update_settings(self, event):
        config = self.window.config
        options = GuiOptions(submit='Save', title=None)
        with options.next_row() as options:
            options.add_bool('remember_pos', 'Remember Last Window Position', config.remember_position)
            options.add_bool('remember_size', 'Remember Last Window Size', config.remember_size)
        with options.next_row() as options:
            options.add_popup(
                'style', 'Style', StylePopup, default=config.style, popup_kwargs={'show_buttons': True}
            )
        with options.next_row() as options:
            options.add_directory('output_base_dir', 'Output Directory', config['output_base_dir'])
        with options.next_row() as options:
            options.add_listbox(
                'rm_tags', 'Tags to Remove', config.get('rm_tags', []), extendable=True, prompt_name='tag to remove'
            )

        results = options.run_popup()
        config.update(results, ignore_none=True, ignore_empty=True)
        self.clear_cached_properties()
        return results

    @cached_property
    def output_base_dir(self) -> Path:
        return Path(self.window.config['output_base_dir']).expanduser()

    @cached_property
    def output_sorted_dir(self) -> Path:
        date_str = date.today().strftime('%Y-%m-%d')
        return self.output_base_dir.joinpath(f'sorted_{date_str}')

    # endregion

    # region Album Selection

    def _get_last_dir(self, dir_type: str = None) -> Optional[Path]:
        if last_dir := self.window.config.get(f'last_dir:{dir_type}' if dir_type else 'last_dir'):
            last_dir = Path(last_dir)
            if not last_dir.exists():
                if last_dir.parent.exists():
                    return last_dir.parent
                else:
                    return self.output_base_dir
            else:
                return last_dir
        return None

    def get_album_selection(self) -> Optional[AlbumDir]:
        last_dir = self._get_last_dir()
        if path := pick_folder_popup(last_dir, 'Pick Album Directory', parent=self.window):
            log.debug(f'Selected album {path=}')
            try:
                album_dir = AlbumDir(path)
            except InvalidAlbumDir as e:
                popup_input_invalid(str(e), logger=log)
            else:
                if path != last_dir:
                    self.window.config['last_dir'] = path.as_posix()
                    self.window.config.save()
                return album_dir
        return None

    # endregion

    # region Event Handlers

    @button_handler('open')
    @menu['File']['Open'].callback
    def pick_next_album(self, event: Event, key=None):
        if album_dir := self.get_album_selection():
            return self.set_next_view(album_dir)
        return None

    # @event_handler(BindEvent.LEFT_CLICK.event)
    # def _handle_left_click(self, event: Event):
    #     from tk_gui.event_handling import log_widget_data
    #
    #     log_widget_data(self.window, event, parent=True)

    # endregion


class InitialView(BaseView, title='Music Manager'):
    window_kwargs = {'exit_on_esc': True, 'config': DEFAULT_CONFIG}
    album = None

    def get_post_window_layout(self) -> Layout:
        button = EventButton('Select Album', key='open', bind_enter=True, size=(30, 5), font=('Helvetica', 20))
        yield [Frame([[button]], anchor='TOP', expand=True)]

    def set_next_view(self, *args, **kwargs):
        from .album import AlbumView

        return super().set_next_view(*args, view_cls=AlbumView, **kwargs)
