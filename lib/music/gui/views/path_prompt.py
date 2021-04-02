"""
View: Path Prompt

Mainly added this to just be able to make ESC work to cancel the path prompt...

:author: Doug Skrypa
"""

import logging
from enum import Enum
from tkinter.filedialog import askdirectory, asksaveasfilename, askopenfilenames, askopenfilename
from pathlib import Path
from typing import Any, Union, Optional, Collection

from PySimpleGUI import Element, Text, Input, Button, FolderBrowse, FileBrowse, FilesBrowse, SaveAs, Popup

from .base import event_handler, GuiView, ViewManager
from .utils import temp_hidden_window

__all__ = ['PathPromptView', 'PathPromptType', 'get_directory', 'get_file_path', 'get_save_path', 'get_file_paths']
log = logging.getLogger(__name__)


class PathPromptType(Enum):
    DIR = 'directory'
    FILE = 'file'
    SAVE = 'save'
    MULTI = 'multiple'


NO_WIN_FUNCS = {
    PathPromptType.FILE: askopenfilename,
    PathPromptType.SAVE: asksaveasfilename,
    PathPromptType.MULTI: askopenfilenames,
    PathPromptType.DIR: askdirectory,
}


class PathPromptView(GuiView, view_name='path_prompt', primary=False):
    def __init__(
        self,
        mgr: 'ViewManager',
        prompt_type: Union[str, PathPromptType],
        prompt: str,
        *,
        title: str = None,
        default_path: Union[str, Path] = None,
        initial_folder: Union[str, Path] = None,
        no_window: bool = False,
        default_extension: str = None,
        file_types: Collection[tuple[str, str]] = None,
    ):
        super().__init__(mgr, binds={'<Escape>': 'Exit'})
        self.type = PathPromptType(prompt_type)
        if self.type == PathPromptType.DIR and (default_extension or file_types):
            raise ValueError('Arguments default_extension/file_types are not supported for directory prompts')
        self.prompt = prompt
        self.title = title
        self.init_path = '' if default_path is None else Path(default_path).as_posix()
        self.init_dir = '' if initial_folder is None else Path(initial_folder).as_posix()
        self.no_window = no_window
        self.ext = default_extension or ''
        self.file_types = tuple(file_types) if file_types else (('ALL Files', '*.*'),)
        self._selection: Optional[str] = None

    @event_handler(default=True)  # noqa
    def default(self, event: str, data: dict[str, Any]):
        raise StopIteration

    def _without_window(self):
        with temp_hidden_window() as root:
            if self.type == PathPromptType.DIR:
                path = NO_WIN_FUNCS[self.type](initialdir=self.init_dir)
            else:
                path = NO_WIN_FUNCS[self.type](
                    parent=root,
                    filetypes=self.file_types,
                    initialdir=self.init_dir,
                    initialfile=self.init_path,
                    defaultextension=self.ext,
                )

        return path

    def get_render_args(self) -> tuple[list[list[Element]], dict[str, Any]]:
        if self.type == PathPromptType.DIR:
            browse = FolderBrowse(initial_folder=self.init_dir)
        else:
            kwargs = {'file_types': self.file_types, 'initial_folder': self.init_dir}
            if self.type == PathPromptType.SAVE:
                browse = SaveAs(default_extension=self.ext, **kwargs)
            elif self.type == PathPromptType.MULTI:
                browse = FilesBrowse(files_delimiter=';', **kwargs)
            elif self.type == PathPromptType.FILE:
                browse = FileBrowse(**kwargs)
            else:
                raise ValueError(f'Unexpected prompt type={self.type!r}')

        layout = [
            [Text(self.prompt, auto_size_text=True)],
            [Input(default_text=self.init_path, key='_INPUT_'), browse],
            [Button('OK', size=(6, 1), bind_return_key=True), Button('Cancel', size=(6, 1))]
        ]
        return layout, {'title': self.title or self.prompt, 'auto_size_text': True}

    @event_handler('OK')  # noqa
    def submit(self, event: str, data: dict[str, Any]):
        self._selection = data['_INPUT_']
        raise StopIteration

    def get_path(self, must_exist: bool = True) -> Optional[Path]:
        if self.type == PathPromptType.MULTI:
            raise AssertionError(f'{self.__class__.__name__}.get_path() is not supported with prompt type=multiple')

        if self.no_window:
            path = self._without_window()
            if not path:
                return None
            path = Path(path) if isinstance(path, str) else Path(path[0])
        else:
            self.render()
            self.run()
            if not self._selection:
                return None
            path = Path(self._selection).expanduser()

        if self.type == PathPromptType.DIR:
            if (must_exist and not path.is_dir()) or (path.exists() and not path.is_dir()):
                Popup(f'Invalid directory: {path}', title='Invalid directory')
                return None
        elif must_exist and not path.is_file():
            Popup(f'Invalid file: {path}', title='Invalid file')
            return None
        return path

    def get_paths(self) -> list[Path]:
        if self.type != PathPromptType.MULTI:
            raise AssertionError(f'{self.__class__.__name__}.get_paths() is only supported with prompt type=multiple')

        if self.no_window:
            paths = self._without_window()
            return [Path(p) for p in paths] if paths else []
        else:
            self.render()
            self.run()
            return [Path(p).expanduser() for p in self._selection.split(';')] if self._selection else []


def get_directory(mgr: 'ViewManager', *args, must_exist: bool = True, **kwargs) -> Optional[Path]:
    return PathPromptView(mgr, PathPromptType.DIR, *args, **kwargs).get_path(must_exist)


def get_file_path(mgr: 'ViewManager', *args, must_exist: bool = True, **kwargs) -> Optional[Path]:
    return PathPromptView(mgr, PathPromptType.FILE, *args, **kwargs).get_path(must_exist)


def get_save_path(mgr: 'ViewManager', *args, must_exist: bool = False, **kwargs) -> Optional[Path]:
    return PathPromptView(mgr, PathPromptType.SAVE, *args, **kwargs).get_path(must_exist)


def get_file_paths(mgr: 'ViewManager', *args, **kwargs) -> list[Path]:
    return PathPromptView(mgr, PathPromptType.FILE, *args, **kwargs).get_paths()
