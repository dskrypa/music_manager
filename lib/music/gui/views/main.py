"""
Main view for the Music Manager GUI.  All other main window views extend this view.

Defines the top menu and some common configuration properties.

:author: Doug Skrypa
"""

from functools import cached_property
from pathlib import Path
from typing import Optional, Any, Type, Union

from PySimpleGUI import Button, Element, Column, Text, Image, Menu

from tz_aware_dt.tz_aware_dt import now
from ds_tools.core.decorate import classproperty
from ...files.album import AlbumDir
from ...files.exceptions import InvalidAlbumDir
from ..base_view import event_handler, GuiView, Layout, Event, EventData, RenderArgs
from ..popups.path_prompt import get_directory
from ..popups.simple import popup_input_invalid
from ..popups.text import popup_error

__all__ = ['MainView']

BACK_BIND = '<Control-Left>'
NEXT_BIND = '<Control-Right>'
DEFAULT_SETTINGS = {'output_base_dir': '~/Music/'}


class MainView(GuiView, view_name='main', defaults=DEFAULT_SETTINGS):
    back_tooltip = 'Go back to previous view'

    def __init__(self, *, last_view: 'MainView' = None, **kwargs):
        super().__init__(binds=kwargs.get('binds'))
        self.last_view = last_view
        self.menu = [
            ['&File', ['&Open', '&Settings', 'E&xit']],
            ['&Actions', ['&Clean', '&Edit', '&Wiki Update', 'Sync &Ratings']],
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
        return Path(cls.state['output_base_dir']).expanduser()

    @classproperty
    def output_sorted_dir(cls) -> Path:
        return cls.output_base_dir.joinpath('sorted_{}'.format(now('%Y-%m-%d')))

    @cached_property
    def display_name(self) -> str:
        return self.name.replace('_', ' ').title()

    def get_render_args(self) -> RenderArgs:
        layout = [[Menu(self.menu)]]
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

        kwargs = {'title': f'Music Manager - {self.display_name}'}
        return layout, kwargs

    def render(self):
        super().render()
        for key, element in self.window.key_dict.items():
            if isinstance(key, str):
                if key.startswith('spacer::'):
                    element.expand(True, True, True)

    @classmethod
    def _get_last_dir(cls, type: str = None) -> Optional[Path]:
        if last_dir := cls.state.get(f'last_dir:{type}' if type else 'last_dir'):
            last_dir = Path(last_dir)
            if not last_dir.exists():
                if last_dir.parent.exists():
                    return last_dir.parent
                else:
                    return cls.output_base_dir
            else:
                return last_dir
        return None

    def get_album_selection(self, new: bool = False, require_album: bool = True) -> Optional[Union[AlbumDir, Path]]:
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
            if require_album:
                try:
                    return AlbumDir(path)
                except InvalidAlbumDir as e:
                    popup_input_invalid(str(e), logger=self.log)
            else:
                return path
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
        if album := self.get_album_selection(require_album=False):
            from .clean import CleanView

            kwargs = {'album' if isinstance(album, AlbumDir) else 'path': album}
            return CleanView(last_view=self, **kwargs)

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
    def sync_ratings(self, event: Event, data: EventData):
        from .rating_sync import SyncRatingsView

        try:
            return SyncRatingsView(last_view=self)
        except ValueError as e:
            popup_error(str(e))

    @event_handler
    def about(self, event: Event, data: EventData):
        from .popups.about import AboutView

        return AboutView()

    @event_handler
    def settings(self, event: Event, data: EventData):
        from .popups.settings import SettingsView

        return SettingsView()
