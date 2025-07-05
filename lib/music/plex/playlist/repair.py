"""
Plex playlist backup restoration utilities

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
from functools import cached_property
from typing import TYPE_CHECKING, Iterator

from plexapi.audio import Track
from ds_tools.output.prefix import DryRunMixin
from ds_tools.output.color import colored

from music.text.name import Name
from .playlist import PlexPlaylist

if TYPE_CHECKING:
    from ..server import LocalPlexServer

    OptServer = LocalPlexServer | None

__all__ = ['PlaylistRepairer']
log = logging.getLogger(__name__)


class PlaylistRepairer(DryRunMixin):
    backup_playlist: PlexPlaylist
    plex: LocalPlexServer

    def __init__(self, backup_playlist: PlexPlaylist, new_name: str | None = None):
        self.backup_playlist = backup_playlist
        self.live_playlist = PlexPlaylist(new_name or backup_playlist.name, backup_playlist.plex)
        self.plex = backup_playlist.plex
        self.dry_run = self.plex.dry_run
        self._track_replacement_finder = TrackReplacementFinder(self.plex)

    def repair(self):
        if self.live_playlist.exists:
            log.debug(f'Playlist {self.live_playlist} already exists')
            self.live_playlist.sync_tracks(self._new_tracks)
        else:
            # Note: Using `_create` to retain track order.  Dry run is handled in create, based on plex.dry_run.
            self.live_playlist._create(self._new_tracks)

    @cached_property
    def _new_tracks(self) -> list[Track]:
        return [new_track for old_track, new_track in self._iter_track_changes() if new_track is not None]

    def _iter_track_changes(self) -> Iterator[tuple[Track, Track | None]]:
        all_tracks = self.plex.all_tracks
        for track in self.backup_playlist.tracks:
            if track in all_tracks:
                yield track, track
            elif alt_track := self._track_replacement_finder.find_alt_track(track):
                a_str = f'{track}[{track.media[0].audioCodec}]'
                b_str = f'{alt_track}[{alt_track.media[0].audioCodec}]'
                log.info(f'Will replace {colored(a_str, 9)} with {colored(b_str, 10)}')
                yield track, alt_track
            else:
                log.warning(f'No alternate match could be found for {track}', extra={'color': 9})
                yield track, None


class TrackReplacementFinder:
    def __init__(self, plex: LocalPlexServer):
        self.plex = plex
        self._artist_album_names = {}

    def find_alt_track(self, track: Track) -> Track | None:
        track_name = Name.from_enclosed(track.title)
        for album_tracks in self._iter_album_candidates(track):
            track_names = {Name.from_enclosed(t.title): t for t in album_tracks}
            if match := track_name.find_best_match(track_names):
                return track_names[match]

        return None

    def _iter_album_candidates(self, track: Track) -> Iterator[list[Track]]:
        if exact_match := self._get_exact_album_match(track):
            yield exact_match
        else:
            track_artist_name = Name.from_enclosed(track.grandparentTitle)
            if artist_matches := sorted(track_artist_name.find_best_matches(self._artist_names), reverse=True):
                track_album_name = Name.from_enclosed(track.parentTitle)
                for artist_score, artist_name in artist_matches:
                    artist_name_str = self._artist_names[artist_name]
                    artist_albums = self._get_album_names(artist_name_str)
                    for _score, album_name in sorted(track_album_name.find_best_matches(artist_albums), reverse=True):
                        yield self._artist_album_tracks_title_map[artist_name_str][artist_albums[album_name]]
            else:
                log.warning(f'Could not find a match for artist={track.grandparentTitle!r} for {track=}')

    def _get_exact_album_match(self, track: Track) -> list[Track] | None:
        try:
            return self._artist_album_tracks_key_map[track.grandparentRatingKey][track.parentRatingKey]
        except KeyError:
            pass
        try:
            return self._artist_album_tracks_title_map[track.grandparentTitle][track.parentTitle]
        except KeyError:
            pass
        return None

    @cached_property
    def _artist_album_tracks_title_map(self) -> dict[str, dict[str, list[Track]]]:
        artist_album_tracks_map = {}
        for track in self.plex.all_tracks:
            try:
                album_track_map = artist_album_tracks_map[track.grandparentTitle]
            except KeyError:
                artist_album_tracks_map[track.grandparentTitle] = album_track_map = {}
            try:
                tracks = album_track_map[track.parentTitle]
            except KeyError:
                album_track_map[track.parentTitle] = [track]
            else:
                tracks.append(track)

        return artist_album_tracks_map

    @cached_property
    def _artist_album_tracks_key_map(self) -> dict[str, dict[str, list[Track]]]:
        artist_album_tracks_map = {}
        for track in self.plex.all_tracks:
            try:
                album_track_map = artist_album_tracks_map[track.grandparentRatingKey]
            except KeyError:
                artist_album_tracks_map[track.grandparentRatingKey] = album_track_map = {}
            try:
                tracks = album_track_map[track.parentRatingKey]
            except KeyError:
                album_track_map[track.parentRatingKey] = [track]
            else:
                tracks.append(track)

        return artist_album_tracks_map

    @cached_property
    def _artist_names(self) -> dict[Name, str]:
        return {Name.from_enclosed(artist): artist for artist in self._artist_album_tracks_title_map}

    def _get_album_names(self, artist_name: str) -> dict[Name, str]:
        try:
            return self._artist_album_names[artist_name]
        except KeyError:
            pass

        album_names = {Name.from_enclosed(album): album for album in self._artist_album_tracks_title_map[artist_name]}
        self._artist_album_names[artist_name] = album_names
        return album_names
