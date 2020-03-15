"""
:author: Doug Skrypa
"""

import atexit
import logging
from numbers import Number
from typing import Iterable, Hashable

from plexapi.audio import Track, Album, Artist
from plexapi.base import OPERATORS, PlexObject
from plexapi.playlist import Playlist

from .utils import stars

__all__ = ['apply_plex_patches', 'track_repr']
log = logging.getLogger(__name__)


def cls_name(obj):
    return obj.__class__.__name__


def track_repr(self, rating=None):
    fmt = '<{}#{}[{}]({!r}, artist={!r}, album={!r})>'
    rating = stars(rating or self.userRating)
    artist = self.originalTitle if self.grandparentTitle == 'Various Artists' else self.grandparentTitle
    return fmt.format(cls_name(self), self._int_key(), rating, self.title, artist, self.parentTitle)


def apply_plex_patches(deinit_colorama=True):
    """
    Monkey-patch...
      - PlexObject's _getAttrOperator to avoid an O(n) operation (n=len(OPERATORS)) on every object in searches, and to
        support negation via __not__{op}
      - PlexObject's fetchItem operators to include a compiled regex pattern search
      - PlexObject's _getAttrValue for minor optimizations
      - PlexObject's _checkAttrs to fix op=exact behavior, and to support filtering based on if an attribute is not set
      - Playlist to support semi-bulk item removal (the Plex REST API does not have a bulk removal handler, but the
        removeItems method added below removes the reload step between items)
      - Track, Album, and Artist to have more readable/useful reprs
      - PlexObject to be sortable

    :param bool deinit_colorama: plexapi.utils imports tqdm (it uses it to print a progress bar during downloads); when
      importing tqdm, tqdm imports and initializes colorama.  Colorama ends up raising exceptions when piping output to
      ``| head``.  Defaults to True.
    """
    OPERATORS.update({
        'custom': None,
        'lc': lambda v, q: v.lower() == q.lower(),
        'eq': lambda v, q: v == q,
        'ieq': lambda v, q: v.lower() == q.lower(),
        'sregex': lambda v, pat: pat.search(v),
        # 'nsregex': lambda v, pat: print('{} !~ {!r}: {}'.format(pat, v, not pat.search(v))) or not pat.search(v),
        'nsregex': lambda v, pat: not pat.search(v),
        'is': lambda v, q: v is q,
        'notset': lambda v, q: (not v) if q else v,
        'is_odd': lambda v, q: divmod(int(float(v)), 2)[1],
        'is_even': lambda v, q: not divmod(int(float(v)), 2)[1],
        'not_in': lambda v, q: v not in q
    })
    op_cache = {}

    if deinit_colorama:
        try:
            import colorama
        except ImportError:
            pass
        else:
            colorama.deinit()
            atexit.unregister(colorama.initialise.reset_all)

    def _bool(value):
        if isinstance(value, str):
            try:
                return bool(int(value))
            except ValueError:
                pass
        return bool(value)

    def get_attr_operator(attr):
        try:
            base, op = attr.rsplit('__', 1)
        except ValueError:
            return attr, 'exact', OPERATORS['exact']
        else:
            try:
                operator = OPERATORS[op]
            except KeyError:
                return attr, 'exact', OPERATORS['exact']
            else:
                if base.endswith('__not'):
                    return base[:-5], 'not ' + op, lambda *a: not operator(*a)
                return base, op, operator

    def _get_attr_operator(self, attr):
        try:
            return op_cache[attr]
        except KeyError:
            base, op, operator = get_attr_operator(attr)
            log.debug('get_attr_operator({!r}) => attr={!r}, op={!r}, operator={}'.format(attr, base, op, operator))
            op_cache[attr] = (base, op, operator)
            return base, op, operator

    op_to_cast_func = {
        k: None for k in (
            'sregex', 'nsregex', 'lc', 'ieq', 'iexact', 'icontains', 'startswith', 'istartswith', 'endswith',
            'iendswith', 'regex', 'iregex'
        )
    }
    cast_funcs = {}

    def cast_func(op, query):
        try:
            return op_to_cast_func[op]
        except KeyError:
            pass
        key = (op, tuple(query) if not isinstance(query, Hashable) else query)
        try:
            return cast_funcs[key]
        except KeyError:
            if op in ('is_odd', 'is_even'):
                func = int
            elif op not in ('exists', 'notset'):
                if isinstance(query, bool):
                    func = lambda x: _bool(x)
                elif isinstance(query, int):
                    func = lambda x: float(x) if '.' in x else int(x)
                elif isinstance(query, Number):
                    func = type(query)
                elif op == 'in' and isinstance(query, Iterable) and not isinstance(query, str):
                    types = {type(v) for v in query}
                    if not types:                       # the set was empty
                        func = None
                    elif len(types) == 1:
                        func = next(iter(types))
                    elif all(isinstance(v, Number) for v in query):
                        func = float
                    else:
                        log.debug('No common type found for values in {}'.format(query))
                        func = None
                else:
                    func = None
            else:
                func = None

            if func is int:
                func = lambda x: float(x) if '.' in x else int(x)

            cast_funcs[key] = func
            return func

    def get_attr_value(elem, attrstr, results=None):
        # log.debug('Fetching {} in {}'.format(attrstr, elem.tag))
        try:
            attr, attrstr = attrstr.split('__', 1)
        except ValueError:
            lc_attr = attrstr.lower()
            # check were looking for the tag
            if lc_attr == 'etag':
                # if elem.tag == 'Genre':
                #     log.debug('Returning [{}]'.format(elem.tag))
                return [elem.tag]
            # loop through attrs so we can perform case-insensitive match
            for _attr, value in elem.attrib.items():
                if lc_attr == _attr.lower():
                    # if elem.tag == 'Genre':
                    #     log.debug('Returning {}'.format(value))
                    return [value]
            # if elem.tag == 'Genre':
            #     log.debug('Returning []')
            return []
        else:
            lc_attr = attr.lower()
            results = [] if results is None else results
            for child in (c for c in elem if c.tag.lower() == lc_attr):
                results += get_attr_value(child, attrstr, results)
            # if elem.tag == 'Genre':
            #     log.debug('Returning {}'.format([r for r in results if r is not None]))
            return [r for r in results if r is not None]

    def _cast(cast, value, attr, elem):
        try:
            return cast(value) if cast is not None else value
        except ValueError:
            log.error('Unable to cast attr={} value={} from elem={}'.format(attr, value, elem))
            raise

    def _checkAttrs(self, elem, **kwargs):
        # Return True if the elem should be included in results, False otherwise
        for attr, query in kwargs.items():
            attr, op, operator = _get_attr_operator(None, attr)
            if op == 'custom':
                if not query(elem.attrib):
                    return False
            else:
                values = get_attr_value(elem, attr)
                # if op == 'sregex' and attr == 'originalTitle':
                #     log.debug(f'Processing title={elem.attrib.get("title")!r} with op={op} values={values}')

                # special case query in (None, 0, '') to include missing attr
                if op == 'exact' and not values and query in (None, 0, ''):
                    # original would return True here, bypassing other filters, which was bad!
                    pass
                elif op == 'notset':
                    if not operator(values, query):
                        return False
                else:
                    cast = cast_func(op, query)
                    # return if attr we're looking for is missing
                    if op in ('ne', 'nsregex') or 'not' in op:
                        # If any value is not truthy for a negative filter, then it should be filtered out
                        if not all(operator(_cast(cast, value, attr, elem), query) for value in values):
                            return False
                    else:
                        # if op == 'in':
                        #     log.debug(f'query: {query}')
                        for value in values:
                            try:
                                if operator(_cast(cast, value, attr, elem), query):
                                    # if op == 'sregex' and attr == 'originalTitle':
                                    #     log.debug(f'[op={op}][attr={attr}][cast={cast}][title={elem.attrib.get("title")!r}] operator({value!r}, {query}) => True')
                                    break
                                # else:
                                #     if op == 'sregex' and attr == 'originalTitle':
                                #         log.debug(f'[op={op}][attr={attr}][cast={cast}][title={elem.attrib.get("title")!r}] operator({value!r}, {query}) => False')
                            except ValueError:
                                if operator(value, query):
                                    break

                            #     log.error(f'Problem processing operator={operator} value={value!r} attr={attr!r} elem={elem!r} query={query!r}')
                            #     raise
                            # else:
                            #     log.debug(f'Successfully processed operator={operator} value={value!r} attr={attr!r} elem={elem!r} query={query!r}')
                        else:
                            return False
        return True

    def removeItems(self, items):
        """ Remove multiple tracks from a playlist. """
        del_method = self._server._session.delete
        uri_fmt = '{}/items/{{}}'.format(self.key)
        results = [self._server.query(uri_fmt.format(item.playlistItemID), method=del_method) for item in items]
        self.reload()
        return results

    def album_repr(self):
        fmt = '<{}#{}[{}]({!r}, artist={!r}, genres={})>'
        rating = stars(float(self._data.attrib.get('userRating', 0)))
        genres = ', '.join(g.tag for g in self.genres)
        return fmt.format(cls_name(self), self._int_key(), rating, self.title, self.parentTitle, genres)

    def artist_repr(self):
        fmt = '<{}#{}[{}]({!r}, genres={})>'
        rating = stars(float(self._data.attrib.get('userRating', 0)))
        genres = ', '.join(g.tag for g in self.genres)
        return fmt.format(cls_name(self), self._int_key(), rating, self.title, genres)

    def full_info(ele):
        return {'_type': ele.tag, 'attributes': ele.attrib, 'elements': [full_info(e) for e in ele]}

    PlexObject._getAttrOperator = _get_attr_operator
    PlexObject._checkAttrs = _checkAttrs
    PlexObject._int_key = lambda self: int(self._clean(self.key))
    PlexObject.__lt__ = lambda self, other: int(self._clean(self.key)) < int(other._clean(other.key))
    PlexObject.as_dict = lambda self: full_info(self._data)

    Playlist.removeItems = removeItems
    Track.__repr__ = track_repr
    Album.__repr__ = album_repr
    Artist.__repr__ = artist_repr
