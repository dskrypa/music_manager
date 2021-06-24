"""
:author: Doug Skrypa
"""

from typing import Union

from lark.exceptions import UnexpectedEOF, UnexpectedInput

__all__ = [
    'PlexException',
    'PlexQueryException',
    'InvalidQueryFilter',
    'InvalidPlaylist',
    'BaseQueryParseError',
    'UnexpectedParseError',
    'QueryParseError',
    'InvaidQuery',
]


class PlexException(Exception):
    """Base exception for the Plex package"""


class PlexQueryException(PlexException):
    """Base query exception"""


class InvalidQueryFilter(PlexQueryException):
    """An invalid query filter was provided"""


class InvalidPlaylist(PlexException):
    """Exception to be raised when an operation is attempted on a playlist does not exist"""


# region Query Parsing Exceptions


class BaseQueryParseError(PlexException):
    """Base class for errors encountered while parsing a query"""


class UnexpectedParseError(BaseQueryParseError):
    """Exception to be raised when a query cannot be parsed"""


class QueryParseError(BaseQueryParseError):
    def __init__(self, text: str, cause: Union[UnexpectedInput, UnexpectedEOF]):
        self.text = text
        self.cause = cause
        if isinstance(cause, UnexpectedInput):
            self.context = cause.get_context(text)
            self.expected = None
        elif isinstance(cause, UnexpectedEOF):
            self.context = None
            self.expected = ', '.join(x.name for x in cause.expected)
        else:
            raise TypeError(f'Unexpected {cause=}')

    def __str__(self):
        if self.context is not None:
            return f'Parsing error - section with unexpected content:\n{self.context}'
        else:
            return f'Parsing error - unexpected EOF - expected one of:\n{self.expected}'


class InvaidQuery(QueryParseError):
    def __str__(self):
        if self.context is not None:
            return f'Invalid query - section with unexpected content:\n{self.context}'
        else:
            return f'Invalid query - unexpected EOF - expected one of:\n{self.expected}'

# endregion
