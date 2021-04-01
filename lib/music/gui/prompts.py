"""
Prompts for the Music Manager GUI

:author: Doug Skrypa
"""

import logging
from pathlib import Path
from typing import Callable, Dict, Tuple, Optional

from PySimpleGUI import Popup, popup_get_folder, popup_get_file, popup_ok

__all__ = ['directory_prompt', 'file_prompt', 'popup_input_invalid']
log = logging.getLogger(__name__)


def path_prompt(popup_func: Callable, args: Tuple, kwargs: Dict, must_exist: bool = True) -> Optional[Path]:
    if popup_func is popup_get_file:
        validator, path_type = 'is_file', 'file'
    elif popup_func is popup_get_folder:
        validator, path_type = 'is_dir', 'directory'
    else:
        validator, path_type = 'exists', 'path'

    while True:
        if path := popup_func(*args, **kwargs):
            path = Path(path).resolve()
            if must_exist and not getattr(path, validator)():
                Popup(f'Invalid {path_type}: {path}', title=f'Invalid {path_type}')
            else:
                return path
        else:
            return None


def directory_prompt(*args, must_exist=True, **kwargs) -> Optional[Path]:
    return path_prompt(popup_get_folder, args, kwargs, must_exist)


def file_prompt(*args, must_exist=True, **kwargs) -> Optional[Path]:
    return path_prompt(popup_get_file, args, kwargs, must_exist)


def popup_input_invalid(*args, title='Invalid Input', **kwargs):
    log.debug(f'Received invalid input - {args[0]}' if args else 'Received invalid input')
    return popup_ok(*args, title=title, **kwargs)
