"""
:author: Doug Skrypa
"""

import logging
from datetime import datetime, date

__all__ = ['parse_date']
log = logging.getLogger(__name__)
DATE_FORMATS = ('%Y-%b-%d', '%Y-%m-%d', '%Y.%m.%d', '%B %d, %Y', '%d %B %Y')


def parse_date(value):
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
