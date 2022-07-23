"""
Tkinter GUI low level popups, including file prompts

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
from abc import ABC
from pathlib import Path
from tkinter import filedialog, colorchooser
from typing import Union, Collection, Optional

from .base import Popup
from ..utils import ON_MAC

__all__ = ['PickFolder', 'PickFile', 'PickFiles', 'SaveAs', 'PickColor']
log = logging.getLogger(__name__)

PathLike = Union[Path, str]
FileTypes = Collection[tuple[str, str]]

ALL_FILES = (('ALL Files', '*.* *'),)


class RawPopup(Popup, ABC):
    def _get_root(self):
        if parent := self.parent:
            return parent.root
        else:
            return None


# region File Prompts


class FilePopup(RawPopup, ABC):
    def __init__(self, initial_dir: PathLike = None):
        super().__init__()
        self.initial_dir = initial_dir


class PickFolder(FilePopup):
    def _run(self) -> Optional[Path]:
        kwargs = {} if ON_MAC else {'parent': self._get_root()}
        if name := filedialog.askdirectory(initialdir=self.initial_dir, **kwargs):
            return Path(name)
        return None


class PickFile(FilePopup):
    def __init__(self, initial_dir: PathLike = None, file_types: FileTypes = None):
        super().__init__(initial_dir)
        self.file_types = file_types

    def _dialog_kwargs(self):
        if ON_MAC:
            return {}
        return {'parent': self._get_root(), 'filetypes': self.file_types or ALL_FILES}

    def _run(self) -> Optional[Path]:
        if name := filedialog.askopenfilename(initialdir=self.initial_dir, **self._dialog_kwargs()):
            return Path(name)
        return None


class PickFiles(PickFile):
    def _run(self) -> list[Path]:
        if names := filedialog.askopenfilenames(initialdir=self.initial_dir, **self._dialog_kwargs()):
            return [Path(name) for name in names]
        return []


class SaveAs(PickFile):
    def __init__(self, initial_dir: PathLike = None, file_types: FileTypes = None, default_ext: str = None):
        super().__init__(initial_dir, file_types)
        self.default_ext = default_ext

    def _run(self) -> Optional[Path]:
        kwargs = self._dialog_kwargs()
        kwargs['defaultextension'] = self.default_ext
        if name := filedialog.asksaveasfilename(initialdir=self.initial_dir, **kwargs):
            return Path(name)
        return None


# endregion


class PickColor(RawPopup):
    def __init__(self, initial_color: str = None):
        super().__init__()
        self.initial_color = initial_color

    def _run(self) -> Optional[tuple[tuple[int, int, int], str]]:
        if color := colorchooser.askcolor(self.initial_color, parent=self._get_root()):
            return color  # noqa  # hex RGB
        return None
