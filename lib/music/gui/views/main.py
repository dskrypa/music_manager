"""
Main view for the Music Manager GUI.  All other main window views extend this view.

Defines the top menu and some common configuration properties.

:author: Doug Skrypa
"""

from pathlib import Path
from typing import Any, Optional

from PySimpleGUI import Button, Element, Column, Text, popup, POPUP_BUTTONS_OK, Menu

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
        # layout, kwargs = super().get_render_args()
        layout = []
        if self.__class__ is MainView:
            select_button = Button(
                'Select Album', key='select_album', bind_return_key=True, size=(30, 5), font=('Helvetica', 20)
            )
            # layout.append([Text(key='spacer::4', pad=(0, 0))])
            # # layout.append([Text(key='spacer::1', pad=(0, 0)), select_button, Text(key='spacer::1', pad=(0, 0))])
            # layout.append([select_button])
            # layout.append([Text(key='spacer::3', pad=(0, 0))])

            inner_layout = [
                [Text(key='spacer::2', pad=(0, 0))],
                [select_button],
                [Text(key='spacer::1', pad=(0, 0))],
            ]
            # layout.extend(inner_layout)
            # layout.append([Column(inner_layout, key='col::select_album', justification='center')])
            as_col = Column(
                inner_layout,
                key='col::select_album',
                justification='center',
                vertical_alignment='center',
                pad=(0, 0),
                expand_y=True,
            )

            # layout.append(self.as_workflow(inner_layout))
            # layout.append(self.as_workflow([[select_button]]))

            layout.append([as_col])

        return layout, {}
        # return layout, kwargs

    def render(self):
        # layout, kwargs = self.get_render_args()
        # loc = self.__class__ if self.primary else self
        #
        # menu_row = [Menu(self.menu, key='menu::main')]
        # inner_layout = [
        #     [Text(key='spacer::2', pad=(0, 0))],
        #     *layout,
        #     [Text(key='spacer::1', pad=(0, 0))],
        # ]
        #
        # content_wrapper = Column(
        #     inner_layout,
        #     key='col::__main_outer_wrapper__',
        #     # element_justification='center',
        #     vertical_alignment='center',
        #     justification='center',
        #     # expand_x=True,
        #     expand_y=True,
        #     pad=(0, 0),
        #     # size=loc._window_size
        # )
        # final_layout = [
        #     menu_row,
        #     [content_wrapper]
        # ]
        #
        # loc.window = self._create_window(final_layout, kwargs)
        # loc._window_size = self.window.size
        # if self.binds:
        #     for key, val in self.binds.items():
        #         self.window.bind(key, val)
        # self.log.debug(f'Rendered {self}')

        # content_wrapper.expand(True, True, True)

        super().render()
        spacers = []
        for key, element in self.window.key_dict.items():
            if isinstance(key, str) and key.startswith('spacer::'):
                spacers.append((key, element))

        for key, element in sorted(spacers):
            self.log.debug(f'Expanding element={key!r}')
            element.expand(True, True, True)

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
            'back': {},
            'next': {},
            'content': {
                # 'element_justification': 'center',
                'justification': 'center',
                'vertical_alignment': 'center',
                # 'expand_x': True,
                # 'expand_y': True,
            },
        }
        for key, val in tuple(kwargs.items()):
            if key.startswith(('back_', 'next_')):
                kwargs.pop(key)
                section, arg = key.split('_', 1)
                section_args[section][arg] = val

        kwargs['font'] = ('Helvetica', 60)

        # width, height = self._window_size
        # size = (width - 300, height - 40)
        # size = (width - 200, height - 40)
        # self.log.debug(f'Using workflow content {size=!r}')
        back_btn = Button('\u2770', key=back_key, size=(1, 2), pad=(0, 0), **section_args['back'], **kwargs)
        back_col = Column(
            [[back_btn]],
            key='col::back',
            # size=(70, 300),
            # pad=((10, 5), 0),
            # justification='left',
            # vertical_alignment='center',
            # expand_x=False,
            # expand_y=True,
        )

        as_col = Column(
            content,
            key='col::__inner_content__',
            justification='center',
            vertical_alignment='center',
            pad=(0, 0),
            expand_y=True,
            expand_x=True,
        )

        # content_column = Column(
        #     [[as_col]],
        #     key='col::__outer_content__',
        #     # size=size,
        #     pad=(0, 0),
        #     # **section_args['content']
        #     justification='center',
        #     vertical_alignment='center',
        #     expand_y=True,
        # )
        # content_column = Column(content, key='col::content', size=size, **section_args['content'])

        next_btn = Button('\u2771', key=next_key, size=(1, 2), pad=(0, 0), **section_args['next'], **kwargs)
        next_col = Column(
            [[next_btn]],
            key='col::next',
            # size=(70, 300),
            # pad=((5, 10), 0),
            # justification='right',
            # vertical_alignment='center',
            # expand_x=False,
            # expand_y=True,
        )

        # sp_1 = Text(key='spacer::2', pad=(0, 0))
        # sp_2 = Text(key='spacer::1', pad=(0, 0))

        # return [back_col, sp_1, content_column, sp_2, next_col]
        return [back_col, as_col, next_col]
        # mega_column = Column(
        #     [[back_col, content_column, next_col]], element_justification='center', key='col::mega'
        # )
        # return [mega_column]
