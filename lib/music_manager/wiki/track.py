"""
:author: Doug Skrypa
"""

import logging

from .base import WikiEntity

__all__ = ['Track']
log = logging.getLogger(__name__)


class Track(WikiEntity):
    _categories = ()
