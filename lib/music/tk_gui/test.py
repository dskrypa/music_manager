# need to run as a module

from pathlib import Path

from cli_command_parser import Command, Action, Counter, Option, main

from ds_tools.logging import init_logging

from ..__version__ import __author_email__, __version__, __author__, __url__  # noqa

from .elements import Table, Input, Image, Animation, SpinnerImage, ClockImage, Button, Text, ScrollFrame, SizeGrip
from .elements.choices import Radio, RadioGroup, CheckBox, Combo, ListBox
from .elements.bars import HorizontalSeparator, VerticalSeparator, ProgressBar, Slider
from .elements.menu import Menu, MenuGroup, MenuItem, CopySelection, GoogleSelection, SearchKpopFandom, SearchGenerasia
from .elements.text import Multiline, gui_log_handler
from .elements.rating import Rating
from .popups import ImagePopup, AnimatedPopup, SpinnerPopup, ClockPopup, BasicPopup, Popup
from .popups.about import AboutPopup
from .popups.base import TextPromptPopup, LoginPromptPopup
from .popups.common import popup_warning, popup_error, popup_yes_no, popup_no_yes, popup_ok
from .popups.raw import PickFolder, PickColor
from .popups.style import StylePopup
from .window import Window

ICONS_DIR = Path(__file__).resolve().parents[3].joinpath('icons')


class GuiTest(Command):
    action = Action(help='The test to perform')
    verbose = Counter('-v', default=2, help='Increase logging verbosity (can specify multiple times)')
    color = Option('-c', help='The initial color to display when action=pick_color')

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
            [ScrollFrame(frame_layout, size=(100, 100), scroll_y=True)],
            # [ScrollFrame(frame_layout, scroll_y=True)],
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
        color = PickColor(self.color).run()
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

    @action
    def progress(self):
        bar = ProgressBar(100)
        window = Window([[Text('Processing...')], [bar]], 'Progress Test', exit_on_esc=True)
        for _ in bar(range(99)):
            window._root.after(50, window.interrupt)
            window.run()

    @action
    def slider(self):
        layout = [
            [Slider(0, 1, interval=0.05, key='A')],
            [Slider(0, 20, tick_interval=5, key='B')],
        ]
        results = Window(layout, 'Slider Test', exit_on_esc=True).run().results
        print(f'Results: {results}')

    @action
    def listbox(self):
        chars = list(map(chr, range(97, 123)))
        layout = [
            [ListBox(chars, key='A', size=(40, 10)), ListBox(chars, ['a', 'b'], key='B', size=(40, 10))]
        ]

        results = Popup(layout, 'ListBox Test', exit_on_esc=True).run()
        # results = Window(layout, 'ListBox Test', exit_on_esc=True).run().results
        print(f'Results: {results}')

    @action
    def rating(self):
        layout = [[Rating(key='a')], [Rating(key='b', show_value=True)]]
        results = Window(layout, 'Slider Test', exit_on_esc=True).run().results
        print(f'Results: {results}')

    @action
    def style(self):
        StylePopup().run()

    @action
    def popup_warning(self):
        popup_warning('This is a test warning!')

    @action
    def popup_error(self):
        popup_error('This is a test error!')

    @action
    def popup_yes_no(self):
        result = popup_yes_no('This is a test!')
        print(f'{result=}')

    @action
    def popup_no_yes(self):
        result = popup_no_yes('This is a test!')
        print(f'{result=}')

    @action
    def popup_ok(self):
        popup_ok('This is a test!')

    @action
    def popup_text(self):
        result = TextPromptPopup('Enter a string').run()
        print(f'{result=}')

    @action
    def popup_login(self):
        user, pw = LoginPromptPopup('Enter your login info').run()
        print(f'{user=}, {pw=}')

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

        class RightClickMenu(Menu):
            MenuItem('Test A', print)
            CopySelection()
            GoogleSelection()
            SearchKpopFandom()
            SearchGenerasia()
            # MenuItem('Test B', print)

        class MenuBar(Menu):
            with MenuGroup('File'):
                # MenuItem('Open', print)
                MenuItem('Pick Color', PickColor.as_callback('#1c1e23'))
            with MenuGroup('Help'):
                MenuItem('About', AboutPopup.as_callback())

        frame_layout = [
            [MenuBar()],
            [table1], [table2],
            [HorizontalSeparator()],
            [inpt, Button('Submit', bind_enter=True), Button(image=search_path, shortcut='s', size=(30, 30))],
            [Animation(gif_path)], [SpinnerImage()], [ClockImage()],
            [Text('test'), VerticalSeparator(), Text('link test', link='https://google.com')],
            # [Text(f'test_{i:03d}')] for i in range(100)
        ]

        # multiline = Multiline(size=(40, 10), expand=True)
        multiline = Multiline(size=(120, None), expand=True)

        layout = [
            # [ScrollFrame(frame_layout, size=(100, 100), scroll_y=True)],
            # [ScrollFrame(frame_layout, 'test frame', scroll_y=True, border=True, border_mode='inner', title_mode='inner')],
            # [ScrollFrame(frame_layout, 'test frame', scroll_y=True, border=True, border_mode='inner')],
            [ScrollFrame(frame_layout, scroll_y=True)],
            [CheckBox('A', key='A', default=True), CheckBox('B', key='B'), CheckBox('C', key='C')],
            [Image(png_path, popup_on_click=True, size=(150, 150))],
            # [Multiline('\n'.join(map(chr, range(97, 123))), size=(40, 10)), SizeGrip()],
            [multiline, SizeGrip()],
        ]

        # Window(layout, size=(600, 600), anchor_elements='c').run()
        # Window(layout, anchor_elements='c', binds={'<Escape>': 'exit'}, kill_others_on_close=True).run()
        # Window(layout, anchor_elements='c', size=(300, 500), binds={'<Escape>': 'exit'}).run()
        # Window(layout, 'Test One', anchor_elements='c', binds={'<Escape>': 'exit'}).run()
        # results = Window(layout, binds={'<Escape>': 'exit'}, right_click_menu=RightClickMenu()).run().results
        window = Window(layout, binds={'<Escape>': 'exit'}, right_click_menu=RightClickMenu())
        with gui_log_handler(multiline):
            results = window.run().results
        print(f'Results: {results}')


if __name__ == '__main__':
    main()
