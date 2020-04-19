"""
Wiki parsing utilities and site-specific parsers

:author: Doug Skrypa
"""

__all__ = ['WikiParser']

from .abc import WikiParser

# Import the site-specific parsers so that WikiParser is aware of their existence, but do not expose them via __all__ so
# the main entry point for using site-specific parsers is via WikiParser.for_site()
from .drama_wiki import DramaWikiParser
from .generasia import GenerasiaParser
from .kpop_fandom import KpopFandomParser, KindieFandomParser
from .wikipedia import WikipediaParser
