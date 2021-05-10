"""
View: Path Prompt

Mainly added this to just be able to make ESC work to cancel the path prompt...

:author: Doug Skrypa
"""

from enum import Enum
from pathlib import Path
from tkinter.filedialog import askdirectory, asksaveasfilename, askopenfilenames, askopenfilename
from typing import Any, Union, Optional, Collection

from PySimpleGUI import Element, Text, Button, FolderBrowse, FileBrowse, FilesBrowse, SaveAs

from ..base_view import event_handler
from ..elements.inputs import DarkInput as Input
from .base import BasePopup
from .utils import temp_hidden_window
from .simple import popup_ok

__all__ = ['PathPromptView', 'PathPromptType', 'get_directory', 'get_file_path', 'get_save_path', 'get_file_paths']


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


class PathPromptView(BasePopup, view_name='path_prompt', primary=False):
    def __init__(
        self,
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
        super().__init__(binds={'<Escape>': 'Exit'}, title=title)
        self.type = PathPromptType(prompt_type)
        if self.type == PathPromptType.DIR and (default_extension or file_types):
            raise ValueError('Arguments default_extension/file_types are not supported for directory prompts')
        self.prompt = prompt
        self.init_path = '' if default_path is None else Path(default_path).as_posix()
        self.init_dir = '' if initial_folder is None else Path(initial_folder).as_posix()
        self.no_window = no_window
        self.ext = default_extension or ''
        self.file_types = tuple(file_types) if file_types else (('All Files', '*.*'),)

    def _without_window(self):
        kwargs = {'initialdir': self.init_dir, 'title': self.title or self.prompt}
        if self.type != PathPromptType.DIR:
            kwargs.update(filetypes=self.file_types, initialfile=self.init_path, defaultextension=self.ext)
        if self.window is not None and (root := self.window.TKroot) is not None:
            return NO_WIN_FUNCS[self.type](parent=root, **kwargs)
        with temp_hidden_window(self.log) as root:
            return NO_WIN_FUNCS[self.type](parent=root, **kwargs)

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

    @event_handler('OK')
    def submit(self, event: str, data: dict[str, Any]):
        self.result = data['_INPUT_']
        raise StopIteration

    def get_path(self, must_exist: bool = True) -> Optional[Path]:
        if self.type == PathPromptType.MULTI:
            raise AssertionError(f'{self.__class__.__name__}.get_path() is not supported with prompt type=multiple')

        if self.no_window:
            if not (path := self._without_window()):
                return None
            path = Path(path) if isinstance(path, str) else Path(path[0])
        else:
            self.render()
            self.run()
            if not self.result:
                return None
            path = Path(self.result).expanduser()

        if self.type == PathPromptType.DIR:
            if (must_exist and not path.is_dir()) or (path.exists() and not path.is_dir()):
                return popup_ok(f'Invalid directory: {path}', title='Invalid directory')
        elif must_exist and not path.is_file():
            return popup_ok(f'Invalid file: {path}', title='Invalid file')
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
            return [Path(p).expanduser() for p in self.result.split(';')] if self.result else []


def get_directory(*args, must_exist: bool = True, **kwargs) -> Optional[Path]:
    return PathPromptView(PathPromptType.DIR, *args, **kwargs).get_path(must_exist)


def get_file_path(*args, must_exist: bool = True, **kwargs) -> Optional[Path]:
    return PathPromptView(PathPromptType.FILE, *args, **kwargs).get_path(must_exist)


def get_save_path(*args, must_exist: bool = False, **kwargs) -> Optional[Path]:
    return PathPromptView(PathPromptType.SAVE, *args, **kwargs).get_path(must_exist)


def get_file_paths(*args, **kwargs) -> list[Path]:
    return PathPromptView(PathPromptType.FILE, *args, **kwargs).get_paths()
