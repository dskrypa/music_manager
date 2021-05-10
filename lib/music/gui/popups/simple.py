"""
Simple popups.

:author: Doug Skrypa
"""

import logging
from typing import Union, Iterable

from PySimpleGUI import Window, Button, Text

__all__ = ['popup', 'popup_ok', 'popup_input_invalid']
log = logging.getLogger(__name__)


def popup_ok(message: str = None, title: str = '', **kwargs):
    """The popup_ok that PySimpleGUI comes with does not provide a way to allow any key to close it"""
    popup(message, title=title, any_key_closes=True, return_event=False, **kwargs)


def popup_input_invalid(message: str = None, title='Invalid Input', logger=None, **kwargs):
    logger = log if logger is None else logger
    logger.debug(f'Received invalid input - {message}' if message else 'Received invalid input')
    popup_ok(message, title=title, **kwargs)


def popup(
    message: str = None,
    title: str = None,
    *,
    button_text: Union[str, Iterable[str]] = 'OK',
    button_color: str = None,
    background_color: str = None,
    text_color: str = None,
    non_blocking: bool = False,
    keep_on_top: bool = False,
    any_key_closes: bool = False,
    modal: bool = True,
    return_event: bool = True,
    **kwargs
):
    """
    Simple version of the popup from PySimpleGUI, but works around an issue where an extra `\r` would prematurely cause
    the popup to close when `any_key_closes` is True
    """
    if isinstance(button_text, str):
        button_text = [button_text]
    button_row = [Button(value, button_color=button_color, focus=not i) for i, value in enumerate(button_text)]
    layout = [
        [Text(message, auto_size_text=True, text_color=text_color, background_color=background_color)],
        button_row,
    ]
    window = Window(
        title, layout, auto_size_text=True, background_color=background_color, button_color=button_color,
        keep_on_top=keep_on_top, return_keyboard_events=any_key_closes, modal=modal, finalize=True, **kwargs
    )
    for button, event in zip(button_row, button_text):  # bind_return_key only works for one
        button.bind('<Return>', '')
    if non_blocking:
        event, data = window.read(timeout=0)
        if event == '\r':
            event, data = window.read(timeout=0)
    else:
        event, data = window.read()
        if event == '\r':
            event, data = window.read()
        window.close()
        del window

    if return_event:
        return button_text.get(event, event) if isinstance(button_text, dict) else event
    return None
