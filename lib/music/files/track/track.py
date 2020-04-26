"""
:author: Doug Skrypa
"""

import logging
import os
import re
from pathlib import Path
from typing import Optional, Union

import mutagen.id3._frames as id3_frames
from plexapi.audio import Track

from ds_tools.compat import cached_property
# from ...text.name import Name
from ...constants import tag_name_map
from .base import BaseSongFile
from ..exceptions import TagException
from .bpm import get_bpm
from .patterns import (
    ALBUM_DIR_CLEANUP_RE_FUNCS, ALBUM_VOLUME_MATCH, EXTRACT_PART_MATCH, compiled_fnmatch_patterns, cleanup_album_name
)
from .utils import print_tag_changes, tag_repr, ON_WINDOWS, TYPED_TAG_MAP

__all__ = ['SongFile']
log = logging.getLogger(__name__)
LYRIC_URL_MATCH = re.compile(r'^(.*)(https?://\S+)$', re.DOTALL).match


class SongFile(BaseSongFile):
    _bpm = None

    @classmethod
    def for_plex_track(cls, track: Track, root: Union[str, Path]):
        if ON_WINDOWS:
            if isinstance(root, Path):                              # Path does not work for network shares in Windows
                root = root.as_posix()
            if root.startswith('/') and not root.startswith('//'):
                root = '/' + root
        rel_path = track.media[0].parts[0].file
        path = os.path.join(root, rel_path[1:] if rel_path.startswith('/') else rel_path)
        return cls(path)

    @cached_property
    def extended_repr(self):
        try:
            info = '[{!r} by {}, in {!r}]'.format(self.tag_title, self.tag_artist, self.album_name_cleaned)
        except Exception as e:
            info = ''
        return '<{}({!r}){}>'.format(self.__class__.__name__, self.rel_path, info)

    @cached_property
    def album_from_dir(self):
        album = self.path.parent.name
        if (tag_artist := self.tag_artist) and album.lower().startswith(tag_artist.lower()):
            album = album[len(tag_artist):].strip()
        if album.startswith('- '):
            album = album[1:].strip()
        for re_func, on_match_func in ALBUM_DIR_CLEANUP_RE_FUNCS:
            if m := re_func(album):
                album = on_match_func(m)
        return album

    @cached_property
    def in_competition_album(self):
        if album_artist := self.tag_album_artist:
            return album_artist.lower().startswith('produce') and album_artist.split()[-1].isdigit()
        return False

    @cached_property
    def _is_full_ost(self):
        album_artist = self.tag_text('album_artist', default='').lower()
        album_name = self.album_name_cleaned
        full_ost = album_name.endswith('OST') and 'part' not in album_name.lower()
        # noinspection PyUnresolvedReferences
        alb_dir = self.album_dir_obj
        multiple_artists = len({f.tag_artist for f in alb_dir}) > 1
        return full_ost and album_artist == 'various artists' and multiple_artists and len(alb_dir) > 2

    @cached_property
    def album_name_cleaned(self):
        return cleanup_album_name(self.tag_album, self.tag_artist) or self.tag_album

    @cached_property
    def album_name_cleaned_plus_and_part(self):
        """Tuple of title, part"""
        return _extract_album_part(self.album_name_cleaned)

    @cached_property
    def album_name_cleaner(self):
        album = self.album_name_cleaned
        if m := ALBUM_VOLUME_MATCH(album):
            album = m.group(1)
        return album

    @cached_property
    def dir_name_cleaned(self):
        return cleanup_album_name(self.path.parent.name, self.tag_artist)

    @cached_property
    def dir_name_cleaned_plus_and_part(self):
        return _extract_album_part(self.dir_name_cleaned)

    def cleanup_lyrics(self, dry_run=False):
        prefix, upd_msg = ('[DRY RUN] ', 'Would update') if dry_run else ('', 'Updating')
        changes = 0
        tag_type = self.tag_type
        new_lyrics = []
        for lyric_tag in self.tags_named('lyrics'):
            lyric = lyric_tag.text if tag_type == 'mp3' else lyric_tag
            if m := LYRIC_URL_MATCH(lyric):
                new_lyric = m.group(1).strip() + '\r\n'
                log.info(f'{prefix}{upd_msg} lyrics for {self} from {tag_repr(lyric)!r} to {tag_repr(new_lyric)!r}')
                if not dry_run:
                    if tag_type == 'mp3':
                        lyric_tag.text = new_lyric
                    else:
                        new_lyrics.append(new_lyric)
                    changes += 1
            else:
                new_lyrics.append(lyric)

        if changes and not dry_run:
            log.info('Saving changes to lyrics in {}'.format(self))
            if tag_type == 'mp4':
                self.set_text_tag('lyrics', new_lyrics)
            self.save()

    def bpm(self, save=True, calculate=True) -> Optional[int]:
        """
        :param bool save: If the BPM was not already stored in a tag, save the calculated BPM in a tag.
        :param bool calculate: If the BPM was not already stored in a tag, calculate it
        :return int: This track's BPM from a tag if available, or calculated
        """
        try:
            bpm = int(self.tag_text('bpm'))
        except TagException:
            if calculate:
                if not (bpm := self._bpm):
                    bpm = self._bpm = get_bpm(self.path)
                if save:
                    self.set_text_tag('bpm', bpm)
                    log.debug(f'Saving {bpm=} for {self}')
                    self.save()
            else:
                bpm = None
        return bpm

    def update_tags(self, name_value_map, dry_run=False, no_log=None):
        """
        :param dict name_value_map: Mapping of {tag name: new value}
        :param bool dry_run: Whether tags should actually be updated
        :param container no_log: Names of tags for which updates should not be logged
        """
        to_update = {}
        for tag_name, new_value in sorted(name_value_map.items()):
            file_value = self.tag_text(tag_name, default=None)
            cmp_value = str(new_value) if tag_name in ('disk', 'track') else new_value
            if cmp_value != file_value:
                to_update[tag_name] = (file_value, new_value)

        if to_update:
            no_log = no_log or ()
            print_tag_changes(self, {k: v for k, v in to_update.items() if k not in no_log}, dry_run)
            do_save = True
            for tag_name, (file_value, new_value) in to_update.items():
                if not dry_run:
                    try:
                        self.set_text_tag(tag_name, new_value, by_id=False)
                    except TagException as e:
                        do_save = False
                        log.error(f'Error setting tag={tag_name} on {self}: {e}')
            if do_save and not dry_run:
                self.save()
        else:
            log.log(19, f'No changes to make for {self.extended_repr}')

    def update_tags_with_value(self, tag_ids, value, patterns=None, partial=False, dry_run=False):
        if partial and not patterns:
            raise ValueError('Unable to perform partial tag update without any patterns')
        patterns = compiled_fnmatch_patterns(patterns)
        prefix, repl_msg, set_msg = ('[DRY RUN] Would ', 'replace', 'set') if dry_run else ('', 'Replacing', 'Setting')
        should_save = False
        for tag_id in tag_ids:
            if names_by_type := TYPED_TAG_MAP.get(tag_id):
                tag_id = names_by_type[self.tag_type]
            tag_name = tag_name_map.get(tag_id)
            if not tag_name:
                raise ValueError(f'Invalid tag ID: {tag_id}')
            _tag_repr = f'{tag_id}/{tag_name}'

            current_vals = self.tags_for_id(tag_id)
            if not current_vals:
                if self.tag_type == 'mp3':
                    try:
                        frame_cls = getattr(id3_frames, tag_id.upper())
                    except AttributeError as e:
                        raise ValueError(f'Invalid tag ID: {tag_id!r} (no frame class found for it)') from e
                else:
                    raise ValueError(f'Adding new tags to non-MP3s is not currently supported for {self}')

                log.info(f'{prefix}{set_msg} {_tag_repr} = {value!r} in file: {self.filename}')
                should_save = True
                if not dry_run:
                    self.tags.add(frame_cls(text=value))
            else:
                if len(current_vals) > 1:
                    log.warning(f'Found multiple values for {_tag_repr} in {self.filename} - using first value')

                current_val = current_vals[0]
                current_text = current_val.text[0]
                new_text = current_text
                if partial:
                    for pat in patterns:
                        new_text = pat.sub(value, new_text)
                else:
                    if patterns:
                        if any(pat.search(current_text) for pat in patterns):
                            new_text = value
                    else:
                        new_text = value

                if new_text != current_text:
                    log.info(f'{prefix}{repl_msg} {_tag_repr} {current_text!r} with {new_text!r} in {self.filename}')
                    should_save = True
                    if not dry_run:
                        current_vals[0].text[0] = new_text

        if should_save:
            if not dry_run:
                self.save()
        else:
            log.log(19, f'Nothing to change for {self.filename}')


def _extract_album_part(title):
    part = None
    if m := EXTRACT_PART_MATCH(title):
        title, part = map(str.strip, m.groups())
    if title.endswith(' -'):
        title = title[:-1].strip()
    return title, part


if __name__ == '__main__':
    from ..patches import apply_mutagen_patches
    apply_mutagen_patches()
