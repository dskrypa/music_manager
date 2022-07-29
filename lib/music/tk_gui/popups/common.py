"""
Tkinter GUI popups: common popups

:author: Doug Skrypa
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from ..elements.buttons import OK
from ..images import image_path
from .base import BasicPopup, BoolPopup

if TYPE_CHECKING:
    from ..typing import Bool, TkSide

__all__ = [
    'popup_ok', 'popup_error', 'popup_warning', 'popup_yes_no', 'popup_no_yes', 'popup_ok_cancel', 'popup_cancel_ok'
]


def popup_ok(text: str, title: str = None, bind_esc: Bool = True, side: TkSide = 'right', **kwargs) -> None:
    BasicPopup(text, title=title, bind_esc=bind_esc, button=OK(side=side), **kwargs).run()


def popup_error(text: str, title: str = 'Error', bind_esc: Bool = True, side: TkSide = 'right', **kwargs) -> None:
    BasicPopup(text, title=title, bind_esc=bind_esc, button=OK(side=side), **kwargs).run()


def popup_warning(text: str, title: str = 'Warning', bind_esc: Bool = True, side: TkSide = 'right', **kwargs) -> None:
    img_path = image_path('exclamation-triangle-yellow.png')
    BasicPopup(text, title=title, bind_esc=bind_esc, image=img_path, button=OK(side=side), **kwargs).run()


def popup_yes_no(text: str, title: str = None, bind_esc: Bool = False, **kwargs) -> Optional[bool]:
    return BoolPopup(text, 'Yes', 'No', 'TF', title=title, bind_esc=bind_esc, **kwargs).run()


def popup_no_yes(text: str, title: str = None, bind_esc: Bool = False, **kwargs) -> Optional[bool]:
    return BoolPopup(text, 'Yes', 'No', 'FT', title=title, bind_esc=bind_esc, **kwargs).run()


def popup_ok_cancel(text: str, title: str = None, bind_esc: Bool = False, **kwargs) -> Optional[bool]:
    return BoolPopup(text, 'OK', 'Cancel', 'TF', title=title, bind_esc=bind_esc, **kwargs).run()


def popup_cancel_ok(text: str, title: str = None, bind_esc: Bool = False, **kwargs) -> Optional[bool]:
    return BoolPopup(text, 'OK', 'Cancel', 'FT', title=title, bind_esc=bind_esc, **kwargs).run()
