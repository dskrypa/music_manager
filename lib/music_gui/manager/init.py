"""
Initial view for the Music Manager GUI.

Defines the top menu and some common configuration properties.

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Union

from tk_gui.elements.menu.menu import Menu, MenuGroup, MenuItem, MenuProperty
from tk_gui.elements.menu.items import CloseWindow
from tk_gui.elements import Button, Frame
from tk_gui.popups import PickFolder, popup_input_invalid
from tk_gui.popups.about import AboutPopup
from tk_gui.popups.style import StylePopup
from tk_gui.views.view import View
from tk_gui.options import GuiOptions

from ds_tools.caching.decorators import cached_property

from music.files.album import AlbumDir
from music.files.exceptions import InvalidAlbumDir

if TYPE_CHECKING:
    from tkinter import Event
    from tk_gui.typing import Layout

__all__ = ['InitialView']
log = logging.getLogger(__name__)

DEFAULT_CONFIG = {'output_base_dir': '~/Music/'}


class MenuBar(Menu):
    with MenuGroup('File'):
        MenuItem('Open')
        MenuItem('Settings')
        CloseWindow()
    with MenuGroup('Actions'):
        MenuItem('Clean', lambda e: print('TODO'))
        MenuItem('Edit', lambda e: print('TODO'))
        MenuItem('Wiki Update', lambda e: print('TODO'))
        MenuItem('Sync Ratings', lambda e: print('TODO'))
    with MenuGroup('Help'):
        MenuItem('About', AboutPopup)


class InitialView(View, title='Music Manager'):
    window_kwargs = {'config': DEFAULT_CONFIG}
    menu = MenuProperty(MenuBar)

    # region Configuration

    @menu['File']['Settings'].callback
    def update_settings(self, event):
        config = self.window.config
        options = GuiOptions(submit='Save', title=None)
        with options.next_row() as options:
            options.add_bool('remember_pos', 'Remember Last Window Position', config.remember_position)
            options.add_bool('remember_size', 'Remember Last Window Size', config.remember_size)
        with options.next_row() as options:
            options.add_popup('style', 'Style', StylePopup, default=config.style, popup_kwargs={'show_buttons': True})
        with options.next_row() as options:
            options.add_directory('output_base_dir', 'Output Directory', config['output_base_dir'])
        with options.next_row() as options:
            options.add_listbox(
                'rm_tags', 'Tags to Remove', config.get('rm_tags', []), extendable=True, prompt_name='tag to remove'
            )

        results = options.run_popup()
        config.update(results, ignore_none=True, ignore_empty=True)
        return results

    @cached_property
    def output_base_dir(self) -> Path:
        return Path(self.window.config['output_base_dir']).expanduser()

    @cached_property
    def output_sorted_dir(self) -> Path:
        date_str = date.today().strftime('%Y-%m-%d')
        return self.output_base_dir.joinpath(f'sorted_{date_str}')

    # endregion

    def get_init_layout(self) -> Layout:
        select_button = Button(
            'Select Album', key='select_album', bind_enter=True, size=(30, 5), font=('Helvetica', 20)
        )
        layout = [
            [self.menu],
            [Frame([[select_button]], anchor='TOP', expand=True)],
        ]
        return layout

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

    def get_album_selection(self, new: bool = False, require_album: bool = True) -> Optional[Union[AlbumDir, Path]]:
        if not new:
            if album := getattr(self, 'album', None):
                return album

        last_dir = self._get_last_dir()
        if path := PickFolder(last_dir).run():
            self.window.take_focus()  # Can't seem to avoid it losing it perceptibly, but this brings it back faster
            if path != last_dir:
                self.window.config['last_dir'] = path.as_posix()
                self.window.config.save()

            log.debug(f'Selected album {path=}')
            if require_album:
                try:
                    return AlbumDir(path)
                except InvalidAlbumDir as e:
                    popup_input_invalid(str(e), logger=log)
            else:
                return path
        else:
            self.window.take_focus()

        return None

    @menu['File']['Open'].callback
    def select_album(self, event: Event):
        if album := self.get_album_selection(True):
            print(f'Selected {album=}')
        else:
            print('No album was selected')


if __name__ == '__main__':
    InitialView().run()
