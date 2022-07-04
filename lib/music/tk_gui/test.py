# need to run as a module

from pathlib import Path

from cli_command_parser import Command, Action, Counter, main

from ds_tools.logging import init_logging

from .core import Window
from .elements import Table, Input, Image, Animation, SpinnerImage, ClockImage, Button
from .popups import ImagePopup, AnimatedPopup, SpinnerPopup, ClockPopup, BasicPopup


ICONS_DIR = Path(__file__).resolve().parents[3].joinpath('icons')


class GuiTest(Command):
    action = Action(help='The test to perform')
    verbose = Counter('-v', default=2, help='Increase logging verbosity (can specify multiple times)')

    def __init__(self):
        init_logging(self.verbose, log_path=None, names=None, set_levels={'PIL.PngImagePlugin': 50})

    @action
    def spinner(self):
        SpinnerPopup(img_size=(400, 400)).run()

    @action
    def gif(self):
        gif_path = ICONS_DIR.joinpath('spinners', 'ring_gray_segments.gif')
        AnimatedPopup(gif_path).run()

    @action
    def image(self):
        png_path = ICONS_DIR.joinpath('exclamation-triangle-yellow.png')
        ImagePopup(png_path).run()

    @action
    def clock(self):
        ClockPopup(toggle_slim_on_click=True).run()

    @action
    def popup(self):
        # results = BasicPopup('This is a test', title='Test', buttons=('OK',)).run()
        results = BasicPopup('This is a test', title='Test', buttons=('Cancel', 'OK'), bind_esc=True).run()
        # results = BasicPopup('This is a test with more words', title='Test', buttons=('Cancel', 'Test', 'OK')).run()
        print(results)

    @action(default=True)
    def window(self):
        table1 = Table.from_data([{'a': 1, 'b': 2}, {'a': 3, 'b': 4}], show_row_nums=True)
        table2 = Table.from_data([{'a': 1, 'b': 2}, {'a': 3, 'b': 4}], show_row_nums=True)
        inpt = Input('test', size=(15, 1))

        gif_path = ICONS_DIR.joinpath('spinners', 'ring_gray_segments.gif')
        png_path = ICONS_DIR.joinpath('exclamation-triangle-yellow.png')

        layout = [
            [table1, table2],
            [inpt, Button('Submit', bind_enter=True)],
            [Animation(gif_path), SpinnerImage()],
            [ClockImage()],
            [Image(png_path)]
        ]

        # Window('Test One', layout, size=(600, 600), anchor_elements='c').run()
        Window('Test One', layout, anchor_elements='c', binds={'<Escape>': 'exit'}).run()


if __name__ == '__main__':
    main()
