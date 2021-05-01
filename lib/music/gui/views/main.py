"""
Main view for the Music Manager GUI.  All other main window views extend this view.

Defines the top menu and some common configuration properties.

:author: Doug Skrypa
"""

import webbrowser
from functools import cached_property
from pathlib import Path
from typing import Optional, Any, Type

from PySimpleGUI import Button, Element, Column, Text, Image

from tz_aware_dt.tz_aware_dt import now
from ds_tools.core.decorate import classproperty
from ...files.album import AlbumDir
from ...files.exceptions import InvalidAlbumDir
from ..state import GuiState
from .base import event_handler, BaseView, Layout, Event, EventData, RenderArgs
from .popups.path_prompt import get_directory
from .popups.simple import popup_input_invalid
from .popups.text import popup_error
from .utils import split_key

__all__ = ['MainView']

DEFAULT_OUTPUT_DIR = '~/Music/'
BACK_BIND = '<Control-Left>'
NEXT_BIND = '<Control-Right>'


class MainView(BaseView, view_name='main'):
    back_tooltip = 'Go back to previous view'
    state = GuiState()

    def __init__(self, *, last_view: 'MainView' = None, **kwargs):
        super().__init__(**kwargs)
        self.last_view = last_view
        self.menu = [
            ['&File', ['&Open', 'Ou&tput', 'E&xit']],
            ['&Actions', ['&Clean', '&Edit', '&Wiki Update', '&Sync Ratings']],
            ['&Help', ['&About']],
        ]
        self.binds[BACK_BIND] = 'ctrl_left'
        self.binds[NEXT_BIND] = 'ctrl_right'
        self._back_key = None
        self._next_key = None

    @event_handler
    def ctrl_left(self, event: Event, data: EventData):
        if self._back_key:
            return self.handle_event(self._back_key, data)

    @event_handler
    def ctrl_right(self, event: Event, data: EventData):
        if self._next_key:
            return self.handle_event(self._next_key, data)

    @classproperty
    def output_base_dir(cls) -> Path:
        return Path(cls.state.get('output_base_dir', DEFAULT_OUTPUT_DIR)).expanduser()

    @classproperty
    def output_sorted_dir(cls) -> Path:
        return cls.output_base_dir.joinpath('sorted_{}'.format(now('%Y-%m-%d')))

    @cached_property
    def display_name(self) -> str:
        return self.name.replace('_', ' ').title()

    def get_render_args(self) -> RenderArgs:
        layout, kwargs = super().get_render_args()
        if self.__class__ is MainView:
            select_button = Button(
                'Select Album', key='select_album', bind_return_key=True, size=(30, 5), font=('Helvetica', 20)
            )
            inner_layout = [[Text(key='spacer::2', pad=(0, 0))], [select_button], [Text(key='spacer::1', pad=(0, 0))]]
            as_col = Column(
                inner_layout,
                key='col::select_album',
                justification='center',
                vertical_alignment='center',
                pad=(0, 0),
                expand_y=True,
            )
            layout.append([as_col])

        kwargs.setdefault('title', f'Music Manager - {self.display_name}')
        return layout, kwargs

    def render(self):
        super().render()
        for key, element in self.window.key_dict.items():
            if isinstance(key, str):
                if key.startswith('spacer::'):
                    element.expand(True, True, True)

    @classmethod
    def _get_last_dir(cls) -> Optional[Path]:
        if last_dir := cls.state.get('last_dir'):
            last_dir = Path(last_dir)
            if not last_dir.exists():
                if last_dir.parent.exists():
                    return last_dir.parent
                else:
                    return cls.output_base_dir
        return None

    def get_album_selection(self, new: bool = False) -> Optional[AlbumDir]:
        if not new:
            if album := getattr(self, 'album', None):
                return album

        last_dir = self._get_last_dir()
        if path := get_directory('Select Album', no_window=True, initial_folder=last_dir):
            self.window.force_focus()  # Can't seem to avoid it losing it perceptibly, but this brings it back faster
            if path != last_dir:
                self.state['last_dir'] = path.as_posix()
                self.state.save()
            self.log.debug(f'Selected album {path=}')
            try:
                return AlbumDir(path)
            except InvalidAlbumDir as e:
                popup_input_invalid(str(e), logger=self.log)
        else:
            self.window.force_focus()

        return None

    @event_handler('Open')
    def select_album(self, event: Event, data: EventData):
        if album := self.get_album_selection(True):
            from .album import AlbumView

            return AlbumView(album, last_view=self)

    @event_handler
    def init_view(self, event: Event, data: EventData):
        data = data[event]
        path = data['path']
        if (view := data['view']) == 'album':
            from .album import AlbumView
            try:
                album = AlbumDir(path)
            except InvalidAlbumDir as e:
                popup_input_invalid(str(e), logger=self.log)
            else:
                return AlbumView(album, last_view=self)
        elif view == 'clean':
            from .clean import CleanView

            return CleanView(path=path, last_view=self)
        else:
            popup_input_invalid(f'Unexpected initial {view=!r}', logger=self.log)

    @event_handler
    def edit(self, event: Event, data: EventData):
        if album := self.get_album_selection():
            from .album import AlbumView

            return AlbumView(album, getattr(self, 'album_formatter', None), editing=True, last_view=self)

    @event_handler
    def clean(self, event: Event, data: EventData):
        if album := self.get_album_selection():
            from .clean import CleanView

            return CleanView(album, last_view=self)

    @event_handler
    def output(self, event: Event, data: EventData):
        current = self.output_base_dir.as_posix()
        kwargs = dict(must_exist=False, no_window=False, default_path=current, initial_folder=current)
        if path := get_directory('Select Output Directory', **kwargs):
            if self.output_base_dir != path:
                self.log.debug(f'Updating saved output base directory from {current} -> {path.as_posix()}')
                self.state['output_base_dir'] = path.as_posix()
                self.state.save()
            else:
                self.log.debug(f'Selected output base directory path={path.as_posix()} == current={current}')

    @event_handler
    def wiki_update(self, event: Event, data: EventData):
        if album := self.get_album_selection():
            from .wiki_update import WikiUpdateView

            return WikiUpdateView(album, getattr(self, 'album_formatter', None), last_view=self)

    def as_workflow(
        self,
        content: Layout,
        back_key: str = 'btn::back',
        next_key: str = 'btn::next',
        scrollable: bool = False,
        **kwargs
    ) -> list[Element]:
        self._back_key = back_key
        self._next_key = next_key
        section_args = {'back': {}, 'next': {}}
        for key, val in tuple(kwargs.items()):
            if key.startswith(('back_', 'next_')):
                kwargs.pop(key)
                section, arg = key.split('_', 1)
                section_args[section][arg] = val

        if self.last_view:
            section_args['back'].setdefault('tooltip', self.last_view.back_tooltip)

        kwargs.update(size=(1, 2), pad=(0, 0), font=('Helvetica', 60))
        back_col = Column([[Button('\u2770', key=back_key, **section_args['back'], **kwargs)]], key='col::back')
        next_col = Column([[Button('\u2771', key=next_key, **section_args['next'], **kwargs)]], key='col::next')

        content_args = dict(justification='center', vertical_alignment='center', expand_y=True, expand_x=True)
        if scrollable:
            content_args.update(scrollable=True, vertical_scroll_only=True)
            # The below Image is a workaround to make it possible to center scrollable columns.
            win_w, win_h = self._window_size
            # back/next button column widths: 55px each => 110 + outer padding (10px each) => 130
            # + inner padding (left, 10px) => 140
            # + scrollbar (17px) => 157 + ??? (2px) => 159
            content.append([Image(size=(win_w - 159, 1), pad=(0, 0), key='img::workflow::spacer')])

        content_column = Column(content, key='col::__inner_content__', pad=(0, 0), **content_args)

        return [back_col, content_column, next_col]

    def _back_kwargs(self, last: 'MainView') -> dict[str, Any]:
        return {}

    @event_handler('btn::back')
    def back(self, event: Event, data: EventData, default_cls: Type['MainView'] = None):
        if ((last := self.last_view) is not None) or default_cls is not None:
            kwargs = {'last_view': self, **self._back_kwargs(last)}
            to_copy = [
                (last, 'options'), (last, 'src_album'), (last, 'dst_album'), (self, 'album'), (self, 'album_formatter')
            ]
            for obj, attr in to_copy:
                try:
                    kwargs[attr] = getattr(obj, attr)
                except AttributeError:
                    pass

            cls = last.__class__ if last else default_cls
            self.log.debug(f'Returning previous view={cls.__name__} with {kwargs=}')
            return cls(**kwargs)

        self.log.warning(f'The back button was clicked, but there was no last view to return to', extra={'color': 11})

    @event_handler
    def open_link(self, event: Event, data: EventData):
        # self.log.debug(f'Open link request received for {event=!r}')
        key = event.rsplit(':::', 1)[0]
        webbrowser.open(data[key])

    @event_handler('img::*')
    def image_clicked(self, event: Event, data: EventData):
        from .popups.image import ImageView

        if album_formatter := getattr(self, 'album_formatter', None):
            img_src = split_key(event)[1]
            if img_src == 'album':
                return ImageView(
                    album_formatter.cover_image_full_obj, f'Album Cover: {album_formatter.album_info.name}'
                )
            else:
                track_formatter = album_formatter.track_formatters[img_src]
                return ImageView(track_formatter.cover_image_obj, f'Track Album Cover: {track_formatter.file_name}')

    @event_handler
    def sync_ratings(self, event: Event, data: EventData):
        from .rating_sync import SyncRatingsView

        try:
            return SyncRatingsView(last_view=self)
        except ValueError as e:
            popup_error(str(e))
