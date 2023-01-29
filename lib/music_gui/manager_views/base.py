"""

"""

from __future__ import annotations

import logging
from abc import ABC
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from ds_tools.caching.decorators import cached_property, ClearableCachedPropertyMixin
from tk_gui.elements import Frame, EventButton, YScrollFrame
from tk_gui.elements.menu import MenuProperty
from tk_gui.enums import CallbackAction
from tk_gui.event_handling import button_handler
from tk_gui.popups import popup_input_invalid, pick_folder_popup
from tk_gui.popups.style import StylePopup
from tk_gui.pseudo_elements import Row
from tk_gui.views.view import View, ViewSpec
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

DEFAULT_CONFIG = {
    'output_base_dir': '~/Music/',
    'size': (1700, 750),
}
WINDOW_KWARGS = {
    'config_name': 'Music Manager',
    'config_path': '~/.config/music_manager/tk_gui_config.json',
    'config': DEFAULT_CONFIG,
    'right_click_menu': FullRightClickMenu(),
    'anchor_elements': 'n',
}


class BaseView(ClearableCachedPropertyMixin, View, ABC, title='Music Manager'):
    menu = MenuProperty(MusicManagerMenuBar)
    window_kwargs = WINDOW_KWARGS
    album: AlbumInfo | AlbumDir
    _scroll_y: bool = False

    def __init_subclass__(cls, scroll_y: bool = None, **kwargs):
        super().__init_subclass__(**kwargs)
        if scroll_y is not None:
            cls._scroll_y = scroll_y

    def __init__(self, *args, prev_view: ViewSpec = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.__prev_view = prev_view

    def __repr__(self) -> str:
        try:
            path_str = self.album.path.as_posix()
        except AttributeError:
            path_str = ''
        return f'<{self.__class__.__name__}[{self.title}][{path_str}]>'

    # region Layout Generation

    def get_pre_window_layout(self) -> Layout:
        yield [self.menu]

    def get_post_window_layout(self) -> Layout:
        if not self.__prev_view:
            yield from self.get_inner_layout()
        else:
            back_button = EventButton(
                '\u2770', key='prev_view', size=(1, 2), pad=(0, 0), font=('Helvetica', 60), anchor='w', side='left'
            )
            frame_cls = YScrollFrame if self._scroll_y else Frame
            content = frame_cls(self.get_inner_layout(), side='top')
            yield Row.custom(self.window, [back_button, content], anchor='c')

    def get_inner_layout(self) -> Layout:
        return []

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
    #     # log_widget_data(self.window, event, parent=True)
    #     log_widget_data(self.window, event)

    # endregion

    # region Run & Previous / Next Views

    @button_handler('prev_view')
    def return_to_prev_view(self, event: Event = None, key=None) -> CallbackAction | None:
        try:
            view_cls, args, kwargs = self.__prev_view
        except TypeError:
            return None
        return self.set_next_view(*args, view_cls=view_cls, **kwargs)

    def get_next_view_spec(self) -> ViewSpec | None:
        try:
            view_cls, args, kwargs = super().get_next_view_spec()
        except TypeError:
            return None
        if album := self.album:
            kwargs['prev_view'] = (self.__class__, (), {'album': album})
        return view_cls, args, kwargs

    # endregion


class InitialView(BaseView, title='Music Manager'):
    window_kwargs = BaseView.window_kwargs | {'exit_on_esc': True, 'anchor_elements': 'c'}
    album = None

    def get_post_window_layout(self) -> Layout:
        button = EventButton('Select Album', key='open', bind_enter=True, size=(30, 5), font=('Helvetica', 20))
        yield [Frame([[button]], anchor='TOP', expand=True)]

    def set_next_view(self, *args, **kwargs):
        from .album import AlbumView

        return super().set_next_view(*args, view_cls=AlbumView, **kwargs)
