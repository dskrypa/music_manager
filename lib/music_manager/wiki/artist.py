"""
:author: Doug Skrypa
"""

import logging

from .base import PersonOrGroup

__all__ = ['Artist', 'Singer', 'Group']
log = logging.getLogger(__name__)


class Artist(PersonOrGroup):
    _categories = ()


class Singer(Artist):
    _categories = ('singer', 'actor', 'actress')


class Group(Artist):
    _categories = ('group',)
