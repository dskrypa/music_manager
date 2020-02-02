"""
:author: Doug Skrypa
"""

import logging
import re
from collections import OrderedDict

from cachetools import LRUCache

from ds_tools.caching import cached
from tz_aware_dt import datetime_with_tz
from ds_tools.http import CodeBasedRestException
from ds_tools.unicode import LangCat, matches_permutation
from ds_tools.utils import (
    DASH_CHARS, QMARKS, ListBasedRecursiveDescentParser, ALL_WHITESPACE, UnexpectedTokenError, ParentheticalParser,
    unsurround, has_unpaired
)
from ...name_processing import (
    categorize_langs, combine_name_parts, eng_cjk_sort, str2list, split_name, has_parens, parse_name
)
from .exceptions import *

__all__ = [
    'album_num_type', 'first_side_info_val', 'LANG_ABBREV_MAP', 'link_tuples', 'NUM2INT', 'parse_date',
    'parse_track_info', 'split_artist_list', 'TrackInfoParser', 'TrackListParser', 'find_href',
    'parse_tracks_from_table'
]
log = logging.getLogger(__name__)

FEAT_ARTIST_INDICATORS = ('with', 'feat.', 'feat ', 'featuring')
LANG_ABBREV_MAP = {
    'chinese': 'Chinese', 'chn': 'Chinese',
    'english': 'English', 'en': 'English', 'eng': 'English',
    'japanese': 'Japanese', 'jp': 'Japanese', 'jap': 'Japanese', 'jpn': 'Japanese',
    'korean': 'Korean', 'kr': 'Korean', 'kor': 'Korean', 'ko': 'Korean',
    'spanish': 'Spanish',
    'mandarin': 'Mandarin'
}
NUM2INT = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9}
NUMS = {
    'first': '1st', 'second': '2nd', 'third': '3rd', 'fourth': '4th', 'fifth': '5th', 'sixth': '6th',
    'seventh': '7th', 'eighth': '8th', 'ninth': '9th', 'tenth': '10th', 'debut': '1st'
}


def find_href(client, anchors, texts, categories=None):
    if not client or not anchors:
        return None
    elif isinstance(texts, str):
        texts = (texts,)
    lc_texts = tuple(filter(None, (t.strip().lower() for t in texts)))
    for a in anchors:
        if isinstance(a, tuple):
            a_text, href = a
        else:
            a_text = a.text
            href = a.get('href') or ''

        if a_text and a_text.strip().lower() in lc_texts:
            href = href[6:] if href.startswith('/wiki/') else href
            if href and 'redlink=1' not in href:
                if href.startswith(('http', '//')):
                    client = client.for_site(href)
                try:
                    if client.is_any_category(href, categories):
                        return href
                except CodeBasedRestException as e:
                    log.log(9, 'Invalid link found: {}'.format(href))
    return None


def _is_invalid_group(text):
    """
    :param text: Text that should be examined for whether it is definitely not a group name or not
    :return bool: True if the given text should be ignored and the group should be set to None, False otherwise
    """
    try:
        part_num_rx = _is_invalid_group._part_num_rx
    except AttributeError:
        part_num_rx = _is_invalid_group._part_num_rx = re.compile(r'^part \d+$', re.IGNORECASE)

    if part_num_rx.match(text):
        return True
    lc_text = text.lower()
    if lc_text in ('full ost only', 'china'):
        return True
    return False


@cached(LRUCache(100), exc=True)
def split_artist_list(artist_list, context=None, anchors=None, client=None):
    """
    feat_indicator ::= feat\.? | featuring | with
    prod_indicator ::= prod(?:\.|uced)? by
    , => delim ::= ,|;[|&|and]  # &|and require special handling...
    group_members ::= member1, member2, ..., memberN
    artist ::= group (group_members) | member (group) |  member_eng (member_cjk) (group_eng (group_cjk)) | group
                | member of group | member1 and member2 of group
    # if artist has parens, if content in parens has a delim: group is before parens, else, group is inside parans
    artists ::= artist and artist | artist[,;&] artist | artist? feat_indicator artists

    :param str artist_list: A list of artists
    :param context: Source of the content being parsed
    :param anchors: List of bs4 'a' elements from a web page
    :param client: WikiClient
    :return tuple: A tuple of (list(artists), list(producers))
    """
    try:
        prod_by_rx = split_artist_list._prod_by_rx
        delim_rx = split_artist_list._delim_rx
        group_paren_members_rx = split_artist_list._group_paren_members_rx
        double_of_rx = split_artist_list._double_of_rx
        space_rx = split_artist_list._space_rx
        and_rx = split_artist_list._and_rx
    except AttributeError:
        prod_by_rx = split_artist_list._prod_by_rx = re.compile(
            r'^(.*)\s\(Prod(?:\.|uced)? by\s+(.*)\)$', re.IGNORECASE
        )
        delim_rx = split_artist_list._delim_rx = re.compile(
            r'(?:,\s*|;\s*|(?:^|\s)(?:,|;|as|feat\.?|featuring|with)\s+)', re.IGNORECASE
        )
        group_paren_members_rx = split_artist_list._group_paren_members_rx = re.compile(r'^([^(]+)\s+\(([^,]+,.*)\)$')
        double_of_rx = split_artist_list._double_of_rx = re.compile(
            r'^(.*?) of (.*?)\s+\((.*?) of (.*)\)$', re.IGNORECASE
        )
        space_rx = split_artist_list._space_rx = re.compile(r'\s+')
        and_rx = split_artist_list._and_rx = re.compile('(?:^|\s)(?:and|&)\s')

    artist_list = space_rx.sub(' ', artist_list)
    artists = []
    producers = []
    group = None
    group_href = None
    # log.debug('split_artist_list({!r}, context={}, anchors={}, client={})'.format(artist_list, context, anchors, client))
    # log.debug('split_artist_list({!r}, context={}, client={})'.format(artist_list, context, client))
    m = group_paren_members_rx.match(artist_list)
    if m:
        if not has_unpaired(m.group(2)):
            # log.debug('{!r} => group={!r}, artist_list={!r}'.format(artist_list, *m.groups()))
            group, artist_list = m.groups()
            if _is_invalid_group(group):
                group, group_href = None, None
            else:
                group_name = split_name(group, prefer_preceder=True)
                group_href = find_href(client, anchors, group_name, 'group')

    for i, artist in enumerate(filter(None, map(str.strip, delim_rx.split(artist_list)))):
        m = group_paren_members_rx.match(artist)
        if m:
            # noinspection PyUnresolvedReferences
            group, artist = m.groups()
            if _is_invalid_group(group):
                group, group_href = None, None
            else:
                group_name = split_name(group, prefer_preceder=True)
                group_href = find_href(client, anchors, group_name, 'group')
        elif artist.startswith('f(') and artist.endswith(')') and '+' in artist:
            group = 'f(x)'
            group_href = find_href(client, anchors, group, 'group')
            artist = ' & '.join(artist[2:-1].split('+'))
        elif i:
            group = None
            group_href = None

        m = prod_by_rx.match(artist)
        if m:
            artist, prod_by = m.groups()
            producers.append(prod_by)

        if ' of ' in artist:
            try:
                soloists, of_group = artist.split(' of ')
            except ValueError as e:
                # log.log(9, 'Error splitting {!r} on "of": {}'.format(artist, e))
                if any(val in artist for val in (' and ', ' & ')):
                    for _artist in re.split(' and | & ', artist):
                        # log.debug('Extending with {!r}'.format(_artist))
                        artists.extend(split_artist_list(_artist, context, anchors, client)[0])
                else:
                    m = double_of_rx.match(artist)
                    if m:
                        soloist_a, group_a, soloist_b, group_b = m.groups()
                        soloist = split_name((soloist_a, soloist_b))
                        group = split_name((group_a, group_b))
                        artist_dict = {
                            'artist': soloist, 'artist_href': find_href(client, anchors, soloist, 'singer'),
                            'of_group': group, 'group_href': find_href(client, anchors, group, 'group'),
                        }
                        artists.append(artist_dict)
                    else:
                        soloist, of_group = artist.split(' of ', 1)
                        try:
                            soloist = split_name(soloist)
                            group = split_name(of_group)
                            artist_dict = {
                                'artist': soloist, 'artist_href': find_href(client, anchors, soloist, 'singer'),
                                'of_group': group, 'group_href': find_href(client, anchors, group, 'group'),
                            }
                        except Exception as e1:
                            msg = 'Unexpected artist name format in {}: {!r}'.format(context, artist)
                            raise WikiEntityParseException(msg) from e
                        else:
                            artists.append(artist_dict)
            else:
                group_href = find_href(client, anchors, of_group, 'group')
                for soloist in re.split(' and | & ', soloists):
                    artist_dict = {
                        'artist_href': find_href(client, anchors, soloist, 'singer'), 'group_href': group_href
                    }
                    for key, val in (('artist', soloist), ('of_group', of_group)):
                        try:
                            artist_dict[key] = split_name(val)
                        except ValueError:
                            artist_dict[key] = split_name(val, require_preceder=False)
                    artists.append(artist_dict)
        else:
            # log.debug('Processing: artist={!r} (did not contain " of ")'.format(artist))
            for _artist in and_rx.split(artist):
                _artist = _artist.strip()
                if not _artist:
                    continue

                _lc_art = _artist.lower()
                if not group and '\'s ' in _artist and (not _lc_art.startswith('girl\'s day') or 'day\'s ' in _lc_art):
                    of_group, _artist = map(str.strip, _artist.split('\'s ', 1))
                    # log.debug('Processing: _artist={!r} group={!r} from {!r}'.format(_artist, of_group, artist))
                    try:
                        soloist = split_name(_artist)
                        group = split_name(of_group)
                        artist_dict = {
                            'artist': soloist, 'artist_href': find_href(client, anchors, soloist, 'singer'),
                            'of_group': group, 'group_href': find_href(client, anchors, group, 'group'),
                        }
                    except Exception as e:
                        msg = 'Unexpected artist name format in {}: {!r}'.format(context, artist)
                        raise WikiEntityParseException(msg) from e
                    else:
                        artists.append(artist_dict)
                        continue

                # log.debug('Processing: _artist={!r} from artist={!r}'.format(_artist, artist))
                try:
                    name = split_name(_artist, prefer_preceder=True)
                except ValueError as e:
                    err_msg = 'Unable to parse artist name={!r} from {}'.format(_artist, context)
                    if not group and LangCat.categorize(_artist) == LangCat.ENG and has_parens(_artist):
                        try:
                            _name, group = ParentheticalParser().parse(_artist)
                        except Exception as e1:
                            err_msg = 'Unable to parse artist name={!r} from {}'.format(_artist, context)
                            raise WikiEntityParseException(err_msg) from e1
                        else:
                            name = split_name(_name)
                            if _is_invalid_group(group):
                                group, group_href = None, None
                            else:
                                try:
                                    group_name = split_name(group)
                                except ValueError:
                                    group_name = split_name(group, require_preceder=False)
                                group_href = find_href(client, anchors, group_name, 'group')
                    else:
                        if _artist.count('(') == 3 and LangCat.categorize(_artist) == LangCat.MIX:
                            parts = ParentheticalParser().parse(_artist)
                            # log.debug('3 parens: {!r} => {}'.format(_artist, parts))
                            if len(parts) != 4:
                                raise WikiEntityParseException(err_msg) from e

                            l0, l1, l2, l3 = categorize_langs(parts)
                            if (l0 == l1 == LangCat.ENG) and (l2 == l3 and l2 in LangCat.asian_cats):
                                name = (parts[0], parts[2])
                                group = (parts[1], parts[3])
                                group_href = find_href(client, anchors, group, 'group')
                            else:
                                raise WikiEntityParseException(err_msg) from e
                        else:
                            raise WikiEntityParseException(err_msg) from e

                try:
                    artist_dict = {'artist': name, 'artist_href': find_href(client, anchors, name, ('singer', 'group'))}
                except Exception as e:
                    if isinstance(e, ValueError) and 'No WikiClient class exists' in str(e):
                        artist_dict = {'artist': name, 'artist_href': None}
                    else:
                        fmt = 'While processing {!r}, error finding href for artist={!r} from {}: {}'
                        log.error(fmt.format(context, name, anchors, e), extra={'color': 'red'})
                        raise

                if group:
                    artist_dict['of_group'] = group
                    artist_dict['group_href'] = group_href
                artists.append(artist_dict)

    # log.debug('split_artist_list({!r}, context={}, client={}) => {}'.format(artist_list, context, client, artists))
    return artists, producers


class TrackListParser(ListBasedRecursiveDescentParser):
    _entry_point = 'tracks'
    _strip = True
    _version_rx = re.compile(r'^[\[(](.*? ver\.?)[\])]\s*(.*)$')
    _quote_reqs = ('WS', 'ARTIST_DELIM', 'COMMA')
    TOKENS = OrderedDict([
        ('QUOTE', '[{}]'.format(QMARKS + "'")),
        ('COMMA', ','),
        ('ARTIST_DELIM', ' as | feat\.? | featuring | with '),
        ('WS', '\s+'),
        ('TEXT', '[^{},]+'.format(QMARKS + "'"))
    ])

    def parse(self, text, context=None, anchors=None, client=None):
        self._context = context
        self._anchors = anchors or tuple()
        self._client = client
        return super().parse(text)

    def tracks(self):
        """
        tracks :: = quote text quote {'with' text}*[, tracks]
        """
        songs = []
        all_collabs = []
        collabs = []
        title = ''
        version = None
        inside_quotes = False
        while self.next_tok:
            if self._accept('QUOTE'):
                if self.prev_tok is None or self.next_tok is None:
                    inside_quotes = not inside_quotes
                elif self._last_any(self._quote_reqs) or self._peek_any(self._quote_reqs):
                    inside_quotes = not inside_quotes
                else:
                    title += self.tok.value
            elif self._accept('COMMA'):
                if inside_quotes:
                    title += self.tok.value
                elif self.next_tok is None or self._peek('QUOTE'):
                    songs.append({
                        'num': None, 'length': '-1:00', 'name_parts': split_name(title), 'collaborators': collabs,
                        'version': version
                    })
                    title = ''
                    version = None
                    collabs = []
            elif self._accept('ARTIST_DELIM'):
                if inside_quotes:
                    title += self.tok.value
            elif self._accept('WS'):
                if inside_quotes:
                    title += self.tok.value
            elif self._accept('TEXT'):
                if inside_quotes:
                    title += self.tok.value
                else:
                    collab = self.tok.value
                    m = self._version_rx.match(collab)
                    if m:
                        version, collab = map(str.strip, m.groups())
                    artists, producers = split_artist_list(collab, self._context, self._anchors, self._client)
                    collabs.extend(artists)
                    all_collabs.extend(artists)
            else:
                raise UnexpectedTokenError('Unexpected {!r} token {!r} in {!r}'.format(
                    self.next_tok.type, self.next_tok.value, self._full
                ))

        title = title.strip()
        if title:
            songs.append({
                'num': None, 'length': '-1:00', 'name_parts': split_name(title), 'collaborators': collabs,
                'version': version
            })
        return songs, all_collabs


class TrackInfoParser(ListBasedRecursiveDescentParser):
    _entry_point = 'content'
    _strip = True
    _opener2closer = {'LPAREN': 'RPAREN', 'LBPAREN': 'RBPAREN', 'LBRKT': 'RBRKT', 'QUOTE': 'QUOTE', 'DASH': 'DASH'}
    _nested_fmts = {'LPAREN': '({})', 'LBPAREN': '({})', 'LBRKT': '[{}]', 'QUOTE': '{!r}', 'DASH': '({})'}
    _content_tokens = ['TEXT', 'WS'] + [v for k, v in _opener2closer.items() if k != v]
    _req_preceders = ['WS'] + list(_opener2closer.values())
    TOKENS = OrderedDict([
        ('QUOTE', '[{}]'.format(QMARKS)),
        ('LPAREN', '\('),
        ('RPAREN', '\)'),
        ('LBPAREN', '（'),
        ('RBPAREN', '）'),
        ('LBRKT', '\['),
        ('RBRKT', '\]'),
        ('TIME', '\s*\d+:\d{2}'),
        ('WS', '\s+'),
        ('DASH', '[{}]'.format(DASH_CHARS)),
        ('TEXT', '[^{}{}()（）\[\]{}]+'.format(DASH_CHARS, QMARKS, ALL_WHITESPACE)),
    ])

    def __init__(self, selective_recombine=True):
        self._selective_recombine = selective_recombine

    def parse(self, text, context=None):
        self._context = context
        return super().parse(text)

    def parenthetical(self, closer='RPAREN'):
        """
        parenthetical ::= ( { text | WS | ( parenthetical ) }* )
        """
        # log.debug('Opening {}'.format(closer))
        self._parenthetical_count += 1
        text = ''
        parts = []
        nested = False
        while self.next_tok:
            if self._accept(closer):
                if text:
                    parts.append(text)
                # log.debug('[closing] Closing {}: {}'.format(closer, parts))
                return parts, nested, False
            elif self._accept_any(self._opener2closer):
                prev_tok_type = self.prev_tok.type
                tok_type = self.tok.type
                if tok_type == 'DASH':
                    # next_dash = self._lookahead('DASH')
                    try:
                        next_dash = self._remaining.index(self.tok.value) + self._pos
                    except ValueError:
                        next_dash = -1
                    next_closer = self._lookahead_unpaired(closer)
                    # log.debug('Found DASH @ pos={}, next is @ pos={}; closer pos={}'.format(self._pos, next_dash, next_closer))
                    if next_dash == -1 or next_dash > next_closer:
                        text += self.tok.value
                        continue
                    elif text and not prev_tok_type == 'WS' and self._peek('TEXT'):
                        text += self.tok.value
                        continue

                if text:
                    parts.append(text)
                    text = ''

                parentheticals, _nested, unpaired = self.parenthetical(self._opener2closer[tok_type])
                if len(parts) == len(parentheticals) == 1 and self._parenthetical_count > 2:
                    if parts[0].lower().startswith(FEAT_ARTIST_INDICATORS):
                        parts[0] = '{} of {}'.format(parts[0].strip(), parentheticals[0])
                    elif parentheticals[0].lower().endswith((' ver.', ' ver', ' version', ' edition', ' ed.')):
                        parts.extend(parentheticals)
                    else:
                        parts[0] += self._nested_fmts[tok_type].format(parentheticals[0])
                else:
                    parts.extend(parentheticals)

                nested = True
            else:
                self._advance()
                text += self.tok.value

        if text:
            parts.append(text)
        # log.debug('[no toks] Closing {}: {}'.format(closer, parts))
        return parts, nested, True

    def content(self):
        """
        content :: = text { (parenthetical) }* { text }*
        """
        self._parenthetical_count = 0
        text = ''
        time_part = None
        parts = []
        while self.next_tok:
            if self._accept_any(self._opener2closer):
                tok_type = self.tok.type
                if text and self.prev_tok.type not in self._req_preceders and self._peek('TEXT'):
                    text += self.tok.value
                    continue
                elif tok_type == 'QUOTE':
                    if any((c not in self._remaining) and (self._full.count(c) % 2 == 1) for c in QMARKS):
                        log.debug('Unpaired quote found in {!r} - {!r}'.format(self._context, self._full))
                        continue
                elif tok_type == 'DASH':
                    # log.debug('Found DASH ({!r}={}); remaining: {!r}'.format(self.tok.value, ord(self.tok.value), self._remaining))
                    if self._peek('TIME'):
                        if text:
                            parts.append(text)
                            text = ''
                        continue
                    elif self._peek('WS') or self.tok.value not in self._remaining:
                        # log.debug('Appending DASH because WS did not follow it or the value does not occur again')
                        text += self.tok.value
                        continue

                if text:
                    parts.append(text)
                    text = ''
                parentheticals, nested, unpaired = self.parenthetical(self._opener2closer[tok_type])
                # log.debug('content parentheticals: {}'.format(parentheticals))
                # log.debug('Parsed {!r} (nested={}); next token={!r}'.format(parentheticals, nested, self.next_tok))
                if not nested and not self._peek('WS') and self.next_tok is not None and len(parentheticals) == 1:
                    text += self._nested_fmts[tok_type].format(parentheticals[0])
                elif len(parentheticals) == 1 and isinstance(parentheticals[0], str):
                    parts.append((parentheticals[0], nested, tok_type))
                else:
                    parts.extend(parentheticals)
            elif self._accept_any(self._content_tokens):
                text += self.tok.value
            elif self._accept('TIME'):
                if self.prev_tok is None:
                    text += self.tok.value
                elif self.prev_tok.type == 'DASH' or not self.next_tok:
                    if time_part:
                        fmt = 'Unexpected {!r} token {!r} in {!r} (time {!r} was already found)'
                        raise UnexpectedTokenError(fmt.format(
                            self.next_tok.type, self.next_tok.value, self._full, time_part
                        ))
                    time_part = self.tok.value.strip()
                else:
                    text += self.tok.value
            else:
                raise UnexpectedTokenError('Unexpected {!r} token {!r} in {!r}'.format(
                    self.next_tok.type, self.next_tok.value, self._full
                ))

        if text:
            parts.append(text)

        if self._selective_recombine:
            single_idxs = set()
            had_nested = False
            for i, part in enumerate(parts):
                if isinstance(part, tuple):
                    nested = part[1]
                    had_nested = had_nested or nested
                    if not nested:
                        single_idxs.add(i)

            # log.debug('{!r} => {} [nested: {}][singles: {}]'.format(self._full, parts, had_nested, sorted(single_idxs)))
            if had_nested and single_idxs:
                single_idxs = sorted(single_idxs)
                while single_idxs:
                    i = single_idxs.pop(0)
                    for ti in (i - 1, i + 1):
                        if (ti < 0) or (ti > (len(parts) - 1)):
                            continue
                        if isinstance(parts[ti], str) and parts[ti].strip():
                            parenthetical, nested, tok_type = parts[i]
                            formatted = self._nested_fmts[tok_type].format(parenthetical)
                            parts[ti] = (formatted + parts[ti]) if ti > i else (parts[ti] + formatted)
                            parts.pop(i)
                            single_idxs = [idx - 1 for idx in single_idxs]
                            break

        cleaned = (part for part in map(str.strip, (p[0] if isinstance(p, tuple) else p for p in parts)) if part)
        return [part for part in cleaned if part not in '"“()（）[]'], time_part


def first_side_info_val(side_info, key):
    try:
        return side_info.get(key, [])[0][0]
    except IndexError:
        return None


def link_tuples(anchors):
    tuple_gen = ((a.text, a.get('href') or '') for a in anchors)
    tuple_gen = ((text, href) for text, href in tuple_gen if '&redlink=1' not in href)
    return tuple((text, href[6:] if href.startswith('/wiki/') else href) for text, href in tuple_gen if href)


def album_num_type(details):
    """

    :param list details: List of words from the first sentence of an intro paragraph that comes after ``is a|the``
    :return tuple: A 2-tuple of (int(album number), str(album type))
    """
    alb_broad_type = next((val for val in ('album', 'single', 'mixtape', 'EP') if val in details), None)
    if alb_broad_type:
        alb_type_desc = details[:details.index(alb_broad_type) + 1]
        if 'full-length' in alb_type_desc:
            alb_type_desc.remove('full-length')
        num = NUMS.get(alb_type_desc[0])
        if alb_broad_type == 'mixtape':
            return num, alb_broad_type
        elif alb_broad_type == 'EP':
            return num, 'extended play'
        return num, ' '.join(alb_type_desc[1:] if num else alb_type_desc)
    elif len(details) > 1 and details[0] == 'song' and details[1] in ('recorded', 'by'):
        return None, 'single'
    elif 'extended play' in ' '.join(details) and details.index('extended') in (1, 2):
        num = NUMS.get(details[1] if details[0] == 'solo' else details[0])
        return num, 'extended play'
    raise ValueError('Unable to determine album type from details: {}'.format(details))


def parse_track_info(
    idx, text, context, length=None, *, include=None, links=None, compilation=False, artist=None, client=None
):
    """
    Split and categorize the given text to identify track metadata such as length, collaborators, and english/cjk name
    parts.

    :param int|str idx: Track number / index in list (1-based)
    :param str|container text: The text to be parsed, or already parsed/split text
    :param str context: uri_path or other identifier for the source of the text being parsed (to add context to errors)
    :param str|None length: Length of the track, if known (MM:SS format)
    :param dict|None include: Additional fields to be included in the returned track dict
    :param list|tuple|None links: List of tuples of (text, href) that were in the html for the given text
    :param bool compilation:
    :param dict|list|None artist: Used to check if a version value matches the artist's name
    :param client: WikiClient to use for link checks
    :return dict: The parsed track information
    """
    if isinstance(idx, str):
        idx = idx.strip()
        if idx.endswith('.'):
            idx = idx[:-1]
        try:
            idx = int(idx)
        except ValueError as e:
            fmt = 'Error parsing track number {!r} for {!r} from {}: {}'
            raise TrackInfoParseException(fmt.format(idx, text, context, e)) from e

    track = {'num': idx, 'length': '-1:00'}
    if include:
        track.update(include)
    if isinstance(text, str):
        text = unsurround(text.strip(), *(c*2 for c in QMARKS))
        try:
            parsed, time_part = TrackInfoParser().parse(text, context)
        except Exception as e:
            raise TrackInfoParseException('Error parsing track from {}: {!r}'.format(context, text)) from e
    else:
        parsed = text
        time_part = None

    # log.debug('{!r} => {}'.format(text, parsed))
    if length:
        track['length'] = length
    if time_part:
        if length:
            fmt = 'Length={!r} was provided for track {}/{!r} from {}, but it was also parsed to be {!r}'
            raise TrackInfoParseException(fmt.format(length, idx, text, context, time_part))
        track['length'] = time_part

    try:
        version_types = parse_track_info._version_types
        misc_indicators = parse_track_info._misc_indicators
    except AttributeError:
        version_types = parse_track_info._version_types = (
            'inst', 'acoustic', 'ballad', 'original', 'remix', 'r&b', 'band', 'karaoke', 'special', 'full length',
            'single', 'album', 'radio', 'limited', 'normal', 'english rap', 'rap', 'piano', 'acapella', 'edm', 'stage',
            'live', 'rock', 'director\'s', 'cd', 'solo', 'classical orchestra', 'orchestra', 'drama', 'acappella',
            'slow', 'guitar'
        )
        misc_indicators = parse_track_info._misc_indicators = ( # spaces intentional
            'bonus', ' ost', ' mix', 'remix', 'special track', 'prod. by', 'produced by', 'director\'s', ' only',
            'remaster', 'intro', 'unit', 'hidden track', 'pre-debut', 'digital'
        )

    name_parts, name_langs, collabs, misc, unknown = [], [], [], [], []
    link_texts = set(link[0] for link in links) if links else None
    if compilation:
        collabs.extend(split_artist_list(parsed.pop(-1), context, links, client)[0])
        # collabs.extend(str2list(parsed.pop(-1), pat='(?: and |,|;|&| feat\.? | featuring | with )'))
        track['compilation'] = True

    for n, part in enumerate(parsed):
        if n == 0:
            # log.debug('{!r}: Adding to name parts: {!r}'.format(text, part))
            name_parts.append(part)
            name_langs.append(LangCat.categorize(part))
            continue
        elif not part:
            continue

        lc_part = part.lower()
        feat = next((val for val in FEAT_ARTIST_INDICATORS if val in lc_part), None)
        duet_etc = next((val for val in (' duet', ' trio') if val in lc_part), None)
        if feat:
            collab_part = part[len(feat):].strip() if lc_part.startswith(feat) else part
            collabs.extend(split_artist_list(collab_part, context, links, client)[0])
            # collabs.extend(str2list(collab_part, pat='(?: and |,|;|&| feat\.? | featuring | with )'))
            # collabs.extend(str2list(part[len(feat):].strip()))
        elif duet_etc:
            collab_part = part[:-len(duet_etc)].strip()
            collabs.extend(split_artist_list(collab_part, context, links, client)[0])
            # collabs.extend(str2list(collab_part, pat='(?: and |,|;|&| feat\.? | featuring | with )'))
        elif lc_part.endswith(' solo'):
            track['artist'] = part[:-5].strip()
        elif lc_part.endswith((' ver.', ' ver', ' version', ' edition', ' ed.')):
            value = part.rsplit(maxsplit=1)[0]
            if lc_part.startswith(version_types) or any(val in lc_part for val in ('remaster',)):
                if track.get('version'):
                    if track['version'].lower() == value.lower():
                        continue
                    elif not track['version'].lower().startswith('inst'):
                        fmt = 'Multiple version entries found for {!r} from {!r}'
                        log.warning(fmt.format(text, context), extra={'color': 14})
                    misc.append('{} ver.'.format(value) if 'ver' in lc_part and 'ver' not in value else part)
                else:
                    track['version'] = value
            else:
                try:
                    track['language'] = LANG_ABBREV_MAP[value.lower()]
                except KeyError:
                    lc_val = value.lower()
                    is_artist_version = False
                    if artist and isinstance(artist, (list, dict)):
                        if isinstance(artist, list) and isinstance(artist[0], dict):
                            _artists = artist
                        elif isinstance(artist, dict):
                            _artists = [artist]
                        else:
                            _artists = []

                        for _artist in _artists:
                            a_name = _artist.get('artist', '')
                            if isinstance(a_name, str):
                                a_name = (a_name,)
                            if any(a_name_part.lower() in lc_val for a_name_part in a_name):
                                is_artist_version = True
                                break

                    if not (is_artist_version or (lc_val == str(context).lower())):
                        dbg_fmt = 'Found unexpected version text in {!r} - {!r}: {!r}'
                        log.debug(dbg_fmt.format(context, text, value), extra={'color': 100})

                    if track.get('version'):
                        old_ver = track['version']
                        if old_ver.lower() == value.lower():
                            continue

                        new_ver = '{} ver.'.format(value) if 'ver' in lc_part and 'ver' not in value else part
                        if len(set(categorize_langs((old_ver, new_ver)))) == 1:
                            warn_fmt = 'Multiple version entries found for {!r} from {!r}'
                            log.warning(warn_fmt.format(text, context), extra={'color': 14})

                        misc.append(new_ver)
                    else:
                        track['version'] = value
        elif lc_part.startswith(('inst', 'acoustic')):
            if track.get('version'):
                _ver = track['version']
                lc_version = _ver.lower()
                if not any(val in lc_version or val in lc_part for val in ('inst', 'acoustic')):
                    fmt = 'Multiple version entries found for {!r} from {!r} (had: {!r}, found: {!r})'
                    log.warning(fmt.format(text, context, _ver, part), extra={'color': 14})
                misc.append('{} ver.'.format(_ver) if 'ver' not in lc_version else _ver)
            track['version'] = part
        elif any(val in lc_part for val in misc_indicators) or all(val in lc_part for val in (' by ', ' of ')):
            misc.append(part)
        elif links and any(link_text in part for link_text in link_texts):
            split_part = str2list(part, pat='(?: and |,|;|&| feat\.? | featuring | with )')
            if any(sp in link_texts for sp in split_part):
                collabs.extend(split_artist_list(part, context, links, client)[0])
                # collabs.extend(split_part)                  # assume links are to artists
            elif len(set(name_langs)) < 2:
                # log.debug('{!r}: Adding to name parts: {!r}'.format(text, part))
                name_parts.append(part)
                name_langs.append(LangCat.categorize(part))
            else:
                log.debug('Assuming {!r} from {!r} > {!r} is misc [no link matches]'.format(part, context, text), extra={'color': 70})
                misc.append(part)
        else:
            if len(set(name_langs)) < 2:
                # log.debug('{!r}: Adding to name parts: {!r}'.format(text, part))
                if '; lit. ' in part:
                    part = part.partition('; lit. ')[0]
                    log.log(9, 'Discarding literal translation from {}: {!r}'.format(context, part))

                part_lang = LangCat.categorize(part)
                if part_lang == LangCat.MIX and ';' in part:
                    cjk, eng = part.split(';', 1)
                    if matches_permutation(eng, cjk):
                        part = cjk
                        part_lang = LangCat.categorize(part)

                name_parts.append(part)
                name_langs.append(part_lang)
            else:
                log.debug('Assuming {!r} from {!r} > {!r} is misc'.format(part, context, text), extra={'color': 70})
                misc.append(part)

    if len(name_parts) > 2:
        log.log(9, 'High name part count in {} [{!r} =>]: {}'.format(context, text, name_parts))
        while len(name_parts) > 2:
            name_parts = combine_name_parts(name_parts)

    try:
        track['name_parts'] = eng_cjk_sort(name_parts[0] if len(name_parts) == 1 else name_parts, tuple(name_langs))
    except ValueError as e:
        # track['name_parts'] = tuple(name_parts) if len(name_parts) == 2 else (name_parts[0], '')
        if len(name_parts) == 2 and len(set(name_langs)) == 1:
            name_parts = combine_name_parts(name_parts)
        try:
            track['name_parts'] = split_name(tuple(name_parts), allow_cjk_mix=True)
        except Exception as e:
            if len(name_parts) == 1 and LangCat.categorize(name_parts[0]) == LangCat.MIX:
                track['name_parts'] = name_parts
            else:
                log.error('Unexpected name_parts={!r} from {} for {}'.format(name_parts, context, track))
                raise e

    if collabs:
        track['collaborators'] = collabs
    if misc:
        track['misc'] = misc
    if unknown:
        track['unknown'] = unknown

    return track


def parse_date(dt_str, try_dateparser=False, source=None):
    dt_formats = ('%Y-%b-%d', '%Y-%m-%d', '%B %d, %Y', '%d %B %Y')
    for dt_fmt in dt_formats:
        try:
            return datetime_with_tz(dt_str, dt_fmt)
        except Exception as e:
            pass

    if try_dateparser:
        try:
            return datetime_with_tz(dt_str, use_dateparser=True)
        except Exception as e:
            pass

    src_msg = ' in {!r}'.format(source) if source else ''
    err_fmt = 'Datetime string {!r}{} did not match any expected format: {}'
    raise UnexpectedDateFormat(err_fmt.format(dt_str, src_msg, ', '.join(map(repr, dt_formats))))


def parse_tracks_from_table(track_tbl, uri_path, client):
    split_cats = (LangCat.HAN, LangCat.MIX)
    tracks = []
    for tr in track_tbl.find_all('tr'):
        tds = tr.find_all('td')
        if len(tds) >= 3:
            include = None
            name_info = tds[1].text
            # log.debug('Processing line for tds[0].text={!r} name_info={!r}'.format(tds[0].text, name_info))
            if tds[0].text.strip().lower() == 'total length:':
                break
            elif has_parens(name_info) and not LangCat.contains_any(name_info, LangCat.HAN):
                name_info_parts = ParentheticalParser().parse(name_info)
                # log.debug('Processing name_info={!r} => {}'.format(name_info, name_info_parts))
                name_info = name_info_parts.pop(0)
                include = {'misc': name_info_parts}
            elif has_parens(name_info) and LangCat.contains_any(name_info, LangCat.HAN):
                name_info_parts = ParentheticalParser().parse(name_info)
                last_part = name_info_parts[-1]
                if len(name_info_parts) > 1 and all(LangCat.contains_any(last_part, cat) for cat in split_cats):
                    orig = name_info_parts.copy()
                    eng_name = name_info_parts.pop(0)
                    extras = LangCat.split(unsurround(name_info_parts.pop(-1)))
                    rom = ''.join(extras.pop(-1).lower().replace('-', '').split())
                    if ';lit.' in rom:
                        rom = rom.partition(';lit.')[0]
                    try:
                        han = extras.pop(-1)
                    except IndexError as e:
                        fmt = 'Error on han: eng={!r} rom={!r} extras={} other={} page={}'
                        log.error(fmt.format(eng_name, rom, extras, name_info_parts, uri_path))
                        raise e

                    # fmt = 'eng={!r} han={!r} rom={!r} extras={}, other={}'
                    # log.debug(fmt.format(eng_name, han, rom, extras, name_info_parts))
                    if LangCat.categorize(han) == LangCat.HAN and matches_permutation(rom, han):
                        name_parts = ['"{} ({})"'.format(eng_name, han)]
                        if extras:
                            name_info_parts.append('; '.join(extras))
                        if name_info_parts:
                            name_parts.extend('({})'.format(part) for part in name_info_parts)
                        name_info = ' '.join(name_parts)
                    elif eng_name.lower().endswith(rom.lower()):
                        name_info = (eng_name, '{} {}'.format(han, rom))
                    else:
                        raise WikiEntityParseException('Unexpected name_info_parts={} in {}'.format(orig, uri_path))

            track = parse_track_info(
                tds[0].text, name_info, uri_path, tds[-1].text.strip(), client=client, include=include
            )
            tracks.append(track)

    return tracks
