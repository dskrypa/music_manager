"""

"""

from __future__ import annotations

from tk_gui.elements.menu import Menu, MenuGroup
from tk_gui.elements.menu.items import CopySelection, PasteClipboard, GoogleSelection, SearchKpopFandom, SearchGenerasia
from tk_gui.elements.menu.items import FlipNameParts, ToUpperCase, ToTitleCase, ToLowerCase
from tk_gui.elements.menu.items import OpenFileLocation, OpenFile

__all__ = ['PathRightClickMenu', 'TextRightClickMenu', 'EditableTextRightClickMenu']


class PathRightClickMenu(Menu):
    CopySelection()
    with MenuGroup('Open'):
        OpenFileLocation()
        OpenFile()
    with MenuGroup('Search'):
        GoogleSelection()
        SearchKpopFandom()
        SearchGenerasia()


class TextRightClickMenu(Menu):
    CopySelection()
    PasteClipboard()
    with MenuGroup('Search'):
        GoogleSelection()
        SearchKpopFandom()
        SearchGenerasia()


class EditableTextRightClickMenu(TextRightClickMenu):
    CopySelection()
    PasteClipboard()
    with MenuGroup('Search'):
        GoogleSelection()
        SearchKpopFandom()
        SearchGenerasia()
    with MenuGroup('Update'):
        FlipNameParts()
        ToLowerCase()
        ToUpperCase()
        ToTitleCase()
