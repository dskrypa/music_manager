"""
View: Show Clock

:author: Doug Skrypa
"""

from math import ceil
from time import monotonic

from ..base_view import event_handler, Event, EventData, RenderArgs
from ..config import GuiConfig
from ..elements.image import ClockImage
from .image import ImageView

__all__ = ['ClockView']

DEFAULT_SETTINGS = {'remember_pos:clock_view': True, 'remember_size:clock_view': True}


class ClockView(ImageView, view_name='clock_view', primary=False):
    config = GuiConfig(auto_save=True, defaults=DEFAULT_SETTINGS)

    def __init__(self, *args, width: int = None, seconds: bool = True, slim: bool = False, **kwargs):
        super().__init__(None, *args, **kwargs)
        cfg = self.config.get
        if width is None and cfg(f'remember_size:{self.name}') and (size := cfg(f'popup_size:{self.name}', type=tuple)):
            self.gui_img = ClockImage(img_size=size, seconds=seconds, slim=slim)

            # self.gui_img._clock.resize(self.gui_img._clock.calc_width(size[1]))
            # width = self.gui_img._clock.calc_width(size[1])
        else:
            self.gui_img = ClockImage(width=width or 40, seconds=seconds, slim=slim)
        self.orig_size = self._last_size = self.gui_img.Size
        self._show_titlebar = False

    @event_handler
    def window_resized(self, event: Event, data: EventData):
        if monotonic() - self._last_resize < 0.1:
            return
        elif new_size := self._get_new_size(*data['new_size']):
            self._last_size = new_size
            self.gui_img.resize(*new_size)
            self.window.set_title(self.title)
            self._last_resize = monotonic()

    def get_render_args(self) -> RenderArgs:
        layout = [[self.gui_img]]
        kwargs = {
            'title': self.title,
            'resizable': True,
            'element_justification': 'center',
            'margins': (0, 0),
            'border_depth': 0,
            'background_color': 'black',
            'alpha_channel': 0.8,
            'grab_anywhere': True,
            'no_titlebar': True,
        }
        return layout, kwargs

    def increase_size(self, event):
        width, height = self.window.size
        height += 10
        clock = self.gui_img._clock
        new_width, _height = clock.time_size(self.gui_img._show_seconds, clock.calc_width(height))
        width = max(width, new_width)
        self.window.size = (width, height)

    def decrease_size(self, event):
        width, height = self.window.size
        height -= 10
        clock = self.gui_img._clock
        new_width, _height = clock.time_size(self.gui_img._show_seconds, clock.calc_width(height))
        if (ceil(clock.bar_pct * clock.calc_width(_height - 6)) if clock.bar_pct else clock.bar) < 3:
            self.log.debug('Unable to decrease clock size further')
            return
        width = min(width, new_width)
        self.window.size = (width, height)

    def show_hide_title(self, event):
        self.window.TKroot.wm_overrideredirect(self._show_titlebar)
        self._show_titlebar = not self._show_titlebar

    def toggle_slim(self, event):
        self.gui_img.toggle_slim()

    def post_render(self):
        super().post_render()
        widget = self.gui_img._widget
        widget.bind('<Button-2>', self.toggle_slim)  # Middle click
        widget.bind('<Button-3>', self.show_hide_title)  # Right click
        bind = self.window.TKroot.bind
        bind('<KeyPress-plus>', self.increase_size)
        bind('<KeyPress-minus>', self.decrease_size)


if __name__ == '__main__':
    from argparse import ArgumentParser
    parser = ArgumentParser()
    parser.add_argument('--show_clock', '-c', action='store_true', help='Show the clock')
    if parser.parse_args().show_clock:
        from ds_tools.logging import init_logging
        init_logging(12, log_path=None, names=None)
        ClockView().get_result()
