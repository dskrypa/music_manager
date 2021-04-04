"""
Simple popups.

:author: Doug Skrypa
"""

import logging
from PySimpleGUI import popup, POPUP_BUTTONS_OK

__all__ = ['popup_ok', 'popup_input_invalid']
log = logging.getLogger(__name__)


def popup_ok(message: str, title: str = '', **kwargs):
    """The popup_ok that PySimpleGUI comes with does not provide a way to allow any key to close it"""
    return popup(message, title=title, button_type=POPUP_BUTTONS_OK, any_key_closes=True, **kwargs)


def popup_input_invalid(*args, title='Invalid Input', logger=None, **kwargs):
    logger = log if logger is None else logger
    logger.debug(f'Received invalid input - {args[0]}' if args else 'Received invalid input')
    return popup_ok(*args, title=title, **kwargs)
