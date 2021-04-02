"""
Utilities for formatting gui elements.

:author: Doug Skrypa
"""

import logging
import tkinter
from contextlib import contextmanager
from typing import Union

from PySimpleGUI import Text, Element, Column, Window, Input

__all__ = [
    'resize_text_column',
    'label_and_val_key',
    'label_and_diff_keys',
    'expand_columns',
    'temp_hidden_window',
    'get_a_to_b',
]
log = logging.getLogger(__name__)


def resize_text_column(rows: list[list[Union[Text, Element]]], column: int = 0):
    longest = max(map(len, (row[column].DisplayText for row in rows)))
    for row in rows:
        row[column].Size = (longest, 1)

    return rows


def label_and_val_key(src: str, tag: str, title: bool = True) -> tuple[Text, str]:
    label = Text(tag.replace('_', ' ').title() if title else tag, key=f'tag::{src}::{tag}')
    return label, f'val::{src}::{tag}'


def label_and_diff_keys(src: str, tag: str) -> tuple[Text, Text, Text, str, str]:
    label = Text(tag.replace('_', ' ').title(), key=f'tag::{src}::{tag}')
    sep_1 = Text('from', key=f'from::{src}::{tag}')
    sep_2 = Text('to', key=f'to::{src}::{tag}')
    return label, sep_1, sep_2, f'src::{src}::{tag}', f'new::{src}::{tag}'


def get_a_to_b(label: str, src_val: str, new_val: str, src: str, tag: str) -> list[Element]:
    label_ele = Text(label)
    src_kwargs = {'size': (len(src_val), 1)} if len(src_val) > 50 else {}
    src_ele = Input(src_val, disabled=True, key=f'src::{src}::{tag}', **src_kwargs)
    arrow = Text('->')
    new_kwargs = {'size': (len(new_val), 1)} if len(new_val) > 50 else {}
    new_ele = Input(new_val, disabled=True, key=f'new::{src}::{tag}', **new_kwargs)
    return [label_ele, src_ele, arrow, new_ele]


def expand_columns(rows: list[list[Element]]):
    for row in rows:
        for ele in row:
            if isinstance(ele, Column):
                ele.expand(True, True)
            try:
                ele_rows = ele.Rows
            except AttributeError:
                pass
            else:
                log.debug(f'Expanding columns on {ele}')
                expand_columns(ele_rows)


@contextmanager
def temp_hidden_window():
    """
    Creates and destroys a temporary Window similar to the way that PySimpleGUI does in
    :func:`popup_get_folder<PySimpleGUI.popup_get_folder>` while creating a file prompt.  Mostly copied from that func.
    """
    if not Window.hidden_master_root:
        # if first window being created, make a throwaway, hidden master root.  This stops one user window from
        # becoming the child of another user window. All windows are children of this hidden window
        Window._IncrementOpenCount()
        Window.hidden_master_root = tkinter.Tk()
        Window.hidden_master_root.attributes('-alpha', 0)  # HIDE this window really really really
        try:
            Window.hidden_master_root.wm_overrideredirect(True)
        except Exception:
            log.error('* Error performing wm_overrideredirect *', exc_info=True)
        Window.hidden_master_root.withdraw()

    root = tkinter.Toplevel()
    try:
        root.attributes('-alpha', 0)  # hide window while building it. makes for smoother 'paint'
        try:
            root.wm_overrideredirect(True)
        except Exception:
            log.error('* Error performing wm_overrideredirect *', exc_info=True)
        root.withdraw()
    except Exception:
        pass

    yield root

    root.destroy()
    if Window.NumOpenWindows == 1:
        Window.NumOpenWindows = 0
        Window.hidden_master_root.destroy()
        Window.hidden_master_root = None
