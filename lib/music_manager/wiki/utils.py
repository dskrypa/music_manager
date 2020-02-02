"""
:author: Doug Skrypa
"""

import logging
from datetime import datetime, date

__all__ = ['parse_date']
log = logging.getLogger(__name__)
DATE_FORMATS = ('%Y-%b-%d', '%Y-%m-%d', '%Y.%m.%d', '%B %d, %Y', '%d %B %Y')


def parse_date(value):
    if value is None or isinstance(value, datetime):
        return value
    elif isinstance(value, date):
        return datetime.fromordinal(value.toordinal())

    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass

    raise ValueError(f'Unable to parse date from {value!r} using common date formats')
