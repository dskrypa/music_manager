"""
Right-click menus, menu bars, and menu items for the Music Manager GUI.
"""

from __future__ import annotations

from tk_gui.elements.menu import Menu, MenuGroup, MenuItem, CloseWindow
from tk_gui.elements.menu.items import CopySelection, PasteClipboard, OpenFileLocation, OpenFile, SearchSelection
from tk_gui.elements.menu.items import GoogleSelection as _Google, SearchWikipedia as _Wikipedia
from tk_gui.elements.menu.items import SearchKpopFandom as _KpopFandom, SearchGenerasia as _Generasia
from tk_gui.elements.menu.items import SearchDramaWiki as _DramaWiki, UpdateTextMenuItem, ToUpperCase, ToLowerCase
from tk_gui.popups.about import AboutPopup

from music.text.extraction import split_enclosed
from music.text.utils import title_case

__all__ = ['PathRightClickMenu', 'TextRightClickMenu', 'EditableTextRightClickMenu', 'MusicManagerMenuBar']


# region Text Editing / Updating


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


# endregion

# region Right-Click Menus


class _KindieFandom(SearchSelection, url='https://kindie.fandom.com/wiki/Special:Search?scope=internal&query={query}'):
    __slots__ = ()


class PathRightClickMenu(Menu):
    CopySelection()
    with MenuGroup('Open'):
        OpenFileLocation()
        OpenFile()
    with MenuGroup('Search'):
        _Google(); _Wikipedia(); _KpopFandom(); _KindieFandom(); _DramaWiki(); _Generasia()  # noqa


class TextRightClickMenu(Menu):
    CopySelection()
    PasteClipboard()
    with MenuGroup('Search'):
        _Google(); _Wikipedia(); _KpopFandom(); _KindieFandom(); _DramaWiki(); _Generasia()  # noqa


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
        _Google(); _Wikipedia(); _KpopFandom(); _KindieFandom(); _DramaWiki(); _Generasia()  # noqa
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
