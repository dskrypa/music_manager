"""
View: Choose item from list

:author: Doug Skrypa
"""

from typing import Callable, Sequence, Any, Union, Collection

from PySimpleGUI import Element, Text, Button, Radio, Column

from ds_tools.input.prompts import _prepare_source
from ..base_view import event_handler
from .base import BasePopup

__all__ = ['ChooseItemPopup', 'choose_item']


class ChooseItemPopup(BasePopup, view_name='choose_item_popup', primary=False):
    def __init__(
        self,
        items: Sequence[Any],
        name: str = 'value',
        source: Any = '',
        before: str = None,
        repr_func: Callable = repr,
        title: str = '',
        **kwargs
    ):
        super().__init__(binds={'<Escape>': 'Exit'}, title=title or f'Select {a_or_an(name)} {name}')
        self.items = items
        self.item_name = name
        self.source = source
        self.before = before
        self.repr_func = repr_func
        self.kwargs = kwargs
        self._selected: bool = False

    @event_handler(default=True)
    def default(self, event: Union[str, tuple[str, int]], data: dict[str, Any]):
        if isinstance(event, tuple) and event[0] == 'choice':
            self.window['submit'].update(disabled=False)
            self.result = self.items[event[1]]
        else:
            raise StopIteration

    def get_render_args(self) -> tuple[list[list[Element]], dict[str, Any]]:
        size = self.kwargs.pop('size', (None, None))
        before = self.before or (
            f'Found multiple {self.item_name}s{_prepare_source(self.source)} - which {self.item_name} should be used?'
        )
        choices = [
            [Radio(self.repr_func(item), 'rad::choices', key=('choice', i), enable_events=True)]
            for i, item in enumerate(self.items)
        ]
        layout = [
            [Text(before, key='txt::before', size=size)],
            [Column(choices, key='col::choices'), Button('Submit', key='submit', disabled=True)],
        ]
        return layout, {'title': self.title, **self.kwargs}

    @event_handler
    def submit(self, event: str, data: dict[str, Any]):
        self._selected = True
        raise StopIteration

    def _get_result(self):
        self.render()
        self.run()
        return self.result if self._selected else None


def choose_item(
    items: Collection[Any],
    name: str = 'value',
    source: Any = '',
    *,
    before: str = None,
    repr_func: Callable = repr,
    **kwargs
) -> Any:
    """
    Given a list of items from which only one value can be used, prompt the user to choose an item.  If only one item
    exists in the provided sequence, then that item is returned with no prompt.

    :param Collection items: A sequence or sortable collection of items to choose from
    :param str name: The name of the item to use in messages/prompts
    :param source: Where the items came from
    :param str before: A message to be printed before listing the items to choose from (default: automatically generated
      using the provided name and source)
    :param Callable repr_func: The function to use to generate a string representation of each item
    :return: The selected item
    """
    if not isinstance(items, Sequence):
        items = sorted(items)
    if not items:
        raise ValueError(f'No {name}s found{_prepare_source(source)}')
    elif len(items) == 1:
        return items[0]
    else:
        popup = ChooseItemPopup(items, name, source, before, repr_func, **kwargs)
        return popup.get_result()


def a_or_an(noun: str) -> str:
    if not noun:
        return 'a'
    return 'an' if noun[0] in 'aeiou' else 'a'
