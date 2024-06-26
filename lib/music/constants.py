TYPED_TAG_MAP = {   # See: https://wiki.hydrogenaud.io/index.php?title=Tag_Mapping
    'title': {'mp4': '\xa9nam', 'id3': 'TIT2', 'vorbis': 'TITLE'},
    'date': {'mp4': '\xa9day', 'id3': 'TDRC', 'vorbis': 'DATE'},
    'genre': {'mp4': '\xa9gen', 'id3': 'TCON', 'vorbis': 'GENRE'},
    'album': {'mp4': '\xa9alb', 'id3': 'TALB', 'vorbis': 'ALBUM'},
    'album_title': {'vorbis': 'ALBUMTITLE'},  # Non-standard tag, but encountered on a fair number of files in the wild
    'artist': {'mp4': '\xa9ART', 'id3': 'TPE1', 'vorbis': 'ARTIST'},
    'album_artist': {'mp4': 'aART', 'id3': 'TPE2', 'vorbis': 'ALBUMARTIST'},
    'track': {'mp4': 'trkn', 'id3': 'TRCK', 'vorbis': 'TRACKNUMBER'},
    'disk': {'mp4': 'disk', 'id3': 'TPOS', 'vorbis': 'DISCNUMBER'},
    'grouping': {'mp4': '\xa9grp', 'id3': 'TIT1', 'vorbis': 'GROUPING'},
    'album_sort_order': {'mp4': 'soal', 'id3': 'TSOA', 'vorbis': 'ALBUMSORT'},
    'track_sort_order': {'mp4': 'sonm', 'id3': 'TSOT', 'vorbis': 'TITLESORT'},
    'album_artist_sort_order': {'mp4': 'soaa', 'id3': 'TSO2', 'vorbis': 'ALBUMARTISTSORT'},
    'track_artist_sort_order': {'mp4': 'soar', 'id3': 'TSOP', 'vorbis': 'ARTISTSORT'},
    'isrc': {'mp4': '----:com.apple.iTunes:ISRC', 'id3': 'TSRC', 'vorbis': 'ISRC'},  # International Standard Recording Code
    'compilation': {'mp4': 'cpil', 'id3': 'TCMP', 'vorbis': 'COMPILATION'},
    'podcast': {'mp4': 'pcst', 'id3': 'PCST'},  # vorbis: None
    'bpm': {'mp4': 'tmpo', 'id3': 'TBPM', 'vorbis': 'BPM'},
    'language': {'mp4': '----:com.apple.iTunes:LANGUAGE', 'id3': 'TLAN', 'vorbis': 'LANGUAGE'},
    'lyrics': {'mp4': '\xa9lyr', 'id3': 'USLT', 'vorbis': 'LYRICS'},
    'cover': {'mp4': 'covr', 'id3': 'APIC', 'vorbis': 'metadata_block_picture'},  # vorbis: FLAC.pictures
    'wiki:album': {'mp4': '----:WIKI:ALBUM', 'id3': 'WXXX:WIKI:ALBUM', 'vorbis': 'WIKI:ALBUM'},
    'wiki:artist': {'mp4': '----:WIKI:ARTIST', 'id3': 'WXXX:WIKI:ARTIST', 'vorbis': 'WIKI:ARTIST'},
    'kpop:gen': {'mp4': 'KPOP:GEN', 'id3': 'TXXX:KPOP:GEN', 'vorbis': 'KPOP:GEN'},
    'rating': {'mp4': 'POPM', 'id3': 'POPM', 'vorbis': 'POPM'},  # No official mp4/vorbis version; 0-255 maps to 0-10
    # 'name': {'mp4': '', 'id3': '', 'vorbis': ''},
}
# Note: Reverse mapping is handled by music.files.track.utils.tag_id_to_name_map_for_type

TAG_NAME_DISPLAY_NAME_MAP = {
    # Common tags
    'album': 'Album',
    'artist': 'Artist',
    'bpm': 'BPM',
    'date': 'Date',
    'genre': 'Genre',
    'grouping': 'Grouping',
    'isrc': 'ISRC',
    'language': 'Language',
    'lyrics': 'Lyrics',
    'title': 'Song title',
    'rating': 'Rating',

    # Custom tags
    'wiki:album': 'Album\'s Wiki URL',
    'wiki:artist': 'Artist\'s Wiki URL',
    'kpop:gen': 'K-Pop Generation',
}


ID3_TAG_DISPLAY_NAME_MAP = {
    # iTunes Verified Fields
    'TIT2': 'Song title',
    'TALB': 'Album',
    'TPE2': 'Album Artist',
    'TPE1': 'Artist',

    'TCOM': 'Composer',
    # 'TRCK': 'Track number',
    'TRCK': 'Track',
    # 'TPOS': 'Disk Number',
    'TPOS': 'Disk',
    'TCON': 'Genre',
    'TYER': 'Year',                                                             #V2.3

    'USLT': 'Lyrics',
    'TIT1': 'Grouping',
    # 'TBPM': 'BPM (beats per minute)',
    'TBPM': 'BPM',
    'TCMP': 'Compilation (boolean)',                                            #iTunes only
    'TSOC': 'Composer [for sorting]',                                           #iTunes only
    'TSO2': 'Album Artist [for sorting]',                                       #iTunes only
    'TSOT': 'Song title [for sorting]',
    'TSOA': 'Album [for sorting]',
    'TSOP': 'Artist [for sorting]',

    # 'POPM': 'Popularimeter',                            # See https://en.wikipedia.org/wiki/ID3#ID3v2_rating_tag_issue
    'POPM': 'Rating',
    'APIC': 'Album Cover',
    'TDRC': 'Date',                                                             #V2.4
    'COMM': 'Comments',
    'PRIV': 'Private frame',
    'TXXX': 'User-defined',
    'WXXX': 'User-defined URL',

    # region Uncommon tags
    # iTunes-only Fields
    'TDES': 'Podcast Description',
    'TGID': 'Podcast Identifier',
    'WFED': 'Podcast URL',
    'PCST': 'Podcast Flag',

    # General Fields
    'TENC': 'Encoded by',
    'AENC': 'Audio encryption',
    'ASPI': 'Audio seek point index',
    'COMR': 'Commercial frame',
    'ENCR': 'Encryption method registration',
    'EQUA': 'Equalisation',                                                     #V2.3
    'EQU2': 'Equalisation (2)',                                                 #V2.4
    'ETCO': 'Event timing codes',
    'GEOB': 'General encapsulated object',
    'GRID': 'Group identification registration',
    'LINK': 'Linked information',
    'MCDI': 'Music CD identifier',
    'MLLT': 'MPEG location lookup table',
    'OWNE': 'Ownership frame',
    'PCNT': 'Play counter',
    'POSS': 'Position synchronisation frame',
    'RBUF': 'Recommended buffer size',
    'RVAD': 'Relative volume adjustment',                                       #V2.3
    'RVA2': 'Relative volume adjustment (2)',                                   #V2.4
    'RVRB': 'Reverb',
    'SEEK': 'Seek frame',
    'SIGN': 'Signature frame',
    'SYLT': 'Synchronised lyric/text',
    'SYTC': 'Synchronised tempo codes',
    'TCOP': 'Copyright message',
    'TDEN': 'Encoding time',
    'TDLY': 'Playlist delay',
    'TORY': 'Original release year',                                            #V2.3
    'TDOR': 'Original release time',                                            #V2.4
    'TDAT': 'Date',                                                             #V2.3
    'TIME': 'Time',                                                             #V2.3
    'TRDA': 'Recording Date',                                                   #V2.3
    'TDRL': 'Release time',
    'TDTG': 'Tagging time',
    'TEXT': 'Lyricist/Text writer',
    'TFLT': 'File type',
    'IPLS': 'Involved people list',                                             #V2.3
    'TIPL': 'Involved people list',                                             #V2.4
    'TIT3': 'Subtitle/Description refinement',
    'TKEY': 'Initial key',
    'TLAN': 'Language(s)',
    'TLEN': 'Length',
    'TMCL': 'Musician credits list',                                            #V2.4
    'TMED': 'Media type',
    'TMOO': 'Mood',
    'TOAL': 'Original album/movie/show title',
    'TOFN': 'Original filename',
    'TOLY': 'Original lyricist(s)/text writer(s)',
    'TOPE': 'Original artist(s)/performer(s)',
    'TOWN': 'File owner/licensee',
    'TPE3': 'Conductor',
    'TPE4': 'Interpreted, remixed, or otherwise modified by',
    'TPRO': 'Produced notice',
    'TPUB': 'Publisher',
    'TRSN': 'Internet radio station name',
    'TRSO': 'Internet radio station owner',
    'TSRC': 'ISRC (international standard recording code)',
    'TSSE': 'Encoding Settings',
    'TSST': 'Set subtitle',
    'UFID': 'Unique file identifier',
    'USER': 'Terms of use',
    'WCOM': 'Commercial info',
    'WCOP': 'Copyright/Legal info',
    'WOAF': 'Audio file\'s website',
    'WOAR': 'Artist\'s website',
    'WOAS': 'Audio source\'s website',
    'WORS': 'Radio station\'s website',
    'WPAY': 'Payment',
    'WPUB': 'Publisher\'s website',

    # Deprecated
    'TSIZ': 'Size',                                                             # Deprecated in V2.4

    # Invalid tags discovered
    'ITNU': 'iTunesU? [invalid]',
    'TCAT': 'Podcast Category? [invalid]',
    'MJCF': 'MediaJukebox? [invalid]',
    'RGAD': 'Replay Gain Adjustment [invalid]',                             # Not widely supported; superseded by RVA2
    'NCON': 'MusicMatch data [invalid]',                                    # MusicMatch proprietary binary data
    'XTCP': '(unknown) [invalid]',
    'XCM1': '(ripper message?) [invalid]',
    'XSOP': 'Performer Sort Order [invalid]',
    'XSOT': 'Title Sort Order [invalid]',
    'XSOA': 'Album Sort Order [invalid]',
    'XDOR': 'Original Release Time [invalid]',
    'TZZZ': 'Text frame [invalid]',
    'CM1': 'Comment? [invalid]'
    # endregion
}


MP4_TAG_DISPLAY_NAME_MAP = {
    '\xa9nam': 'Song title',
    '\xa9alb': 'Album',
    '\xa9ART': 'Artist',
    'aART': 'Album Artist',
    '\xa9wrt': 'Composer',
    '\xa9day': 'Year',
    '\xa9cmt': 'Comment',
    'desc': 'Description',  # usually used in podcasts
    'purd': 'Purchase Date',
    '\xa9grp': 'Grouping',
    '\xa9gen': 'Genre',
    '\xa9lyr': 'Lyrics',
    'purl': 'Podcast URL',
    'egid': 'Podcast episode GUID',
    'catg': 'Podcast category',
    'keyw': 'Podcast keywords',
    '\xa9too': 'Encoded by',
    'cprt': 'Copyright',
    'soal': 'Album [for sorting]',
    'soaa': 'Album Artist [for sorting]',
    'soar': 'Artist [for sorting]',
    'sonm': 'Title [for sorting]',
    'soco': 'Composer [for sorting]',
    'sosn': 'Show [for sorting]',
    'tvsh': 'Show Name',
    '\xa9wrk': 'Work',
    '\xa9mvn': 'Movement',

    # Boolean values:
    'cpil': 'Compilation (boolean)',
    'pgap': 'Gapless Album (boolean)',
    'pcst': 'Podcast (boolean)',  # iTunes reads this only on import

    # Tuples of ints (multiple values per key are supported):
    'trkn': '(Track, Total Tracks)',
    'disk': '(Disk, Total Disks)',

    # Integer values:
    'tmpo': 'BPM / Tempo',
    '\xa9mvc': 'Movement Count',
    '\xa9mvi': 'Movement Index',
    'shwm': 'Work / Movement',
    'stik': 'Media Kind',
    'rtng': 'Content Rating',
    'tves': 'TV Episode',
    'tvsn': 'TV Season',
    'plID': '(internally used by iTunes)',
    'cnID': '(internally used by iTunes)',
    'geID': '(internally used by iTunes)',
    'atID': '(internally used by iTunes)',
    'sfID': '(internally used by iTunes)',
    'cmID': '(internally used by iTunes)',
    'akID': '(internally used by iTunes)',

    # Others:
    'covr': 'Album Cover',  # list of MP4Cover objects
    'gnre': 'ID3v1 genre. Not supported, use \'\xa9gen\' instead.',
}


VORBIS_TAG_DISPLAY_NAME_MAP = {
    'album': 'Album',
    'albumartist': 'Album Artist',
    'albumartistsort': 'Album Artist [for sorting]',
    'albumsort': 'Album [for sorting]',
    'artist': 'Artist',
    'artistsort': 'Artist [for sorting]',
    'bpm': 'BPM',
    'compilation': 'Compilation (boolean)',
    'date': 'Date',
    'discnumber': 'Disk',
    'genre': 'Genre',
    'grouping': 'Grouping',
    'isrc': 'ISRC',
    'language': 'Language',
    'lyrics': 'Lyrics',
    'title': 'Song title',
    'titlesort': 'Song title [for sorting]',
    'tracknumber': 'Track',
    'unsynced lyrics': 'Lyrics',
}


TYPED_TAG_DISPLAY_NAME_MAP = {
    'id3': ID3_TAG_DISPLAY_NAME_MAP, 'mp4': MP4_TAG_DISPLAY_NAME_MAP, 'vorbis': VORBIS_TAG_DISPLAY_NAME_MAP
}
