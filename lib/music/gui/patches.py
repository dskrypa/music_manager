"""
Monkey patches for FreeSimpleGUI

:author: Doug Skrypa
"""

from FreeSimpleGUI import Element

__all__ = ['patch_all', 'patch_element_repr']


def patch_all(element_repr=True):
    if element_repr:
        patch_element_repr()


def patch_element_repr():
    def element_repr(self):
        try:
            key = self.Key
            if (widget := self.Widget) is not None:
                size = self.get_size()
                pos = widget.winfo_x(), widget.winfo_y()
                # pos = widget.winfo_rootx(), widget.winfo_rooty()
            else:
                size = self.Size
                pos = ('?', '?')
        except Exception:
            return f'<{self.__class__.__qualname__}#{id(self)}>'
        else:
            return f'<{self.__class__.__qualname__}#{id(self)}[{key=}, {size=} {pos=}]>'

    Element.__repr__ = element_repr
