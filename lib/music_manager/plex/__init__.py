"""
Package for working with the Plex API, and for syncing Plex ratings with ratings stored in ID3 tags.

Note on fetchItems:
The kwargs to fetchItem/fetchItems use __ to access nested attributes, but the only nested attributes available are
those that are returned in the items in ``plex._session.query(plex._ekey(search_type))``, not the higher level objects.
Example available attributes::\n
    >>> data = plex._session.query(plex._ekey('track'))
    >>> media = [c for c in data[0]]
    >>> for m in media:
    ...     m
    ...     m.attrib
    ...     print(', '.join(sorted(m.attrib)))
    ...     for part in m:
    ...         part
    ...         part.attrib
    ...         print(', '.join(sorted(part.attrib)))
    ...
    <Element 'Media' at 0x000001E4E3971458>
    {'id': '76273', 'duration': '238680', 'bitrate': '320', 'audioChannels': '2', 'audioCodec': 'mp3', 'container': 'mp3'}
    audioChannels, audioCodec, bitrate, container, duration, id
    <Element 'Part' at 0x000001E4E48D9458>
    {'id': '76387', 'key': '/library/parts/76387/1555183134/file.mp3', 'duration': '238680', 'file': '/path/to/song.mp3', 'size': '9773247', 'container': 'mp3', 'hasThumbnail': '1'}
    container, duration, file, hasThumbnail, id, key, size

    >>> data = plex._session.query(plex._ekey('album'))
    >>> data[0]
    <Element 'Directory' at 0x000001E4E3C92458>
    >>> print(', '.join(sorted(data[0].attrib.keys())))
    addedAt, guid, index, key, loudnessAnalysisVersion, originallyAvailableAt, parentGuid, parentKey, parentRatingKey, parentThumb, parentTitle, ratingKey, summary, thumb, title, type, updatedAt, year
    >>> elements = [c for c in data[0]]
    >>> for e in elements:
    ...     e
    ...     e.attrib
    ...     for sub_ele in e:
    ...         sub_ele
    ...         sub_ele.attrib
    ...
    <Element 'Genre' at 0x000001E4E3C929F8>
    {'tag': 'K-pop'}

Example playlist syncs::\n
    >>> plex.sync_playlist('K-Pop 3+ Stars', userRating__gte=6, genre__like='[kj]-?pop')
    2019-06-01 08:53:39 EDT INFO __main__ 178 Creating playlist K-Pop 3+ Stars with 485 tracks
    >>> plex.sync_playlist('K-Pop 4+ Stars', userRating__gte=8, genre__like='[kj]-?pop')
    2019-06-01 08:54:13 EDT INFO __main__ 178 Creating playlist K-Pop 4+ Stars with 257 tracks
    >>> plex.sync_playlist('K-Pop 5 Stars', userRating__gte=10, genre__like='[kj]-?pop')
    2019-06-01 08:54:22 EDT INFO __main__ 178 Creating playlist K-Pop 5 Stars with 78 tracks
    >>> plex.sync_playlist('K-Pop 5 Stars', userRating__gte=10, genre__like='[kj]-?pop')
    2019-06-01 08:54:58 EDT VERBOSE __main__ 196 Playlist K-Pop 5 Stars does not contain any tracks that should be removed
    2019-06-01 08:54:58 EDT VERBOSE __main__ 208 Playlist K-Pop 5 Stars is not missing any tracks
    2019-06-01 08:54:58 EDT INFO __main__ 212 Playlist K-Pop 5 Stars contains 78 tracks and is already in sync with the given criteria


Object and element attributes and elements available for searching:
 - track:
    - attributes: addedAt, duration, grandparentGuid, grandparentKey, grandparentRatingKey, grandparentThumb,
      grandparentTitle, guid, index, key, originalTitle, parentGuid, parentIndex, parentKey, parentRatingKey,
      parentThumb, parentTitle, ratingKey, summary, thumb, title, type, updatedAt
    - elements: media
 - album:
    - attributes: addedAt, guid, index, key, loudnessAnalysisVersion, originallyAvailableAt, parentGuid, parentKey,
      parentRatingKey, parentThumb, parentTitle, ratingKey, summary, thumb, title, type, updatedAt, year
    - elements: genre
 - artist:
    - attributes: addedAt, guid, index, key, lastViewedAt, ratingKey, summary, thumb, title, type, updatedAt,
      userRating, viewCount
    - elements: genre
 - media:
    - attributes: audioChannels, audioCodec, bitrate, container, duration, id
    - elements: part
 - genre:
    - attributes: tag
 - part:
    - attributes: container, duration, file, hasThumbnail, id, key, size

:author: Doug Skrypa
"""

from .server import LocalPlexServer
from .utils import stars
