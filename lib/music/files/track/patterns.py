"""
:author: Doug Skrypa
"""

from __future__ import annotations

import re
from fnmatch import translate as fnmatch_to_regex_str
from typing import TYPE_CHECKING, Iterable, Pattern, Union

if TYPE_CHECKING:
    from music.typing import OptStr

__all__ = [
    'ALBUM_CLEANUP_RE_FUNCS', 'EXTRACT_PART_MATCH', 'GROUP_TITLE_MATCH_FUNCS', 'LYRIC_URL_MATCH', 'SAMPLE_RATE_PAT',
    'glob_patterns', 'cleanup_album_name', 'cleanup_lyrics', 'split_album_part',
]

StrsOrPatterns = Iterable[Union[str, Pattern]]

# region Globals

ALBUM_CLEANUP_RE_FUNCS = (
    (re.compile(r'^\[\d{4}[0-9.]*\](.*)', re.IGNORECASE).match, lambda m: m.group(1).strip()),
    (re.compile(r'(.*)\s*\[.*Album(?: repackage)?\]', re.IGNORECASE).match, lambda m: m.group(1).strip()),
    (
        re.compile(
            r'^(.*?)-?\s*(?:the)?\s*[0-9](?:st|nd|rd|th)\s+\S*\s*album\s*(?:repackage)?\s*(.*)$', re.IGNORECASE
        ).match,
        lambda m: ' '.join(map(str.strip, m.groups())).strip()
    ),
    (re.compile(r'((?:^|\s+)\d+\s*집(?:$|\s+))').search, lambda m: m.string.replace(m.group(1), ' ').strip()),
    (re.compile(r'(.*)(\s-\s*(?:EP|Single))$', re.IGNORECASE).match, lambda m: m.group(1)),
    (re.compile(r'^(.*)\sO\.S\.T\.?(\s.*|$)', re.IGNORECASE).match, lambda m: '{} OST{}'.format(*m.groups()))
)

EXTRACT_PART_MATCH = re.compile(r'^(.*)\s+((?:Part|Code No)\.?\s*\d+)$', re.IGNORECASE).match

GROUP_TITLE_MATCH_FUNCS = [re.compile('^(.*) `(.*)`$').match, re.compile('^(.*) - (.*)$').match]

LYRIC_URL_MATCH = re.compile(r'^(.*)(https?://\S+)$', re.DOTALL).match

SAMPLE_RATE_PAT = re.compile(r'\((\d+(?:\.\d+)?)\s*kHz\)', re.IGNORECASE)


# endregion


def glob_patterns(patterns: StrsOrPatterns) -> list[Pattern]:
    if patterns:
        return [re.compile(fnmatch_to_regex_str(p)[4:-3]) if isinstance(p, str) else p for p in patterns]
    return []


def cleanup_album_name(album: str, artist: str = None) -> str:
    for re_func, on_match_func in ALBUM_CLEANUP_RE_FUNCS:
        if m := re_func(album):
            album = on_match_func(m)

    if artist:
        for re_func in GROUP_TITLE_MATCH_FUNCS:
            if m := re_func(album):
                group, title = m.groups()
                if group in artist:
                    album = title
                break

    return album.replace(' : ', ': ').strip()


def cleanup_lyrics(lyrics: str) -> OptStr:
    if m := LYRIC_URL_MATCH(lyrics):
        return m.group(1).strip() + '\r\n'
    return None


def split_album_part(title: str) -> tuple[str, OptStr]:
    if m := EXTRACT_PART_MATCH(title):
        title, part = map(str.strip, m.groups())
    else:
        part = None
    if title.endswith(' -'):
        title = title[:-1].strip()
    return title, part
