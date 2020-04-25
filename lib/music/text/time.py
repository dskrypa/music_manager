"""
:author: Doug Skrypa
"""

from datetime import datetime, date
from typing import Union

__all__ = ['parse_date']
DATE_FORMATS = ('%Y-%b-%d', '%Y-%m-%d', '%Y.%m.%d', '%B %d, %Y', '%d %B %Y')
DateObj = Union[date, datetime, str, None]


def parse_date(value: DateObj) -> date:
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

    raise ValueError(f'Unable to parse date from {value!r} using common date formats')
