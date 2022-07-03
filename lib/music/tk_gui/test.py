# need to run as a module

from pathlib import Path

from ds_tools.logging import init_logging

from .core import Window
from .elements import Table, Input, Image, Animation, SpinnerImage, ClockImage, Button
from .popups import ImagePopup, AnimatedPopup, SpinnerPopup, ClockPopup


def main():
    init_logging(2, log_path=None, names=None)

    table1 = Table.from_data([{'a': 1, 'b': 2}, {'a': 3, 'b': 4}], show_row_nums=True)
    table2 = Table.from_data([{'a': 1, 'b': 2}, {'a': 3, 'b': 4}], show_row_nums=True)
    inpt = Input('test', size=(15, 1))

    icons_dir = Path(__file__).resolve().parents[3].joinpath('icons')
    gif_path = icons_dir.joinpath('spinners', 'ring_gray_segments.gif')
    png_path = icons_dir.joinpath('exclamation-triangle-yellow.png')

    layout = [
        [table1, table2],
        [inpt, Button('Submit')],
        [Animation(gif_path), SpinnerImage()],
        [ClockImage()],
        [Image(png_path)]
    ]

    # ImagePopup(png_path).run()
    # AnimatedPopup(gif_path).run()
    # SpinnerPopup(img_size=(400, 400)).run()
    # ClockPopup(toggle_slim_on_click=True).run()

    # window = Window('Test One', layout, size=(600, 600), element_justification='c')
    window = Window('Test One', layout, element_justification='c', binds={'<Escape>': 'exit'})
    window.run()


if __name__ == '__main__':
    main()
