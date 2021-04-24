TYPED_TAG_MAP = {   # See: https://wiki.hydrogenaud.io/index.php?title=Tag_Mapping
    'title': {'mp4': '\xa9nam', 'mp3': 'TIT2', 'flac': 'TITLE'},
    'date': {'mp4': '\xa9day', 'mp3': 'TDRC', 'flac': 'DATE'},
    'genre': {'mp4': '\xa9gen', 'mp3': 'TCON', 'flac': 'GENRE'},
    'album': {'mp4': '\xa9alb', 'mp3': 'TALB', 'flac': 'ALBUM'},
    'artist': {'mp4': '\xa9ART', 'mp3': 'TPE1', 'flac': 'ARTIST'},
    'album_artist': {'mp4': 'aART', 'mp3': 'TPE2', 'flac': 'ALBUMARTIST'},
    'track': {'mp4': 'trkn', 'mp3': 'TRCK', 'flac': 'TRACKNUMBER'},
    'disk': {'mp4': 'disk', 'mp3': 'TPOS', 'flac': 'DISCNUMBER'},
    'grouping': {'mp4': '\xa9grp', 'mp3': 'TIT1', 'flac': 'GROUPING'},
    'album_sort_order': {'mp4': 'soal', 'mp3': 'TSOA', 'flac': 'ALBUMSORT'},
    'track_sort_order': {'mp4': 'sonm', 'mp3': 'TSOT', 'flac': 'TITLESORT'},
    'album_artist_sort_order': {'mp4': 'soaa', 'mp3': 'TSO2', 'flac': 'ALBUMARTISTSORT'},
    'track_artist_sort_order': {'mp4': 'soar', 'mp3': 'TSOP', 'flac': 'ARTISTSORT'},
    'isrc': {'mp4': '----:com.apple.iTunes:ISRC', 'mp3': 'TSRC', 'flac': 'ISRC'},  # International Standard Recording Code
    'compilation': {'mp4': 'cpil', 'mp3': 'TCMP', 'flac': 'COMPILATION'},
    'podcast': {'mp4': 'pcst', 'mp3': 'PCST'},  # flac: None
    'bpm': {'mp4': 'tmpo', 'mp3': 'TBPM', 'flac': 'BPM'},
    'language': {'mp4': '----:com.apple.iTunes:LANGUAGE', 'mp3': 'TLAN', 'flac': 'LANGUAGE'},
    'lyrics': {'mp4': '\xa9lyr', 'mp3': 'USLT', 'flac': 'LYRICS'},
    'cover': {'mp4': 'covr', 'mp3': 'APIC'},  # flac: FLAC.pictures
    'wiki:album': {'mp4': 'WIKI:ALBUM', 'mp3': 'WXXX:WIKI:ALBUM', 'flac': 'WIKI:ALBUM'},
    'wiki:artist': {'mp4': 'WIKI:ARTIST', 'mp3': 'WXXX:WIKI:ARTIST', 'flac': 'WIKI:ARTIST'},
    'kpop:gen': {'mp4': 'KPOP:GEN', 'mp3': 'TXXX:KPOP:GEN', 'flac': 'KPOP:GEN'},
    # 'name': {'mp4': '', 'mp3': '', 'flac': ''},
}

tag_name_map = {
    # Custom
    'WXXX:WIKI:ALBUM': 'Album\'s Wiki URL',
    'WXXX:WIKI:ARTIST': 'Artist\'s Wiki URL',
    'TXXX:KPOP:GEN': 'K-Pop Generation',

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


mp4_tag_name_map = {
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


flac_tag_name_map = {
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


typed_tag_name_map = {'mp3': tag_name_map, 'mp4': mp4_tag_name_map, 'flac': flac_tag_name_map}
