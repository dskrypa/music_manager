"""

"""


from __future__ import annotations

from base64 import b64decode, b64encode
from datetime import date
from hashlib import sha256
from pathlib import Path
from platform import system
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Optional, Union, Iterable, Any, Collection, Type, Mapping, TypeVar, Callable
from urllib.parse import quote
from weakref import WeakValueDictionary

from mutagen import File, FileType
from mutagen.flac import VCFLACDict, FLAC, Picture
from mutagen.id3 import ID3, POPM, TDRC, Frames, Frame, _frames, ID3FileType, APIC, PictureType, Encoding
from mutagen.id3._specs import MultiSpec, Spec
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4Tags, MP4, MP4Cover, AtomDataType, MP4FreeForm
from mutagen.ogg import OggFileType, OggPage
from mutagen.oggflac import OggFLAC
from mutagen.oggvorbis import OggVorbis
from mutagen.oggopus import OggOpus
from mutagen.wave import WAVE, _WaveID3

from ds_tools.caching.decorators import cached_property, ClearableCachedPropertyMixin
from ds_tools.core.decorate import cached_classproperty
from ds_tools.core.patterns import PatternMatcher, FnMatcher, ReMatcher
from ds_tools.fs.paths import iter_files, Paths
from ds_tools.output.formatting import readable_bytes
from ds_tools.output.prefix import LoggingPrefix

from music.common.ratings import stars_to_256, stars_from_256, stars
from music.common.utils import format_duration
from music.constants import TYPED_TAG_MAP, TYPED_TAG_DISPLAY_NAME_MAP, TAG_NAME_DISPLAY_NAME_MAP
from music.text.name import Name
from .track.track import SongFile

__all__ = []


MutagenFile = Union[MP3, MP4, FLAC, FileType]
ImageTag = Union[APIC, MP4Cover, Picture]
TagsType = Union[ID3, MP4Tags, VCFLACDict]
ID3Tag = TypeVar('ID3Tag', bound=Frame)

TagChanges = dict[str, tuple[Any, Any]]

ProgressCB = Callable[[SongFile, int], Any]
TrackIter = Iterable[SongFile]
