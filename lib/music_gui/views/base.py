"""

"""

from __future__ import annotations

import logging
from abc import ABC
from typing import Type

from tk_gui.enums import CallbackAction
from tk_gui.views.view import View

__all__ = ['BaseView']
log = logging.getLogger(__name__)


class BaseView(View, ABC):
    __next = None

    def set_next_view(self, *args, view_cls: Type[View] = None, **kwargs) -> CallbackAction:
        """
        Set the next view that should be displayed.  From a Button callback, ``return self.set_next_view(...)`` can be
        used to trigger the advancement to that view immediately.  If that behavior is not desired, then it can simply
        be called without returning the value that is returned by this method.

        :param args: Positional arguments to use when initializing the next view
        :param view_cls: The class for the next View that should be displayed (defaults to the current class)
        :param kwargs: Keyword arguments to use when initializing the next view
        :return: The ``CallbackAction.EXIT`` callback action
        """
        if view_cls is None:
            view_cls = self.__class__
        self.__next = (view_cls, args, kwargs)
        return CallbackAction.EXIT

    def get_next_view(self) -> View | None:
        try:
            view_cls, args, kwargs = self.__next
        except TypeError:
            return None
        return view_cls(*args, **kwargs)
