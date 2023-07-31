"""
Right-click menus, menu bars, and menu items for the Music Manager GUI.
"""

from __future__ import annotations

from tk_gui.elements.menu import Menu, MenuGroup, MenuItem, CloseWindow
from tk_gui.elements.menu.items import CopySelection, PasteClipboard, OpenFileLocation, OpenFile, GoogleSelection
from tk_gui.elements.menu.items import SearchKpopFandom, SearchGenerasia, SearchDramaWiki, SearchWikipedia
from tk_gui.elements.menu.items import UpdateTextMenuItem, ToUpperCase, ToLowerCase
from tk_gui.popups.about import AboutPopup

from music.text.extraction import split_enclosed
from music.text.utils import title_case

__all__ = ['PathRightClickMenu', 'TextRightClickMenu', 'EditableTextRightClickMenu', 'MusicManagerMenuBar']


def flip_name_parts(text: str) -> str:
    try:
        a, b = split_enclosed(text, maxsplit=1)
    except ValueError:
        return text
    else:
        return f'{b} ({a})'


class FlipNameParts(UpdateTextMenuItem, update_func=flip_name_parts, label='Flip name parts'):
    __slots__ = ()


class ToTitleCase(UpdateTextMenuItem, update_func=title_case, label='Change case: Title'):
    __slots__ = ()


# region Right-Click Menus


class PathRightClickMenu(Menu):
    CopySelection()
    with MenuGroup('Open'):
        OpenFileLocation()
        OpenFile()
    with MenuGroup('Search'):
        GoogleSelection(); SearchWikipedia(); SearchKpopFandom(); SearchDramaWiki(); SearchGenerasia()  # noqa


class TextRightClickMenu(Menu):
    CopySelection()
    PasteClipboard()
    with MenuGroup('Search'):
        GoogleSelection(); SearchWikipedia(); SearchKpopFandom(); SearchDramaWiki(); SearchGenerasia()  # noqa


class EditableTextRightClickMenu(TextRightClickMenu):
    with MenuGroup('Update'):
        ToLowerCase(); ToUpperCase(); ToTitleCase(); FlipNameParts()  # noqa


class FullRightClickMenu(Menu):
    CopySelection()
    PasteClipboard()
    with MenuGroup('Open'):
        OpenFileLocation()
        OpenFile()
    with MenuGroup('Search'):
        GoogleSelection(); SearchWikipedia(); SearchKpopFandom(); SearchDramaWiki(); SearchGenerasia()  # noqa
    with MenuGroup('Update'):
        ToLowerCase(); ToUpperCase(); ToTitleCase(); FlipNameParts()  # noqa


# endregion

# region Menu Bars


class MusicManagerMenuBar(Menu):
    with MenuGroup('File'):
        MenuItem('Open')
        MenuItem('Settings')
        CloseWindow()
    with MenuGroup('Actions'):
        MenuItem('Clean')
        MenuItem('View Album')
        MenuItem('Wiki Update')
    with MenuGroup('Help'):
        MenuItem('About', AboutPopup)


# endregion
