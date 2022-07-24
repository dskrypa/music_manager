"""
Tkinter GUI popup: Style

:author: Doug Skrypa
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Iterator

from ..elements import Text, HorizontalSeparator
from ..style import Style, StyleSpec, STATE_NAMES
from .base import Popup

if TYPE_CHECKING:
    from ..elements import Element
    from ..typing import Layout

__all__ = ['StylePopup']


class StylePopup(Popup):
    def __init__(self, style: StyleSpec = None, **kwargs):
        kwargs.setdefault('bind_esc', True)
        kwargs.setdefault('scroll_y', True)
        kwargs.setdefault('title', 'Style')
        super().__init__(**kwargs)
        self.style = Style.get_style(style)

    def get_layout(self) -> Layout:
        style = self.style
        layout = [
            [Text('Style:', size=(10, 1), anchor='e', selectable=False), Text(style.name)],
            [Text('Parent:', size=(10, 1), anchor='e', selectable=False), Text(style.parent.name)],
            [Text('TTK Theme:', size=(10, 1), anchor='e', selectable=False), Text(style.ttk_theme)],
        ]
        layout.extend(self.build_rows())
        return layout

    def build_rows(self) -> Iterator[list[Element]]:
        style = self.style
        styles = {}
        text_keys = {'font', 'border_width', 'arrow_width', 'bar_width'}
        state_nums = range(len(STATE_NAMES))
        name_style = style.sub_style(text_font=style.text.sub_font('default', None, None, 'bold'))
        header_style = style.sub_style(text_font=style.text.sub_font('default', None, None, 'bold', 'underline'))

        IText = partial(Text, size=(10, 1), justify='c')
        HText = partial(Text, size=(10, 1), justify='c', style=header_style)

        for name, layer in style.iter_layers():
            if not (layer_vals := dict(layer.iter_values())):
                continue

            yield [HorizontalSeparator()]
            yield [Text('Layer:', size=(10, 1), selectable=False), Text(name, style=name_style)]
            yield [HText('field'), *(HText(state) for state in STATE_NAMES)]

            for key, values in layer_vals.items():
                row = [IText(key)]
                if key in text_keys:
                    row.extend(IText(values[state]) for state in state_nums)
                    yield row
                else:
                    for state in state_nums:
                        color = values[state]
                        try:
                            ele_style = styles[color]
                        except KeyError:
                            styles[color] = ele_style = style.sub_style(color, text_bg=color)

                        row.append(IText(color, style=ele_style))

                    yield row
