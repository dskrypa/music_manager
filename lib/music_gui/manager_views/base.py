"""
Base view and commonly used config-related utilities for other Music Manager views.
"""

from __future__ import annotations

import logging
from abc import ABC
from collections import defaultdict
from typing import TYPE_CHECKING, Type, Any, Iterable, Mapping

from ds_tools.caching.decorators import cached_property, ClearableCachedPropertyMixin
from tk_gui import CallbackAction, BindEvent, button_handler, event_handler  # noqa
from tk_gui import View
from tk_gui.elements import Frame, EventButton, YScrollFrame, Button, Spacer, MenuProperty
from tk_gui.pseudo_elements import Row
from tk_gui.options import GuiOptions, OptionComponent
from tk_gui.styles.base import DEFAULT_FONT_NAME

from music_gui.config import DirManager, ConfigUpdater
from music_gui.elements.helpers import nav_button
from music_gui.elements.menus import FullRightClickMenu, MusicManagerMenuBar
from music_gui.utils import find_values

if TYPE_CHECKING:
    from tkinter import Event
    from tk_gui import Window, ViewSpec, Layout
    from music.typing import AnyAlbum

__all__ = ['BaseView', 'InitialView']
log = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    'output_base_dir': '~/Music/',
    'size': (1700, 750),
}
TITLE = 'Music Manager'
CFG_PATH = '~/.config/music_manager/tk_gui_config.json'
_CLS_KWARGS = {'title': TITLE, 'config_name': TITLE, 'config_path': CFG_PATH, 'config_defaults': DEFAULT_CONFIG}
WINDOW_KWARGS = {
    'right_click_menu': FullRightClickMenu(),
    'anchor_elements': 'n',
    'margins': (5, 0),
}

_OptionLayout = Iterable[Iterable[OptionComponent]]
_Options = Mapping[str, Any] | GuiOptions | None


class BaseView(ClearableCachedPropertyMixin, View, ABC, **_CLS_KWARGS):
    menu = MenuProperty(MusicManagerMenuBar)
    default_window_kwargs = WINDOW_KWARGS
    album: AnyAlbum
    _scroll_y: bool = False

    def __init_subclass__(cls, scroll_y: bool = None, **kwargs):
        super().__init_subclass__(**kwargs)
        if scroll_y is not None:
            cls._scroll_y = scroll_y

    def __repr__(self) -> str:
        try:
            path_str = self.album.path.as_posix()
        except AttributeError:
            path_str = ''
        return f'<{self.__class__.__name__}[{self.title}][{path_str}]>'

    # region Shared State / Options

    @property
    def state_data(self) -> dict[str, Any]:
        try:
            album_path = self.album.path
        except AttributeError:
            album_path = None
        state_data = self.gui_state.data
        if not state_data or state_data.get('album_path') != album_path:
            return self._reset_state_data(state_data, album_path)
        return state_data

    def reset_state_data(self) -> dict[str, Any]:
        try:
            album_path = self.album.path
        except AttributeError:
            album_path = None
        return self._reset_state_data(self.gui_state.data, album_path)

    def _reset_state_data(self, state_data, album_path) -> dict[str, Any]:  # noqa
        state_data['album_path'] = album_path
        state_data['modified'] = False
        state_data['options'] = defaultdict(dict)
        return state_data

    def get_shared_options(self) -> tuple[dict[str, Any], dict[str, Any]]:
        options = self.state_data['options']
        return options['common'], options[self.__class__.__name__]

    def init_gui_options(self, option_layout: _OptionLayout, options: _Options = None) -> GuiOptions:
        common, previous = self.get_shared_options()
        gui_options = GuiOptions(option_layout)
        mappings = (previous, common, options) if options else (previous, common)
        if overrides := find_values(gui_options.options, *mappings):
            gui_options.update(overrides)
        return gui_options

    def update_gui_options(self, options: _Options):
        if options:
            common, previous = self.get_shared_options()
            common.update(options)
            previous.update(options)

    # endregion

    # region Layout Generation

    # def init_window(self):
    #     from tk_gui.event_handling import ClickHighlighter
    #     window = super().init_window()
    #     kwargs = {'window': window, 'show_config': True, 'show_pack_info': True}
    #     ClickHighlighter(level=0, log_event=True, log_event_kwargs=kwargs).register(window)
    #     return window

    def get_pre_window_layout(self) -> Layout:
        yield [self.menu]

    @cached_property
    def back_button(self) -> Button | None:
        if not self.gui_state.can_go_reverse:
            return None
        return nav_button('left')

    @property
    def next_button(self) -> Button | None:
        return None

    def get_post_window_layout(self) -> Layout:
        back_button, next_button, scroll_y = self.back_button, self.next_button, self._scroll_y
        if back_button is next_button is None and not scroll_y:
            yield from self.get_inner_layout()
        else:
            if scroll_y:
                content = YScrollFrame(self.get_inner_layout(), side='top', pad=(0, 0), fill_y=True)
            else:
                content = Frame(self.get_inner_layout(), side='top', pad=(0, 0))

            if back_button is None:
                back_button = Spacer(size=(53, 241), anchor='w', side='left')
            if next_button is None:
                next_button = Spacer(size=(53, 241), anchor='e', side='right')

            # noinspection PyTypeChecker
            yield Row.custom(self.window, [back_button, next_button, content], anchor='n', expand=True, fill='both')

    def get_inner_layout(self) -> Layout:
        return []

    # endregion

    # region Configuration

    @menu['File']['Settings'].callback
    def update_settings(self, event):
        save, results = ConfigUpdater(self.config).update()
        if save:
            self.clear_cached_properties()
            self.dir_manager.clear_cached_properties()
        return results

    @cached_property
    def dir_manager(self) -> DirManager:
        return DirManager(self.config)

    # endregion

    @classmethod
    def prepare_transition(
        cls, dir_manager: DirManager, *, album: AnyAlbum = None, parent: Window = None, **kwargs
    ) -> ViewSpec | None:
        """Returns a ViewSpec if a transition should be made, or None to stay on the current view."""
        if album:
            return cls.as_view_spec(album)
        elif album_dir := dir_manager.get_album_selection(parent=parent):
            return cls.as_view_spec(album_dir)
        return None

    # region Event Handlers

    @button_handler('open')
    @menu['File']['Open'].callback
    def pick_next_album(self, event: Event, key=None) -> CallbackAction | None:
        if album_dir := self.dir_manager.get_album_selection(parent=self.window):
            return self.go_to_next_view(self.as_view_spec(album_dir))
        return None

    def _maybe_take_action(self, view_cls: Type[BaseView]) -> CallbackAction | None:
        if (album := self.album) and isinstance(self, view_cls):
            album = None
        if spec := view_cls.prepare_transition(self.dir_manager, album=album, parent=self.window):
            return self.go_to_next_view(spec)
        return None

    @menu['Actions']['Clean'].callback
    def take_action_clean(self, event: Event) -> CallbackAction | None:
        from .clean import CleanView

        return self._maybe_take_action(CleanView)

    @menu['Actions']['View Album'].callback
    def take_action_clean(self, event: Event) -> CallbackAction | None:
        from .album import AlbumView

        return self._maybe_take_action(AlbumView)

    @menu['Actions']['Wiki Update'].callback
    def take_action_clean(self, event: Event) -> CallbackAction | None:
        from .wiki_update import WikiUpdateView

        return self._maybe_take_action(WikiUpdateView)

    # endregion

    # region Run & Previous / Next Views

    @button_handler('prev_view')
    def return_to_prev_view(self, event: Event = None, key=None) -> CallbackAction | None:
        return self.go_to_prev_view()

    # endregion


class InitialView(BaseView):
    default_window_kwargs = BaseView.default_window_kwargs | {'exit_on_esc': True, 'anchor_elements': 'c'}
    album = None

    def get_post_window_layout(self) -> Layout:
        button = EventButton('Select Album', key='open', bind_enter=True, size=(30, 5), font=(DEFAULT_FONT_NAME, 20))
        yield [Frame([[button]], anchor='TOP', expand=True)]

    def go_to_next_view(self, spec: ViewSpec, **kwargs) -> CallbackAction:
        if spec.view_cls is self.__class__:
            from .album import AlbumView

            spec.view_cls = AlbumView

        return super().go_to_next_view(spec, forget_last=True)
