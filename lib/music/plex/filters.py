"""
Replaces some of PlexAPI's query filtering methods.  Used by :mod:`.query`.  Without directly monkey-patching, the
functions here change:

  - PlexObject's _getAttrOperator to avoid an O(n) operation (n=len(OPERATORS)) on every object in searches, and to
    support negation via __not__{op}
  - PlexObject's fetchItem operators to include a compiled regex pattern search
  - PlexObject's _getAttrValue for minor optimizations
  - PlexObject's _checkAttrs to fix op=exact behavior, and to support filtering based on if an attribute is not set

:author: Doug Skrypa
"""

import logging
from numbers import Number
from typing import Iterable, Hashable

from plexapi.base import OPERATORS as _OPERATORS

__all__ = ['check_attrs']
log = logging.getLogger(__name__)

CAST_FUNCS = {}
OP_CACHE = {}
OP_TO_CAST_FUNC = {
    k: None for k in (
        'sregex', 'nsregex', 'lc', 'ieq', 'iexact', 'icontains', 'startswith', 'istartswith', 'endswith',
        'iendswith', 'regex', 'iregex'
    )
}
OPERATORS = dict(_OPERATORS, **{
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


def check_attrs(elem, **kwargs):
    # Return True if the elem should be included in results, False otherwise
    for attr, query in kwargs.items():
        attr, op, operator = get_attr_operator(attr)
        # log.debug(f'Processing {attr=!r} {op=!r} {query=!r} for {elem.attrib.get("key", elem)!r}')
        if op == 'custom':
            if not query(elem.attrib):
                return False
        else:
            values = get_attr_value(elem, attr)
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
                if op == 'ne' or op == 'nsregex' or 'not' in op:
                    # If any value is not truthy for a negative filter, then it should be filtered out
                    if not all(operator(_cast(cast, value, attr, elem), query) for value in values):
                        return False
                else:
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
                            # log.error(f'Problem processing operator={operator} value={value!r} attr={attr!r} elem={elem!r} query={query!r}')
                            # raise
                            if operator(value, query):
                                break
                    else:
                        return False
    return True


def get_attr_value(elem, attrstr, results=None):
    # log.debug('Fetching {} in {}'.format(attrstr, elem.tag))
    try:
        attr, attrstr = attrstr.split('__', 1)
    except ValueError:
        lc_attr = attrstr.lower()
        # check were looking for the tag
        if lc_attr == 'etag':
            return [elem.tag]
        # loop through attrs so we can perform case-insensitive match
        for _attr, value in elem.attrib.items():
            if lc_attr == _attr.lower():
                return [value]
        return []
    else:
        lc_attr = attr.lower()
        results = [] if results is None else results
        for child in (c for c in elem if c.tag.lower() == lc_attr):
            results.extend(get_attr_value(child, attrstr, results))
        return list(filter(lambda r: r is not None, results))


def _cast(cast, value, attr, elem):
    if cast is None:
        return value
    else:
        try:
            return cast(value)
        except ValueError:
            log.error(f'Unable to cast {attr=!r} {value=!r} from {elem=!r}')
            raise


def cast_func(op, query):
    try:
        return OP_TO_CAST_FUNC[op]
    except KeyError:
        pass
    key = (op, tuple(query) if not isinstance(query, Hashable) else query)
    try:
        return CAST_FUNCS[key]
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

        CAST_FUNCS[key] = func
        return func


def get_attr_operator(attr):
    try:
        return OP_CACHE[attr]
    except KeyError:
        base, op, operator = _get_attr_operator(attr)
        # log.debug('get_attr_operator({!r}) => attr={!r}, op={!r}, operator={}'.format(attr, base, op, operator))
        OP_CACHE[attr] = (base, op, operator)
        return base, op, operator


def _get_attr_operator(attr):
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


def _bool(value):
    if isinstance(value, str):
        try:
            return bool(int(value))
        except ValueError:
            pass
    return bool(value)
