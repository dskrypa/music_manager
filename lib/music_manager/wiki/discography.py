"""
:author: Doug Skrypa
"""

import logging

from .base import WikiEntity

__all__ = ['Discography']
log = logging.getLogger(__name__)


class Discography(WikiEntity):
    _categories = ('discography',)
