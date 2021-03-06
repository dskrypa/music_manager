"""
Monkey patches for PySimpleGUI

:author: Doug Skrypa
"""

from PySimpleGUI import Element

__all__ = ['patch_all', 'patch_element_repr']


def patch_all(element_repr=True):
    if element_repr:
        patch_element_repr()


def patch_element_repr():
    def element_repr(self):
        try:
            key = self.Key
            size = self.get_size()
        except Exception:
            return f'<{self.__class__.__qualname__}#{id(self)}>'
        else:
            return f'<{self.__class__.__qualname__}#{id(self)}[{key=}, {size=}]>'

    Element.__repr__ = element_repr
