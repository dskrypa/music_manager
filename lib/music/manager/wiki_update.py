"""
:author: Doug Skrypa
"""

from __future__ import annotations

import json
import logging
import webbrowser
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Union, Optional, Iterator

from ds_tools.caching.decorators import cached_property
from ds_tools.fs.paths import Paths, get_user_cache_dir
from wiki_nodes.http import MediaWikiClient

from ..common.disco_entry import DiscoEntryType
from ..common.prompts import choose_item
from ..files.album import iter_album_dirs, AlbumDir
from ..files.track.track import SongFile
from ..text.name import Name
from ..wiki import Track, Artist, Singer, Group
from ..wiki.album import DiscographyEntry, DEEdition, DEPart, DiscoObj, Soundtrack, SoundtrackEdition
from ..wiki.parsing.utils import LANG_ABBREV_MAP
from ..wiki.typing import StrOrStrs
from .config import UpdateConfig
from .enums import CollabMode
from .exceptions import MatchException, NoArtistFoundError
from .update import AlbumInfo, TrackInfo, normalize_case
from .wiki_match import AlbumFinder, find_artists
from .wiki_utils import get_disco_part

__all__ = ['update_tracks']
log = logging.getLogger(__name__)

ArtistType = Union[Artist, Group, Singer, 'ArtistSet']

CONFIG_DIR = Path('~/.config/music_manager/').expanduser()


def update_tracks(
    paths: Paths,
    dry_run: bool = False,
    soloist: bool = False,
    hide_edition: bool = False,
    collab_mode: Union[CollabMode, str] = CollabMode.ARTIST,
    url: Optional[str] = None,
    add_bpm: bool = False,
    dest_base_dir: Union[Path, str, None] = None,
    title_case: bool = False,
    artist_sites: StrOrStrs = None,
    album_sites: StrOrStrs = None,
    dump: Optional[str] = None,
    load: Optional[str] = None,
    artist_url: Optional[str] = None,
    update_cover: bool = False,
    no_album_move: bool = False,
    artist_only: bool = False,
    add_genre: bool = True,
):
    config = UpdateConfig(
        soloist=soloist,
        hide_edition=hide_edition,
        collab_mode=collab_mode,
        add_bpm=add_bpm,
        title_case=title_case,
        artist_sites=artist_sites,
        album_sites=album_sites,
        update_cover=update_cover,
        no_album_move=no_album_move,
        artist_only=artist_only,
        add_genre=add_genre,
    )
    WikiUpdater(paths, config, artist_url=artist_url).update(dest_base_dir, load, url, dry_run, dump)


class WikiUpdater:
    """
    This class mainly exists to prevent needing to shuffle a large number of variables between functions.

    Variables are split so that those used during discovery are provided in init, and those used during updating are
    provided in update.
    """

    def __init__(self, paths: Paths, config: UpdateConfig, artist_url: Optional[str] = None):
        self.paths = paths
        self.config = config
        self.artist_url = artist_url

    @cached_property
    def artist(self) -> Optional[Artist]:
        if self.artist_url:
            return Artist.from_url(self.artist_url)
        return None

    def update(
        self,
        dest_base_dir: Union[Path, str, None] = None,
        load_path: Optional[str] = None,
        album_url: Optional[str] = None,
        dry_run: bool = False,
        dump: Optional[str] = None,
    ):
        if dest_base_dir is not None and not isinstance(dest_base_dir, Path):
            dest_base_dir = Path(dest_base_dir).expanduser().resolve()

        for album_dir, album_info in self._iter_dir_info(load_path, album_url):
            album_dir.remove_bad_tags(dry_run)
            album_dir.fix_song_tags(dry_run, self.config.add_bpm)
            if dump:
                album_info.dump(Path(dump).expanduser().resolve())
                return
            else:
                album_info.update_and_move(
                    album_dir, dest_base_dir, dry_run, self.config.no_album_move, self.config.add_genre
                )

    def get_album_info(self, album_url: Optional[str]) -> tuple[AlbumDir, ArtistInfoProcessor]:
        if album_url:
            return self._from_album_url(album_url)
        elif self.config.artist_only:
            if self.artist:
                return next(iter(self._from_artist()))
            else:
                album_dir = next(iter(iter_album_dirs(self.paths)))
                processor = ArtistInfoProcessor.for_album_dir(album_dir, self.config)
                return album_dir, processor
        else:
            album_dir = next(iter(iter_album_dirs(self.paths)))
            processor = AlbumInfoProcessor.for_album_dir(album_dir, self.config)
            return album_dir, processor

    def _iter_dir_info(self, load_path: str, album_url: str) -> Iterator[tuple[AlbumDir, AlbumInfo]]:
        if load_path:
            yield self._from_path(load_path)
        elif album_url:
            album_dir, processor = self._from_album_url(album_url)
            yield album_dir, processor.to_album_info()
        else:
            if self.config.artist_only:
                if self.artist:
                    for album_dir, processor in self._from_artist():
                        yield album_dir, processor.to_album_info()
                else:
                    yield from self._from_artist_matches()
            else:
                yield from self._from_album_matches()

    def _from_path(self, load_path: str) -> tuple[AlbumDir, AlbumInfo]:
        album_info = AlbumInfo.load(Path(load_path).expanduser().resolve())
        try:
            album_dir = album_info.album_dir
        except ValueError:
            album_dir = get_album_dir(self.paths, 'load path')
        return album_dir, album_info

    def _from_album_url(self, album_url: str) -> tuple[AlbumDir, AlbumInfoProcessor]:
        album_dir = get_album_dir(self.paths, 'wiki URL')
        entry = DiscographyEntry.from_url(album_url)
        processor = AlbumInfoProcessor(album_dir, entry, self.config, self.artist)
        return album_dir, processor

    def _from_artist(self) -> Iterator[tuple[AlbumDir, ArtistInfoProcessor]]:
        for album_dir in iter_album_dirs(self.paths):
            processor = ArtistInfoProcessor(album_dir, self.config, self.artist)
            yield album_dir, processor

    def _from_artist_matches(self) -> Iterator[tuple[AlbumDir, AlbumInfo]]:
        for album_dir in iter_album_dirs(self.paths):
            try:
                processor = ArtistInfoProcessor.for_album_dir(album_dir, self.config)
            except MatchException as e:
                log.log(e.lvl, e, extra={'color': 9})
                log.debug(e, exc_info=True)
            else:
                yield album_dir, processor.to_album_info()

    def _from_album_matches(self) -> Iterator[tuple[AlbumDir, AlbumInfo]]:
        for album_dir in iter_album_dirs(self.paths):
            try:
                processor = AlbumInfoProcessor.for_album_dir(album_dir, self.config)
            except MatchException as e:
                log.log(e.lvl, e, extra={'color': 9})
                log.debug(e, exc_info=True)
            else:
                yield album_dir, processor.to_album_info()


class ArtistInfoProcessor:
    def __init__(self, album_dir: AlbumDir, config: UpdateConfig, artist: Optional[Artist] = None):
        self.album_dir = album_dir
        self.config = config
        self._init_artist = artist
        self._artist_from_tag = False

    @classmethod
    def for_album_dir(cls, album_dir: AlbumDir, config: UpdateConfig) -> ArtistInfoProcessor:
        try:
            artists = find_artists(album_dir, sites=config.artist_sites)
        except Exception as e:
            if isinstance(e, ValueError) and e.args[0] == 'No candidates found':
                raise MatchException(30, f'No match found for {album_dir} ({album_dir.name})') from e
            else:
                raise MatchException(40, f'Error finding an artist match for {album_dir}: {e}') from e
        else:
            artist = choose_item(artists, 'artist', before=f'Found multiple artists for {album_dir}')
            log.info(f'Matched {album_dir}\'s artist to {artist}')
            return cls(album_dir, config, artist)

    def to_album_info(self) -> AlbumInfo:
        album_info = AlbumInfo.from_album_dir(self.album_dir)
        return self.set_artist_album_info(album_info)

    def set_artist_album_info(self, album_info: AlbumInfo) -> AlbumInfo:
        album_info.artist = self.album_artist_name
        # album_info.parent = self.normalize_artist(self.album_artist.name.english)
        album_info.parent = Name.from_enclosed(self.album_artist_name).english
        album_info.singer = self.normalize_artist(self.artist.name.english)
        album_info.solo_of_group = isinstance(self.artist, Singer) and self.artist.groups and not self.soloist
        album_info.wiki_artist = getattr(self.album_artist, 'url', None)

        for path, track in album_info.tracks.items():
            track.artist = self.artist_name

        return album_info

    # region Configurable Overrides

    @cached_property
    def artist_name_overrides(self) -> dict[str, str]:
        overrides_path = CONFIG_DIR.joinpath('artist_name_overrides.json')
        if overrides_path.exists():
            log.debug(f'Loading {overrides_path}')
            with overrides_path.open('r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    @cached_property
    def _soloist_overrides(self) -> dict[str, str]:
        overrides_path = CONFIG_DIR.joinpath('soloist_overrides.json')
        if overrides_path.exists():
            log.debug(f'Loading {overrides_path}')
            with overrides_path.open('r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    # endregion

    # region Artist / Group Methods

    @cached_property
    def artist(self) -> ArtistType:
        return self._init_artist

    @cached_property
    def album_artist(self) -> ArtistType:
        return self._artist_group or self.artist

    @cached_property
    def soloist(self) -> bool:
        if self.config.soloist:
            return True
        return self._soloist_overrides.get(str(self.artist.name), False)

    @cached_property
    def _artist_group(self) -> Optional[Group]:
        artist = self.artist
        if isinstance(artist, Singer) and artist.groups and not self.soloist:
            return choose_item(artist.groups, 'group', before=f'Found multiple groups for {artist}')
        return None

    # endregion

    # region Name Methods

    @cached_property
    def album_artist_name(self) -> str:
        if group := self._artist_group:
            return f'{self.normalize_artist(self.artist.name)} ({group.name})'
        return self.normalize_artist(self.album_artist.name)

    @cached_property
    def artist_name(self) -> str:
        artist_name = self.normalize_artist(self.artist.name)
        if group := self._artist_group:
            return f'{artist_name} ({group.name})'
        return artist_name

    def _normalize_name(self, name: str) -> str:
        if self.config.title_case:
            name = normalize_case(name)
        return name.strip()

    def normalize_artist(self, artist) -> str:
        artist_name = str(artist)
        if override := self.artist_name_overrides.get(artist_name):
            log.debug(f'Overriding {artist_name=!r} with {override!r}')
            return override
        return artist_name

    # endregion


class AlbumInfoProcessor(ArtistInfoProcessor):
    def __init__(self, album_dir: AlbumDir, album: DiscoObj, config: UpdateConfig, artist: Optional[Artist] = None):
        super().__init__(album_dir, config, artist)
        self.album = album

    @classmethod
    def for_album_dir(
        cls, album_dir: AlbumDir, config: UpdateConfig, artist: Optional[Artist] = None
    ) -> AlbumInfoProcessor:
        try:
            album = AlbumFinder(album_dir, sites=config.album_sites).find_album()
        except Exception as e:
            if isinstance(e, ValueError) and e.args[0] == 'No candidates found':
                raise MatchException(30, f'No album match found for {album_dir} ({album_dir.name})') from e
            else:
                raise MatchException(40, f'Error finding an album match for {album_dir}: {e}') from e
        else:
            log.info(f'Matched {album_dir} to {album}')
            return cls(album_dir, album, config, artist=artist)

    def to_album_info(self) -> AlbumInfo:
        log.info(f'Artist for {self.edition}: {self.artist}')
        if (ed_lang := self.edition.lang) and (lang := LANG_ABBREV_MAP.get(ed_lang.lower())):
            genre = f'{lang[0]}-Pop' if lang in ('Chinese', 'Japanese', 'Korean', 'Mandarin') else None
        else:
            genre = None

        config = self.config
        full_name = self.disco_part.full_name(config.hide_edition, config.part_in_title)
        album_info = AlbumInfo(
            title=self._normalize_name(full_name),
            artist=self.album_artist_name,
            date=self.disco_part.date,
            disk=self.disco_part.disc,
            genre=genre,
            name=full_name.strip(),
            # parent=self.normalize_artist(self.album_artist.name.english),
            parent=Name.from_enclosed(self.album_artist_name).english,
            singer=self.normalize_artist(self.artist.name.english),
            solo_of_group=isinstance(self.artist, Singer) and self.artist.groups and not self.soloist,
            type=self.edition.type,
            number=self.edition.entry.number,
            numbered_type=self.edition.numbered_type,
            disks=max(part.disc for part in self.edition.parts),
            mp4=all(file.tag_type == 'mp4' for file in self.album_dir),
            cover_path=self.get_album_cover(),
            wiki_album=self.edition.page.url,
            # wiki_artist=getattr(self.edition.artist, 'url', None),
            wiki_artist=getattr(self.album_artist, 'url', None),
        )
        # TODO: OST with Various Artists + no artist matches appears to want to replace all track artists with empty string

        alt_artist_site = config.artist_sites and self._artists_source.page.site not in config.artist_sites
        collabs_in_title = config.collab_mode in (CollabMode.TITLE, CollabMode.BOTH)
        collabs_in_artist = config.collab_mode in (CollabMode.ARTIST, CollabMode.BOTH)
        for file, track in self.file_track_map.items():
            log.debug(f'Matched {file} to {track.name.full_repr()}')
            title = self._normalize_name(track.full_name(collabs_in_title))
            if alt_artist_site and (extra := track.name.extra):
                extra.pop('artists', None)

            album_info.tracks[file.path.as_posix()] = TrackInfo(
                album_info,
                title=title,
                artist=track.artist_name(self.artist_name, collabs_in_artist),
                num=track.num,
                name=self._normalize_name(track.full_name(self._artist != self.artist)),
                disk=track.disk,
            )

        return album_info

    @cached_property
    def file_track_map(self) -> dict[SongFile, Track]:
        return TrackZip(self.album_dir, self.disco_part).zip()

    @cached_property
    def disco_part(self) -> DEPart:
        if isinstance(self.album, Soundtrack):
            self.config.hide_edition = True
            full, parts, extras = self.album.split_editions()
            if extras:
                entry = self.album
            else:
                full_len = len(full.parts[0]) if full and full.parts else None
                entry = full if full_len and len(self.album_dir) == full_len else parts
        else:
            entry = self.album

        if isinstance(entry, SoundtrackEdition):
            if len(entry.parts) == 1:
                entry = entry.parts[0]
            elif alb_part := self.album_dir.name.part:
                for part in entry.parts:
                    if part.part == alb_part:
                        entry = part
                        break

        return get_disco_part(entry)

    @cached_property
    def edition(self) -> DEEdition:
        edition = self.disco_part.edition
        if isinstance(edition, SoundtrackEdition):
            self.config.hide_edition = True
        return edition

    # region OST Properties

    @cached_property
    def is_ost(self) -> bool:
        return self.edition.type == DiscoEntryType.Soundtrack

    @cached_property
    def full_ost(self) -> bool:
        return self.is_ost and self.edition.full_ost

    @cached_property
    def is_ost_part(self) -> bool:
        return self.is_ost and not self.edition.full_ost

    # endregion

    # region Artist Discovery

    @cached_property
    def _artists_source(self) -> Union[str, DEPart, DEEdition]:
        if artist_url := self.album_dir.artist_url:
            self._artist_from_tag = True
            # log.debug(f'Found artist URL via tag for {self.album_dir}: {artist_url}', extra={'color': 10})
            return artist_url
        elif self.disco_part.is_ost:
            return self.disco_part
        else:
            return self.edition

    @cached_property
    def _artists(self) -> list[Artist]:
        source = self._artists_source
        log.debug(f'Processing artists from {source=}')
        if isinstance(source, str):
            return [Artist.from_url(self._artists_source)]
        return sorted(self._artists_source.artists)

    @cached_property
    def _artist(self) -> ArtistType:
        src = self._artists_source
        if self.config.artist_sites and src.page.site not in self.config.artist_sites:
            processor = ArtistInfoProcessor.for_album_dir(self.album_dir, self.config)
            return processor.artist

        artists = self._artists
        if len(artists) > 1:
            return self._prepare_artist_from_many(artists)
        else:
            return self._prepare_artist(artists)

    def _prepare_artist(self, artists: list[Artist]) -> ArtistType:
        try:
            return artists[0]
        except IndexError:
            pass

        if self._init_artist:
            return self._init_artist

        # TODO: Prompt for artist override?
        raise NoArtistFoundError(self.album, self._artists_source)

    def _prepare_artist_from_many(self, artists: list[Artist]) -> ArtistType:
        others = set(artists)
        if len(artists) > 1 and getattr(self.disco_part.edition, 'full_ost', False):
            artist = 'Various Artists'
        else:
            artist = choose_item(artists + ['[combine all]', 'Various Artists'], 'artist', self.disco_part)  # noqa

        if artist == '[combine all]':
            path_artist = choose_item(
                artists + ['Various Artists'], 'artist', before_color=13,  # noqa
                before='\nWhich artist\'s name should be used in the file path?'
            )
            if path_artist != 'Various Artists':
                path_artist = path_artist.name.english
            artist = ArtistSet(artists, path_artist)
        elif artist == 'Various Artists':
            artist = ArtistSet(artists, 'Various Artists', 'Various Artists')
        else:
            others.remove(artist)
            for track in self.file_track_map.values():
                track.add_collabs(others)

        return artist

    @cached_property
    def artist(self) -> ArtistType:
        if self._init_artist is not None:
            return self._init_artist

        artist = self._artist
        retryable = self.is_ost_part and not isinstance(self._artists_source, str)
        if retryable and not isinstance(artist, ArtistSet) and not any('fandom' in site for site in artist._pages):
            # log.debug(f'Replacing {artist=} with pages={artist._pages}')
            if name := artist.name.english or artist.name.non_eng:
                try:
                    artist = Artist.from_title(name, sites=self.config.artist_sites, name=artist.name, entity=artist)
                except Exception as e:
                    log.warning(f'Error finding alternate version of {artist=!r}: {e}')

        return artist

    # endregion

    # region Album Cover Methods

    @cached_property
    def _edition_client(self) -> MediaWikiClient:
        return MediaWikiClient(self.edition.page.site)

    def get_album_cover_urls(self) -> Optional[dict[str, str]]:
        page = self.edition.page
        if image_titles := self._edition_client.get_page_image_titles(page.title)[page.title]:
            return self._edition_client.get_image_urls(image_titles)
        return None

    def get_album_cover(self) -> Optional[str]:
        if not self.config.update_cover:
            return None
        elif not (urls := self.get_album_cover_urls()):
            return None

        title = self._get_album_cover_choice(urls)
        if title == '[Keep Current]':
            return None

        name = title.split(':', 1)[1] if title.lower().startswith('file:') else title
        path = Path(get_user_cache_dir('music_manager/cover_art')).joinpath(name)
        if path.is_file():
            return path.as_posix()

        path.write_bytes(self._edition_client.get_image(title))
        return path.as_posix()

    def _get_album_cover_choice(self, urls: dict[str, str]) -> Optional[str]:
        with TemporaryDirectory() as td:
            tmp_dir = Path(td)
            try:
                song_file: SongFile = next(iter(self.album_dir))
                cover_data, ext = song_file.get_cover_data()
            except Exception as e:
                log.error(f'Unable to extract current album art: {e}')
                tmp_img = None
            else:
                tmp_img = tmp_dir.joinpath(f'current.{ext}')
                tmp_img.write_bytes(cover_data)

            tmp_html = tmp_dir.joinpath('options.html')
            with tmp_html.open('w', encoding='utf-8', newline='\n') as f:
                f.write(_render_album_cover_options_html(tmp_img, urls))
                f.flush()

            webbrowser.open(f'file:///{tmp_html.as_posix()}')
            return choose_item(list(urls) + ['[Keep Current]'], 'album cover image')

    # endregion


def _render_album_cover_options_html(img_path: Optional[Path], urls: dict[str, str]) -> str:
    sio = StringIO()
    sio.write('<html>\n<head><title>Album Cover Options</title></head>\n<body>\n')
    if img_path:
        sio.write(f'<h1>Current Cover</h1><img src="file:///{img_path.as_posix()}" style="max-width: 800;"></img>')

    sio.write('<h1>Album Cover Options</h1>\n<ul>\n')
    for title, url in urls.items():
        sio.write(f'<li><div>{title}</div><img src="{url}" style="max-width: 800;"></img></li>\n')

    sio.write('</ul>\n</body>\n</html>\n')
    return sio.getvalue()


class ArtistSet:
    __slots__ = ('name', 'artists', 'english', '_str')

    def __init__(self, artists, english, _str: str = None):
        self.name = self            # Prevent needing to have a separate class for the fake Name
        self.artists = artists
        self.english = english
        self._str = _str

    def __str__(self) -> str:
        if self._str:
            return self._str
        return ', '.join(str(a.name) for a in self.artists)


def get_album_dir(paths: Paths, message: str) -> AlbumDir:
    album_dirs = list(iter_album_dirs(paths))
    if len(album_dirs) > 1:
        log.debug(f'Found dirs: {album_dirs}')
        raise ValueError(f'When a {message} is provided, only one album can be processed at a time')
    elif not album_dirs:
        raise ValueError(f'No album dirs found for {paths}')
    return album_dirs[0]


class TrackZip:
    __slots__ = ('album_dir', 'disco_part', 'files', 'tracks')
    album_dir: AlbumDir
    disco_part: DEPart
    files: list[SongFile]
    tracks: list[Track]

    def __init__(self, album_dir: AlbumDir, disco_part: DEPart):
        self.album_dir = album_dir
        self.disco_part = disco_part
        self.files = album_dir.songs
        self.tracks = disco_part.tracks

    def _basic(self, multi_disk: bool = False) -> dict[SongFile, Track]:
        if multi_disk:
            files = sorted(self.files, key=lambda sf: (sf.disk_num, sf.track_num))
            wiki_tracks = [t for part in self.disco_part.edition.parts for t in part.tracks]
        else:
            files = sorted(self.files, key=lambda sf: sf.track_num)
            wiki_tracks = self.tracks
        return {song_file: wiki_track for song_file, wiki_track in zip(files, wiki_tracks)}

    def _zip_by_number(self, tracks: list[Track], src: str) -> dict[SongFile, Track]:
        file_track_map = {}
        for song_file in self.files:
            try:
                file_track_map[song_file] = tracks[song_file.track_num - 1]
            except IndexError:
                raise TrackZipError(f'Unable to match {song_file=} by number between {self.album_dir} and {src}')
        return file_track_map

    def _zip_by_number_multi_disk(self, track_map: dict[tuple[int, int], Track], src: str) -> dict[SongFile, Track]:
        file_track_map = {}
        for song_file in self.files:
            try:
                file_track_map[song_file] = track_map[(song_file.disk_num, song_file.track_num)]
            except IndexError:
                raise TrackZipError(f'Unable to match {song_file=} by number between {self.album_dir} and {src}')
        return file_track_map

    def _by_number(self) -> dict[SongFile, Track]:
        return self._zip_by_number(self.tracks, str(self.disco_part))

    def _by_number_and_availability(self) -> dict[SongFile, Track]:
        tracks = [track for track in self.tracks if 'availability' not in track.extras]
        if (available := len(tracks)) != (file_count := len(self.files)):
            raise TrackZipError(f'Tracks that are {available=} != {file_count=}')
        return self._zip_by_number(tracks, f'available tracks in {self.disco_part}')

    def _by_number_multi_disk(self, track_map: dict[tuple[int, int], Track]) -> dict[SongFile, Track]:
        return self._zip_by_number_multi_disk(track_map, str(self.disco_part))

    def _by_number_and_availability_multi_disk(self, track_map: dict[tuple[int, int], Track]) -> dict[SongFile, Track]:
        tracks = {k: track for k, track in track_map.items() if 'availability' not in track.extras}
        if (available := len(tracks)) != (file_count := len(self.files)):
            raise TrackZipError(f'Tracks that are {available=} != {file_count=}')
        return self._zip_by_number_multi_disk(tracks, f'available tracks in {self.disco_part}')

    def _zip_multi_disk(self) -> dict[SongFile, Track]:
        tracks = [t for part in self.disco_part.edition.parts for t in part.tracks]
        if len(tracks) == len(self.files):
            return self._basic(True)

        track_map: dict[tuple[int, int], Track] = {
            (d, n): track
            for d, part in enumerate(self.disco_part.edition.parts, 1)
            for n, track in enumerate(part.tracks, 1)
        }
        for method in (self._by_number_and_availability_multi_disk, self._by_number_multi_disk):
            try:
                return method(track_map)  # noqa
            except TrackZipError as e:
                log.debug(e)

        return self._basic(True)

    def zip(self) -> dict[SongFile, Track]:
        n_files = len(self.files)
        n_tracks = len(self.tracks)
        if n_files == n_tracks:
            return self._basic()

        edition = self.disco_part.edition
        if n_files > n_tracks and len(edition.parts) > 1 and self.disco_part == edition.parts[0]:
            return self._zip_multi_disk()

        for method in (self._by_number_and_availability, self._by_number):
            try:
                return method()
            except TrackZipError as e:
                log.debug(e)

        return self._basic()


class TrackZipError(Exception):
    """Used internally; intended to be caught by :meth:`TrackZip.zip`"""
