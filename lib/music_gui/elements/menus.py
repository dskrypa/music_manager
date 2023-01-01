"""

"""

from __future__ import annotations

from tk_gui.elements.menu import Menu, MenuGroup
from tk_gui.elements.menu.items import CopySelection, PasteClipboard, OpenFileLocation, OpenFile, GoogleSelection
from tk_gui.elements.menu.items import SearchKpopFandom, SearchGenerasia, SearchDramaWiki, SearchWikipedia
from tk_gui.elements.menu.items import UpdateTextMenuItem, ToUpperCase, ToTitleCase, ToLowerCase

from music.text.extraction import split_enclosed

__all__ = ['PathRightClickMenu', 'TextRightClickMenu', 'EditableTextRightClickMenu']


def flip_name_parts(text: str) -> str:
    try:
        a, b = split_enclosed(text, maxsplit=1)
    except ValueError:
        return text
    else:
        return f'{b} ({a})'


class FlipNameParts(UpdateTextMenuItem, update_func=flip_name_parts, label='Flip name parts'):
    __slots__ = ()


class PathRightClickMenu(Menu):
    CopySelection()
    with MenuGroup('Open'):
        OpenFileLocation()
        OpenFile()
    with MenuGroup('Search'):
        GoogleSelection()
        SearchWikipedia()
        SearchKpopFandom()
        SearchDramaWiki()
        SearchGenerasia()


class TextRightClickMenu(Menu):
    CopySelection()
    PasteClipboard()
    with MenuGroup('Search'):
        GoogleSelection()
        SearchWikipedia()
        SearchKpopFandom()
        SearchDramaWiki()
        SearchGenerasia()


class EditableTextRightClickMenu(TextRightClickMenu):
    with MenuGroup('Update'):
        ToLowerCase()
        ToUpperCase()
        ToTitleCase()
        FlipNameParts()
