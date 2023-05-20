"""
Plex query grammar / parsing

:author: Doug Skrypa
"""

import logging
from functools import cached_property
from io import StringIO
from typing import Iterable

from lark import Lark, Tree, Token, Transformer, v_args
from lark.exceptions import UnexpectedEOF, UnexpectedInput

from ds_tools.core.decorate import cached_classproperty
from .exceptions import UnexpectedParseError, InvaidQuery

__all__ = ['PlexQuery']
log = logging.getLogger(__name__)


PLEX_QUERY_GRAMMAR = r"""
?start: query
query: key_val_expr (_WS key_val_expr)*
key_val_expr: KEY operation value
operation.2: _WS NOT (_US | _WS) TEXT_OP _WS | _WS EXC? TEXT_OP _WS | _WS? EXC? (EQ | LIKE) _WS? | _WS? MATH_OP _WS?
value: ESCAPED_STRING | VALUE (_WS VALUE)*

KEY: /[a-zA-Z]+/
VALUE: /[^!=~\s]+/
TEXT_OP: /(like(_exact)?|i?(contains|endswith|eq|exact|regex|startswith)|is(_odd|_even)?|[gl]te?|ne|in|lc|exists|n?sregex|notset)/i
MATH_OP: "<=" | "<" | ">=" | ">" | "=="
NOT: "NOT"i
EXC: "!"
EQ: "="
LIKE: "~"
_US: "_"

%import common.WS_INLINE -> _WS
%import common.ESCAPED_STRING
"""


class PlexQuery:
    def __init__(self, query: str, escape: str = '()'):
        self._query = query.strip()
        self._escape = escape
        self.escape_tbl = str.maketrans({c: '\\' + c for c in '()[]{}^$+*.?|\\' if c in escape})

    @classmethod
    def parse(cls, query: str, escape: str = '()', allow_inst: bool = False, title: str = None):
        filters = cls(query, escape).parsed if query else {}
        if title and title != '.*':
            if not any(c in title for c in '()[]{}^$+*.?' if c not in escape):
                filters.setdefault('title__icontains', title)
            else:
                filters.setdefault('title__like', title)
        if not allow_inst:
            filters.setdefault('title__not_like', r'inst(?:\.?|rumental)')
        return filters

    @classmethod
    def parse_old(cls, obj_type: str, title: str, query: str, escape: str = '()', allow_inst: bool = False):
        obj_type = obj_type[:-1] if obj_type.endswith('s') else obj_type
        plex_query = cls(query, escape)
        title = title.translate(plex_query.escape_tbl)
        filters = plex_query.parsed
        if title and title != '.*':
            if not any(c in title for c in '()[]{}^$+*.?' if c not in escape):
                filters.setdefault('title__icontains', title)
            else:
                filters.setdefault('title__like', title)

        if not allow_inst:
            filters.setdefault('title__not_like', r'inst(?:\.?|rumental)')
        return obj_type, filters

    @cached_property
    def parsed(self):
        parsed = {
            f'{key}__{op}': value.translate(self.escape_tbl) if 'regex' in op or 'like' in op else value
            for (key, op), value in self._parsed.items()
        }
        return parsed

    @cached_property
    def _parsed(self):
        return QueryTransformer().transform(self._parsed_tree)

    @cached_property
    def _parsed_tree(self):
        try:
            return self.parser.parse(self._query)  # noqa
        except (UnexpectedEOF, UnexpectedInput) as e:
            raise InvaidQuery(self._query, e) from e
        except Exception as e:
            err_msg = f'Unexpected error parsing query={self._query!r}'
            log.error(f'{err_msg}:', exc_info=True)
            raise UnexpectedParseError(err_msg) from e

    @cached_classproperty
    def parser(cls) -> Lark:  # noqa
        return Lark(PLEX_QUERY_GRAMMAR)


class QueryTransformer(Transformer):
    math_op_value_map = {'>=': 'gte', '>': 'gt', '<=': 'lte', '<': 'lt', '==': 'exact'}

    @v_args()
    def operation(self, parts: Iterable[str]) -> str:
        return ''.join(parts)

    @v_args()
    def value(self, parts: Iterable[str]) -> str | float | int:
        value = ' '.join(parts)
        for cls in (int, float):
            try:
                return cls(value)
            except (TypeError, ValueError):
                pass
        return value

    @v_args(inline=True)
    def key_val_expr(self, key: str, op: str, value: str) -> tuple[tuple[str, str], str]:
        return (key, op), value

    def query(self, key_val_exprs: dict[tuple[str, str], str]):  # noqa
        return dict(key_val_exprs)

    def ESCAPED_STRING(self, tok: Token) -> str:  # noqa
        return tok.value[1:-1].replace('\\"', '"')

    def KEY(self, tok: Token) -> str:  # noqa
        return tok.value

    def NOT(self, tok: Token) -> str:  # noqa
        return 'not_'

    def EQ(self, tok: Token) -> str:  # noqa
        return 'exact'

    def LIKE(self, tok: Token) -> str:  # noqa
        return 'like'

    def MATH_OP(self, tok: Token) -> str:  # noqa
        return self.math_op_value_map[tok.value]

    VALUE = KEY
    EXC = NOT


def print_tree(tree):
    print(format_tree(tree))


def format_tree(tree, indent: int = 0, in_list: bool = False) -> str:
    sio = StringIO()
    prefix = ' ' * indent
    suffix = ',' if in_list else ''
    if isinstance(tree, Tree):
        sio.write(f'{prefix}Tree({tree.data!r}, [\n')
        for child in tree.children:
            sio.write(format_tree(child, indent + 4, True))
        sio.write(f'{prefix}]){suffix}\n')
    elif isinstance(tree, Token):
        sio.write(f'{prefix}{tree!r}{suffix}\n')
    else:
        raise TypeError(f'Unexpected type={tree.__class__.__name__!r} for {tree=}')
    return sio.getvalue()
