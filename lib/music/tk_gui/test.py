# need to run as a module

from pathlib import Path

from cli_command_parser import Command, Action, Counter, main

from ds_tools.logging import init_logging

from ..__version__ import __author_email__, __version__, __author__, __url__  # noqa

from .elements import Table, Input, Image, Animation, SpinnerImage, ClockImage, Button, Text, Multiline, Frame
from .elements.choices import Radio, RadioGroup, Checkbox, Combo
from .popups import ImagePopup, AnimatedPopup, SpinnerPopup, ClockPopup, BasicPopup
from .popups.about import AboutPopup
from .popups.raw import PickFolder, PickColor
from .window import Window

ICONS_DIR = Path(__file__).resolve().parents[3].joinpath('icons')


class GuiTest(Command):
    action = Action(help='The test to perform')
    verbose = Counter('-v', default=2, help='Increase logging verbosity (can specify multiple times)')

    def __init__(self):
        init_logging(self.verbose, log_path=None, names=None, set_levels={'PIL.PngImagePlugin': 50})

    @action
    def about(self):
        AboutPopup().run()

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

    @action
    def scroll(self):
        frame_layout = [[Text(f'test_{i:03d}')] for i in range(100)]
        png_path = ICONS_DIR.joinpath('exclamation-triangle-yellow.png')

        layout = [
            [Frame(frame_layout, size=(100, 100), scroll_y=True)],
            # [Frame(frame_layout, scroll_y=True)],
            [Image(png_path, popup_on_click=True, size=(150, 150))],
            [Multiline('\n'.join(map(chr, range(97, 123))), size=(40, 10))],
        ]

        Window(
            layout,
            'Scroll Test',
            size=(300, 500),
            exit_on_esc=True,
            scroll_y=True,
            # handle_configure=True,
        ).run()

    @action
    def max_size(self):
        layout = [[Text(f'test_{i:03d}')] for i in range(100)]
        Window(layout, 'Auto Max Size Test', exit_on_esc=True, handle_configure=True).run()

    @action
    def pick_folder(self):
        path = PickFolder().run()
        print(f'Picked: {path.as_posix() if path else path}')

    @action
    def pick_color(self):
        color = PickColor().run()
        print(f'Picked {color=}')

    @action
    def radio(self):
        b = RadioGroup('group 2')
        with RadioGroup('group 1'):
            layout = [
                [Radio('A1', default=True), Radio('B1', group=b)],
                [Radio('A2'), Radio('B2', 'b two', group=b)],
                [Radio('A3'), Radio('B3', group=b)],
            ]

        results = Window(layout, 'Radio Test', exit_on_esc=True).run().results
        print(f'Results: {results}')

    @action
    def combo(self):
        layout = [
            [Combo(['A', 'B', 'C', 'D'], key='A')],
            [Combo({'A': 1, 'B': 2, 'C': 3}, key='B', default='C')],
        ]
        results = Window(layout, 'Combo Test', exit_on_esc=True).run().results
        print(f'Results: {results}')

    @action(default=True)
    def window(self):
        table1 = Table.from_data([{'a': 1, 'b': 2}, {'a': 3, 'b': 4}], show_row_nums=True)
        table2 = Table.from_data(
            [{'a': n, 'b': n + 1, 'c': n + 2} for n in range(1, 21, 3)], show_row_nums=True, size=(4, 4)
        )
        inpt = Input('test', size=(15, 1))

        gif_path = ICONS_DIR.joinpath('spinners', 'ring_gray_segments.gif')
        png_path = ICONS_DIR.joinpath('exclamation-triangle-yellow.png')
        search_path = ICONS_DIR.joinpath('search.png')

        # layout = [
        #     [table1, table2],
        #     [inpt, Button('Submit', bind_enter=True), Button(image=search_path, shortcut='s', size=(30, 30))],
        #     [Animation(gif_path), SpinnerImage(), ClockImage()],
        #     [Text('test'), Text('link test', link='https://google.com')],
        #     [Image(png_path, popup_on_click=True, size=(150, 150))],
        #     [Multiline('\n'.join(map(chr, range(97, 123))), size=(40, 10))],
        # ]

        frame_layout = [
            [table1], [table2],
            [inpt, Button('Submit', bind_enter=True), Button(image=search_path, shortcut='s', size=(30, 30))],
            [Animation(gif_path)], [SpinnerImage()], [ClockImage()],
            [Text('test'), Text('link test', link='https://google.com')],
            # [Text(f'test_{i:03d}')] for i in range(100)
        ]

        layout = [
            # [Frame(frame_layout, size=(100, 100), scroll_y=True)],
            # [Frame(frame_layout, 'test frame', scroll_y=True, border=True, border_mode='inner', title_mode='inner')],
            # [Frame(frame_layout, 'test frame', scroll_y=True, border=True, border_mode='inner')],
            [Frame(frame_layout, scroll_y=True)],
            [Checkbox('A', key='A', default=True), Checkbox('B', key='B'), Checkbox('C', key='C')],
            [Image(png_path, popup_on_click=True, size=(150, 150))],
            [Multiline('\n'.join(map(chr, range(97, 123))), size=(40, 10))],
        ]

        # Window(layout, size=(600, 600), anchor_elements='c').run()
        # Window(layout, anchor_elements='c', binds={'<Escape>': 'exit'}, kill_others_on_close=True).run()
        # Window(layout, anchor_elements='c', size=(300, 500), binds={'<Escape>': 'exit'}).run()
        # Window(layout, 'Test One', anchor_elements='c', binds={'<Escape>': 'exit'}).run()
        results = Window(layout, anchor_elements='c', binds={'<Escape>': 'exit'}).run().results
        print(f'Results: {results}')


if __name__ == '__main__':
    main()
