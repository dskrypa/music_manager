"""
Main view for the Music Manager GUI.  All other main window views extend this view.

Defines the top menu and some common configuration properties.

:author: Doug Skrypa
"""

from pathlib import Path
from typing import Any, Optional

from PySimpleGUI import Button, Element, Column, Text, popup, POPUP_BUTTONS_OK

from tz_aware_dt.tz_aware_dt import now
from ...files.album import AlbumDir
from ...files.exceptions import InvalidAlbumDir
from ..prompts import popup_input_invalid
from ..state import GuiState
from .base import event_handler, BaseView
from .path_prompt import get_directory

__all__ = ['MainView']

DEFAULT_OUTPUT_DIR = '~/Music/'


class MainView(BaseView, view_name='main'):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.state = GuiState()
        self.menu = [
            ['File', ['Open', 'Output', 'Exit']],
            ['Actions', ['Clean', 'Edit', 'Wiki Update']],
            ['Help', ['About']],
        ]

    @property
    def output_base_dir(self) -> Path:
        return Path(self.state.get('output_base_dir', DEFAULT_OUTPUT_DIR)).expanduser()

    @property
    def output_sorted_dir(self) -> Path:
        return self.output_base_dir.joinpath('sorted_{}'.format(now('%Y-%m-%d')))

    def get_render_args(self) -> tuple[list[list[Element]], dict[str, Any]]:
        layout, kwargs = super().get_render_args()
        if self.__class__ is MainView:
            select_button = Button(
                'Select Album', key='select_album', bind_return_key=True, size=(30, 5), font=('Helvetica', 20)
            )
            layout.append([Text(key='__TOP_SPACER__', pad=(0, 0))])
            layout.append([select_button])
            layout.append([Text(key='__BOTTOM_SPACER__', pad=(0, 0))])
        return layout, kwargs

    def render(self):
        super().render()
        if self.__class__ is MainView:
            for key in ('__BOTTOM_SPACER__', '__TOP_SPACER__'):
                try:
                    self.window.key_dict[key].expand(True, True, True)
                except KeyError:
                    pass

    def get_album_selection(self, new: bool = False) -> Optional[AlbumDir]:
        if not new:
            if album := getattr(self, 'album', None):
                return album

        if path := get_directory('Select Album', no_window=True):
            self.window.force_focus()  # Can't seem to avoid it losing it perceptibly, but this brings it back faster
            self.log.debug(f'Selected album {path=}')
            try:
                return AlbumDir(path)
            except InvalidAlbumDir as e:
                popup_input_invalid(str(e))
        else:
            self.window.force_focus()

        return None

    @event_handler('Open')  # noqa
    def select_album(self, event: str, data: dict[str, Any]):
        if album := self.get_album_selection(True):
            from .album import AlbumView

            return AlbumView(album)

    @event_handler
    def edit(self, event: str, data: dict[str, Any]):
        if album := self.get_album_selection():
            from .album import AlbumView

            return AlbumView(album, getattr(self, 'album_block', None), editing=True)

    @event_handler
    def clean(self, event: str, data: dict[str, Any]):
        if album := self.get_album_selection():
            from .clean import CleanView

            return CleanView(album)

    @event_handler
    def output(self, event: str, data: dict[str, Any]):
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
    def wiki_update(self, event: str, data: dict[str, Any]):
        popup('Wiki update is not implemented yet.', title='', button_type=POPUP_BUTTONS_OK, any_key_closes=True)

    def as_workflow(
        self, content: list[list[Element]], back_key: str = 'btn::back', next_key: str = 'btn::next', **kwargs
    ) -> list[Element]:
        section_args = {
            'back': {}, 'next': {}, 'content': {'element_justification': 'center', 'justification': 'center'}
        }
        for key, val in tuple(kwargs.items()):
            if key.startswith(('back_', 'next_')):
                kwargs.pop(key)
                section, arg = key.split('_', 1)
                section_args[section][arg] = val

        kwargs['font'] = ('Helvetica', 60)
        width, height = self._window_size
        size = (width - 150, height - 40)
        back_btn = Button('\u2770', key=back_key, size=(1, 2), pad=(0, 0), **section_args['back'], **kwargs)
        content_column = Column(content, key='col::content', size=size, pad=(0, 0), **section_args['content'])
        next_btn = Button('\u2771', key=next_key, size=(1, 2), pad=(0, 0), **section_args['next'], **kwargs)
        return [Column([[back_btn]], key='col::back'), content_column, Column([[next_btn]], key='col::next')]
