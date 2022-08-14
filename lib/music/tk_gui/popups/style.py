"""
Tkinter GUI popup: Style

:author: Doug Skrypa
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Iterator

from ..color import pick_fg
from ..elements import Text, HorizontalSeparator, Combo
from ..style import Style, StyleSpec, STATE_NAMES
from ..window import Window
from .base import Popup

if TYPE_CHECKING:
    from tkinter import Event
    from ..elements import Element
    from ..typing import Layout

__all__ = ['StylePopup']


class StylePopup(Popup):
    def __init__(self, show_style: StyleSpec = None, **kwargs):
        kwargs.setdefault('bind_esc', True)
        kwargs.setdefault('scroll_y', True)
        kwargs.setdefault('title', 'Style')
        kwargs.setdefault('style', show_style)
        kwargs['show'] = False
        super().__init__(**kwargs)
        self.show_style = Style.get_style(show_style)
        self._next_style = None

    def _get_layout(self, window: Window) -> Layout:
        style = self.show_style
        if parent := style.parent:
            def parent_cb(event=None):
                self.__class__(parent).run()

            parent_kwargs = {'value': parent.name, 'link': parent_cb, 'tooltip': f'View style: {parent.name}'}
        else:
            parent_kwargs = {}

        layout = [
            [
                Text('Style:', size=(10, 1), anchor='e', selectable=False),
                Combo(Style.style_names(), style.name, callback=self._style_selected),
            ],
            [Text('Parent:', size=(10, 1), anchor='e', selectable=False), Text(**parent_kwargs)],
            [Text('TTK Theme:', size=(10, 1), anchor='e', selectable=False), Text(style.ttk_theme)],
        ]
        layout.extend(self.build_rows(window))
        return layout

    def prepare_window(self) -> Window:
        window = Window(title=self.title, is_popup=True, **self.window_kwargs)
        window.add_rows(self._get_layout(window))
        return window

    def _run(self):
        with self.window(take_focus=True) as window:
            window.run()
            if style := self._next_style:
                popup = self.__class__(style)
            else:
                return window.results
        return popup._run()

    def _style_selected(self, event: Event):
        if (choice := event.widget.get()) != self.show_style.name:
            self._next_style = choice
            self.window.interrupt()

    def build_rows(self, window: Window) -> Iterator[list[Element]]:
        style = window.style
        styles = {}
        text_keys = {'font', 'border_width', 'arrow_width', 'bar_width'}
        state_nums = range(len(STATE_NAMES))
        name_style = style.sub_style(text_font=style.text.sub_font('default', None, None, 'bold'))
        header_style = style.sub_style(text_font=style.text.sub_font('default', None, None, 'bold', 'underline'))

        IText = partial(Text, size=(15, 1), justify='c')
        HText = partial(Text, size=(15, 1), justify='c', style=header_style)

        for name, layer in self.show_style.iter_layers():
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
                            styles[color] = ele_style = style.sub_style(color, text_bg=color, text_fg=pick_fg(color))

                        row.append(IText(color, style=ele_style))

                    yield row
