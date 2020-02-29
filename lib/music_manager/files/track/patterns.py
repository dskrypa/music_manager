"""
:author: Doug Skrypa
"""

import re
from fnmatch import translate as fnmatch_to_regex_str

__all__ = [
    'ALBUM_CLEANUP_RE_FUNCS', 'ALBUM_DIR_CLEANUP_RE_FUNCS', 'ALBUM_VOLUME_MATCH', 'EXTRACT_PART_MATCH',
    'GROUP_TITLE_MATCH_FUNCS', 'compiled_fnmatch_patterns', 'cleanup_album_name'
]

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

ALBUM_DIR_CLEANUP_RE_FUNCS = (
    (re.compile(r'^\[\d{4}[0-9.]*\] (.*)$').match, lambda m: m.group(1).strip()),   # Begins with date
    (re.compile(r'(.*)\s*\[.*Album\]').match, lambda m: m.group(1).strip()),        # Ends with Xth Album
)

ALBUM_VOLUME_MATCH = re.compile(r'(.*)(\((?:vol.?|volume) (?:\d+|[ivx]+)\))$', re.IGNORECASE).match

EXTRACT_PART_MATCH = re.compile(r'^(.*)\s+((?:Part|Code No)\.?\s*\d+)$', re.IGNORECASE).match

GROUP_TITLE_MATCH_FUNCS = [re.compile('^(.*) `(.*)`$').match, re.compile('^(.*) - (.*)$').match]


def compiled_fnmatch_patterns(patterns):
    if patterns:
        return [re.compile(fnmatch_to_regex_str(p)[4:-3]) if isinstance(p, str) else p for p in patterns]
    return []


def cleanup_album_name(album, artist=None):
    for re_func, on_match_func in ALBUM_CLEANUP_RE_FUNCS:
        m = re_func(album)
        if m:
            album = on_match_func(m)

    if artist:
        for re_func in GROUP_TITLE_MATCH_FUNCS:
            m = re_func(album)
            if m:
                group, title = m.groups()
                if group in artist:
                    album = title
                break

    return album.replace(' : ', ': ').strip()
