"""
Track / Album typing helpers
"""

from __future__ import annotations

from typing import Union, Iterable, Any, TypeVar, Callable

from mutagen import FileType
from mutagen.flac import VCFLACDict, FLAC, Picture
from mutagen.id3 import ID3, Frame, APIC
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4Tags, MP4, MP4Cover

from .track.track import SongFile


MutagenFile = Union[MP3, MP4, FLAC, FileType]
ImageTag = Union[APIC, MP4Cover, Picture]
TagsType = Union[ID3, MP4Tags, VCFLACDict]
ID3Tag = TypeVar('ID3Tag', bound=Frame)

TagChanges = dict[str, tuple[Any, Any]]

ProgressCB = Callable[[SongFile, int], Any]
TrackIter = Iterable[SongFile]
