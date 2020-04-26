"""
:author: Doug Skrypa
"""

from datetime import datetime, date
from typing import Union

__all__ = ['parse_date', 'DateResult']
DATE_FORMATS = ('%Y-%b-%d', '%Y-%m-%d', '%Y.%m.%d', '%B %d, %Y', '%d %B %Y')
DateObj = Union[date, datetime, str, None]
DateResult = Union[date, 'FutureDate']


class FutureDate:
    __slots__ = ('circa', '_date')

    def __init__(self, circa=None):
        self.circa = circa
        if circa:
            try:
                self._date = datetime.strptime(circa, '%Y').date()
            except ValueError:
                self._date = date(9999, 1, 1)
        else:
            self._date = date(9999, 1, 1)

    def __eq__(self, other):
        if isinstance(other, FutureDate):
            return self.circa == other.circa
        return False

    def __lt__(self, other):
        if isinstance(other, FutureDate):
            return self._date < other._date
        return self._date < other

    def __repr__(self):
        return f'<{self.__class__.__name__}({self.circa!r})>'

    def strftime(self, format_str=None):
        return f'TBA({self.circa})' if self.circa else 'TBA'

    @property
    def year(self):
        year = self._date.year
        return 'TBA' if year == 9999 else year


def parse_date(value: DateObj) -> DateResult:
    """
    :param str|date|datetime|None value: The value from which a date should be parsed
    :return: The parsed date
    """
    if value is None or isinstance(value, date):
        return value
    elif isinstance(value, datetime):
        return value.date()

    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass

    if value.isdigit() and len(value) == 4 and value.startswith(datetime.now().strftime('%Y')[:2]):
        return FutureDate(value)

    raise ValueError(f'Unable to parse date from {value!r} using common date formats')
