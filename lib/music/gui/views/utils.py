"""
Utilities for formatting gui elements.

:author: Doug Skrypa
"""

import logging
from pathlib import Path
from typing import Union, Optional

from PySimpleGUI import Text, Element, Column, Checkbox

from ..elements.inputs import DarkInput

__all__ = [
    'resize_text_column',
    'label_and_val_key',
    'label_and_diff_keys',
    'expand_columns',
    'get_a_to_b',
    'make_checkbox_grid',
    'split_key',
]
log = logging.getLogger(__name__)


def resize_text_column(rows: list[list[Union[Text, Element]]], column: int = 0):
    if rows:
        longest = max(map(len, (row[column].DisplayText for row in rows)))
        for row in rows:
            row[column].Size = (longest, 1)

    return rows


def make_checkbox_grid(rows: list[list[Checkbox]]):
    if len(rows) > 1 and len(rows[-1]) == 1:
        last_row = rows[-1]
        rows = rows[:-1]
    else:
        last_row = None

    shortest_row = min(map(len, (row for row in rows)))
    longest_boxes = [max(map(len, (row[column].Text for row in rows))) for column in range(shortest_row)]
    for row in rows:
        for column, width in enumerate(longest_boxes):
            row[column].Size = (width, 1)

    if last_row is not None:
        rows.append(last_row)
    return rows


def label_and_val_key(src: str, tag: str, title: bool = True) -> tuple[Text, str]:
    label = Text(tag.replace('_', ' ').title() if title else tag, key=f'tag::{src}::{tag}')
    return label, f'val::{src}::{tag}'


def label_and_diff_keys(src: str, tag: str) -> tuple[Text, Text, Text, str, str]:
    label = Text(tag.replace('_', ' ').title(), key=f'tag::{src}::{tag}')
    sep_1 = Text('from', key=f'from::{src}::{tag}')
    sep_2 = Text('to', key=f'to::{src}::{tag}')
    return label, sep_1, sep_2, f'src::{src}::{tag}', f'new::{src}::{tag}'


def get_a_to_b(label: str, src_val: Union[str, Path], new_val: Union[str, Path], src: str, tag: str) -> list[Element]:
    src_val = src_val.as_posix() if isinstance(src_val, Path) else src_val
    src_kwargs = {'size': (len(src_val), 1)} if len(src_val) > 50 else {}
    src_ele = DarkInput(src_val, disabled=True, key=f'src::{src}::{tag}', **src_kwargs)

    new_val = new_val.as_posix() if isinstance(new_val, Path) else new_val
    new_kwargs = {'size': (len(new_val), 1)} if len(new_val) > 50 else {}
    new_ele = DarkInput(new_val, disabled=True, key=f'new::{src}::{tag}', **new_kwargs)
    return [Text(label), src_ele, Text('\u2794', font=('Helvetica', 15)), new_ele]


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


def split_key(key: str) -> Optional[tuple[str, str, str]]:
    try:
        key_type, obj_key = key.split('::', 1)
        obj, item = obj_key.rsplit('::', 1)
    except Exception:
        return None
    else:
        return key_type, obj, item
