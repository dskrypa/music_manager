"""
Utilities for formatting gui elements.

:author: Doug Skrypa
"""

import logging
from pathlib import Path
from typing import Union, Optional, Iterator

from PySimpleGUI import Text, Element, WRITE_ONLY_KEY, Image

from ..elements.inputs import ExtInput

__all__ = ['label_and_val_key', 'label_and_diff_keys', 'get_a_to_b', 'split_key']
log = logging.getLogger(__name__)


def label_and_val_key(src: str, tag: str, title: bool = True) -> tuple[Text, str]:
    label = Text(tag.replace('_', ' ').title() if title else tag, key=f'tag::{src}::{tag}{WRITE_ONLY_KEY}')
    return label, f'val::{src}::{tag}'


def label_and_diff_keys(src: str, tag: str) -> tuple[Text, Text, Text, str, str]:
    label = Text(tag.replace('_', ' ').title(), key=f'tag::{src}::{tag}{WRITE_ONLY_KEY}')
    sep_1 = Text('from', key=f'from::{src}::{tag}')
    sep_2 = Text('to', key=f'to::{src}::{tag}')
    return label, sep_1, sep_2, f'src::{src}::{tag}', f'new::{src}::{tag}'


def get_a_to_b(
    label: str, src_val: Union[str, Path], new_val: Union[str, Path], src: str, tag: str
) -> Iterator[list[Element]]:
    src_val = src_val.as_posix() if isinstance(src_val, Path) else src_val
    src_kwargs = {'size': (len(src_val), 1)} if len(src_val) > 50 else {}
    src_ele = ExtInput(src_val, disabled=True, key=f'src::{src}::{tag}', **src_kwargs)

    new_val = new_val.as_posix() if isinstance(new_val, Path) else new_val
    new_kwargs = {'size': (len(new_val), 1)} if len(new_val) > 50 else {}
    new_ele = ExtInput(new_val, disabled=True, key=f'new::{src}::{tag}', **new_kwargs)
    if len(src_val) + len(new_val) > 200:
        yield [Text(label), src_ele]
        yield [Image(size=(len(label) * 7, 1)), Text('\u2794', font=('Helvetica', 15)), new_ele]
    else:
        yield [Text(label), src_ele, Text('\u2794', font=('Helvetica', 15)), new_ele]


def split_key(key: str) -> Optional[tuple[str, str, str]]:
    try:
        key_type, obj_key = key.split('::', 1)
        if key_type == '_val':
            obj, item, sub_key = obj_key.rsplit('::', 2)
        else:
            obj, item = obj_key.rsplit('::', 1)
    except Exception:  # noqa
        return None
    else:
        return key_type, obj, item
