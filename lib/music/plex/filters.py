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

from __future__ import annotations

import logging
from numbers import Number
from typing import TYPE_CHECKING, Iterable, Hashable, Callable, Any

from plexapi.base import OPERATORS as _OPERATORS

if TYPE_CHECKING:
    from xml.etree.ElementTree import Element

    Operator = Callable[[Any, Any], bool | Any]
    DoesNotMatchFunc = Callable[[Element, Any, str, str, Operator], bool]

__all__ = ['ele_matches_filters']
log = logging.getLogger(__name__)

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
    'not_in': lambda v, q: v not in q,
    'inot_in': lambda v, q: v.lower() not in q.lower(),
    'inot_in_any': lambda v, qs: all(lv not in q.lower() for q in qs) if (lv := v.lower()) else False,
    'not_contains': lambda v, q: q not in v,
    'inot_contains': lambda v, q: q.lower() not in v.lower(),
    'inot_contains_any': lambda v, qs: all(q.lower() not in lv for q in qs) if (lv := v.lower()) else True,
})


class ElementFilterer:
    __slots__ = ('op_cache', 'cast_funcs')

    def __init__(self):
        self.op_cache = {}
        self.cast_funcs = {}

    def ele_matches_filters(self, elem: Element, **kwargs) -> bool:
        # This method replaces :meth:`PlexObject._checkAttrs`
        # Returns True if the element should be included in results, False otherwise
        for attr, query in kwargs.items():
            attr, op, operator, does_not_match = self._get_attr_operator(attr)
            # log.debug(f'Processing {attr=} {op=} {query=} for {elem.attrib.get("key", elem)!r}')
            if does_not_match(elem, query, attr, op, operator):
                return False

        return True

    def _get_attr_operator(self, attr: str) -> tuple[str, str, Operator, DoesNotMatchFunc]:
        try:
            return self.op_cache[attr]
        except KeyError:
            base, op, operator = get_attr_operator(attr)
            if op == 'custom':
                func = self._custom_does_not_match
            elif op == 'notset':
                func = self._notset_does_not_match
            elif op == 'ne' or op == 'nsregex' or 'not' in op:
                func = self._negated_does_not_match
            else:
                func = self._other_does_not_match

            # log.debug(f'get_attr_operator({attr!r}) => attr={base!r}, {op=}, {operator=}, {func=}')
            self.op_cache[attr] = result = base, op, operator, func
            return result

    @classmethod
    def _custom_does_not_match(cls, elem: Element, query, attr: str, op: str, operator: Operator) -> bool:
        return not query(elem.attrib)

    @classmethod
    def _notset_does_not_match(cls, elem: Element, query, attr: str, op: str, operator: Operator) -> bool:
        values = get_attr_value(elem, attr)
        return not operator(values, query)

    def _negated_does_not_match(self, elem: Element, query, attr: str, op: str, operator: Operator) -> bool:
        values = get_attr_value(elem, attr)
        cast = self._get_cast_func(op, query)
        # If any value is not truthy for a negative filter, then it should be filtered out
        return not all(operator(_cast(cast, value, attr, elem), query) for value in values)

    def _other_does_not_match(self, elem: Element, query, attr: str, op: str, operator: Operator) -> bool:
        values = get_attr_value(elem, attr)
        if not values:
            # special case query in (None, 0, '') to include missing attr
            if op == 'exact' and query in (None, 0, ''):
                # original would return that it was a match here, bypassing other filters, which was bad!
                return False
            return True

        cast = self._get_cast_func(op, query)
        for value in values:
            try:
                if operator(_cast(cast, value, attr, elem), query):
                    # if op == 'sregex' and attr == 'originalTitle':
                    #     _log_filter_op(op, attr, cast, elem, value, query, 'True')
                    return False
                # else:
                #     if op == 'sregex' and attr == 'originalTitle':
                #         _log_filter_op(op, attr, cast, elem, value, query, 'False')
            except ValueError:
                # log.error(f'Problem processing {operator=} {value=} {attr=} {elem=} {query=}')
                # raise
                if operator(value, query):
                    return False

        return True

    def _get_cast_func(self, op: str, query: Any):
        try:
            return OP_TO_CAST_FUNC[op]
        except KeyError:
            pass

        key = (op, tuple(query) if not isinstance(query, Hashable) else query)
        try:
            return self.cast_funcs[key]
        except KeyError:
            pass

        self.cast_funcs[key] = func = self._get_cast_func_for_op(op, query)
        return func

    @classmethod
    def _get_cast_func_for_op(cls, op: str, query):
        if op in ('is_odd', 'is_even'):
            return _float_or_int
        elif op not in ('exists', 'notset'):
            if isinstance(query, bool):
                return _bool
            elif isinstance(query, int):
                return _float_or_int
            elif isinstance(query, Number):
                return type(query)
            elif op == 'in' and isinstance(query, Iterable) and not isinstance(query, str):
                types = {type(v) for v in query}
                if not types:  # the set was empty
                    return None
                elif len(types) == 1:
                    func = next(iter(types))
                    return _float_or_int if func is int else func
                elif all(isinstance(v, Number) for v in query):
                    return float
                else:
                    log.debug(f'No common type found for values in {query}')

        return None


# def _log_filter_op(op, attr, cast, elem, value, query, result):
#     log.debug(
#         f'[{op=}][{attr=}][{cast=}][title={elem.attrib.get("title")!r}] operator({value!r}, {query}) => {result}'
#     )


_ELE_FILTERER = ElementFilterer()
ele_matches_filters = _ELE_FILTERER.ele_matches_filters


def get_attr_value(elem: Element, attrstr: str, results=None):
    # log.debug(f'Fetching {attrstr} in {elem.tag}')
    try:
        value = elem.attrib[attrstr]
    except KeyError:
        if attrstr == 'etag':
            return [elem.tag]
    else:
        return [value]

    try:
        attr, attrstr = attrstr.split('__', 1)
    except ValueError:
        lc_attr = attrstr.lower()
        try:
            value = elem.attrib[lc_attr]
        except KeyError:
            # loop through attrs so we can perform case-insensitive match
            for attr, value in elem.attrib.items():
                if lc_attr == attr.lower():
                    return [value]

            return []
        else:
            return [value]
    else:
        lc_attr = attr.lower()
        if results is None:
            results = []

        for child in elem:
            if child.tag.lower() == lc_attr:
                results.extend(get_attr_value(child, attrstr, results))

        return [r for r in results if r is not None]


def _cast(cast, value, attr, elem):
    if cast is None:
        return value
    else:
        try:
            return cast(value)
        except ValueError:
            log.error(f'Unable to cast {attr=} {value=} from {elem=}')
            raise


def get_attr_operator(attr: str):
    try:
        return OP_CACHE[attr]
    except KeyError:
        base, op, operator = _get_attr_operator(attr)
        # log.debug(f'get_attr_operator({attr!r}) => attr={base!r}, {op=}, {operator=}')
        OP_CACHE[attr] = (base, op, operator)
        return base, op, operator


def _get_attr_operator(attr: str):
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


def _float_or_int(x):
    return float(x) if '.' in x else int(x)
