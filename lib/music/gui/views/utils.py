"""
Utilities for formatting gui elements.

:author: Doug Skrypa
"""

from typing import Union

from PySimpleGUI import Text, Element

__all__ = ['resize_text_column', 'label_and_val_key']


def resize_text_column(rows: list[list[Union[Text, Element]]], column: int = 0):
    longest = max(map(len, (row[column].DisplayText for row in rows)))
    for row in rows:
        row[column].Size = (longest, 1)

    return rows


def label_and_val_key(src: str, tag: str, title: bool = True) -> tuple[Text, str]:
    key = f'tag::{src}::{tag}'
    label = Text(tag.replace('_', ' ').title() if title else tag, key=key)
    return label, f'val::{src}::{tag}'
