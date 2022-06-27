# need to run as a module

from ds_tools.logging import init_logging

from .core import Window
from .table import Table
from .inputs import Input


def main():
    init_logging(2, log_path=None, names=None)

    table1 = Table.from_data([{'a': 1, 'b': 2}, {'a': 3, 'b': 4}], show_row_nums=True)
    table2 = Table.from_data([{'a': 1, 'b': 2}, {'a': 3, 'b': 4}], show_row_nums=True)
    inpt = Input('test', size=(15, 1))
    window = Window('Test One', [[table1, table2], [inpt]], size=(600, 600), element_justification='c')
    window.run()


if __name__ == '__main__':
    main()
