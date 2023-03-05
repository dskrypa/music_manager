"""

"""

from __future__ import annotations

import logging
from abc import ABC
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Type, Any, Iterable, Mapping

from ds_tools.caching.decorators import cached_property, ClearableCachedPropertyMixin
from tk_gui.elements import Frame, EventButton, YScrollFrame, Button, Spacer
from tk_gui.elements.menu import MenuProperty
from tk_gui.enums import CallbackAction, BindEvent  # noqa
from tk_gui.event_handling import button_handler, event_handler  # noqa
from tk_gui.popups import popup_input_invalid, pick_folder_popup
from tk_gui.popups.style import StylePopup
from tk_gui.pseudo_elements import Row
from tk_gui.views import View, ViewSpec
from tk_gui.options import GuiOptions, BoolOption, PopupOption, ListboxOption, DirectoryOption, SubmitOption
from tk_gui.options.layout import OptionComponent

from music.files.album import AlbumDir
from music.files.exceptions import InvalidAlbumDir
from music_gui.elements.helpers import nav_button
from music_gui.elements.menus import FullRightClickMenu, MusicManagerMenuBar
from music_gui.utils import find_values

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
    'margins': (5, 0),
}

_OptionLayout = Iterable[Iterable[OptionComponent]]
_Options = Mapping[str, Any] | GuiOptions | None


class BaseView(ClearableCachedPropertyMixin, View, ABC, title='Music Manager'):
    menu = MenuProperty(MusicManagerMenuBar)
    default_window_kwargs = WINDOW_KWARGS
    album: AlbumInfo | AlbumDir
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
        if state_data.get('album_path') != album_path:
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
            frame_cls = YScrollFrame if scroll_y else Frame
            kwargs = {'fill_y': True, 'scroll_y_amount': 1} if scroll_y else {}
            content = frame_cls(self.get_inner_layout(), side='top', pad=(0, 0), **kwargs)
            if back_button is None:
                back_button = Spacer(size=(53, 241), anchor='w', side='left')
            if next_button is None:
                next_button = Spacer(size=(53, 241), anchor='e', side='right')
            yield Row.custom(self.window, [back_button, next_button, content], anchor='n', expand=True, fill='both')

    def get_inner_layout(self) -> Layout:
        return []

    # endregion

    # region Configuration

    @menu['File']['Settings'].callback
    def update_settings(self, event):
        config = self.window.config
        log.debug(f'Preparing options view for {config.data=}')
        kwargs = {'label_size': (16, 1), 'size': (30, None)}

        rm_kwargs = {'extendable': True, 'prompt_name': 'tag to remove'} | kwargs
        style_kwargs = {'popup_kwargs': {'show_buttons': True}} | kwargs
        layout = [
            [
                BoolOption('remember_pos', 'Remember Last Window Position', config.remember_position),
                BoolOption('remember_size', 'Remember Last Window Size', config.remember_size),
            ],
            [PopupOption('style', 'Style', StylePopup, default=config.style, **style_kwargs)],
            [DirectoryOption('output_base_dir', 'Output Directory', default=config['output_base_dir'], **kwargs)],
            [ListboxOption('rm_tags', 'Tags to Remove', config.get('rm_tags', []), **rm_kwargs)],
            [SubmitOption('save', 'Save')],
        ]

        results = GuiOptions(layout).run_popup()
        log.debug(f'Options view {results=}')
        if results.pop('save', False):
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

    # @event_handler(BindEvent.LEFT_CLICK.event)
    # def _handle_left_click(self, event: Event):
    #     from tk_gui.widgets.utils import log_event_widget_data
    #
    #     log_event_widget_data(self.window, event)
    #     # log_event_widget_data(self.window, event, parent=True)
    #     # log_event_widget_data(self.window, event, show_config=True)

    @button_handler('open')
    @menu['File']['Open'].callback
    def pick_next_album(self, event: Event, key=None) -> CallbackAction | None:
        if album_dir := self.get_album_selection():
            return self.go_to_next_view(self.as_view_spec(album_dir))
        return None

    def _maybe_take_action(self, view_cls: Type[View]) -> CallbackAction | None:
        if (album := self.album) and not isinstance(self, view_cls):
            return self.go_to_next_view(view_cls.as_view_spec(album))
        elif album_dir := self.get_album_selection():
            return self.go_to_next_view(view_cls.as_view_spec(album_dir))
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

    # def set_next_view(
    #     self, *args, view_cls: Type[View] = None, retain_prev_view: bool = False, **kwargs
    # ) -> CallbackAction:
    #     if retain_prev_view:
    #         kwargs['prev_view'] = self.__prev_view
    #     elif view_cls is None:
    #         kwargs.setdefault('prev_view', None)
    #     return super().set_next_view(*args, view_cls=view_cls, **kwargs)

    # def get_next_view_spec(self) -> ViewSpec | None:
    #     try:
    #         view_cls, args, kwargs = super().get_next_view_spec()
    #     except TypeError:
    #         return None
    #     # if (album := self.album) and 'prev_view' not in kwargs:
    #     #     kwargs['prev_view'] = (self.__class__, (), {'album': album})
    #     return view_cls, args, kwargs

    # endregion


class InitialView(BaseView, title='Music Manager'):
    default_window_kwargs = BaseView.default_window_kwargs | {'exit_on_esc': True, 'anchor_elements': 'c'}
    album = None

    def get_post_window_layout(self) -> Layout:
        button = EventButton('Select Album', key='open', bind_enter=True, size=(30, 5), font=('Helvetica', 20))
        yield [Frame([[button]], anchor='TOP', expand=True)]

    def go_to_next_view(self, spec: ViewSpec, **kwargs) -> CallbackAction:
        from .album import AlbumView

        spec.view_cls = AlbumView
        return super().go_to_next_view(spec, forget_last=True)
