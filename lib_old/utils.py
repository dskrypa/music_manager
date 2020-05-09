"""
:author: Doug Skrypa
"""

import logging
import re
from collections import OrderedDict
from itertools import chain
from urllib.parse import urlparse

from ds_tools.utils import QMARKS, regexcape
from ds_tools.utils.soup import soupify

__all__ = ['get_page_category', 'synonym_pattern']
log = logging.getLogger(__name__)

FEAT_ARTIST_INDICATORS = ('with', 'feat.', 'feat ', 'featuring')
NUM_STRIP_TBL = str.maketrans({c: '' for c in '0123456789'})

PAGE_CATEGORIES = OrderedDict([
    ('album', ('albums', 'discography article stubs', ' eps')),     # Note: space in ' eps' is intentional
    ('group', ('group', 'group article stubs', 'bands', 'duos')),
    ('singer', ('singer', 'person article stubs', 'actor', 'actress', 'musician', 'rapper', 'living people')),
    ('soundtrack', ('osts', 'kost', 'jost', 'cost')),
    ('competition_or_show', ('competition', 'variety show', 'variety television')),
    ('tv_series', ('television series', 'drama', 'competition shows')),
    ('discography', ('discographies',)),
    ('disambiguation', ('disambiguation', 'ambiguous')),
    ('agency', ('agencies',)),
    ('sports team', ('sports team',)),
    ('movie', ('movies', 'films')),
    ('play', ('plays',)),
    ('characters', ('fictional characters', 'film characters')),
    ('filmography', ('filmographies',)),
    ('misc', (
        'games', 'comics', 'deities', 'television seasons', 'appliances', 'standards', 'military', 'amusement',
        'episodes', 'hobbies', 'astronauts', 'war', 'economics', 'disasters', 'events', 'bugs', 'modules', 'elves',
        'dwarves', 'orcs', 'lists', 'twost', 'food', 'alcohol', 'pubs', 'geography', 'towns', 'cities', 'countries',
        'counties', 'landmark', 'lake', 'ocean', 'forest', 'roads', 'manga'
    )),
])

QMARK_STRIP_TBL = str.maketrans({c: '' for c in QMARKS})
SYNONYM_SETS = [{'and', '&', '+'}, {'version', 'ver.'}]


def synonym_pattern(text, synonym_sets=None, chain_sets=True):
    """
    :param str text: Text from which a regex pattern should be generated
    :param synonym_sets: Iterable that yields sets of synonym strings, or None to use :data:`SYNONYM_SETS`
    :param bool chain_sets: Chain the given synonym_sets with :data:`SYNONYM_SETS` (if False: only consider the provided
      synonym_sets)
    :return: Compiled regex pattern for the given text that will match the provided synonyms
    """
    parts = [regexcape(part) for part in re.split('(\W)', re.sub('\s+', ' ', text.lower())) if part]
    synonym_sets = chain(SYNONYM_SETS, synonym_sets) if chain_sets and synonym_sets else synonym_sets or SYNONYM_SETS

    for synonym_set in synonym_sets:
        for i, part in enumerate(list(parts)):
            if part in synonym_set:
                parts[i] = '(?:{})'.format('|'.join(regexcape(s) for s in sorted(synonym_set)))

    pattern = ''.join('\s+' if part == ' ' else part for part in parts)
    # log.debug('Synonym pattern: {!r} => {!r}'.format(text, pattern))
    return re.compile(pattern, re.IGNORECASE)


def get_page_category(url, cats, no_debug=False, raw=None):
    if url.endswith('_discography'):
        return 'discography'
    elif any(i in cat for i in ('singles', 'songs') for cat in cats):
        if any('single album' in cat for cat in cats):
            return 'album'
        else:
            return 'collab/feature/single'
    else:
        to_return = None
        for category, indicators in PAGE_CATEGORIES.items():
            if any(i in cat for i in indicators for cat in cats):
                to_return = category
                break

        if to_return == 'soundtrack':
            uri_path = urlparse(url).path
            uri_path = uri_path[6:] if uri_path.startswith('/wiki/') else uri_path
            if uri_path.count('/') > 1 and raw and 'Lyrics' in raw:
                expected = uri_path.rsplit('/', 1)[0]
                for a in soupify(raw).find_all('a'):
                    if a.get('href') == expected:
                        return 'lyrics'
        elif to_return == 'tv_series' and any(val in cats for val in ('banjun drama', 'lists', 'manga series')):
            return 'misc'

        if to_return:
            return to_return

        if '/wiki/Template:' in url:
            return 'template'

        if not no_debug:
            log.debug('Unable to determine category for {}'.format(url))
        return None
